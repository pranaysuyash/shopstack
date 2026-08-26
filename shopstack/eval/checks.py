"""Online eval checks (EVAL-OP-1).

Each check is a small, pure function: ``Check(record, history) -> CheckResult``.
The :class:`EvalCheckRegistry` dispatches a record through every
registered check, collects the results, and the recorder uses them to
compute the final ``eval_passed`` / ``eval_score`` on the record.

A new check is one function + one registry entry. No central dispatcher
rewrite — the motto_v3 §0 "extend canonical paths" doctrine.

Built-in checks:

* :func:`check_parse_success` — output parses to the expected shape.
* :func:`check_latency_budget` — within per-route budget (or default).
* :func:`check_length_sanity` — output not empty, not absurdly long.
* :func:`check_cost_budget` — single-call cost under a hard cap.
* :func:`check_tokens_within_context` — output_tokens ≤ model context.
* :func:`check_non_duplicate` — same prompt not fired > N times in window.

The history is provided by the registry and is the previous N records
(default 64) — enough to detect repetition, short enough to keep the
check cheap.
"""
from __future__ import annotations

import json
import logging
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from shopstack.eval.recorder import (
    SHAPE_BYTES,
    SHAPE_RAW,
    SHAPE_STRUCTURED,
    SHAPE_TEXT,
    SHAPE_TOOL_CALLS,
    CheckResult,
    ModelCallRecord,
)

logger = logging.getLogger(__name__)


# Default budgets — overridable per-route via the registry's
# ``with_budget()`` factory or via settings in the future.
DEFAULT_LATENCY_BUDGET_MS = 30_000.0
DEFAULT_COST_BUDGET_USD = 0.50
DEFAULT_MAX_OUTPUT_LENGTH = 50_000
DEFAULT_DUPLICATE_WINDOW = 64
DEFAULT_DUPLICATE_THRESHOLD = 3
DEFAULT_DUPLICATE_TIME_WINDOW_S = 60.0
DEFAULT_MODEL_CONTEXT_TOKENS = 8_192  # conservative lower bound


# ── Built-in checks ───────────────────────────────────────────────────


def check_parse_success(
    record: ModelCallRecord,
    history: Iterable[ModelCallRecord] = (),
) -> CheckResult:
    """Output must parse to the expected shape.

    Shapes:
        tool_calls: output is JSON with a non-empty list of tool calls
        text:       output is a non-empty string
        structured: output is JSON or YAML dict
        bytes:      skipped (no parse)
        raw:        skipped (no parse)
    """
    shape = record.capability_expected_shape or SHAPE_RAW
    if shape == SHAPE_RAW or shape == SHAPE_BYTES:
        return CheckResult("parse_success", True, 1.0, f"shape={shape} skipped")

    output = record.output or ""
    if not output:
        return CheckResult("parse_success", False, 0.0, "empty output")

    if shape == SHAPE_TEXT:
        if not output.strip():
            return CheckResult("parse_success", False, 0.0, "output is whitespace")
        return CheckResult("parse_success", True, 1.0, f"{len(output)} chars")

    if shape == SHAPE_STRUCTURED:
        # Try JSON, fall back to YAML-lite
        try:
            parsed = json.loads(output)
            if not isinstance(parsed, (dict, list)):
                return CheckResult(
                    "parse_success", False, 0.5,
                    f"JSON parsed but top-level is {type(parsed).__name__}",
                )
            return CheckResult("parse_success", True, 1.0, "JSON structured")
        except (json.JSONDecodeError, ValueError):
            return CheckResult(
                "parse_success", False, 0.0,
                f"not valid JSON (first 60 chars: {output[:60]!r})",
            )

    if shape == SHAPE_TOOL_CALLS:
        # Look for a JSON array of tool calls, or the model returning
        # prose. Be generous: a single tool call in object form also
        # counts as success.
        text = output.strip()
        if not text:
            return CheckResult("parse_success", False, 0.0, "empty output")
        try:
            parsed = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return CheckResult(
                "parse_success", False, 0.0,
                f"not valid JSON; first 80 chars: {text[:80]!r}",
            )
        if isinstance(parsed, list):
            if not parsed:
                return CheckResult(
                    "parse_success", False, 0.5, "empty tool call list",
                )
            if not all(isinstance(item, dict) for item in parsed):
                return CheckResult(
                    "parse_success", False, 0.3,
                    "list contains non-dict items",
                )
            return CheckResult(
                "parse_success", True, 1.0,
                f"{len(parsed)} tool call(s) parsed",
            )
        if isinstance(parsed, dict):
            if "tool" in parsed or "tool_name" in parsed or "tool_calls" in parsed:
                return CheckResult(
                    "parse_success", True, 0.8,
                    "single tool call (object form)",
                )
            return CheckResult(
                "parse_success", False, 0.3,
                "object lacks tool/tool_name/tool_calls",
            )
        return CheckResult(
            "parse_success", False, 0.0,
            f"unexpected top-level type {type(parsed).__name__}",
        )

    return CheckResult("parse_success", True, 1.0, f"unknown shape={shape} pass-through")


