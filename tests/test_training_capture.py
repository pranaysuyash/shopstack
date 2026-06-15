"""Tests for the trace-tuned parser training capture pipeline.

motto_v3 §0.5: every layer of the AI feature must have a
regression net. The capture pipeline turns confirmed user
traces into permanent training rows; these tests verify the
extraction, filtering, ranking, and JSONL write mechanics.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pytest

from shopstack.services.training_capture import (
    CONFIRMATION_RANK,
    MIN_RANK_DEFAULT,
    CaptureReport,
    TrainingExample,
    capture_from_database,
    extract_training_examples,
    maybe_capture_before_retention,
    write_training_jsonl,
)


# ── Fixtures ──────────────────────────────────────────────────────


@dataclass
class _FakeToolCall:
    """Minimal stand-in for a Pydantic ToolCall."""

    tool_name: str = ""
    args: dict = field(default_factory=dict)
    confidence: float = 1.0

    def model_dump(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "args": self.args,
            "confidence": self.confidence,
        }


@dataclass
class _FakeTrace:
    """Minimal stand-in for a Pydantic Trace."""

    trace_id: str = "tr-1"
    redacted_user_request: str = ""
    human_confirmation: str | None = None
    proposed_tool_calls: list = field(default_factory=list)
    timestamp: str = "2026-06-14T10:00:00"
    actor_id: str = "house-1"


def _confirmed_trace(
    text: str = "add 2 L milk",
    confirmation: str = "confirmed-by-user",
    tool_name: str = "add_inventory_lot",
    args: dict | None = None,
) -> _FakeTrace:
    return _FakeTrace(
        redacted_user_request=text,
        human_confirmation=confirmation,
        proposed_tool_calls=[
            _FakeToolCall(
                tool_name=tool_name,
                args=args or {"canonical_name": "milk", "quantity": 2.0, "unit": "L"},
                confidence=0.95,
            )
        ],
    )


# ── Confirmation-value ranking ───────────────────────────────────


class TestConfirmationRank:
    def test_user_confirmed_is_highest(self):
        """The user explicitly clicked confirm — that's the
        strongest training signal we have."""
        assert CONFIRMATION_RANK["confirmed-by-user"] >= 90

    def test_auto_confirmed_is_high(self):
        assert CONFIRMATION_RANK["auto-confirmed"] >= 60
        assert CONFIRMATION_RANK["auto-confirmed"] < CONFIRMATION_RANK["confirmed-by-user"]

    def test_uncommitted_is_zero(self):
        """Uncommitted traces are pure noise — never a training
        example."""
        assert CONFIRMATION_RANK["uncommitted"] == 0

    def test_min_rank_default_includes_user_and_auto(self):
        """The default floor of 70 includes both
        'confirmed-by-user' (100) and 'auto-confirmed' (70)."""
        assert MIN_RANK_DEFAULT <= CONFIRMATION_RANK["confirmed-by-user"]
        assert MIN_RANK_DEFAULT <= CONFIRMATION_RANK["auto-confirmed"]


# ── Core extraction ───────────────────────────────────────────────


class TestExtractTrainingExamples:
    def test_user_confirmed_trace_becomes_example(self):
        trace = _confirmed_trace("add 2 L milk")
        report = extract_training_examples([trace])
        assert report.total == 1
        ex = report.captured[0]
        assert ex.text == "add 2 L milk"
        assert ex.intent == "add_inventory_item"  # renamed from add_inventory_lot
        assert ex.args["canonical_name"] == "milk"
        assert ex.confirmation == "confirmed-by-user"
        assert ex.source == "real-confirmed"
        assert ex.trace_id == "tr-1"

    def test_uncommitted_trace_is_dropped(self):
        trace = _confirmed_trace(confirmation="uncommitted")
        report = extract_training_examples([trace])
        assert report.total == 0
        assert report.skipped_unconfirmed == 1

    def test_none_confirmation_is_dropped(self):
        trace = _confirmed_trace()
        trace.human_confirmation = None
        report = extract_training_examples([trace])
        assert report.total == 0
        assert report.skipped_unconfirmed == 1

    def test_empty_request_is_dropped(self):
        trace = _confirmed_trace(text="   ")
        report = extract_training_examples([trace])
        assert report.total == 0
        assert report.skipped_empty_request == 1

    def test_trace_with_no_tool_calls_is_dropped(self):
        trace = _confirmed_trace()
        trace.proposed_tool_calls = []
        report = extract_training_examples([trace])
        assert report.total == 0
        assert report.skipped_no_tool_call == 1

    def test_min_rank_floor_excludes_auto_summarized(self):
        """The default min_rank (70) keeps only the high-signal
        confirmations; 'auto-summarized' (40) is below the floor."""
        trace = _confirmed_trace(confirmation="auto-summarized")
        report = extract_training_examples([trace])
        assert report.total == 0

    def test_min_rank_zero_keeps_everything_with_confirmation(self):
        """Floor=0 means 'keep anything that has a confirmation
        value at all' — for diagnostic runs that want the
        full picture. None is still dropped (no signal at all).
        """
        traces = [
            _confirmed_trace(confirmation="auto-summarized"),
            _confirmed_trace(confirmation="responded"),
            _confirmed_trace(confirmation="uncommitted"),  # rank 0 → kept at floor=0
        ]
        report = extract_training_examples(traces, min_rank=0)
        # All 3 kept (None is the only thing dropped at floor=0).
        assert report.total == 3

    def test_min_rank_zero_still_drops_none_confirmation(self):
        """None confirmation is always dropped — no confirmation
        field means no signal at all, regardless of min_rank."""
        trace = _confirmed_trace()
        trace.human_confirmation = None
        report = extract_training_examples([trace], min_rank=0)
        assert report.total == 0
        assert report.skipped_unconfirmed == 1

    def test_multiple_tool_calls_uses_first(self):
        """The parser trains on a single intent per utterance.
        When the trace has multiple tool calls, the first one
        wins (the most-likely intent)."""
        trace = _FakeTrace(
            redacted_user_request="add milk and bread",
            human_confirmation="confirmed-by-user",
            proposed_tool_calls=[
                _FakeToolCall(
                    tool_name="add_inventory_lot",
                    args={"canonical_name": "milk", "quantity": 1, "unit": "L"},
                ),
                _FakeToolCall(
                    tool_name="add_inventory_lot",
                    args={"canonical_name": "bread", "quantity": 2, "unit": "unit"},
                ),
            ],
        )
        report = extract_training_examples([trace])
        assert report.total == 1
        assert report.captured[0].args["canonical_name"] == "milk"

    def test_preserves_order(self):
        """Output order matches input order — important for
        downstream tooling that diffs runs."""
        traces = [
            _confirmed_trace(text=f"utterance {i}") for i in range(5)
        ]
        report = extract_training_examples(traces)
        assert [ex.text for ex in report.captured] == [
            f"utterance {i}" for i in range(5)
        ]

    def test_dict_style_tool_call_is_accepted(self):
        """Older traces store raw dicts instead of Pydantic
        models; both must work.
        """
        trace = _FakeTrace(
            redacted_user_request="consume 1 L milk",
            human_confirmation="confirmed-by-user",
            proposed_tool_calls=[
                {
                    "tool_name": "consume_inventory",
                    "args": {"canonical_name": "milk", "quantity": 1.0},
                    "confidence": 0.8,
                }
            ],
        )
        report = extract_training_examples([trace])
        assert report.total == 1
        assert report.captured[0].intent == "consume_inventory"

    def test_empty_traces_list_returns_empty_report(self):
        report = extract_training_examples([])
        assert report.total == 0
        assert report.skipped_unconfirmed == 0
        assert report.skipped_empty_request == 0
        assert report.skipped_no_tool_call == 0


# ── JSONL writer ─────────────────────────────────────────────────


class TestWriteTrainingJsonl:
    def test_writes_one_jsonl_row_per_example(self, tmp_path: Path):
        out = tmp_path / "training.jsonl"
        ex = TrainingExample(text="add milk", intent="add_inventory_item")
        n = write_training_jsonl([ex], out)
        assert n == 1
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["text"] == "add milk"
        assert parsed["intent"] == "add_inventory_item"

    def test_appends_to_existing_file(self, tmp_path: Path):
        """Append-only semantics: a daily capture pass must
        not clobber yesterday's rows."""
        out = tmp_path / "training.jsonl"
        write_training_jsonl(
            [TrainingExample(text="t1", intent="add_inventory_item")], out
        )
        write_training_jsonl(
            [TrainingExample(text="t2", intent="consume_item")], out
        )
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["text"] == "t1"
        assert json.loads(lines[1])["text"] == "t2"

    def test_creates_parent_directory(self, tmp_path: Path):
        out = tmp_path / "nested" / "deeper" / "training.jsonl"
        write_training_jsonl(
            [TrainingExample(text="x", intent="general_query")], out
        )
        assert out.is_file()


