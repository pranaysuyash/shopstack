"""Per-route aggregation and regression detection (EVAL-OP-1).

Two responsibilities:

1. :func:`aggregate_by_route` — group records by (domain_route,
   capability) and compute success_rate, p50/p95 latency, total cost,
   counts by outcome. Backed by the SQLite table.
2. :func:`route_regression_report` — compare the latest rolling
   window against a per-route baseline (``route_baseline.json``) and
   emit a non-blocking regression verdict per route.

The baseline file is git-tracked (reviewed, known-good). The window
defaults to "last 100 records OR last 24h, whichever is larger" so
fresh routes still get verdicts quickly.

Design notes (motto_v3 §0):

* No copy of the bench_results regression — we *use* it. The per-metric
  lower-is-better / higher-is-better direction logic is the same
  function. Per-route is a different grain, not a different
  algorithm.
* Per-route baselines are tracked separately from per-capability batch
  baselines. A route (``planner``) and a capability
  (``planner_tool_calling``) are intentionally different — a route
  can call multiple capabilities.
"""
from __future__ import annotations

import json
import logging
import math
import statistics
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from shopstack.eval.recorder import (
    OUTCOME_BLOCKED,
    OUTCOME_EMPTY,
    OUTCOME_EXCEPTION,
    OUTCOME_PARSE_ERROR,
    OUTCOME_SUCCESS,
    OUTCOME_TIMEOUT,
    ModelCallRecord,
)
from shopstack.eval.storage import SqliteSink

logger = logging.getLogger(__name__)


# Repo-root path. Sits next to bench_baseline.json.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_ROUTE_BASELINE_PATH = _REPO_ROOT / "shopstack" / "eval" / "route_baseline.json"


# Failure outcomes — used to compute the "success" side of success_rate.
FAILURE_OUTCOMES = {
    OUTCOME_EMPTY,
    OUTCOME_PARSE_ERROR,
    OUTCOME_TIMEOUT,
    OUTCOME_EXCEPTION,
    OUTCOME_BLOCKED,
}


# ── Aggregation ───────────────────────────────────────────────────────


@dataclass
class RouteStats:
    """Aggregated stats for one (domain_route, capability) pair."""

    domain_route: str
    capability: str
    n_calls: int = 0
    n_success: int = 0
    n_failed: int = 0
    n_eval_passed: int = 0
    success_rate: float = 1.0
    eval_pass_rate: float = 1.0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    mean_latency_ms: float = 0.0
    total_cost_usd: float = 0.0
    mean_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    latest_at: str = ""
    window_start: str = ""
    window_end: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Linear-interpolated percentile. ``pct`` in [0, 100]."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    k = (len(sorted_values) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_values[int(k)])
    d0 = float(sorted_values[int(f)]) * (c - k)
    d1 = float(sorted_values[int(c)]) * (k - f)
    return d0 + d1


def _row_to_record(row: dict[str, Any]) -> ModelCallRecord:
    """Project a SQLite row back into a ModelCallRecord (for aggregation)."""
    try:
        eval_results = json.loads(row.get("eval_check_results") or "[]")
    except (TypeError, ValueError):
        eval_results = []
    from shopstack.eval.recorder import CheckResult
    checks = [
        CheckResult(
            check=c.get("check", ""),
            passed=bool(c.get("passed", False)),
            score=float(c.get("score", 0.0)),
            notes=c.get("notes", ""),
        )
        for c in eval_results
        if isinstance(c, dict)
    ]
    return ModelCallRecord(
        record_id=row.get("record_id", ""),
        trace_id=row.get("trace_id", ""),
        user_id=row.get("user_id", ""),
        household_id=row.get("household_id", ""),
        started_at=row.get("started_at", ""),
        domain_route=row.get("domain_route", ""),
        code_route=row.get("code_route", ""),
        capability=row.get("capability", ""),
        capability_expected_shape=row.get("capability_shape", ""),
        model=row.get("model", ""),
        backend=row.get("backend", ""),
        provider_name=row.get("provider_name", ""),
        prompt=row.get("prompt", ""),
        output=row.get("output", ""),
        prompt_length=int(row.get("prompt_length") or 0),
        output_length=int(row.get("output_length") or 0),
        latency_ms=float(row.get("latency_ms") or 0.0),
        input_tokens=int(row.get("input_tokens") or 0),
        output_tokens=int(row.get("output_tokens") or 0),
        cost_usd=float(row.get("cost_usd") or 0.0),
        outcome=row.get("outcome", OUTCOME_SUCCESS),
        error=row.get("error", ""),
        eval_passed=bool(row.get("eval_passed")),
        eval_score=float(row.get("eval_score") or 0.0),
        eval_check_results=checks,
    )


