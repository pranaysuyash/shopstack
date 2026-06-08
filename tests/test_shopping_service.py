"""Tests for services/shopping.py — shopping classification, enrichment, and completion.

Simple service functions use conftest fixtures (``db``, ``tool_registry``).
Completion functions that depend on ``shopstack.app_context`` are imported
inside the test method body (not at module level) so the import captures the
correct ``db`` reference after the ``app`` fixture has bootstrapped it.
"""

from __future__ import annotations

import json
import os

import pytest
from shopstack.schemas.models import InventoryLot


# ── Session-level env setter (same pattern as test_views.py) ──────────────

@pytest.fixture(scope="session", autouse=True)
def _set_test_env():
    os.environ["SHOPSTACK_DB_PATH"] = ":memory:"
    yield


@pytest.fixture
def app():
    """Import app module fresh for each test, giving a clean :memory: DB."""
    import importlib
    import sys

    _preserved = {"shopstack.schemas", "shopstack.schemas.models"}
    for mod in list(sys.modules.keys()):
        if mod in ("app",) or (mod.startswith("shopstack") and mod not in _preserved):
            del sys.modules[mod]

    import app as _app
    return _app


# ══════════════════════════════════════════════════════════════════════════
# ShoppingPlan dataclass
# ══════════════════════════════════════════════════════════════════════════

class TestShoppingPlan:
    def test_empty_plan(self):
        from shopstack.services.shopping import ShoppingPlan
        plan = ShoppingPlan()
        assert plan.all_items == []

    def test_all_items_aggregates(self):
        from shopstack.services.shopping import ShoppingPlan
        plan = ShoppingPlan(
            must_buy=[{"canonical_name": "Milk"}],
            optional=[{"canonical_name": "Eggs"}],
            skipped=[{"canonical_name": "Rice"}],
            use_soon=[{"canonical_name": "Tomato"}],
        )
        names = {i["canonical_name"] for i in plan.all_items}
        assert names == {"Milk", "Eggs", "Rice", "Tomato"}

    def test_all_items_preserves_order(self):
        from shopstack.services.shopping import ShoppingPlan
        plan = ShoppingPlan(
            must_buy=[{"canonical_name": "A"}],
            optional=[{"canonical_name": "B"}],
            skipped=[{"canonical_name": "C"}],
            use_soon=[{"canonical_name": "D"}],
        )
        assert [i["canonical_name"] for i in plan.all_items] == ["A", "B", "C", "D"]


# ══════════════════════════════════════════════════════════════════════════
# normalize_item_name — edge cases beyond basic aliases
# ══════════════════════════════════════════════════════════════════════════

class TestNormalizeItemName:
    def test_punctuation_removed(self):
        from shopstack.services.shopping import normalize_item_name
        assert normalize_item_name("milk!!!") == "milk"

    def test_leading_trailing_spaces(self):
        from shopstack.services.shopping import normalize_item_name
        assert normalize_item_name("  Tomato  ") == "tomato"

    def test_special_characters_stripped(self):
        from shopstack.services.shopping import normalize_item_name
        # "coriander (dhania)" → "coriander  dhania" (parentheses become spaces)
        result = normalize_item_name("coriander (dhania)")
        assert "coriander" in result
        assert "dhania" in result

    def test_multiple_spaces_left_as_is(self):
        from shopstack.services.shopping import normalize_item_name
        # normalize_item_name does NOT collapse internal spaces
        result = normalize_item_name("wheat    flour")
        assert "wheat" in result
        assert "flour" in result
        assert "    " in result

    def test_unknown_returns_cleaned(self):
        from shopstack.services.shopping import normalize_item_name
        assert normalize_item_name("Saffron!") == "saffron"

    def test_empty_string(self):
        from shopstack.services.shopping import normalize_item_name
        assert normalize_item_name("") == ""

    def test_only_special_chars(self):
        from shopstack.services.shopping import normalize_item_name
        assert normalize_item_name("!!!") == ""


# ══════════════════════════════════════════════════════════════════════════
# classify_shopping_items — comprehensive decision paths
# ══════════════════════════════════════════════════════════════════════════

