from __future__ import annotations

from shopstack.services.trip_context import (
    TripAdvice,
    _estimate_price_advantage,
    _has_urgent_items,
    format_trip_advice_html,
    get_trip_advice,
)


def test_trip_advice_defaults():
    advice = TripAdvice(worth_it=True, confidence="likely", reason="test")
    assert advice.weather is None
    assert advice.estimated_savings == 0.0
    assert advice.items_to_buy == []


def test_get_trip_advice_urgent_item(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="milk", display_name="Milk", quantity=0.1, unit="L",
    )
    advice = get_trip_advice(db, "DMart", ["milk"])
    assert advice.worth_it is True
    assert advice.confidence == "confident"


def test_get_trip_advice_no_items(db):
    advice = get_trip_advice(db, "DMart", [])
    assert isinstance(advice, TripAdvice)
    assert advice.worth_it is True


def test_has_urgent_items_true(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="bread", display_name="Bread", quantity=0.2, unit="unit",
    )
    assert _has_urgent_items(db, ["bread"]) is True


def test_has_urgent_items_false(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="rice", display_name="Rice", quantity=5.0, unit="kg",
    )
    assert _has_urgent_items(db, ["rice"]) is False


def test_estimate_price_advantage_no_history(db):
    assert _estimate_price_advantage(db, "DMart", ["milk"]) == 0.0


def test_format_trip_advice_html_go():
    advice = TripAdvice(
        worth_it=True, confidence="confident", reason="Good weather",
        items_to_buy=["milk", "bread"],
    )
    html = format_trip_advice_html(advice)
    assert "Go" in html
    assert "milk" in html


def test_format_trip_advice_html_wait():
    advice = TripAdvice(
        worth_it=False, confidence="confident", reason="Stormy weather",
    )
    html = format_trip_advice_html(advice)
    assert "Wait" in html


def test_format_trip_advice_html_with_savings():
    advice = TripAdvice(
        worth_it=True, confidence="likely", reason="Good prices",
        estimated_savings=150.0,
    )
    html = format_trip_advice_html(advice)
    assert "150" in html