def check_latency_budget(
    record: ModelCallRecord,
    history: Iterable[ModelCallRecord] = (),
    budget_ms: float = DEFAULT_LATENCY_BUDGET_MS,
) -> CheckResult:
    """latency_ms must be under the route budget."""
    if record.latency_ms <= 0:
        return CheckResult("latency_budget", True, 1.0, "no latency reported")
    if record.latency_ms <= budget_ms:
        score = max(0.5, 1.0 - (record.latency_ms / (budget_ms * 2)))
        return CheckResult(
            "latency_budget", True, round(score, 4),
            f"{record.latency_ms:.0f}ms ≤ {budget_ms:.0f}ms",
        )
    score = max(0.0, 1.0 - (record.latency_ms - budget_ms) / budget_ms)
    return CheckResult(
        "latency_budget", False, round(score, 4),
        f"{record.latency_ms:.0f}ms > {budget_ms:.0f}ms budget",
    )


def check_length_sanity(
    record: ModelCallRecord,
    history: Iterable[ModelCallRecord] = (),
    max_output_length: int = DEFAULT_MAX_OUTPUT_LENGTH,
) -> CheckResult:
    """Output must be non-empty and not absurdly long."""
    if record.output_length == 0:
        return CheckResult("length_sanity", False, 0.0, "empty output")
    if record.output_length > max_output_length:
        return CheckResult(
            "length_sanity", False, 0.0,
            f"output {record.output_length} chars > {max_output_length}",
        )
    # Score mildly penalizes very long but not-blocked outputs.
    ratio = record.output_length / max_output_length
    score = 1.0 - (0.2 * ratio) if ratio > 0.5 else 1.0
    return CheckResult(
        "length_sanity", True, round(score, 4),
        f"{record.output_length} chars",
    )


def check_cost_budget(
    record: ModelCallRecord,
    history: Iterable[ModelCallRecord] = (),
    budget_usd: float = DEFAULT_COST_BUDGET_USD,
) -> CheckResult:
    """Single-call cost must be under the hard cap."""
    if record.cost_usd <= 0:
        return CheckResult("cost_budget", True, 1.0, "no cost reported (likely local)")
    if record.cost_usd <= budget_usd:
        return CheckResult(
            "cost_budget", True, 1.0,
            f"${record.cost_usd:.4f} ≤ ${budget_usd:.2f}",
        )
    return CheckResult(
        "cost_budget", False, 0.0,
        f"${record.cost_usd:.4f} > ${budget_usd:.2f} cap",
    )


def check_tokens_within_context(
    record: ModelCallRecord,
    history: Iterable[ModelCallRecord] = (),
    max_context_tokens: int = DEFAULT_MODEL_CONTEXT_TOKENS,
) -> CheckResult:
    """Output tokens must fit in the model's context window.

    This is a soft check — a real context budget depends on the
    model. We use a conservative default; the real model context
    length can be plumbed in later via the registry.
    """
    if record.output_tokens == 0:
        return CheckResult(
            "tokens_within_context", True, 1.0,
            "no token count reported",
        )
    if record.output_tokens <= max_context_tokens:
        return CheckResult(
            "tokens_within_context", True, 1.0,
            f"{record.output_tokens} ≤ {max_context_tokens}",
        )
    return CheckResult(
        "tokens_within_context", False, 0.0,
        f"{record.output_tokens} > {max_context_tokens} ctx (default cap)",
    )


def check_non_duplicate(
    record: ModelCallRecord,
    history: Iterable[ModelCallRecord] = (),
    window: int = DEFAULT_DUPLICATE_WINDOW,
    threshold: int = DEFAULT_DUPLICATE_THRESHOLD,
    time_window_s: float = DEFAULT_DUPLICATE_TIME_WINDOW_S,
) -> CheckResult:
    """The same prompt must not be fired > ``threshold`` times in
    ``time_window_s`` seconds. Catches model loops.

    Prompt comparison is on the *length* and the first 200 chars; full
    exact match is too strict (whitespace / time-of-day noise).
    """
    if not record.prompt:
        return CheckResult("non_duplicate", True, 1.0, "not_available: prompt is None")

    # Build a fingerprint of the current prompt
    fp = (len(record.prompt), record.prompt[:200])
    if not fp[0]:
        return CheckResult("non_duplicate", True, 1.0, "empty prompt")

    count = 1
    try:
        from datetime import datetime
        current_dt = datetime.fromisoformat(record.started_at)
    except (TypeError, ValueError):
        current_dt = None

    # Walk the history (caller provides a bounded deque)
    for prev in list(history)[:window]:
        prev_fp = (len(prev.prompt or ""), (prev.prompt or "")[:200])
        if prev_fp != fp:
            continue
        if current_dt is not None:
            try:
                prev_dt = datetime.fromisoformat(prev.started_at)
                if abs((current_dt - prev_dt).total_seconds()) > time_window_s:
                    continue
            except (TypeError, ValueError):
                pass
        count += 1
        if count >= threshold:
            return CheckResult(
                "non_duplicate", False, 0.0,
                f"prompt fingerprint seen {count}× in {time_window_s:.0f}s",
            )
    return CheckResult(
        "non_duplicate", True, 1.0,
        f"prompt fingerprint seen {count}× in window",
    )