class TestClassifyShoppingItems:
    def test_empty_items(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items, ShoppingPlan
        plan = classify_shopping_items([], tool_registry)
        assert isinstance(plan, ShoppingPlan)
        assert plan.all_items == []

    def test_must_buy_when_not_in_inventory(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        items = [{"canonical_name": "butter", "requested_quantity": 1, "unit": "unit"}]
        plan = classify_shopping_items(items, tool_registry)
        assert len(plan.must_buy) == 1
        assert plan.must_buy[0]["canonical_name"] == "Butter"
        assert plan.must_buy[0]["priority"] == "must_buy"
        assert plan.must_buy[0]["smart_decision"] == "buy"

    def test_optional_when_just_enough_in_inventory(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        tool_registry.add_inventory_item(
            canonical_name="eggs", display_name="Eggs", quantity=12, unit="pieces",
        )
        items = [{"canonical_name": "eggs", "requested_quantity": 12, "unit": "pieces"}]
        plan = classify_shopping_items(items, tool_registry)
        assert len(plan.optional) == 1
        assert plan.optional[0]["priority"] == "optional"
        assert plan.optional[0]["smart_decision"] == "optional"

    def test_low_stock_becomes_must_buy(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        tool_registry.add_inventory_item(
            canonical_name="milk", display_name="Milk", quantity=0.2, unit="L",
        )
        items = [{"canonical_name": "milk", "requested_quantity": 2, "unit": "L"}]
        plan = classify_shopping_items(items, tool_registry)
        assert len(plan.must_buy) == 1
        assert plan.must_buy[0]["priority"] == "must_buy"

    def test_well_stocked_becomes_skip(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        tool_registry.add_inventory_item(
            canonical_name="rice", display_name="Rice", quantity=5, unit="kg",
        )
        items = [{"canonical_name": "rice", "requested_quantity": 1, "unit": "kg"}]
        plan = classify_shopping_items(items, tool_registry)
        assert len(plan.skipped) == 1
        assert plan.skipped[0]["priority"] == "avoid_buying"

    def test_dedup_repeated_items(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        items = [
            {"canonical_name": "milk", "requested_quantity": 1, "unit": "L"},
            {"canonical_name": "milk", "requested_quantity": 1, "unit": "L"},
        ]
        plan = classify_shopping_items(items, tool_registry)
        assert len(plan.all_items) == 1

    def test_dedup_with_alias(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        items = [
            {"canonical_name": "milk", "requested_quantity": 1, "unit": "L"},
            {"canonical_name": "Milk", "requested_quantity": 1, "unit": "L"},
        ]
        plan = classify_shopping_items(items, tool_registry)
        assert len(plan.all_items) == 1

    def test_mutates_item_dicts(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        items = [{"canonical_name": "milk", "requested_quantity": 1, "unit": "L"}]
        classify_shopping_items(items, tool_registry)
        assert "reason" in items[0]
        assert "priority" in items[0]
        assert "smart_decision" in items[0]

    def test_handles_none_quantity(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        items = [{"canonical_name": "milk", "requested_quantity": None, "unit": "L"}]
        plan = classify_shopping_items(items, tool_registry)
        assert len(plan.must_buy) == 1

    def test_handles_invalid_quantity(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        items = [{"canonical_name": "milk", "requested_quantity": "abc", "unit": "L"}]
        plan = classify_shopping_items(items, tool_registry)
        assert len(plan.must_buy) == 1

    def test_handles_none_unit(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        items = [{"canonical_name": "milk", "requested_quantity": 1, "unit": None}]
        plan = classify_shopping_items(items, tool_registry)
        assert len(plan.must_buy) == 1

    def test_confidence_must_buy_not_at_home(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        items = [{"canonical_name": "butter", "requested_quantity": 1, "unit": "unit"}]
        plan = classify_shopping_items(items, tool_registry)
        assert plan.must_buy[0]["confidence"] == 0.52

    def test_confidence_must_buy_with_stock(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        tool_registry.add_inventory_item(
            canonical_name="milk", display_name="Milk", quantity=0.5, unit="L",
        )
        items = [{"canonical_name": "milk", "requested_quantity": 2, "unit": "L"}]
        plan = classify_shopping_items(items, tool_registry)
        assert plan.must_buy[0]["confidence"] == 0.62

    def test_confidence_optional(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        tool_registry.add_inventory_item(
            canonical_name="eggs", display_name="Eggs", quantity=12, unit="pieces",
        )
        items = [{"canonical_name": "eggs", "requested_quantity": 12, "unit": "pieces"}]
        plan = classify_shopping_items(items, tool_registry)
        assert plan.optional[0]["confidence"] == 0.72

    def test_confidence_skip(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        tool_registry.add_inventory_item(
            canonical_name="rice", display_name="Rice", quantity=5, unit="kg",
        )
        items = [{"canonical_name": "rice", "requested_quantity": 1, "unit": "kg"}]
        plan = classify_shopping_items(items, tool_registry)
        assert plan.skipped[0]["confidence"] > 0.80

    def test_normalizes_names_via_alias(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        items = [{"canonical_name": "tamatar", "requested_quantity": 1, "unit": "kg"}]
        plan = classify_shopping_items(items, tool_registry)
        assert plan.all_items[0]["canonical_name"] == "Tomato"

    def test_use_soon_reclassification(self, db, tool_registry):
        from datetime import date
        from shopstack.services.shopping import classify_shopping_items
        # Seed a lot expiring today with qty < requested*2 so it's NOT skipped
        from shopstack.schemas.models import InventoryLot
        db.add_inventory_lot(InventoryLot(
            canonical_name="milk", display_name="Milk",
            quantity=1.5, unit="L",
            label_expiry_date=date.today(),
        ))
        items = [{"canonical_name": "milk", "requested_quantity": 1, "unit": "L"}]
        plan = classify_shopping_items(items, tool_registry)
        assert len(plan.use_soon) == 1
        assert plan.use_soon[0]["canonical_name"] == "Milk"
        assert plan.use_soon[0]["smart_decision"] == "use_soon"
        assert plan.use_soon[0]["priority"] == "must_buy"

    def test_enriches_with_swiggy_data(self, db, tool_registry):
        from shopstack.services.shopping import classify_shopping_items
        items = [{"canonical_name": "tomato", "requested_quantity": 1, "unit": "kg"}]
        plan = classify_shopping_items(items, tool_registry)
        for item in plan.all_items:
            assert "swiggy_price" in item
            assert "swiggy_available" in item


# ══════════════════════════════════════════════════════════════════════════
# enrich_items_with_swiggy — error handling
# ══════════════════════════════════════════════════════════════════════════

class TestEnrichItemsWithSwiggy:
    def test_empty_items(self):
        from shopstack.services.shopping import enrich_items_with_swiggy
        result = enrich_items_with_swiggy([])
        assert result == []

    def test_known_item_has_swiggy_fields(self):
        from shopstack.services.shopping import enrich_items_with_swiggy
        items = [{"canonical_name": "tomato"}]
        result = enrich_items_with_swiggy(items)
        assert result[0]["swiggy_price"] is not None
        assert result[0]["swiggy_available"] is not None
        assert "swiggy_size" in result[0]

    def test_unknown_item_returns_none(self):
        from shopstack.services.shopping import enrich_items_with_swiggy
        items = [{"canonical_name": "unobtainium"}]
        result = enrich_items_with_swiggy(items)
        assert result[0]["swiggy_price"] is None
        assert result[0]["swiggy_available"] is None
        assert result[0]["swiggy_size"] == ""

    def test_multiple_items(self):
        from shopstack.services.shopping import enrich_items_with_swiggy
        items = [{"canonical_name": "tomato"}, {"canonical_name": "unobtainium"}]
        result = enrich_items_with_swiggy(items)
        assert result[0]["swiggy_price"] is not None
        assert result[1]["swiggy_price"] is None


# ══════════════════════════════════════════════════════════════════════════
# complete_shopping_list_service — all paths
# ══════════════════════════════════════════════════════════════════════════

class TestCompleteShoppingListService:
    def test_empty_list_id(self, app):
        from shopstack.services.shopping import complete_shopping_list_service
        result = complete_shopping_list_service("", app.tools, app.db)
        assert not result.success
        assert "No active shopping list" in result.message

    def test_list_not_found(self, app):
        from shopstack.services.shopping import complete_shopping_list_service
        result = complete_shopping_list_service("nonexistent_id", app.tools, app.db)
        assert not result.success
        assert "not found" in result.message.lower()

    def test_empty_items_list(self, app):
        from shopstack.services.shopping import complete_shopping_list_service
        app.tools.create_or_update_shopping_list(items=[], goal="Empty trip")
        sl = app.db.get_active_shopping_list()
        result = complete_shopping_list_service(sl.list_id, app.tools, app.db)
        assert result.success
        assert result.count == 0

    def test_must_buy_items_added_to_inventory(self, app):
        from shopstack.services.shopping import complete_shopping_list_service
        app.tools.create_or_update_shopping_list(
            items=[{"canonical_name": "milk", "requested_quantity": 2, "unit": "L"}],
            goal="Weekly shop",
        )
        sl = app.db.get_active_shopping_list()
        result = complete_shopping_list_service(sl.list_id, app.tools, app.db)
        assert result.success
        assert result.count == 1
        assert result.items_added[0].canonical_name == "milk"
        items = app.db.get_inventory()
        assert any(i.canonical_name == "milk" for i in items)

    def test_optional_item_quantity_halved(self, app):
        from shopstack.services.shopping import complete_shopping_list_service
        app.tools.create_or_update_shopping_list(
            items=[{"canonical_name": "chips", "requested_quantity": 2, "unit": "packet", "priority": "optional"}],
            goal="Snacks",
        )
        sl = app.db.get_active_shopping_list()
        complete_shopping_list_service(sl.list_id, app.tools, app.db)
        items = app.db.get_inventory()
        chips = [i for i in items if i.canonical_name == "chips"]
        assert len(chips) == 1
        assert chips[0].quantity == 1.0  # 2.0 * 0.5 = 1.0

    def test_optional_quantity_clamped_to_0_5(self, app):
        from shopstack.services.shopping import complete_shopping_list_service
        app.tools.create_or_update_shopping_list(
            items=[{"canonical_name": "gum", "requested_quantity": 0.3, "unit": "pack", "priority": "optional"}],
            goal="Treats",
        )
        sl = app.db.get_active_shopping_list()
        complete_shopping_list_service(sl.list_id, app.tools, app.db)
        items = app.db.get_inventory()
        gum = [i for i in items if i.canonical_name == "gum"]
        assert len(gum) == 1
        assert gum[0].quantity == 0.5  # 0.3 * 0.5 = 0.15, clamped to min 0.5

    def test_avoid_buying_skipped(self, app):
        from shopstack.services.shopping import complete_shopping_list_service
        app.tools.create_or_update_shopping_list(
            items=[
                {"canonical_name": "milk", "requested_quantity": 2, "unit": "L", "priority": "must_buy"},
                {"canonical_name": "rice", "requested_quantity": 5, "unit": "kg", "priority": "avoid_buying"},
            ],
            goal="Weekly shop",
        )
        sl = app.db.get_active_shopping_list()
        result = complete_shopping_list_service(sl.list_id, app.tools, app.db)
        assert result.count == 1
        assert result.items_skipped == 1

    def test_list_marked_complete(self, app):
        from shopstack.services.shopping import complete_shopping_list_service
        app.tools.create_or_update_shopping_list(
            items=[{"canonical_name": "milk", "requested_quantity": 1, "unit": "L"}],
            goal="Test",
        )
        sl = app.db.get_active_shopping_list()
        assert sl is not None
        complete_shopping_list_service(sl.list_id, app.tools, app.db)
        assert app.db.get_active_shopping_list() is None

    def test_trace_created(self, app):
        from shopstack.services.shopping import complete_shopping_list_service
        app.tools.create_or_update_shopping_list(
            items=[{"canonical_name": "milk", "requested_quantity": 1, "unit": "L"}],
            goal="Test trace",
        )
        sl = app.db.get_active_shopping_list()
        complete_shopping_list_service(sl.list_id, app.tools, app.db)
        traces = app.db.get_traces()
        assert any(t.user_goal == "complete_shopping_list" for t in traces)

    def test_escapes_html(self, app):
        from shopstack.services.shopping import complete_shopping_list_service
        app.tools.create_or_update_shopping_list(
            items=[{"canonical_name": "<script>alert('x')</script>", "requested_quantity": 1}],
            goal="XSS test",
        )
        sl = app.db.get_active_shopping_list()
        result = complete_shopping_list_service(sl.list_id, app.tools, app.db)
        html = result.to_html()
        assert "&lt;script&gt;" in html
        assert "<script>" not in html


# ══════════════════════════════════════════════════════════════════════════
# mark_items_purchased_service — all paths
# ══════════════════════════════════════════════════════════════════════════

class TestMarkItemsPurchasedService:
    def test_empty_input(self, app):
        from shopstack.services.shopping import mark_items_purchased_service
        result = mark_items_purchased_service("", app.tools, app.db)
        assert not result.success
        assert "No items selected" in result.message

    def test_empty_json_array(self, app):
        from shopstack.services.shopping import mark_items_purchased_service
        result = mark_items_purchased_service("[]", app.tools, app.db)
        assert not result.success
        assert "No items selected" in result.message

    def test_invalid_json(self, app):
        from shopstack.services.shopping import mark_items_purchased_service
        result = mark_items_purchased_service("{bad json}", app.tools, app.db)
        assert not result.success
        assert "Could not parse" in result.message

    def test_no_active_list(self, app):
        from shopstack.services.shopping import mark_items_purchased_service
        result = mark_items_purchased_service('["item1"]', app.tools, app.db)
        assert not result.success
        assert "No active shopping list" in result.message

    def test_marks_items_as_purchased(self, app):
        from shopstack.services.shopping import mark_items_purchased_service
        app.tools.create_or_update_shopping_list(
            items=[{"canonical_name": "milk", "requested_quantity": 2, "unit": "L"}],
            goal="Test",
        )
        sl = app.db.get_active_shopping_list()
        item_id = sl.items[0].list_item_id
        result = mark_items_purchased_service(json.dumps([item_id]), app.tools, app.db)
        assert result.success
        assert result.count == 1
        assert result.items_added[0].canonical_name == "milk"
        items = app.db.get_inventory()
        assert any(i.canonical_name == "milk" for i in items)

    def test_marks_selected_only(self, app):
        from shopstack.services.shopping import mark_items_purchased_service
        app.tools.create_or_update_shopping_list(
            items=[
                {"canonical_name": "milk", "requested_quantity": 2, "unit": "L"},
                {"canonical_name": "bread", "requested_quantity": 1, "unit": "loaf"},
            ],
            goal="Test",
        )
        sl = app.db.get_active_shopping_list()
        milk_id = sl.items[0].list_item_id
        result = mark_items_purchased_service(json.dumps([milk_id]), app.tools, app.db)
        assert result.count == 1
        items = app.db.get_inventory()
        names = [i.canonical_name for i in items]
        assert "milk" in names
        updated_sl = app.db.get_active_shopping_list()
        bread_item = [i for i in updated_sl.items if i.canonical_name == "bread"][0]
        assert bread_item.status != "bought"

    def test_unknown_item_ids_skipped(self, app):
        from shopstack.services.shopping import mark_items_purchased_service
        app.tools.create_or_update_shopping_list(
            items=[{"canonical_name": "milk", "requested_quantity": 1, "unit": "L"}],
            goal="Test",
        )
        result = mark_items_purchased_service('["nonexistent_id"]', app.tools, app.db)
        assert not result.success
        assert "No valid items found" in result.message

    def test_escapes_html(self, app):
        from shopstack.services.shopping import mark_items_purchased_service
        app.tools.create_or_update_shopping_list(
            items=[{"canonical_name": "<script>x</script>", "requested_quantity": 1}],
            goal="XSS test",
        )
        sl = app.db.get_active_shopping_list()
        item_id = sl.items[0].list_item_id
        result = mark_items_purchased_service(json.dumps([item_id]), app.tools, app.db)
        html = result.to_html()
        assert "&lt;script&gt;" in html
