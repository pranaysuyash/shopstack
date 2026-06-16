"""Tests for the o/p eval aggregator + regression detection (EVAL-OP-1)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from shopstack.eval import (
    CAP_PLANNER_TOOL_CALLING,
    ModelCallRecord,
    SqliteSink,
)
from shopstack.eval.aggregator import (
    DEFAULT_TOLERANCE,
    RouteStats,
    aggregate_by_route,
    aggregate_records,
    load_route_baseline,
    route_regression_for_all,
    route_regression_report,
    save_route_baseline,
)
from shopstack.eval.recorder import (
    OUTCOME_EXCEPTION,
    OUTCOME_PARSE_ERROR,
    OUTCOME_SUCCESS,
)


def _record(
    domain_route: str = "planner",
    capability: str = CAP_PLANNER_TOOL_CALLING,
    outcome: str = OUTCOME_SUCCESS,
    latency_ms: float = 100.0,
    cost_usd: float = 0.001,
    started_at: str | None = None,
    eval_passed: bool = True,
    eval_score: float = 1.0,
) -> ModelCallRecord:
    return ModelCallRecord(
        domain_route=domain_route,
        capability=capability,
        outcome=outcome,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
        started_at=started_at or datetime.now(timezone.utc).isoformat(),
        eval_passed=eval_passed,
        eval_score=eval_score,
    )


# ── aggregate_records ─────────────────────────────────────────────────


def test_aggregate_records_basic_counts():
    records = [
        _record(outcome=OUTCOME_SUCCESS, latency_ms=100.0),
        _record(outcome=OUTCOME_SUCCESS, latency_ms=200.0),
        _record(outcome=OUTCOME_EXCEPTION, latency_ms=300.0),
        _record(outcome=OUTCOME_PARSE_ERROR, latency_ms=400.0),
    ]
    grouped = aggregate_records(records)
    stats = grouped[("planner", CAP_PLANNER_TOOL_CALLING)]
    assert stats.n_calls == 4
    assert stats.n_success == 2
    assert stats.n_failed == 2
    assert stats.success_rate == 0.5


def test_aggregate_records_p50_p95_latency():
    records = [_record(latency_ms=float(i)) for i in range(1, 101)]
    grouped = aggregate_records(records)
    stats = grouped[("planner", CAP_PLANNER_TOOL_CALLING)]
    # p50 of 1..100 is around 50, p95 is around 95
    assert 48.0 <= stats.p50_latency_ms <= 52.0
    assert 93.0 <= stats.p95_latency_ms <= 97.0
    assert stats.mean_latency_ms == 50.5


def test_aggregate_records_groups_by_route_and_capability():
    records = [
        _record(domain_route="planner"),
        _record(domain_route="market_lens", capability="vision_x"),
        _record(domain_route="market_lens", capability="vision_x"),
    ]
    grouped = aggregate_records(records)
    assert len(grouped) == 2
    assert ("planner", CAP_PLANNER_TOOL_CALLING) in grouped
    assert ("market_lens", "vision_x") in grouped


def test_aggregate_records_handles_zero_latency():
    records = [_record(latency_ms=0.0), _record(latency_ms=0.0)]
    grouped = aggregate_records(records)
    stats = grouped[("planner", CAP_PLANNER_TOOL_CALLING)]
    assert stats.p50_latency_ms == 0.0
    assert stats.p95_latency_ms == 0.0


def test_aggregate_records_total_cost_and_tokens():
    records = [
        _record(cost_usd=0.001, eval_passed=True),
        _record(cost_usd=0.002, eval_passed=True),
        _record(cost_usd=0.003, eval_passed=False, outcome=OUTCOME_PARSE_ERROR),
    ]
    grouped = aggregate_records(records)
    stats = grouped[("planner", CAP_PLANNER_TOOL_CALLING)]
    assert stats.total_cost_usd == pytest.approx(0.006)
    assert stats.mean_cost_usd == pytest.approx(0.002)
    # eval_pass_rate is rounded to 4 dp; allow ±0.001
    assert abs(stats.eval_pass_rate - 2/3) < 0.001


# ── aggregate_by_route via SqliteSink ─────────────────────────────────


def test_aggregate_by_route_uses_sqlite_sink(tmp_path):
    sqlite = SqliteSink(tmp_path / "test.db")
    sqlite.write(_record(domain_route="planner"))
    sqlite.write(_record(domain_route="planner", outcome=OUTCOME_EXCEPTION))
    sqlite.write(_record(domain_route="vision", capability="vision_x"))
    stats_list = aggregate_by_route(sqlite, limit=100)
    assert len(stats_list) == 2
    by_route = {s.domain_route: s for s in stats_list}
    assert by_route["planner"].n_calls == 2
    assert by_route["planner"].n_success == 1
    assert by_route["vision"].n_calls == 1


# ── route_regression_report ───────────────────────────────────────────


def test_route_regression_report_pass_within_tolerance():
    stats = RouteStats(
        domain_route="planner",
        capability=CAP_PLANNER_TOOL_CALLING,
        n_calls=10,
        n_success=10,
        success_rate=0.90,
        p95_latency_ms=8000.0,
        mean_cost_usd=0.010,
    )
    baseline = {
        "success_rate": 0.90,
        "p95_latency_ms": 8000.0,
        "mean_cost_usd": 0.010,
    }
    rep = route_regression_report(stats, baseline)
    assert rep.passed is True
    assert rep.regressions == []


def test_route_regression_report_success_rate_drop():
    stats = RouteStats(
        domain_route="planner",
        capability=CAP_PLANNER_TOOL_CALLING,
        n_calls=10,
        n_success=7,
        success_rate=0.70,  # dropped from 0.90
        p95_latency_ms=8000.0,
        mean_cost_usd=0.010,
    )
    baseline = {"success_rate": 0.90, "p95_latency_ms": 8000.0, "mean_cost_usd": 0.010}
    rep = route_regression_report(stats, baseline, tolerance={"success_rate": 0.10})
    assert rep.passed is False
    assert any("success_rate" in r for r in rep.regressions)


def test_route_regression_report_p95_latency_spike():
    stats = RouteStats(
        domain_route="planner",
        capability=CAP_PLANNER_TOOL_CALLING,
        n_calls=10,
        success_rate=0.90,
        p95_latency_ms=15000.0,  # way above 8000
        mean_cost_usd=0.010,
    )
    baseline = {"success_rate": 0.90, "p95_latency_ms": 8000.0, "mean_cost_usd": 0.010}
    rep = route_regression_report(stats, baseline)
    assert rep.passed is False
    assert any("p95_latency_ms" in r for r in rep.regressions)


def test_route_regression_report_cost_spike():
    stats = RouteStats(
        domain_route="planner",
        capability=CAP_PLANNER_TOOL_CALLING,
        n_calls=10,
        success_rate=0.90,
        p95_latency_ms=8000.0,
        mean_cost_usd=0.10,  # 10x baseline
    )
    baseline = {"success_rate": 0.90, "p95_latency_ms": 8000.0, "mean_cost_usd": 0.010}
    rep = route_regression_report(stats, baseline)
    assert rep.passed is False
    assert any("mean_cost_usd" in r for r in rep.regressions)


def test_route_regression_report_missing_metric_skipped():
    stats = RouteStats(
        domain_route="planner",
        capability=CAP_PLANNER_TOOL_CALLING,
        n_calls=10,
        success_rate=0.90,
        p95_latency_ms=8000.0,
        mean_cost_usd=0.010,
    )
    # Baseline only has success_rate; latency/cost not compared
    rep = route_regression_report(stats, {"success_rate": 0.90})
    assert rep.passed is True


def test_route_regression_for_all_runs_every_route():
    stats_list = [
        RouteStats(
            domain_route="planner", capability=CAP_PLANNER_TOOL_CALLING,
            n_calls=5, n_success=5, success_rate=1.0, p95_latency_ms=100.0, mean_cost_usd=0.001,
        ),
        RouteStats(
            domain_route="unknown_route", capability="x",
            n_calls=1, n_success=0, success_rate=0.0, p95_latency_ms=100.0, mean_cost_usd=0.001,
        ),
    ]
    baseline = {
        "planner": {"success_rate": 0.90, "p95_latency_ms": 8000.0, "mean_cost_usd": 0.01},
        # unknown_route has no baseline — should not regress
    }
    reports = route_regression_for_all(stats_list, baseline=baseline)
    assert len(reports) == 2
    by_route = {r.domain_route: r for r in reports}
    assert by_route["planner"].passed is True
    assert by_route["unknown_route"].passed is True  # no baseline = no regression


# ── baseline file round trip ──────────────────────────────────────────


def test_load_save_route_baseline_round_trip(tmp_path):
    path = tmp_path / "baseline.json"
    data = {
        "planner": {
            "success_rate": 0.90,
            "p95_latency_ms": 8000.0,
            "mean_cost_usd": 0.01,
            "tolerance": {"success_rate": 0.10},
        },
        "vision": {"success_rate": 0.85},
    }
    save_route_baseline(data, path=path)
    loaded = load_route_baseline(path=path)
    assert loaded == data


def test_load_route_baseline_missing_returns_empty(tmp_path):
    loaded = load_route_baseline(path=tmp_path / "nope.json")
    assert loaded == {}