def aggregate_records(
    records: Iterable[ModelCallRecord],
) -> dict[tuple[str, str], RouteStats]:
    """Group records by (domain_route, capability) and compute stats."""
    buckets: dict[tuple[str, str], list[ModelCallRecord]] = {}
    for r in records:
        key = (r.domain_route or "unknown", r.capability or "unknown")
        buckets.setdefault(key, []).append(r)

    out: dict[tuple[str, str], RouteStats] = {}
    for key, items in buckets.items():
        latencies = sorted(float(r.latency_ms) for r in items if r.latency_ms > 0)
        n = len(items)
        n_success = sum(1 for r in items if r.outcome == OUTCOME_SUCCESS)
        n_failed = n - n_success
        n_eval_passed = sum(1 for r in items if r.eval_passed)
        total_cost = sum(float(r.cost_usd) for r in items)
        total_in_tok = sum(int(r.input_tokens) for r in items)
        total_out_tok = sum(int(r.output_tokens) for r in items)
        latest = max((r.started_at for r in items if r.started_at), default="")
        window_start = min(
            (r.started_at for r in items if r.started_at), default="",
        )
        stats = RouteStats(
            domain_route=key[0],
            capability=key[1],
            n_calls=n,
            n_success=n_success,
            n_failed=n_failed,
            n_eval_passed=n_eval_passed,
            success_rate=round(n_success / n, 4) if n else 1.0,
            eval_pass_rate=round(n_eval_passed / n, 4) if n else 1.0,
            p50_latency_ms=round(_percentile(latencies, 50), 2),
            p95_latency_ms=round(_percentile(latencies, 95), 2),
            mean_latency_ms=round(
                (sum(latencies) / len(latencies)) if latencies else 0.0, 2
            ),
            total_cost_usd=round(total_cost, 6),
            mean_cost_usd=round(total_cost / n, 6) if n else 0.0,
            total_input_tokens=total_in_tok,
            total_output_tokens=total_out_tok,
            latest_at=latest,
            window_start=window_start,
            window_end=latest,
        )
        out[key] = stats
    return out


def aggregate_by_route(
    sink: SqliteSink,
    since_iso: str | None = None,
    limit: int = 1000,
) -> list[RouteStats]:
    """Aggregate the latest ``limit`` records (or since ``since_iso``) by route."""
    rows = sink.query(since_iso=since_iso, limit=limit)
    records = [_row_to_record(r) for r in rows]
    grouped = aggregate_records(records)
    # Sort: most recent activity first, then by n_calls desc
    return sorted(
        grouped.values(),
        key=lambda s: (s.latest_at, s.n_calls),
        reverse=True,
    )


# ── Regression detection ─────────────────────────────────────────────


@dataclass
class RouteRegression:
    """Regression verdict for one (domain_route, capability) pair."""

    domain_route: str
    capability: str
    sample_size: int
    measured: dict[str, float]
    baseline: dict[str, float]
    tolerance: dict[str, float]
    regressions: list[str] = field(default_factory=list)
    passed: bool = True
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Default tolerances — overridable per-route in the baseline.
DEFAULT_TOLERANCE = {
    "success_rate": 0.10,   # success rate can drop 10%
    "p95_latency_ms": 0.25, # p95 latency can rise 25%
    "mean_cost_usd": 0.50,  # mean cost can rise 50%
}


def _is_lower_better(metric: str) -> bool:
    return metric in ("p95_latency_ms", "mean_latency_ms", "mean_cost_usd", "p50_latency_ms")


