"""Tests for shopstack.services.analytics (Phase 8 — analytics dashboard)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from shopstack.services.analytics import (
    HouseholdAnalytics,
    aggregate_analytics,
    render_analytics_html,
)


@dataclass
class FakeTrace:
    action_type: str
    created_at: datetime
    user_id: str = "hh-1"
    payload: dict | None = None


# ── aggregate_analytics basics ────────────────────────────────────


def test_aggregate_analytics_empty_input():
    a = aggregate_analytics([])
    assert a.purchase_count == 0
    assert a.spend_this_month == 0.0
    assert a.spend_this_year == 0.0
    assert a.waste_rate_pct == 0.0


def test_aggregate_analytics_counts_purchases():
    today = datetime(2026, 6, 13, 10, 0, 0)
    traces = [
        FakeTrace("add_purchase", today, payload={"total": 100}),
        FakeTrace("add_purchase", today, payload={"total": 50}),
    ]
    a = aggregate_analytics(traces, today=today)
    assert a.purchase_count == 2
    assert a.spend_this_month == 150.0
    assert a.spend_this_year == 150.0


def test_aggregate_analytics_separates_month_year():
    today = datetime(2026, 6, 13)
    # Use 2026-01-15 (in 2026, this year) for the year-trace so it's counted
    in_2026 = datetime(2026, 1, 15)
    traces = [
        FakeTrace("add_purchase", today, payload={"total": 200}),
        FakeTrace("add_purchase", in_2026, payload={"total": 100}),
    ]
    a = aggregate_analytics(traces, today=today)
    assert a.spend_this_year == 300.0
    assert a.spend_this_month == 200.0


def test_aggregate_analytics_excludes_previous_year():
    today = datetime(2026, 6, 13)
    last_year = datetime(2025, 12, 1)
    traces = [
        FakeTrace("add_purchase", today, payload={"total": 200}),
        FakeTrace("add_purchase", last_year, payload={"total": 100}),
    ]
    a = aggregate_analytics(traces, today=today)
    # 2025-12 is not in "this year" (2026)
    assert a.spend_this_year == 200.0
    assert a.spend_this_month == 200.0


def test_aggregate_analytics_groups_by_store():
    today = datetime(2026, 6, 13)
    traces = [
        FakeTrace("add_purchase", today, payload={"total": 100, "store": "DMart"}),
        FakeTrace("add_purchase", today, payload={"total": 200, "store": "Reliance"}),
    ]
    a = aggregate_analytics(traces, today=today)
    assert a.spend_by_store == {"Reliance": 200.0, "DMart": 100.0}


def test_aggregate_analytics_groups_by_category():
    today = datetime(2026, 6, 13)
    traces = [
        FakeTrace("add_purchase", today, payload={"total": 100, "category": "dairy"}),
        FakeTrace("add_purchase", today, payload={"total": 50, "category": "snacks"}),
    ]
    a = aggregate_analytics(traces, today=today)
    assert a.spend_by_category == {"dairy": 100.0, "snacks": 50.0}


def test_aggregate_analytics_top_items():
    today = datetime(2026, 6, 13)
    traces = [
        FakeTrace("add_purchase", today, payload={"total": 100, "canonical_name": "milk"}),
        FakeTrace("add_purchase", today, payload={"total": 200, "canonical_name": "bread"}),
        FakeTrace("add_purchase", today, payload={"total": 50, "canonical_name": "egg"}),
    ]
    a = aggregate_analytics(traces, today=today)
    assert a.top_items[0] == ("bread", 200.0)
    assert a.top_items[1] == ("milk", 100.0)


def test_aggregate_analytics_consume_count():
    today = datetime(2026, 6, 13)
    traces = [
        FakeTrace("consume_item", today),
        FakeTrace("consume", today),
        FakeTrace("add_purchase", today, payload={"total": 100}),
    ]
    a = aggregate_analytics(traces, today=today)
    assert a.consume_count == 2
    assert a.purchase_count == 1


def test_aggregate_analytics_use_soon_count():
    today = datetime(2026, 6, 13)
    traces = [
        FakeTrace("use_soon", today),
        FakeTrace("waste", today),
    ]
    a = aggregate_analytics(traces, today=today)
    assert a.use_soon_count == 2


def test_aggregate_analytics_waste_rate():
    today = datetime(2026, 6, 13)
    traces = [
        FakeTrace("consume", today),
        FakeTrace("consume", today),
        FakeTrace("use_soon", today),
    ]
    a = aggregate_analytics(traces, today=today)
    assert a.waste_rate_pct == 50.0  # 1 of 2 consumptions was use-soon


def test_aggregate_analytics_waste_rate_zero_consume():
    a = aggregate_analytics([])
    assert a.waste_rate_pct == 0.0


def test_aggregate_analytics_spend_trend_six_months():
    today = datetime(2026, 6, 13)
    traces = [
        FakeTrace("add_purchase", today, payload={"total": 100}),
    ]
    a = aggregate_analytics(traces, today=today)
    assert len(a.spend_trend) == 6
    # The most recent month (2026-06) has 100
    assert a.spend_trend[-1] == ("2026-06", 100.0)


def test_aggregate_analytics_top_merchants():
    today = datetime(2026, 6, 13)
    traces = [
        FakeTrace("add_purchase", today, payload={"total": 50, "store": "DMart"}),
        FakeTrace("add_purchase", today, payload={"total": 50, "store": "DMart"}),
        FakeTrace("add_purchase", today, payload={"total": 50, "store": "Reliance"}),
    ]
    a = aggregate_analytics(traces, today=today)
    assert a.top_merchants[0] == ("DMart", 2)


def test_aggregate_analytics_new_items_added():
    today = datetime(2026, 6, 13)
    traces = [
        FakeTrace("add_inventory_item", today),
        FakeTrace("add_inventory_item", today),
        FakeTrace("add_purchase", today, payload={"total": 50}),
    ]
    a = aggregate_analytics(traces, today=today)
    assert a.new_items_added == 2


def test_aggregate_analytics_handles_dict_traces():
    today = datetime(2026, 6, 13)
    traces = [
        {"action_type": "add_purchase", "created_at": today,
         "payload": {"total": 100, "store": "DMart"}},
    ]
    a = aggregate_analytics(traces, today=today)
    assert a.purchase_count == 1
    assert a.spend_this_month == 100.0


def test_aggregate_analytics_handles_string_timestamp():
    today = datetime(2026, 6, 13)
    traces = [
        {"action_type": "add_purchase", "created_at": "2026-06-13T10:00:00",
         "payload": {"total": 50}},
    ]
    a = aggregate_analytics(traces, today=today)
    assert a.spend_this_month == 50.0


def test_aggregate_analytics_respects_window():
    today = datetime(2026, 6, 13)
    old = today - timedelta(days=400)
    traces = [
        FakeTrace("add_purchase", today, payload={"total": 100}),
        FakeTrace("add_purchase", old, payload={"total": 200}),  # outside window
    ]
    a = aggregate_analytics(traces, window_days=180, today=today)
    # Only the in-window one counts
    assert a.purchase_count == 1
    assert a.spend_this_month == 100.0


# ── render_analytics_html ──────────────────────────────────────────


def test_render_analytics_html_empty():
    a = HouseholdAnalytics()
    html = render_analytics_html(a)
    assert "No purchase history" in html


def test_render_analytics_html_basic():
    a = HouseholdAnalytics(
        spend_this_month=500.0,
        spend_this_year=2500.0,
        purchase_count=12,
        new_items_added=5,
        spend_trend=[("2026-01", 100), ("2026-02", 200), ("2026-03", 300)],
        top_items=[("milk", 150.0), ("bread", 100.0)],
        top_merchants=[("DMart", 8)],
    )
    html = render_analytics_html(a)
    assert "ha-block" in html
    assert "₹500" in html
    assert "₹2,500" in html
    assert "12" in html
    assert "5" in html
    assert "Monthly trend" in html
    assert "Top items" in html
    assert "Top merchants" in html


def test_render_analytics_html_waste_rate_badge():
    a = HouseholdAnalytics(
        spend_this_month=100.0,
        purchase_count=2,
        consume_count=10,
        use_soon_count=3,
    )
    html = render_analytics_html(a)
    assert "Waste rate" in html
    # The renderer formats the rate with one decimal, so "30.0%"
    assert "30.0%" in html  # 3 / 10 = 30%


def test_render_analytics_html_escapes_xss():
    a = HouseholdAnalytics(
        spend_this_month=100.0,
        purchase_count=1,
        top_items=[("<script>alert(1)</script>", 50.0)],
    )
    html = render_analytics_html(a)
    # The canonical name is title-cased; check for the escaped form
    assert "&lt;script&gt;" in html.lower()
    # The raw <script> tag must never appear unescaped
    assert "<script>alert" not in html.lower()
