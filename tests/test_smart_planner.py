"""Tests for shopstack.services.smart_planner (Phase 9)."""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from shopstack.services.smart_planner import (
    BUY_NOW,
    WAIT,
    SmartBasket,
    SmartLine,
    build_smart_basket,
    render_smart_basket_html,
)


@dataclass
class FakeBasketComparison:
    """Minimal BasketComparison for tests."""
    lines: list = field(default_factory=list)


@dataclass
class FakeLine:
    canonical_name: str
    cheapest_total: float
    best_source: str = ""


# ── build_smart_basket basics ──────────────────────────────────


def test_build_empty_basket():
    basket = build_smart_basket([])
    assert basket.lines == []
    assert basket.total_buy_now == 0.0
    assert basket.n_buy_now == 0


def test_build_filters_empty_canonical_names():
    basket = build_smart_basket([
        {"canonical_name": "", "quantity": 1, "unit": "kg"},
    ])
    assert basket.lines == []


def test_build_no_price_no_community_defaults_to_buy_now():
    basket = build_smart_basket([
        {"canonical_name": "tomato", "quantity": 1, "unit": "kg"},
    ])
    assert basket.lines[0].verdict == BUY_NOW


def test_build_uses_basket_comparison_cheapest_price():
    comparison = FakeBasketComparison(lines=[
        FakeLine("tomato", cheapest_total=80.0, best_source="DMart"),
    ])
    basket = build_smart_basket(
        [{"canonical_name": "tomato", "quantity": 1, "unit": "kg"}],
        basket_comparison=comparison,
    )
    line = basket.lines[0]
    assert line.cheapest_price == 80.0
    assert line.recommended_store == "DMart"


def test_build_recommends_wait_when_15pct_above_median():
    comparison = FakeBasketComparison(lines=[
        FakeLine("tomato", cheapest_total=100.0, best_source="DMart"),
    ])
    basket = build_smart_basket(
        [{"canonical_name": "tomato", "quantity": 1, "unit": "kg"}],
        basket_comparison=comparison,
        community_medians={"tomato": 80.0},  # median is ₹80, current is ₹100 (+25%)
    )
    assert basket.lines[0].verdict == WAIT
    assert basket.lines[0].pct_above_median == pytest.approx(25.0)
    assert "above the community median" in basket.lines[0].reason.lower()


def test_build_recommends_wait_with_threshold_at_15pct():
    """Threshold is 15%; 14% above median should still be BUY_NOW."""
    comparison = FakeBasketComparison(lines=[
        FakeLine("x", cheapest_total=100.0, best_source="DMart"),
    ])
    basket = build_smart_basket(
        [{"canonical_name": "x", "quantity": 1, "unit": "kg"}],
        basket_comparison=comparison,
        community_medians={"x": 88.0},  # +13.6%
    )
    assert basket.lines[0].verdict == BUY_NOW


def test_build_use_soon_critical_overrides_wait():
    """If item is use-soon critical (≤2 days), buy now even if overpriced."""
    comparison = FakeBasketComparison(lines=[
        FakeLine("milk", cheapest_total=100.0, best_source="DMart"),
    ])
    basket = build_smart_basket(
        [{"canonical_name": "milk", "quantity": 1, "unit": "L"}],
        basket_comparison=comparison,
        community_medians={"milk": 50.0},  # +100%
        use_soon_items=[{"canonical_name": "milk", "days_until_expiry": 1}],
    )
    assert basket.lines[0].verdict == BUY_NOW
    assert "spoil" in basket.lines[0].reason.lower() or "soon" in basket.lines[0].reason.lower()


def test_build_totals_buy_now_and_wait():
    comparison = FakeBasketComparison(lines=[
        FakeLine("tomato", cheapest_total=100.0, best_source="DMart"),
        FakeLine("rice", cheapest_total=50.0, best_source="Reliance"),
    ])
    basket = build_smart_basket(
        [
            {"canonical_name": "tomato", "quantity": 2, "unit": "kg"},
            {"canonical_name": "rice", "quantity": 1, "unit": "kg"},
        ],
        basket_comparison=comparison,
        community_medians={"tomato": 50.0, "rice": 30.0},  # both overpriced
    )
    # Both should be WAIT (both > 15% above median)
    # Actually rice: 50 vs 30 = +66%, tomato: 100 vs 50 = +100% → both WAIT
    # Wait is only counted if community_median is present
    assert basket.n_wait == 2
    assert basket.total_savings_if_wait == pytest.approx(
        (100 - 50) * 2 + (50 - 30) * 1  # (price - median) * qty
    )


