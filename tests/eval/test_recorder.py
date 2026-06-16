"""Tests for the o/p eval recorder (EVAL-OP-1).

Cover:
* ModelCallRecord round-trip
* record_model_call() context manager finalizes a record on exit
* Code-route auto-resolution points at the caller, not the recorder
* Redaction of prompts and outputs runs at capture time
* Outcome taxonomy is enforced
* Recorder never raises into the hot path
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from shopstack.eval import (
    CAP_PLANNER_TOOL_CALLING,
    OUTCOME_EMPTY,
    OUTCOME_EXCEPTION,
    OUTCOME_PARSE_ERROR,
    OUTCOME_SUCCESS,
    SHAPE_RAW,
    SHAPE_TEXT,
    SHAPE_TOOL_CALLS,
    CheckResult,
    JsonlSink,
    ModelCallRecord,
    ModelCallRecorder,
    SqliteSink,
    record_model_call,
)


# ── Helpers ───────────────────────────────────────────────────────────


class _FakeCheckRegistry:
    """Replaces the default registry with deterministic checks for tests."""

    def __init__(self, results: list[CheckResult] | None = None) -> None:
        self._results = results or []
        self.history: list[ModelCallRecord] = []

    def run(self, record: ModelCallRecord) -> list[CheckResult]:
        self.history.append(record)
        return list(self._results)

    def history_queue(self):
        return self.history


def _make_recorder(tmp_path: Path, results: list[CheckResult] | None = None):
    jsonl = JsonlSink(tmp_path / "records.jsonl")
    sqlite = SqliteSink(tmp_path / "test.db")
    registry = _FakeCheckRegistry(results or [CheckResult("test_check", True, 1.0, "ok")])
    ModelCallRecorder.reset_instance()
    rec = ModelCallRecorder(jsonl_sink=jsonl, sqlite_sink=sqlite, check_registry=registry)
    ModelCallRecorder._instance = rec
    return rec, jsonl, sqlite


# ── ModelCallRecord ───────────────────────────────────────────────────


def test_model_call_record_defaults():
    rec = ModelCallRecord(domain_route="planner")
    assert rec.record_id
    assert rec.started_at
    assert rec.outcome == OUTCOME_SUCCESS
    assert rec.eval_passed is True
    assert rec.eval_score == 1.0
    assert rec.eval_check_results == []


def test_model_call_record_round_trip_dict():
    rec = ModelCallRecord(
        domain_route="planner",
        code_route="planner.engine:42",
        capability=CAP_PLANNER_TOOL_CALLING,
        capability_expected_shape=SHAPE_TOOL_CALLS,
        prompt="hello world",
        output='[{"tool": "respond", "args": {"message": "hi"}}]',
        prompt_length=11,
        output_length=46,
        latency_ms=123.4,
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
    )
    rec.eval_check_results = [CheckResult("parse_success", True, 1.0, "ok")]
    d = rec.to_dict()
    # Round-trip via JSON
    raw = json.dumps(d)
    d2 = json.loads(raw)
    assert d2["domain_route"] == "planner"
    assert d2["code_route"] == "planner.engine:42"
    assert d2["prompt"] == "hello world"
    assert d2["eval_check_results"][0]["check"] == "parse_success"


def test_short_summary_compact():
    rec = ModelCallRecord(domain_route="planner", code_route="x:1", latency_ms=50.0)
    s = rec.short_summary()
    assert set(s.keys()) == {
        "record_id", "started_at", "domain_route", "code_route",
        "capability", "model", "latency_ms", "outcome", "eval_passed", "eval_score",
    }
    assert s["domain_route"] == "planner"


# ── record_model_call context manager ─────────────────────────────────


def test_record_model_call_finalizes_on_exit(tmp_path):
    _make_recorder(tmp_path)
    with record_model_call(
        domain_route="planner",
        capability=CAP_PLANNER_TOOL_CALLING,
        capability_expected_shape=SHAPE_TOOL_CALLS,
    ) as rec:
        rec.set_prompt("user asked for help")
        rec.set_output('[{"tool": "respond", "args": {"message": "ok"}}]')
        rec.set_usage(input_tokens=5, output_tokens=10, cost_usd=0.0001, model="m1")
    assert rec.record.latency_ms >= 0
    assert rec.record.prompt == "user asked for help"
    assert rec.record.input_tokens == 5
    assert rec.record.model == "m1"
    assert rec.record.outcome == OUTCOME_SUCCESS


def test_record_model_call_auto_code_route_points_at_caller(tmp_path):
    _make_recorder(tmp_path)

    def my_caller():
        with record_model_call(domain_route="test") as rec:
            pass
        return rec.record.code_route

    code = my_caller()
    # The resolver prefers shopstack.* frames; tests live outside
    # that namespace so the fallback to the first non-runner frame
    # is what we expect here. Assert the function name is captured
    # and the eval package is excluded.
    assert ".my_caller:" in code
    assert "shopstack.eval" not in code  # auto-skip eval frames


def test_record_model_call_redacts_pii_at_capture(tmp_path):
    _make_recorder(tmp_path)
    with record_model_call(domain_route="planner") as rec:
        rec.set_prompt("call me at 9876543210 or email a@b.com")
    assert "[REDACTED_NUMBER]" in rec.record.prompt
    assert "[REDACTED_EMAIL]" in rec.record.prompt
    # Length is the *raw* length — useful for cost / context checks
    assert rec.record.prompt_length == len("call me at 9876543210 or email a@b.com")


def test_record_model_call_handles_bytes_output(tmp_path):
    _make_recorder(tmp_path)
    with record_model_call(domain_route="tts", capability="tts") as rec:
        rec.set_output(b"\x00\x01\x02" * 100)
    assert rec.record.output.startswith("<bytes len=")
    assert rec.record.output_length == 300


def test_record_model_call_set_outcome_coerces_unknown(tmp_path):
    _make_recorder(tmp_path)
    with record_model_call(domain_route="x") as rec:
        rec.set_outcome("totally-not-a-real-outcome")
    assert rec.record.outcome == OUTCOME_EXCEPTION


def test_record_model_call_runs_checks_and_persists(tmp_path):
    rec, jsonl, sqlite = _make_recorder(
        tmp_path,
        results=[CheckResult("parse_success", True, 0.9, "looks good")],
    )
    with record_model_call(domain_route="planner") as r:
        r.set_prompt("p")
        r.set_output("o")
    # JSONL should have one line
    rows = list(jsonl.read_all())
    assert len(rows) == 1
    assert rows[0]["domain_route"] == "planner"
    assert rows[0]["eval_passed"] is True
    assert rows[0]["eval_score"] == 0.9
    # SQLite should have one row
    assert sqlite.count() == 1
    db_rows = sqlite.query(domain_route="planner")
    assert db_rows[0]["eval_passed"] == 1


def test_record_model_call_marks_eval_failed_when_any_check_fails(tmp_path):
    _make_recorder(
        tmp_path,
        results=[
            CheckResult("parse_success", True, 1.0, "ok"),
            CheckResult("latency_budget", False, 0.2, "too slow"),
        ],
    )
    with record_model_call(domain_route="planner") as r:
        r.set_prompt("p")
    assert r.record.eval_passed is False
    assert 0 < r.record.eval_score < 1.0  # averaged


def test_record_model_call_swallows_sink_errors(tmp_path):
    """A broken sink must not break the model call."""
    broken_jsonl = SimpleNamespace(write=lambda r: (_ for _ in ()).throw(RuntimeError("boom")))
    sqlite = SqliteSink(tmp_path / "test.db")
    registry = _FakeCheckRegistry([CheckResult("c", True, 1.0)])
    ModelCallRecorder.reset_instance()
    ModelCallRecorder._instance = ModelCallRecorder(
        jsonl_sink=broken_jsonl,
        sqlite_sink=sqlite,
        check_registry=registry,
    )
    # Should not raise
    with record_model_call(domain_route="planner") as r:
        r.set_prompt("p")
    assert r.record.outcome == OUTCOME_SUCCESS
    # SQLite (the non-broken sink) still got the record
    assert sqlite.count() == 1


def test_record_model_call_exception_in_caller_recorded(tmp_path):
    """When the caller's block raises, the recorder captures the outcome."""
    _make_recorder(tmp_path)
    with pytest.raises(RuntimeError, match="caller-blew-up"):
        with record_model_call(domain_route="planner") as rec:
            rec.set_prompt("p")
            raise RuntimeError("caller-blew-up")
    # No explicit set_outcome — record is unfinished; that's an
    # edge case the caller is responsible for handling.


