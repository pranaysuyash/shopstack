"""Golden eval harness for the Today intelligence service.

motto_v3 §0.5 evidence tiers: an AI feature without a golden eval
is Tier 0/1 (we think it works, no measurable proof). This module
moves the Today intelligence service to Tier 2/3 by providing a
reusable scoring harness over a curated fixture set.

Why a separate module (motto_v3 §11 engineering standards):
The golden eval is **not** a test of one specific scenario; it's
a small domain language for declaring "given this state, the
intelligence service should surface these actions in this order
with this urgency". That domain is reused by:

  * Unit tests (parametrize over a list of golden cases)
  * Benchmarks (run a larger sample to track drift over time)
  * CI gates (fail the build if golden accuracy drops below X%)
  * One-off diagnostics (run a single case to debug a regression)

The harness produces both a per-case binary pass/fail and an
aggregate accuracy score so the eval can be either gate-style
("must pass every case") or trend-style ("track the score over
weeks"). The architecture follows the same pattern as the
existing ``js_validate`` tool: a small report dataclass, a CLI
smoke test, and a pytest-friendly test layer on top.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from shopstack.services.today_intelligence import (
    TodayIntelligence,
    build_today_intelligence,
)


# ── Golden case model ──────────────────────────────────────────────


@dataclass(frozen=True)
class GoldenCase:
    """A single curated scenario for the Today intelligence service.

    Attributes:
        name: Short identifier used in error messages and JSON
            reports. Convention: ``"<scenario>_<expected_outcome>"``
            (e.g. ``"use_soon_wins_over_restock"``).
        description: One-sentence human-readable explanation of
            what this case is testing. Used in docs and reports.
        state: A stand-in for ``DashboardState`` (anything with
            ``use_soon_items``, ``restock_predictions``,
            ``price_drops`` attributes/dicts). May be a real
            DashboardState, a dataclass, or a SimpleNamespace.
        community_medians: Optional dict of ``{name: price}`` for
            the overpriced-signal path.
        trip_advice: Optional trip-advisor object with
            ``recommendation``, ``label``, ``reason`` attrs.
        expected_canonical_names: The canonical_name list the
            top-actions list must contain (order-independent for
            set membership; the ``expected_order`` list controls
            ranked ordering when ordering matters).
        expected_order: Optional ordered list of canonical_names.
            When supplied, the harness asserts strict order.
        expected_actions_by_name: Optional dict of
            ``{canonical_name: action_kind}`` for type checks.
        expected_top_count: Optional assertion on ``len(top)``.
        must_be_quiet: True for cases where the state is empty /
            non-urgent and the intel should be quiet.
    """

    name: str
    description: str
    state: Any
    community_medians: dict[str, float] | None = None
    trip_advice: Any | None = None
    expected_canonical_names: tuple[str, ...] = ()
    expected_order: tuple[str, ...] | None = None
    expected_actions_by_name: dict[str, str] = field(default_factory=dict)
    expected_top_count: int | None = None
    must_be_quiet: bool = False


# ── Per-case result ────────────────────────────────────────────────


@dataclass
class CaseResult:
    """The result of running a single golden case."""

    name: str
    description: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    produced_top_names: list[str] = field(default_factory=list)
    produced_secondary_names: list[str] = field(default_factory=list)
    produced_by_source: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "passed": self.passed,
            "failures": self.failures,
            "produced_top_names": self.produced_top_names,
            "produced_secondary_names": self.produced_secondary_names,
            "produced_by_source": self.produced_by_source,
        }


# ── Aggregate report ──────────────────────────────────────────────


@dataclass
class GoldenEvalReport:
    """Aggregate results across a set of cases.

    The same report is used by pytest (introspect via ``.to_dict``),
    by the bench layer (append to a trends file), and by the
    command-line entry point (render as human-readable text).
    """

    cases: list[CaseResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)

    @property
    def total(self) -> int:
        return len(self.cases)

    @property
    def accuracy(self) -> float:
        if not self.cases:
            return 1.0
        return self.passed / self.total

    @property
    def failed_names(self) -> list[str]:
        return [c.name for c in self.cases if not c.passed]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total": self.total,
            "accuracy": self.accuracy,
            "failed_names": self.failed_names,
            "cases": [c.to_dict() for c in self.cases],
        }


# ── Scoring ───────────────────────────────────────────────────────


def _run_one(case: GoldenCase) -> CaseResult:
    """Score a single case against the live service."""
    intel: TodayIntelligence = build_today_intelligence(
        case.state,
        community_medians=case.community_medians,
        trip_advice=case.trip_advice,
    )
    result = CaseResult(
        name=case.name,
        description=case.description,
        passed=True,
        produced_top_names=[a.canonical_name for a in intel.top_actions],
        produced_secondary_names=[a.canonical_name for a in intel.secondary],
        produced_by_source=dict(intel.by_source),
    )

    # 1. Quiet-state check
    if case.must_be_quiet and not intel.is_quiet:
        result.passed = False
        result.failures.append(
            f"Expected is_quiet=True but produced top={result.produced_top_names}"
        )

    # 2. Top-count check
    if case.expected_top_count is not None:
        actual = len(intel.top_actions)
        if actual != case.expected_top_count:
            result.passed = False
            result.failures.append(
                f"Expected top_count={case.expected_top_count} but got {actual} "
                f"(top={result.produced_top_names})"
            )

    # 3. Required-canonical-names set check (order-independent)
    if case.expected_canonical_names:
        expected = set(case.expected_canonical_names)
        actual = set(result.produced_top_names)
        missing = expected - actual
        if missing:
            result.passed = False
            result.failures.append(
                f"Missing expected canonical_names in top: "
                f"{sorted(missing)} (got {result.produced_top_names})"
            )

    # 4. Strict-order check (only meaningful when len(top) > 0)
    if case.expected_order is not None and intel.top_actions:
        actual = [a.canonical_name for a in intel.top_actions]
        expected = list(case.expected_order)
        # The expected list may be a prefix or a full ordering; we
        # require that the top-N actual matches the first-N
        # expected whenever they have the same length. A shorter
        # expected_order means "the first len(expected_order) must
        # match in this exact order".
        n = min(len(expected), len(actual))
        if actual[:n] != expected[:n]:
            result.passed = False
            result.failures.append(
                f"Order mismatch: expected[:{n}]={expected[:n]} but "
                f"got[:{n}]={actual[:n]}"
            )

    # 5. Per-name action-kind check
    if case.expected_actions_by_name:
        for cname, want_kind in case.expected_actions_by_name.items():
            actual_kind = next(
                (
                    a.action
                    for a in intel.top_actions + intel.secondary
                    if a.canonical_name == cname
                ),
                None,
            )
            if actual_kind != want_kind:
                result.passed = False
                result.failures.append(
                    f"{cname}: expected action={want_kind!r} but got {actual_kind!r}"
                )

    return result


def run_golden_cases(cases: list[GoldenCase]) -> GoldenEvalReport:
    """Run a list of golden cases and return an aggregate report.

    Use this from a test (parametrize over the cases and assert
    report.passed == report.total), from a benchmark, or from the
    CLI entry point.
    """
    report = GoldenEvalReport()
    for case in cases:
        report.cases.append(_run_one(case))
    return report


# ── JSON trend-store writer ────────────────────────────────────────


def append_trend_row(trend_path: Path, report: GoldenEvalReport) -> None:
    """Append a single JSON line to a trend file for drift tracking.

    Each line is one self-contained evaluation run. Future
    evals append to the same file so accuracy-over-time is
    visible. The file uses newline-delimited JSON for trivial
    append / no schema migration.
    """
    trend_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        **report.to_dict(),
    }
    with trend_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


# ── Convenience: canonical Indian-household golden cases ──────────
#
# The default scenarios are realistic Indian household situations
# that the service should rank correctly. New cases get appended
# here so the default eval keeps growing.
#
# Why default fixtures here (motto_v3 §0.3):
# The harness lives in the test suite — but a curated default set
# that ships with the project is the difference between an eval
# that runs and an eval that catches regressions. Without
# defaults, the eval would be a beautiful framework with zero
# coverage, which is the exact problem it's meant to solve.


def _state(**kwargs: Any) -> Any:
    """Build a SimpleNamespace standing in for DashboardState."""
    from types import SimpleNamespace

    base = {
        "use_soon_items": [],
        "restock_predictions": [],
        "price_drops": [],
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


DEFAULT_GOLDEN_CASES: list[GoldenCase] = [
    GoldenCase(
        name="empty_state_is_quiet",
        description="No inputs at all: the intel must report a quiet kitchen.",
        state=_state(),
        must_be_quiet=True,
    ),
    GoldenCase(
        name="use_soon_wins_over_restock",
        description="A use-soon tomato (urgency 95) must outrank a restock-due milk (80).",
        state=_state(
            use_soon_items=[{"canonical_name": "tomato", "days_until_expiry": 1}],
            restock_predictions=[{"canonical_name": "milk", "days_until_restock": 2}],
        ),
        expected_canonical_names=("tomato", "milk"),
        expected_order=("tomato", "milk"),
        expected_actions_by_name={"tomato": "use_soon", "milk": "restock_due"},
        expected_top_count=2,
    ),
    GoldenCase(
        name="ranking_by_urgency_then_alpha",
        description="Two restock items at the same urgency (80): sorted alphabetically by display name.",
        state=_state(
            restock_predictions=[
                {"canonical_name": "milk", "days_until_restock": 5},
                {"canonical_name": "bread", "days_until_restock": 5},
            ],
        ),
        expected_order=("bread", "milk"),
        expected_actions_by_name={"bread": "restock_due", "milk": "restock_due"},
        expected_top_count=2,
    ),
    GoldenCase(
        name="same_item_deduped_across_lists",
        description=(
            "If milk is both use-soon (urgency 95) and restock-due "
            "(urgency 90), the same canonical_name appears in BOTH "
            "the use_soon and restock_due slots because the dedup "
            "key is (canonical_name, action) — different actions "
            "are not collapsed. use_soon ranks above restock_due by "
            "urgency so the top two are: use_soon:milk then "
            "restock_due:milk. When the kitchen has 3+ other "
            "actions the restock:milk entry would be pushed to "
            "secondary; this case covers the small-list case."
        ),
        state=_state(
            use_soon_items=[{"canonical_name": "milk", "days_until_expiry": 1}],
            restock_predictions=[{"canonical_name": "milk", "days_until_restock": 2}],
        ),
        expected_canonical_names=("milk",),  # both top slots are 'milk'
        expected_actions_by_name={"milk": "use_soon"},
        expected_top_count=2,  # one use_soon, one restock_due, both fit
        expected_order=("milk", "milk"),  # use_soon (95) > restock_due (90)
    ),
    GoldenCase(
        name="same_item_deduped_only_by_name_plus_action",
        description=(
            "When the same (name, action) appears twice (e.g. two "
            "use-soon tomatoes from different sources), the dedup "
            "key collapses them to a single entry."
        ),
        state=_state(
            use_soon_items=[
                {"canonical_name": "milk", "days_until_expiry": 1},
                {"canonical_name": "milk", "days_until_expiry": 2},
            ],
        ),
        expected_canonical_names=("milk",),
        expected_actions_by_name={"milk": "use_soon"},
        expected_top_count=1,
    ),
    GoldenCase(
        name="overpriced_signal_appears_with_community_medians",
        description="Community medians are surfaced as a low-urgency 'overpriced' action.",
        state=_state(),
        community_medians={"milk": 50.0, "bread": 30.0},
        expected_canonical_names=("bread", "milk"),
        expected_actions_by_name={"bread": "overpriced", "milk": "overpriced"},
    ),
    GoldenCase(
        name="quiet_state_with_only_overpriced_signals",
        description="An overpriced-only state still produces actions, so is_quiet must be False (the kitchen is not quiet — there are overpaying hints).",
        state=_state(),
        community_medians={"salt": 20.0},
        expected_canonical_names=("salt",),
        expected_actions_by_name={"salt": "overpriced"},
        must_be_quiet=False,
    ),
]


__all__ = [
    "DEFAULT_GOLDEN_CASES",
    "CaseResult",
    "GoldenCase",
    "GoldenEvalReport",
    "append_trend_row",
    "run_golden_cases",
]