# ── DB integration ───────────────────────────────────────────────


class _FakeDB:
    """Minimal stand-in matching the ``get_traces(limit)`` contract."""

    def __init__(self, traces: list | None = None, raise_on_get: bool = False):
        self._traces = traces or []
        self._raise = raise_on_get

    def get_traces(self, limit: int = 50, user_id: str = "") -> list:
        if self._raise:
            raise RuntimeError("simulated DB error")
        return self._traces[:limit]


class TestCaptureFromDatabase:
    def test_pulls_traces_and_extracts(self):
        traces = [_confirmed_trace(text=f"t{i}") for i in range(3)]
        db = _FakeDB(traces=traces)
        report = capture_from_database(db, limit=10)
        assert report.total == 3

    def test_respects_limit(self):
        traces = [_confirmed_trace(text=f"t{i}") for i in range(20)]
        db = _FakeDB(traces=traces)
        report = capture_from_database(db, limit=5)
        assert report.total == 5

    def test_db_error_returns_empty_report(self):
        """A DB error must not crash the capture pass — return
        an empty report so the caller can log + move on.
        """
        db = _FakeDB(raise_on_get=True)
        report = capture_from_database(db)
        assert report.total == 0


# ── Retention integration ────────────────────────────────────────


class TestMaybeCaptureBeforeRetention:
    def test_writes_only_when_there_are_examples(self, tmp_path: Path):
        """If every trace was unconfirmed, we don't create an
        empty file — silent nothing happened."""
        db = _FakeDB(traces=[_confirmed_trace(confirmation="uncommitted")])
        out = tmp_path / "training.jsonl"
        report = maybe_capture_before_retention(db, out_path=out)
        assert report.total == 0
        assert not out.exists()

    def test_writes_when_there_are_confirmed(self, tmp_path: Path):
        db = _FakeDB(traces=[_confirmed_trace(text="add 2 L milk")])
        out = tmp_path / "training.jsonl"
        report = maybe_capture_before_retention(db, out_path=out)
        assert report.total == 1
        assert out.is_file()
        line = out.read_text(encoding="utf-8").strip()
        parsed = json.loads(line)
        assert parsed["text"] == "add 2 L milk"

    def test_diagnostic_counter_in_report(self, tmp_path: Path):
        """The report's skip counters let the operator see what
        was dropped and why — important for a daily cron
        that needs to alert on rising skip counts."""
        db = _FakeDB(traces=[
            _confirmed_trace(text="ok 1"),
            _confirmed_trace(text="ok 2"),
            _confirmed_trace(text="x", confirmation="uncommitted"),
            _confirmed_trace(text="   "),  # empty request
            _FakeTrace(  # no tool call
                redacted_user_request="orphan",
                human_confirmation="confirmed-by-user",
                proposed_tool_calls=[],
            ),
        ])
        out = tmp_path / "training.jsonl"
        report = maybe_capture_before_retention(db, out_path=out)
        assert report.total == 2
        assert report.skipped_unconfirmed == 1
        assert report.skipped_empty_request == 1
        assert report.skipped_no_tool_call == 1