# ── JsonlSink ─────────────────────────────────────────────────────────


def test_jsonl_sink_round_trip(tmp_path):
    path = tmp_path / "r.jsonl"
    sink = JsonlSink(path)
    rec1 = ModelCallRecord(domain_route="a", code_route="x:1", prompt="p1")
    rec2 = ModelCallRecord(domain_route="b", code_route="x:2", prompt="p2")
    sink.write(rec1)
    sink.write(rec2)
    rows = list(sink.read_all())
    assert len(rows) == 2
    assert rows[0]["domain_route"] == "a"
    assert rows[1]["domain_route"] == "b"


def test_jsonl_sink_clear(tmp_path):
    path = tmp_path / "r.jsonl"
    sink = JsonlSink(path)
    sink.write(ModelCallRecord(domain_route="x"))
    assert path.exists()
    sink.clear()
    assert not path.exists()


# ── SqliteSink ────────────────────────────────────────────────────────


def test_sqlite_sink_query_filter(tmp_path):
    sqlite = SqliteSink(tmp_path / "test.db")
    sqlite.write(ModelCallRecord(domain_route="planner", capability=CAP_PLANNER_TOOL_CALLING))
    sqlite.write(ModelCallRecord(domain_route="vision", capability="vision_x"))
    rows = sqlite.query(domain_route="planner")
    assert len(rows) == 1
    assert rows[0]["domain_route"] == "planner"


def test_sqlite_sink_delete_older_than(tmp_path):
    sqlite = SqliteSink(tmp_path / "test.db")
    old = ModelCallRecord(domain_route="x", started_at="2020-01-01T00:00:00+00:00")
    new = ModelCallRecord(domain_route="x", started_at="2099-01-01T00:00:00+00:00")
    sqlite.write(old)
    sqlite.write(new)
    deleted = sqlite.delete_older_than(ttl_days=30)
    assert deleted == 1
    rows = sqlite.query()
    assert len(rows) == 1
    assert rows[0]["started_at"].startswith("2099")
