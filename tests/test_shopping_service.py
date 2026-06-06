from __future__ import annotations

from shopstack.services.shopping import (
    ShoppingPlan,
    classify_shopping_items,
    enrich_items_with_swiggy,
    normalize_item_name,
)


def test_normalize_item_aliases():
    assert normalize_item_name("tamatar") == "tomato"
    assert normalize_item_name("Pyaaz") == "onion"


def test_classify_low_stock_item_as_buy(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="milk",
        display_name="Milk",
        quantity=0.2,
        unit="L",
    )
    items = [{"canonical_name": "milk", "requested_quantity": 1, "unit": "L"}]

    plan = classify_shopping_items(items, tool_registry)

    assert isinstance(plan, ShoppingPlan)
    assert len(plan.must_buy) == 1
    assert plan.must_buy[0]["canonical_name"] == "Milk"
    assert items[0]["priority"] == "must_buy"


def test_classify_well_stocked_item_as_skip(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="rice",
        display_name="Rice",
        quantity=5,
        unit="kg",
    )
    items = [{"canonical_name": "rice", "requested_quantity": 1, "unit": "kg"}]

    plan = classify_shopping_items(items, tool_registry)

    assert len(plan.skipped) == 1
    assert plan.skipped[0]["priority"] == "avoid_buying"
    assert items[0]["smart_decision"] == "skip"


def test_enrich_items_with_swiggy_known_item():
    items = [{"canonical_name": "tomato"}]

    result = enrich_items_with_swiggy(items)

    assert "swiggy_price" in result[0]
    assert "swiggy_available" in result[0]


def test_enrich_items_with_swiggy_unknown_item():
    items = [{"canonical_name": "unobtainium"}]

    result = enrich_items_with_swiggy(items)

    assert result[0]["swiggy_price"] is None
    assert result[0]["swiggy_available"] is None