def test_build_by_source_counts_stores():
    comparison = FakeBasketComparison(lines=[
        FakeLine("tomato", cheapest_total=80.0, best_source="DMart"),
        FakeLine("rice", cheapest_total=50.0, best_source="DMart"),
        FakeLine("milk", cheapest_total=30.0, best_source="Reliance"),
    ])
    basket = build_smart_basket(
        [
            {"canonical_name": "tomato", "quantity": 1, "unit": "kg"},
            {"canonical_name": "rice", "quantity": 1, "unit": "kg"},
            {"canonical_name": "milk", "quantity": 1, "unit": "L"},
        ],
        basket_comparison=comparison,
    )
    assert basket.by_source == {"DMart": 2, "Reliance": 1}


def test_build_case_insensitive_canonical_name_match():
    comparison = FakeBasketComparison(lines=[
        FakeLine("Tomato", cheapest_total=80.0, best_source="DMart"),
    ])
    basket = build_smart_basket(
        [{"canonical_name": "tomato", "quantity": 1, "unit": "kg"}],
        basket_comparison=comparison,
    )
    assert basket.lines[0].cheapest_price == 80.0


# ── render_smart_basket_html ────────────────────────────────────


def test_render_empty_basket():
    basket = SmartBasket(generated_at="")
    html = render_smart_basket_html(basket)
    assert "sp-block" in html
    assert "Add items" in html


def test_render_with_buy_now_lines():
    comparison = FakeBasketComparison(lines=[
        FakeLine("tomato", cheapest_total=80.0, best_source="DMart"),
    ])
    basket = build_smart_basket(
        [{"canonical_name": "tomato", "quantity": 1, "unit": "kg"}],
        basket_comparison=comparison,
    )
    html = render_smart_basket_html(basket)
    assert "Tomato" in html
    assert "DMart" in html
    assert "₹80" in html
    assert "sp-block" in html


def test_render_with_wait_lines():
    comparison = FakeBasketComparison(lines=[
        FakeLine("rice", cheapest_total=100.0, best_source="DMart"),
    ])
    basket = build_smart_basket(
        [{"canonical_name": "rice", "quantity": 1, "unit": "kg"}],
        basket_comparison=comparison,
        community_medians={"rice": 50.0},
    )
    html = render_smart_basket_html(basket)
    # Should show community median with +% delta
    assert "👥" in html
    assert "+100%" in html or "100%" in html
    # Should show savings
    assert "save" in html.lower()


def test_render_with_sources_chip():
    comparison = FakeBasketComparison(lines=[
        FakeLine("tomato", cheapest_total=80.0, best_source="DMart"),
    ])
    basket = build_smart_basket(
        [{"canonical_name": "tomato", "quantity": 1, "unit": "kg"}],
        basket_comparison=comparison,
    )
    html = render_smart_basket_html(basket)
    assert "DMart" in html
    assert "sp-chip" in html


def test_render_escapes_xss():
    comparison = FakeBasketComparison(lines=[
        FakeLine("<script>alert(1)</script>", cheapest_total=80.0, best_source="DMart"),
    ])
    basket = build_smart_basket(
        [{"canonical_name": "<script>alert(1)</script>", "quantity": 1, "unit": "kg"}],
        basket_comparison=comparison,
    )
    html = render_smart_basket_html(basket)
    # The display name is title-cased; check case-insensitively
    assert "<script>alert" not in html.lower()
    assert "&lt;script&gt;" in html.lower()


def test_render_color_coding_by_verdict():
    comparison = FakeBasketComparison(lines=[
        FakeLine("tomato", cheapest_total=80.0, best_source="DMart"),
        FakeLine("rice", cheapest_total=100.0, best_source="DMart"),
    ])
    basket = build_smart_basket(
        [
            {"canonical_name": "tomato", "quantity": 1, "unit": "kg"},
            {"canonical_name": "rice", "quantity": 1, "unit": "kg"},
        ],
        basket_comparison=comparison,
        community_medians={"rice": 50.0},  # only rice is WAIT
    )
    html = render_smart_basket_html(basket)
    # Green (buy now) + amber (wait)
    assert "176B49" in html  # green
    assert "A76012" in html  # amber