def _check_one(
    metric: str,
    measured: float,
    baseline: float,
    tolerance: float,
) -> tuple[bool, str]:
    """Return (is_regression, description)."""
    if baseline <= 0:
        return False, f"{metric}: no baseline"
    if _is_lower_better(metric):
        threshold = baseline * (1.0 + tolerance)
        if measured > threshold:
            return True, (
                f"{metric}={measured:.4f} > baseline×(1+{tolerance})={threshold:.4f}"
            )
        return False, f"{metric}={measured:.4f} ≤ {threshold:.4f} OK"
    # higher is better
    threshold = baseline * max(0.0, 1.0 - tolerance)
    if measured < threshold:
        return True, (
            f"{metric}={measured:.4f} < baseline×(1-{tolerance})={threshold:.4f}"
        )
    return False, f"{metric}={measured:.4f} ≥ {threshold:.4f} OK"


def load_route_baseline(
    path: Path | str | None = None,
) -> dict[str, dict[str, Any]]:
    """Load the per-route baseline file. Returns
    ``{domain_route: {metric: value, ...}, ...}`` or ``{}`` if missing."""
    target = Path(path) if path is not None else DEFAULT_ROUTE_BASELINE_PATH
    if not target.exists():
        return {}
    with open(target, encoding="utf-8") as f:
        return json.load(f)


def save_route_baseline(
    baseline: dict[str, dict[str, Any]],
    path: Path | str | None = None,
) -> None:
    target = Path(path) if path is not None else DEFAULT_ROUTE_BASELINE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, ensure_ascii=False)
        f.write("\n")


def route_regression_report(
    stats: RouteStats,
    baseline: dict[str, Any],
    tolerance: dict[str, float] | None = None,
) -> RouteRegression:
    """Compare a single RouteStats against a baseline dict.

    The baseline dict can carry per-route tolerances. Missing metrics
    in either side are skipped silently.
    """
    tol = dict(DEFAULT_TOLERANCE)
    if tolerance:
        tol.update(tolerance)
    measured = {
        "success_rate": stats.success_rate,
        "p95_latency_ms": stats.p95_latency_ms,
        "mean_cost_usd": stats.mean_cost_usd,
    }
    regressions: list[str] = []
    for metric, value in measured.items():
        if metric not in baseline:
            continue
        is_reg, desc = _check_one(
            metric, value, float(baseline[metric]), float(tol.get(metric, 0.0)),
        )
        if is_reg:
            regressions.append(desc)
    passed = not regressions
    summary = (
        f"[{'PASS' if passed else 'REGRESSION'}] "
        f"{stats.domain_route}/{stats.capability} "
        f"n={stats.n_calls} "
        f"success={stats.success_rate:.4f} "
        f"p95={stats.p95_latency_ms:.0f}ms "
        f"cost=${stats.mean_cost_usd:.4f}"
    )
    if regressions:
        summary += " | " + " ; ".join(regressions)
    return RouteRegression(
        domain_route=stats.domain_route,
        capability=stats.capability,
        sample_size=stats.n_calls,
        measured=measured,
        baseline={k: float(baseline[k]) for k in measured if k in baseline},
        tolerance=tol,
        regressions=regressions,
        passed=passed,
        summary=summary,
    )


def route_regression_for_all(
    stats_list: Iterable[RouteStats],
    baseline: dict[str, dict[str, Any]] | None = None,
) -> list[RouteRegression]:
    """Run regression for every RouteStats using a single baseline file."""
    bl = baseline if baseline is not None else load_route_baseline()
    out: list[RouteRegression] = []
    for stats in stats_list:
        key = stats.domain_route
        per_route = bl.get(key, {})
        out.append(route_regression_report(stats, per_route))
    return out


__all__ = [
    "DEFAULT_ROUTE_BASELINE_PATH",
    "DEFAULT_TOLERANCE",
    "FAILURE_OUTCOMES",
    "RouteStats",
    "RouteRegression",
    "aggregate_by_route",
    "aggregate_records",
    "load_route_baseline",
    "route_regression_for_all",
    "route_regression_report",
    "save_route_baseline",
]
