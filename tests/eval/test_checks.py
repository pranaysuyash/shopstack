"""Tests for the o/p eval built-in checks (EVAL-OP-1).

Cover every check in :mod:`shopstack.eval.checks`:

* parse_success across all expected shapes
* latency_budget pass / fail
* length_sanity empty / too long / OK
* cost_budget pass / fail / no cost reported
* tokens_within_context pass / fail
* non_duplicate threshold met / not met
* the registry runs all checks, marks the record, and pushes to history
"""
from __future__ import annotations

import pytest

from shopstack.eval import (
    CAP_PLANNER_TOOL_CALLING,
    CheckResult,
    ModelCallRecord,
    SHAPE_BYTES,
    SHAPE_RAW,
    SHAPE_STRUCTURED,
    SHAPE_TEXT,
    SHAPE_TOOL_CALLS,
)
from shopstack.eval.checks import (
    EvalCheckRegistry,
    check_cost_budget,
    check_latency_budget,
    check_length_sanity,
    check_non_duplicate,
    check_parse_success,
    check_tokens_within_context,
    default_registry,
)


def _record(**kwargs) -> ModelCallRecord:
    base = dict(
        domain_route="planner",
        capability=CAP_PLANNER_TOOL_CALLING,
        capability_expected_shape=SHAPE_TOOL_CALLS,
    )
    base.update(kwargs)
    return ModelCallRecord(**base)


# ── parse_success ─────────────────────────────────────────────────────


def test_parse_success_raw_passes():
    r = _record(capability_expected_shape=SHAPE_RAW, output="anything")
    res = check_parse_success(r)
    assert res.passed is True
    assert "skipped" in res.notes


def test_parse_success_bytes_passes():
    r = _record(capability_expected_shape=SHAPE_BYTES, output="")
    res = check_parse_success(r)
    assert res.passed is True


def test_parse_success_text_empty_fails():
    r = _record(capability_expected_shape=SHAPE_TEXT, output="")
    res = check_parse_success(r)
    assert res.passed is False
    assert res.score == 0.0


def test_parse_success_text_passes():
    r = _record(capability_expected_shape=SHAPE_TEXT, output="hello world")
    res = check_parse_success(r)
    assert res.passed is True


def test_parse_success_text_whitespace_only_fails():
    r = _record(capability_expected_shape=SHAPE_TEXT, output="   \n  ")
    res = check_parse_success(r)
    assert res.passed is False


def test_parse_success_structured_json_passes():
    r = _record(
        capability_expected_shape=SHAPE_STRUCTURED,
        output='{"items": ["a", "b"]}',
    )
    res = check_parse_success(r)
    assert res.passed is True


def test_parse_success_structured_invalid_json_fails():
    r = _record(capability_expected_shape=SHAPE_STRUCTURED, output="not json")
    res = check_parse_success(r)
    assert res.passed is False


def test_parse_success_tool_calls_list_passes():
    r = _record(
        capability_expected_shape=SHAPE_TOOL_CALLS,
        output='[{"tool": "respond", "args": {"message": "ok"}}]',
    )
    res = check_parse_success(r)
    assert res.passed is True
    assert "1 tool call" in res.notes


def test_parse_success_tool_calls_object_form_passes_with_partial_credit():
    r = _record(
        capability_expected_shape=SHAPE_TOOL_CALLS,
        output='{"tool": "respond", "args": {"message": "ok"}}',
    )
    res = check_parse_success(r)
    assert res.passed is True
    assert res.score == 0.8


def test_parse_success_tool_calls_empty_list_partial():
    r = _record(
        capability_expected_shape=SHAPE_TOOL_CALLS,
        output="[]",
    )
    res = check_parse_success(r)
    assert res.passed is False
    assert 0 < res.score < 1


def test_parse_success_tool_calls_invalid_json_fails():
    r = _record(
        capability_expected_shape=SHAPE_TOOL_CALLS,
        output="I cannot do that",
    )
    res = check_parse_success(r)
    assert res.passed is False


# ── latency_budget ────────────────────────────────────────────────────


def test_latency_budget_no_latency_reported_passes():
    r = _record(latency_ms=0.0)
    res = check_latency_budget(r)
    assert res.passed is True


def test_latency_budget_within_budget_passes():
    r = _record(latency_ms=500.0)
    res = check_latency_budget(r, budget_ms=1000.0)
    assert res.passed is True


def test_latency_budget_exceeds_fails():
    r = _record(latency_ms=5000.0)
    res = check_latency_budget(r, budget_ms=1000.0)
    assert res.passed is False
    assert "budget" in res.notes


# ── length_sanity ─────────────────────────────────────────────────────


def test_length_sanity_empty_fails():
    r = _record(output="", output_length=0)
    res = check_length_sanity(r)
    assert res.passed is False


def test_length_sanity_normal_passes():
    r = _record(output="hello", output_length=5)
    res = check_length_sanity(r)
    assert res.passed is True


def test_length_sanity_too_long_fails():
    r = _record(output="x" * 100, output_length=100)
    res = check_length_sanity(r, max_output_length=50)
    assert res.passed is False


# ── cost_budget ───────────────────────────────────────────────────────


