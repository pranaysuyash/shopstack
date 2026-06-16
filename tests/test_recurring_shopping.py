"""Tests for the recurring shopping plan (Pass 19).

**Why this exists (motto_v3 §0.14 product reality):**

Every household has a shopping rhythm. ShopStack detects
it via ``detect_purchase_cadence``. The data exists; the
product gap is that the user never sees it. Pass 19 closes
this gap with a recurring shopping plan service + renderer +
CLI subcommand + HTTP endpoint.

These tests guard the service contract: the plan is a list
of ``DecisionResult`` (action=buy, with reasons/evidence),
the cadence filter is correct, the plan is ordered by
imminence, and the service handles edge cases (no rhythm,
single-purchase items, long intervals, etc.).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pytest

from shopstack.schemas.models import (
    DecisionResult,
    PurchaseEvent,
)
from shopstack.services.recurring_shopping import (
    DEFAULT_WINDOW_DAYS,
    MAX_INTERVAL_DAYS,
    MIN_INTERVAL_DAYS,
    MIN_PURCHASE_COUNT,
    build_recurring_shopping_plan,
    summarize_plan,
)


# ── Fake DB for testing (no real SQLite needed) ────────────────────


class _FakeDB:
    """Minimal DB stand-in for testing the recurring plan service.

    Only implements the methods ``build_recurring_shopping_plan``
    actually calls: ``get_purchase_events`` and the cadence
    detection (which uses internal SQL via the real service).
    """

    def __init__(self, purchases: list[PurchaseEvent]):
        self._purchases = purchases
        # The real ``detect_purchase_cadence`` uses
        # ``db.get_purchase_events(limit=200, user_id=...)`` and
        # accesses ``.timestamp``, ``.canonical_name``, etc.

    def get_purchase_events(self, *, limit: int = 200, user_id: str = "") -> list[PurchaseEvent]:
        return [p for p in self._purchases if (user_id == "" or getattr(p, "user_id", user_id) == user_id)][:limit]


def _make_purchase(
    canonical_name: str,
    *,
    days_ago: int,
    quantity: float = 1.0,
    unit: str = "unit",
    total_price: float = 50.0,
    today: date | None = None,
) -> PurchaseEvent:
    today = today or date(2026, 6, 15)
    return PurchaseEvent(
        canonical_name=canonical_name,
        quantity=quantity,
        unit=unit,
        total_price=total_price,
        timestamp=datetime.combine(today - timedelta(days=days_ago), datetime.min.time()),
    )


# ── Test edge cases ───────────────────────────────────────────────


class TestBuildRecurringShoppingPlanEmpty:
    def test_empty_db_returns_empty_plan(self):
        db = _FakeDB([])
        plan = build_recurring_shopping_plan(db, user_id="", window_days=3)
        assert plan == []

    def test_single_purchase_returns_empty_plan(self):
        """An item with only 1 purchase has no rhythm (need >= 2)."""
        db = _FakeDB([_make_purchase("milk", days_ago=2)])
        plan = build_recurring_shopping_plan(db, user_id="", window_days=3)
        assert plan == []


class TestBuildRecurringShoppingPlanFilters:
    def test_long_interval_excluded(self):
        """Items with avg_interval > MAX_INTERVAL_DAYS are excluded."""
        today = date(2026, 6, 15)
        # 2 purchases, 90 days apart → avg interval 90 days
        db = _FakeDB([
            _make_purchase("specialty_oil", days_ago=180, today=today),
            _make_purchase("specialty_oil", days_ago=90, today=today),
        ])
        plan = build_recurring_shopping_plan(db, user_id="", window_days=3, today=today)
        assert plan == []

    def test_short_interval_included(self):
        """Items with avg_interval in [MIN, MAX] are included."""
        today = date(2026, 6, 15)
        # 2 purchases, 3 days apart → avg interval 3 days (in range)
        db = _FakeDB([
            _make_purchase("milk", days_ago=6, today=today),
            _make_purchase("milk", days_ago=3, today=today),
        ])
        plan = build_recurring_shopping_plan(db, user_id="", window_days=3, today=today)
        assert len(plan) == 1
        assert plan[0].canonical_name == "milk"

    def test_item_outside_window_excluded(self):
        """Items whose next_expected is BEYOND the window are excluded."""
        today = date(2026, 6, 15)
        # 2 purchases, 14 days apart → avg interval 14 days.
        # Last bought 2 days ago → next expected in 12 days.
        # Window is 3 days → 12 > 3 → excluded.
        db = _FakeDB([
            _make_purchase("rice", days_ago=16, today=today),
            _make_purchase("rice", days_ago=2, today=today),
        ])
        plan = build_recurring_shopping_plan(db, user_id="", window_days=3, today=today)
        assert plan == []

    def test_item_inside_window_included(self):
        today = date(2026, 6, 15)
        # 2 purchases, 3 days apart → avg interval 3 days.
        # Last bought 2 days ago → next expected in 1 day.
        # Window is 3 days → 1 <= 3 → included.
        db = _FakeDB([
            _make_purchase("milk", days_ago=5, today=today),
            _make_purchase("milk", days_ago=2, today=today),
        ])
        plan = build_recurring_shopping_plan(db, user_id="", window_days=3, today=today)
        assert len(plan) == 1
        assert plan[0].canonical_name == "milk"


class TestBuildRecurringShoppingPlanOutput:
    def test_output_is_decision_results(self):
        """Each plan item is a ``DecisionResult`` with action=buy."""
        today = date(2026, 6, 15)
        db = _FakeDB([
            _make_purchase("milk", days_ago=5, today=today),
            _make_purchase("milk", days_ago=2, today=today),
        ])
        plan = build_recurring_shopping_plan(db, user_id="", window_days=3, today=today)
        for d in plan:
            assert isinstance(d, DecisionResult)
            assert d.action == "buy"

    def test_plan_includes_reasons_and_evidence(self):
        """Each plan item has structured reasons + evidence (for the Why? toggle)."""
        today = date(2026, 6, 15)
        db = _FakeDB([
            _make_purchase("milk", days_ago=5, today=today, quantity=1.5, unit="L"),
            _make_purchase("milk", days_ago=2, today=today, quantity=1.5, unit="L"),
        ])
        plan = build_recurring_shopping_plan(db, user_id="", window_days=3, today=today)
        assert len(plan) == 1
        d = plan[0]
        assert d.reasons, "plan items must have reasons (for explainability)"
        assert d.evidence, "plan items must have evidence (for explainability)"
        # The reasons should mention the rhythm.
        assert any("every" in r for r in d.reasons)
        assert any("due" in r for r in d.reasons)
        # The evidence should mention the cadence source.
        assert any(e.source == "purchase_cadence" for e in d.evidence)

    def test_plan_is_ordered_by_priority(self):
        """The plan is sorted by priority (most-imminent first)."""
        today = date(2026, 6, 15)
        # milk: due today (priority 10)
        # bread: due tomorrow (priority 8)
        db = _FakeDB([
            _make_purchase("milk", days_ago=2, today=today),
            _make_purchase("milk", days_ago=5, today=today),
            _make_purchase("bread", days_ago=1, today=today),
            _make_purchase("bread", days_ago=3, today=today),
        ])
        plan = build_recurring_shopping_plan(db, user_id="", window_days=3, today=today)
        # Both should be in the plan.
        assert len(plan) == 2
        # Ordered by priority (most-imminent first).
        assert plan[0].priority >= plan[1].priority
        # The first one should be the more imminent (higher priority).
        names = [d.canonical_name for d in plan]
        # Due-today items have priority=10; due-tomorrow priority=8.
        # milk is due today (priority 10), bread is due tomorrow (priority 8).
        # The plan should put milk first.
        assert names[0] == "milk"

    def test_confidence_based_on_purchase_count(self):
        """Confidence increases with purchase count (3+ → medium, 5+ → high)."""
        today = date(2026, 6, 15)
        # Item with 2 purchases (just at MIN) → confidence 0.55
        db_2 = _FakeDB([
            _make_purchase("milk", days_ago=5, today=today),
            _make_purchase("milk", days_ago=2, today=today),
        ])
        plan = build_recurring_shopping_plan(db_2, user_id="", window_days=3, today=today)
        assert plan[0].confidence == pytest.approx(0.55, abs=0.01)

        # Item with 4 purchases → confidence 0.7
        db_4 = _FakeDB([
            _make_purchase("milk", days_ago=12, today=today),
            _make_purchase("milk", days_ago=9, today=today),
            _make_purchase("milk", days_ago=6, today=today),
            _make_purchase("milk", days_ago=3, today=today),
        ])
        plan = build_recurring_shopping_plan(db_4, user_id="", window_days=3, today=today)
        assert plan[0].confidence == pytest.approx(0.7, abs=0.01)

        # Item with 5+ purchases → confidence 0.85
        db_5 = _FakeDB([
            _make_purchase("milk", days_ago=12, today=today),
            _make_purchase("milk", days_ago=9, today=today),
            _make_purchase("milk", days_ago=6, today=today),
            _make_purchase("milk", days_ago=3, today=today),
            _make_purchase("milk", days_ago=0, today=today),
        ])
        plan = build_recurring_shopping_plan(db_5, user_id="", window_days=3, today=today)
        assert plan[0].confidence == pytest.approx(0.85, abs=0.01)

    def test_due_today_reason_says_due_today(self):
        """An item due today has the reason 'is due today'."""
        today = date(2026, 6, 15)
        # 2 purchases, 3 days apart, last bought 3 days ago → next expected today
        db = _FakeDB([
            _make_purchase("milk", days_ago=6, today=today),
            _make_purchase("milk", days_ago=3, today=today),
        ])
        plan = build_recurring_shopping_plan(db, user_id="", window_days=3, today=today)
        assert len(plan) == 1
        assert any("today" in r for r in plan[0].reasons)

    def test_overdue_item_has_negative_days(self):
        """An overdue item has a high priority and 'was due N days ago' reason."""
        today = date(2026, 6, 15)
        # 2 purchases, 3 days apart, last bought 5 days ago → next expected 2 days ago
        db = _FakeDB([
            _make_purchase("milk", days_ago=8, today=today),
            _make_purchase("milk", days_ago=5, today=today),
        ])
        plan = build_recurring_shopping_plan(db, user_id="", window_days=3, today=today)
        assert len(plan) == 1
        # Overdue items get priority 20.
        assert plan[0].priority == 20
        # The reason says "was due N days ago".
        assert any("was due" in r for r in plan[0].reasons)


class TestSummarizePlan:
    def test_empty_plan_summarizes_to_no_items(self):
        assert summarize_plan([]) == "No items due in your usual rhythm right now."

    def test_one_item_summarizes_to_one(self):
        from shopstack.schemas.models import DecisionResult
        d = DecisionResult(canonical_name="milk", display_name="Milk", action="buy", confidence=0.7)
        assert summarize_plan([d]) == "1 item due in your usual rhythm."

    def test_three_items_summarizes_to_count(self):
        from shopstack.schemas.models import DecisionResult
        ds = [
            DecisionResult(canonical_name="a", display_name="A", action="buy"),
            DecisionResult(canonical_name="b", display_name="B", action="buy"),
            DecisionResult(canonical_name="c", display_name="C", action="buy"),
        ]
        assert summarize_plan(ds) == "3 items due in your usual rhythm."


class TestConstants:
    def test_default_window_is_3_days(self):
        assert DEFAULT_WINDOW_DAYS == 3

    def test_min_interval_is_at_least_1_day(self):
        assert MIN_INTERVAL_DAYS >= 1.0

    def test_max_interval_is_at_most_60_days(self):
        assert MAX_INTERVAL_DAYS <= 60.0

    def test_min_purchase_count_is_at_least_2(self):
        assert MIN_PURCHASE_COUNT >= 2
