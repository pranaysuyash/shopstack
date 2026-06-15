"""Capture user-confirmed traces as parser training data.

Closes Item #16 (motto_v3 §0.5 evidence tiers, §0.6
risk-based verification, §0.14 product reality): the project
already exports **synthetic** training pairs from
``shopstack.services.fine_tuned_parser.build_training_pairs()``.
This module closes the *real* signal gap — every trace the
user explicitly confirmed (or that the system auto-confirmed
with a clear intent) is a labelled training example the
fine-tuned parser can learn from.

**Why a separate module (motto_v3 §11 engineering standards):**

The trace system is forward-only — once a trace ages past
``settings.trace_ttl_days`` (default 30), it's deleted. The
fine-tuned parser's training set would always be one TTL
behind. This module runs **before** retention so confirmed
traces become permanent training rows. Splitting it out:

* keeps ``fine_tuned_parser`` focused on the inference side
  (synthetic pairs + classify);
* keeps ``data_retention`` focused on the policy (what gets
  deleted when);
* lets us call the capture step from tests, the retention
  job, and the bench layer with the same function.

**Supersession rule (motto_v3 §7):** callers opt in by
calling :func:`capture_confirmed_traces` before retention. We
do NOT auto-wrap the DB write path or the retention job —
that's a hidden side effect of the wrong kind. The
``maybe_capture_before_retention`` helper is the explicit
opt-in seam.

**Confirmation-value ranking:**

Not every confirmed trace is a good training example. We
rank the ``human_confirmation`` values so a single canonical
pass produces a sensible labelled set:

* ``"confirmed-by-user"`` — gold (the user actually clicked yes)
* ``"auto-confirmed"`` — high (the system + user intent both clear)
* ``"responded"``, ``"auto"``, ``"auto-summarized"`` — medium
* ``"uncommitted"`` — drop (no signal)
* ``None`` / unknown — drop

The ranking lives in :data:`CONFIRMATION_RANK`; tests assert it.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ── Confirmation-value ranking ─────────────────────────────────────


# Higher rank = stronger training signal. The capture pass
# filters to confirmation values with rank >= MIN_RANK.
CONFIRMATION_RANK: dict[str, int] = {
    "confirmed-by-user": 100,  # user explicitly clicked confirm
    "auto-confirmed": 70,       # system high-confidence + user intent clear
    "responded": 50,            # the assistant produced a response
    "auto": 40,                 # system-generated but auto-bucketed
    "auto-summarized": 40,      # system summarized
    "uncommitted": 0,           # no signal — drop
}

# Default floor: include "confirmed-by-user" and "auto-confirmed"
# (the two values where a user's intent is unambiguously known).
# Callers can lower the floor to include more, or raise it to
# be stricter.
MIN_RANK_DEFAULT: int = CONFIRMATION_RANK["auto-confirmed"]


# ── Result model ──────────────────────────────────────────────────


@dataclass
class TrainingExample:
    """A single confirmed-trace training example.

    The shape matches the JSONL the fine-tuned parser ingests
    in :mod:`shopstack.services.fine_tuned_parser` so we can
    append to the same training set without changing the
    inference side. The ``source`` field distinguishes
    real-captured rows from synthetic ones when the data
    is later analysed.
    """

    text: str
    intent: str
    args: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    confirmation: str = "confirmed-by-user"
    trace_id: str = ""
    timestamp: str = ""
    household_id: str = ""
    source: str = "real-confirmed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "intent": self.intent,
            "args": self.args,
            "confidence": self.confidence,
            "confirmation": self.confirmation,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "household_id": self.household_id,
            "source": self.source,
        }


@dataclass
class CaptureReport:
    """Aggregate result of a capture pass."""

    captured: list[TrainingExample] = field(default_factory=list)
    skipped_unconfirmed: int = 0
    skipped_empty_request: int = 0
    skipped_no_tool_call: int = 0

    @property
    def total(self) -> int:
        return len(self.captured)

    def to_dict(self) -> dict[str, Any]:
        return {
            "captured": len(self.captured),
            "skipped_unconfirmed": self.skipped_unconfirmed,
            "skipped_empty_request": self.skipped_empty_request,
            "skipped_no_tool_call": self.skipped_no_tool_call,
        }


# ── Core extraction ───────────────────────────────────────────────


def _first_tool_call(trace: Any) -> dict[str, Any] | None:
    """Return the first proposed tool call as a dict, or None."""
    calls = getattr(trace, "proposed_tool_calls", None) or []
    if not calls:
        return None
    # The schema defines ToolCall as a Pydantic BaseModel with
    # .call_id, .tool_name, .args, .success, .error, .timestamp,
    # .requires_confirmation, .confirmed. Older traces may store
    # raw dicts; the result of .model_dump() works for both.
    first = calls[0]
    if hasattr(first, "model_dump"):
        return first.model_dump()
    if isinstance(first, dict):
        return first
    # Last resort: best-effort attribute access.
    return {
        "tool_name": getattr(first, "tool_name", ""),
        "args": getattr(first, "args", {}) or {},
        "confidence": getattr(first, "confidence", 0.0),
    }


def _intent_from_tool_call(tool_call: dict[str, Any]) -> str:
    """Map a tool-call shape to the parser's intent taxonomy.

    The fine-tuned parser's intents are coarse (e.g.
    ``"add_inventory_item"``, ``"consume_item"``). We use the
    tool_name as the intent. A trace whose first tool call is
    ``add_inventory_lot`` therefore maps to
    ``"add_inventory_item"`` (the parser intent, not the tool
    name) — they're the same in practice but a future
    rename is easy enough to add here.
    """
    tool = (tool_call.get("tool_name") or "").strip()
    if not tool:
        return "general_query"
    # Common renames: tool → parser intent
    if tool == "add_inventory_lot":
        return "add_inventory_item"
    return tool


def _args_from_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    """Normalize a tool call's args for training.

    The parser's training data is a flat dict of kwargs.
    Pydantic args from a ToolCall may contain list values
    (e.g. ``linked_inventory_lots``); we keep them as-is —
    the parser handles them downstream.
    """
    args = tool_call.get("args") or {}
    if not isinstance(args, dict):
        return {}
    return dict(args)


def extract_training_examples(
    traces: Iterable[Any],
    *,
    min_rank: int = MIN_RANK_DEFAULT,
) -> CaptureReport:
    """Convert a list of Trace objects into confirmed training examples.

    Filters out:
    * traces with no ``proposed_tool_calls``
    * traces whose ``human_confirmation`` rank is below ``min_rank``
    * traces whose ``redacted_user_request`` is empty / whitespace

    Args:
        traces: Any iterable of :class:`shopstack.schemas.models.Trace`
            instances. Order is preserved in the output.
        min_rank: Minimum :data:`CONFIRMATION_RANK` value to keep
            a trace. Defaults to 70 (includes "confirmed-by-user"
            and "auto-confirmed"). Set to 0 to keep everything
            that has any confirmation value at all.

    Returns:
        A :class:`CaptureReport` carrying the captured examples
        and skip counters for diagnostics.
    """
    report = CaptureReport()
    for trace in traces:
        confirmation = getattr(trace, "human_confirmation", None)
        if confirmation is None:
            report.skipped_unconfirmed += 1
            continue
        if CONFIRMATION_RANK.get(confirmation, 0) < min_rank:
            report.skipped_unconfirmed += 1
            continue
        text = (getattr(trace, "redacted_user_request", "") or "").strip()
        if not text:
            report.skipped_empty_request += 1
            continue
        call = _first_tool_call(trace)
        if call is None:
            report.skipped_no_tool_call += 1
            continue
        report.captured.append(
            TrainingExample(
                text=text,
                intent=_intent_from_tool_call(call),
                args=_args_from_tool_call(call),
                confidence=float(call.get("confidence") or 0.0) or 1.0,
                confirmation=str(confirmation),
                trace_id=getattr(trace, "trace_id", ""),
                timestamp=str(getattr(trace, "timestamp", "") or ""),
                household_id=getattr(trace, "actor_id", "") or "",
            )
        )
    return report


# ── DB helper ─────────────────────────────────────────────────────


def capture_from_database(
    database: Any,
    *,
    limit: int = 500,
    min_rank: int = MIN_RANK_DEFAULT,
) -> CaptureReport:
    """Read traces from the database and extract training examples.

    Convenience over :func:`extract_training_examples` — pulls
    the latest ``limit`` traces via ``database.get_traces``
    and filters by confirmation rank. The ``limit`` exists
    so a single capture pass doesn't accidentally pull
    100k rows from a long-running household.
    """
    try:
        traces = database.get_traces(limit=limit)
    except Exception as exc:  # noqa: BLE001
        logger.warning("training_capture.get_traces failed: %s", exc)
        return CaptureReport()
    return extract_training_examples(traces, min_rank=min_rank)


# ── JSONL writer ─────────────────────────────────────────────────


DEFAULT_OUTPUT_PATH: str = "data/parser_training_real.jsonl"


def write_training_jsonl(
    examples: Iterable[TrainingExample],
    out_path: str | Path = DEFAULT_OUTPUT_PATH,
) -> int:
    """Append training examples to a JSONL file.

    The output file is append-only so a daily capture pass
    builds up the training set without clobbering prior rows.
    Each line is one self-contained example (see
    :meth:`TrainingExample.to_dict`).

    Returns the number of rows written. Creates the parent
    directory if it doesn't exist.
    """
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("a", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")
            n += 1
    return n


# ── Retention integration ────────────────────────────────────────


def maybe_capture_before_retention(
    database: Any,
    *,
    out_path: str | Path = DEFAULT_OUTPUT_PATH,
    limit: int = 500,
    min_rank: int = MIN_RANK_DEFAULT,
) -> CaptureReport:
    """One-shot convenience: capture confirmed traces and
    append to the real-training JSONL.

    Callers (the data-retention job, the bench layer, an
    operator script) can invoke this before pruning so
    confirmed traces don't get deleted before being
    captured. Returns the report so the caller can log it.
    """
    report = capture_from_database(
        database, limit=limit, min_rank=min_rank
    )
    if report.captured:
        written = write_training_jsonl(report.captured, out_path)
        logger.info(
            "training_capture wrote %d examples to %s "
            "(skipped: %d unconfirmed, %d empty, %d no-tool-call)",
            written,
            out_path,
            report.skipped_unconfirmed,
            report.skipped_empty_request,
            report.skipped_no_tool_call,
        )
    return report


__all__ = [
    "CONFIRMATION_RANK",
    "CaptureReport",
    "DEFAULT_OUTPUT_PATH",
    "MIN_RANK_DEFAULT",
    "TrainingExample",
    "capture_from_database",
    "extract_training_examples",
    "maybe_capture_before_retention",
    "write_training_jsonl",
]