def test_cost_budget_no_cost_passes():
    r = _record(cost_usd=0.0)
    res = check_cost_budget(r)
    assert res.passed is True
    assert "local" in res.notes


def test_cost_budget_within_passes():
    r = _record(cost_usd=0.05)
    res = check_cost_budget(r, budget_usd=0.50)
    assert res.passed is True


def test_cost_budget_exceeds_fails():
    r = _record(cost_usd=1.00)
    res = check_cost_budget(r, budget_usd=0.50)
    assert res.passed is False


# ── tokens_within_context ─────────────────────────────────────────────


def test_tokens_within_context_no_count_passes():
    r = _record(output_tokens=0)
    res = check_tokens_within_context(r)
    assert res.passed is True


def test_tokens_within_context_fits():
    r = _record(output_tokens=2000)
    res = check_tokens_within_context(r, max_context_tokens=4096)
    assert res.passed is True


def test_tokens_within_context_overflow_fails():
    r = _record(output_tokens=10000)
    res = check_tokens_within_context(r, max_context_tokens=4096)
    assert res.passed is False


# ── non_duplicate ─────────────────────────────────────────────────────


def test_non_duplicate_no_history_passes():
    r = _record(prompt="hello", prompt_length=5)
    res = check_non_duplicate(r, history=[])
    assert res.passed is True


def test_non_duplicate_first_call_passes():
    r = _record(prompt="hello", prompt_length=5)
    res = check_non_duplicate(r, history=[])
    assert res.passed is True


def test_non_duplicate_loop_detected():
    base = dict(
        domain_route="planner",
        capability=CAP_PLANNER_TOOL_CALLING,
        capability_expected_shape=SHAPE_TOOL_CALLS,
        prompt="same prompt",
        prompt_length=11,
        output="x",
    )
    history = [
        ModelCallRecord(started_at="2026-01-01T00:00:00+00:00", **base),
        ModelCallRecord(started_at="2026-01-01T00:00:01+00:00", **base),
    ]
    current = ModelCallRecord(started_at="2026-01-01T00:00:02+00:00", **base)
    res = check_non_duplicate(current, history=history, threshold=3, time_window_s=60.0)
    assert res.passed is False
    assert "3×" in res.notes


def test_non_duplicate_within_time_window_only():
    base = dict(
        domain_route="planner",
        capability=CAP_PLANNER_TOOL_CALLING,
        capability_expected_shape=SHAPE_TOOL_CALLS,
        prompt="same prompt",
        prompt_length=11,
        output="x",
    )
    history = [
        ModelCallRecord(started_at="2020-01-01T00:00:00+00:00", **base),
        ModelCallRecord(started_at="2020-01-01T00:00:01+00:00", **base),
    ]
    current = ModelCallRecord(started_at="2026-01-01T00:00:02+00:00", **base)
    # Old history is outside the 60s window — current call should pass
    res = check_non_duplicate(current, history=history, threshold=3, time_window_s=60.0)
    assert res.passed is True


def test_non_duplicate_different_prompts_pass():
    r1 = _record(prompt="alpha", prompt_length=5)
    r2 = _record(prompt="beta", prompt_length=4)
    r3 = _record(prompt="gamma", prompt_length=5)
    res = check_non_duplicate(r3, history=[r1, r2])
    assert res.passed is True


# ── Registry ──────────────────────────────────────────────────────────


def test_default_registry_runs_all_six_checks():
    reg = default_registry()
    names = [c.name for c in reg._checks]  # noqa: SLF001 - testing internals
    assert names == [
        "parse_success",
        "latency_budget",
        "length_sanity",
        "cost_budget",
        "tokens_within_context",
        "non_duplicate",
    ]


def test_registry_returns_check_results_and_pushes_to_history():
    reg = EvalCheckRegistry()
    reg.register("always_pass", lambda r, h, **kw: CheckResult("always_pass", True, 1.0))
    r1 = _record(prompt="x", output="y", prompt_length=1, output_length=1)
    r2 = _record(prompt="z", output="w", prompt_length=1, output_length=1)
    results1 = reg.run(r1)
    results2 = reg.run(r2)
    assert len(results1) == 1 and results1[0].passed
    assert len(results2) == 1 and results2[0].passed
    # r1 is in history by the time r2 runs
    assert r1 in list(reg.history())[:1]


def test_registry_continues_when_check_raises():
    reg = EvalCheckRegistry()
    reg.register("ok", lambda r, h, **kw: CheckResult("ok", True, 1.0))

    def bad(r, h, **kw):
        raise ValueError("simulated")

    reg.register("bad", bad)
    r = _record(prompt="x", output="y", prompt_length=1, output_length=1)
    results = reg.run(r)
    assert len(results) == 2
    bad_result = next(c for c in results if c.check == "bad")
    assert bad_result.passed is False
    assert "raised" in bad_result.notes


def test_registry_register_replaces_existing():
    reg = EvalCheckRegistry()
    reg.register("c", lambda r, h, **kw: CheckResult("c", True, 1.0))
    reg.register("c", lambda r, h, **kw: CheckResult("c", False, 0.0, "replaced"))
    r = _record(prompt="x", output="y", prompt_length=1, output_length=1)
    results = reg.run(r)
    assert len(results) == 1
    assert results[0].passed is False
    assert "replaced" in results[0].notes