# ── DB retention integration ─────────────────────────────────────


class TestRetentionIntegration:
    """The capture call must run inside
    :meth:`Database._apply_trace_retention_policy` (Item #16)
    so confirmed traces don't get deleted before they become
    training rows. This is a real production contract; we
    monkeypatch the capture helper and assert the DB calls it.
    """

    def test_apply_retention_calls_capture(self, monkeypatch, tmp_path: Path):
        # Monkeypatch the helper that database.py calls so the
        # test doesn't depend on a real DB or real JSONL write.
        calls: list = []
        from shopstack.services import training_capture

        def fake_capture(db, **kwargs):
            calls.append(db)
            return training_capture.CaptureReport()
        monkeypatch.setattr(
            training_capture, "maybe_capture_before_retention", fake_capture
        )

        # Build a minimal Database just enough to call
        # _apply_trace_retention_policy. The function reads
        # settings.trace_max_rows and trace_ttl_days, then
        # calls prune_traces; we stub both to no-ops.
        import os
        os.environ["SHOPSTACK_DB_PATH"] = str(tmp_path / "ret.db")
        os.environ["SHOPSTACK_LOCAL_AUTO_DOWNLOAD"] = "false"
        from shopstack.persistence.database import Database

        # Note: Database.__init__ itself calls
        # _apply_trace_retention_policy at line 453. We just
        # need the capture to have been called at least once
        # with the DB instance — the call count includes both
        # the implicit init and the explicit test call. We
        # assert "called with our DB" rather than a count.
        db = Database(str(tmp_path / "ret.db"))
        # Stub prune_traces so the test doesn't depend on real
        # trace rows / dates.
        db.prune_traces = lambda *a, **kw: 0  # type: ignore[assignment]

        before = len(calls)
        db._apply_trace_retention_policy()
        after = len(calls)

        # The capture helper was called with `self` at least
        # once for our DB instance. We don't care which DB,
        # just that the capture step ran.
        assert after > before, (
            f"_apply_trace_retention_policy must call "
            f"training_capture.maybe_capture_before_retention(self) "
            f"before pruning. Calls observed: {calls}"
        )
        assert all(c is db for c in calls[before:]), (
            "The capture call must pass the DB instance as the first arg"
        )

    def test_capture_failure_does_not_block_retention(self, monkeypatch, tmp_path: Path):
        """A capture failure (e.g. disk full on JSONL write)
        must not block the prune — the prune is the data
        retention guarantee and the capture is a best-effort
        extra. This is the motto_v3 §0.6 risk-based verification
        contract: a non-critical side path must never block a
        critical one.
        """
        from shopstack.services import training_capture

        def exploding_capture(db, **kwargs):
            raise RuntimeError("disk full on the training JSONL write")

        monkeypatch.setattr(
            training_capture, "maybe_capture_before_retention", exploding_capture
        )

        import os
        os.environ["SHOPSTACK_DB_PATH"] = str(tmp_path / "ret2.db")
        os.environ["SHOPSTACK_LOCAL_AUTO_DOWNLOAD"] = "false"
        from shopstack.persistence.database import Database

        db = Database(str(tmp_path / "ret2.db"))
        db.prune_traces = lambda *a, **kw: 0  # type: ignore[assignment]

        # Should not raise. The try/except inside
        # _apply_trace_retention_policy catches the capture
        # failure and proceeds to the prune.
        db._apply_trace_retention_policy()