def check_execution_success(
    record: ModelCallRecord,
    history: Iterable[ModelCallRecord] = (),
) -> CheckResult:
    """Ensure the agentic execution phase did not hide tool failures."""
    execution = record.execution or {}
    if not execution:
        return CheckResult(
            "execution_success", True, 1.0,
            "not_available: no execution summary",
        )

    status = str(execution.get("status", "unknown"))
    failed = int(execution.get("tool_calls_failed", 0) or 0)
    truncated = int(execution.get("tool_calls_truncated", 0) or 0)
    if status in {"completed", "responded"} and failed == 0 and truncated == 0:
        return CheckResult("execution_success", True, 1.0, status)
    if status == "parse_failed":
        return CheckResult(
            "execution_success", False, 0.0,
            "parser rejected the provider output",
        )
    if status == "cost_blocked":
        return CheckResult(
            "execution_success", False, 0.0,
            "run blocked by cost budget",
        )
    return CheckResult(
        "execution_success",
        False,
        0.0 if failed else 0.5,
        f"status={status}, failed={failed}, truncated={truncated}",
    )


# ── Registry ───────────────────────────────────────────────────────────


CheckFn = Callable[..., CheckResult]


@dataclass
class _RegisteredCheck:
    name: str
    fn: CheckFn
    kwargs: dict[str, Any]


class EvalCheckRegistry:
    """Holds the ordered list of checks and runs them per record."""

    def __init__(self, checks: list[_RegisteredCheck] | None = None) -> None:
        self._checks: list[_RegisteredCheck] = list(checks or [])
        self._history: deque[ModelCallRecord] = deque(maxlen=128)
        # Pull a sensible default for the duplicate window.
        self._history_maxlen = max(DEFAULT_DUPLICATE_WINDOW, 32)

    def register(
        self,
        name: str,
        fn: CheckFn,
        **kwargs: Any,
    ) -> None:
        """Add a check (or replace one with the same name)."""
        for i, existing in enumerate(self._checks):
            if existing.name == name:
                self._checks[i] = _RegisteredCheck(name, fn, kwargs)
                return
        self._checks.append(_RegisteredCheck(name, fn, kwargs))

    def history(self) -> deque[ModelCallRecord]:
        return self._history

    def run(self, record: ModelCallRecord) -> list[CheckResult]:
        results: list[CheckResult] = []
        for entry in self._checks:
            try:
                result = entry.fn(record, self._history, **entry.kwargs)
            except Exception as exc:  # pragma: no cover
                logger.warning("check %s raised: %s", entry.name, exc, exc_info=True)
                result = CheckResult(
                    entry.name, False, 0.0,
                    f"check raised {type(exc).__name__}",
                )
            results.append(result)
        # After evaluation, push into history (capped to maxlen).
        if self._history.maxlen != self._history_maxlen:
            self._history = deque(self._history, maxlen=self._history_maxlen)
        self._history.append(record)
        return results


# Default set of checks for the live app.

def default_registry() -> EvalCheckRegistry:
    reg = EvalCheckRegistry()
    reg.register("parse_success", check_parse_success)
    reg.register("latency_budget", check_latency_budget)
    reg.register("length_sanity", check_length_sanity)
    reg.register("cost_budget", check_cost_budget)
    reg.register("tokens_within_context", check_tokens_within_context)
    reg.register("non_duplicate", check_non_duplicate)
    reg.register("execution_success", check_execution_success)
    return reg


__all__ = [
    "DEFAULT_COST_BUDGET_USD",
    "DEFAULT_DUPLICATE_THRESHOLD",
    "DEFAULT_DUPLICATE_TIME_WINDOW_S",
    "DEFAULT_DUPLICATE_WINDOW",
    "DEFAULT_LATENCY_BUDGET_MS",
    "DEFAULT_MAX_OUTPUT_LENGTH",
    "DEFAULT_MODEL_CONTEXT_TOKENS",
    "EvalCheckRegistry",
    "check_cost_budget",
    "check_execution_success",
    "check_latency_budget",
    "check_length_sanity",
    "check_non_duplicate",
    "check_parse_success",
    "check_tokens_within_context",
    "default_registry",
]
