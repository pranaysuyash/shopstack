"""Tests for the Today-intelligence golden eval harness + the
default Indian-household golden set.

motto_v3 §0.5: this is the Tier 2/3 evidence layer for the
Today intelligence AI feature. Without it, every change to
the ranking algorithm is unproven and the team relies on
spot-checks + anecdotes.

Architecture:
  * ``shopstack/services/today_intelligence_golden.py`` is the
    framework: the GoldenCase / CaseResult / GoldenEvalReport
    dataclasses and the scoring function. Reusable from
    tests, benches, and a future CLI / CI gate.
  * This file runs the default curated cases (5 realistic
    Indian household scenarios) and asserts every one passes.
    A regression here is a real product regression.
  * The framework itself is also tested: the run_golden_cases
    function returns a report, accuracy is well-defined,
    and individual checks (must_be_quiet, expected_order,
    expected_actions_by_name) work in isolation.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from shopstack.services.today_intelligence_golden import (
    DEFAULT_GOLDEN_CASES,
    GoldenCase,
    GoldenEvalReport,
    append_trend_row,
    run_golden_cases,
)
from shopstack.services.today_intelligence import build_today_intelligence


# ── Default golden set ─────────────────────────────────────────────


class TestDefaultGoldenCases:
    """The default curated scenarios must all pass. A failure here
    is a real product regression — the ranking algorithm changed
    in a way that violates the team's documented expectations.

    These tests are deliberately NOT marked ``xfail`` or
    ``skip`` because every case is a hard contract. If a
    case is too strict, fix the case (with a dated addendum
    and a comment explaining the changed expectation), don't
    silence the test.
    """

    def test_all_default_cases_pass(self):
        report = run_golden_cases(DEFAULT_GOLDEN_CASES)
        assert report.passed == report.total, (
            f"Default golden set regression: {report.failed_names} failed.\n"
            f"Per-case details:\n" +
            "\n".join(
                f"  - {c.name}: {c.failures}\n    produced_top={c.produced_top_names}"
                for c in report.cases if not c.passed
            )
        )

    def test_default_set_has_at_least_four_cases(self):
        """Guard against the default set silently shrinking to 0.
        motto_v3 §0.5: an eval with no cases is the same as
        no eval.
        """
        assert len(DEFAULT_GOLDEN_CASES) >= 4, (
            "DEFAULT_GOLDEN_CASES must have at least 4 curated cases; "
            "add more before shipping, not after"
        )

    def test_default_cases_have_unique_names(self):
        """Duplicate names would silently collapse the trend store.
        """
        names = [c.name for c in DEFAULT_GOLDEN_CASES]
        assert len(names) == len(set(names)), (
            f"Duplicate case names in DEFAULT_GOLDEN_CASES: {names}"
        )

    def test_default_cases_have_nonempty_descriptions(self):
        for c in DEFAULT_GOLDEN_CASES:
            assert c.description.strip(), (
                f"Case {c.name!r} has an empty description"
            )


# ── Framework contract ────────────────────────────────────────────


def _empty_state():
    return SimpleNamespace(
        use_soon_items=[],
        restock_predictions=[],
        price_drops=[],
    )


def _make_overpriced_only_case():
    return GoldenCase(
        name="framework_overpriced_only",
        description="Single overpriced signal must appear, not be quiet.",
        state=_empty_state(),
        community_medians={"salt": 20.0},
        expected_canonical_names=("salt",),
        expected_actions_by_name={"salt": "overpriced"},
    )


def _make_must_be_quiet_case():
    return GoldenCase(
        name="framework_empty_quiet",
        description="Empty state must report is_quiet=True.",
        state=_empty_state(),
        must_be_quiet=True,
    )


class TestFrameworkContracts:
    def test_must_be_quiet_fails_on_nonempty_state(self):
        """If we declare must_be_quiet=True but the state produces
        actions, the case must fail with a clear message."""
        case = GoldenCase(
            name="bad_quiet",
            description="Wrongly declares quiet on a state with use-soon items.",
            state=SimpleNamespace(
                use_soon_items=[{"canonical_name": "milk"}],
                restock_predictions=[],
                price_drops=[],
            ),
            must_be_quiet=True,
        )
        result = run_golden_cases([case])
        assert result.passed == 0
        assert "Expected is_quiet" in result.cases[0].failures[0]

    def test_expected_order_uses_strict_prefix_match(self):
        """When the expected_order is shorter than top-N, only
        the first N positions must match."""
        case = GoldenCase(
            name="order_prefix",
            description="expected_order has 2 entries, top has 3; only first 2 must match.",
            state=SimpleNamespace(
                # All restock items at days=5 → urgency=80 each, so
                # the alphabetical tiebreaker is the only sort key.
                use_soon_items=[],
                restock_predictions=[
                    {"canonical_name": "milk", "days_until_restock": 5},
                    {"canonical_name": "bread", "days_until_restock": 5},
                    {"canonical_name": "apple", "days_until_restock": 5},
                ],
                price_drops=[],
            ),
            expected_order=("apple", "bread"),
        )
        result = run_golden_cases([case])
        assert result.passed == 1, result.cases[0].failures

    def test_per_name_action_kind_check(self):
        case = _make_overpriced_only_case()
        result = run_golden_cases([case])
        assert result.passed == 1

    def test_per_name_action_kind_mismatch(self):
        case = GoldenCase(
            name="wrong_action",
            description="Asserts the wrong action kind for a real action.",
            state=SimpleNamespace(
                use_soon_items=[{"canonical_name": "milk"}],
                restock_predictions=[],
                price_drops=[],
            ),
            expected_canonical_names=("milk",),
            expected_actions_by_name={"milk": "price_drop"},  # WRONG: it's use_soon
        )
        result = run_golden_cases([case])
        assert result.passed == 0
        assert any("milk" in f and "price_drop" in f for f in result.cases[0].failures)

    def test_quiet_case_passes_when_empty(self):
        case = _make_must_be_quiet_case()
        result = run_golden_cases([case])
        assert result.passed == 1

    def test_top_count_assertion(self):
        case = GoldenCase(
            name="top_count_check",
            description="Asserts that exactly 1 action is in top.",
            state=SimpleNamespace(
                use_soon_items=[{"canonical_name": "milk"}],
                restock_predictions=[],
                price_drops=[],
            ),
            expected_top_count=1,
        )
        result = run_golden_cases([case])
        assert result.passed == 1

    def test_top_count_mismatch(self):
        case = GoldenCase(
            name="top_count_mismatch",
            description="Expects 5 top items but only 1 exists.",
            state=SimpleNamespace(
                use_soon_items=[{"canonical_name": "milk"}],
                restock_predictions=[],
                price_drops=[],
            ),
            expected_top_count=5,
        )
        result = run_golden_cases([case])
        assert result.passed == 0
        assert any("top_count" in f for f in result.cases[0].failures)


# ── Report shape ───────────────────────────────────────────────────


class TestReportShape:
    def test_accuracy_is_zero_on_empty_report(self):
        r = GoldenEvalReport()
        assert r.accuracy == 1.0  # vacuous
        assert r.passed == 0
        assert r.total == 0
        assert r.failed_names == []

    def test_accuracy_is_fraction_passing(self):
        r = GoldenEvalReport()
        r.cases.append(_CaseStub(passed=True))
        r.cases.append(_CaseStub(passed=False))
        r.cases.append(_CaseStub(passed=True))
        assert r.accuracy == pytest.approx(2 / 3)

    def test_to_dict_includes_failed_names(self):
        r = GoldenEvalReport()
        r.cases.append(_CaseStub(passed=True, name="passes"))
        r.cases.append(_CaseStub(passed=False, name="fails"))
        d = r.to_dict()
        assert d["failed_names"] == ["fails"]
        assert d["passed"] == 1
        assert d["total"] == 2

    def test_append_trend_row_creates_valid_jsonl(self, tmp_path):
        r = GoldenEvalReport()
        r.cases.append(_CaseStub(passed=True, name="x"))
        trend = tmp_path / "trend.jsonl"
        append_trend_row(trend, r)
        line = trend.read_text(encoding="utf-8").strip()
        import json as _json
        parsed = _json.loads(line)
        assert parsed["passed"] == 1
        assert parsed["cases"][0]["name"] == "x"
        # Subsequent appends add new lines (don't overwrite).
        append_trend_row(trend, r)
        assert len(trend.read_text(encoding="utf-8").strip().splitlines()) == 2


# A small dataclass-free stand-in for CaseResult in framework
# shape tests — keeps this test file independent of the case
# dataclass import path.
def _CaseStub(passed: bool, name: str = "stub") -> Any:
    from dataclasses import dataclass, field
    from typing import List, Dict

    @dataclass
    class Stub:
        passed: bool
        name: str
        description: str = ""
        failures: List[str] = field(default_factory=list)
        produced_top_names: List[str] = field(default_factory=list)
        produced_secondary_names: List[str] = field(default_factory=list)
        produced_by_source: Dict[str, int] = field(default_factory=dict)

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

    return Stub(passed=passed, name=name)
