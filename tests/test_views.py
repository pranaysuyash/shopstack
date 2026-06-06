from __future__ import annotations

import os
from datetime import date

import pytest

from shopstack.schemas.models import InventoryLot, Trace


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


class TestTodayDashboard:
    def test_returns_five_strings(self, app):
        results = app.today_dashboard()
        assert len(results) == 5
        for r in results:
            assert isinstance(r, str)

    def test_shows_use_soon(self, app):
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="milk", display_name="Milk", quantity=0.5, unit="L")
        )
        results = app.today_dashboard()
        assert any("Milk" in r for r in results)

    def test_shows_low_stock(self, app):
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="bread", display_name="Bread", quantity=0.3, unit="loaf")
        )
        results = app.today_dashboard()
        assert any("Bread" in r for r in results)


class TestShoppingListView:
    def test_empty(self, app):
        html, table, list_id, goal = app.shopping_list_view()
        assert "No active shopping list" in html

    def test_create_and_view(self, app):
        result = app.shopping_list_create(
            "Weekly groceries", '[{"canonical_name":"milk","requested_quantity":2}]'
        )
        assert "Created list" in result
        html, table, list_id, goal = app.shopping_list_view()
        assert list_id
        assert goal == "Weekly groceries"

    def test_create_bare_list(self, app):
        result = app.shopping_list_create("Quick trip", "[]")
        assert "Created list" in result

    def test_create_list_invalid_json(self, app):
        result = app.shopping_list_create("Quick trip", "{bad json}")
        assert "Invalid JSON" in result

    def test_create_list_with_natural_text(self, app):
        app.db.add_inventory_lot(
            InventoryLot(
                canonical_name="milk",
                display_name="Milk",
                quantity=0.2,
                unit="L",
                storage_location_id="fridge",
            )
        )
        result = app.shopping_list_create("Breakfast run", "milk, bread, tomato")
        assert "Created list" in result
        cards, list_html, _table, list_id, goal, share = app._shopping_list_view_with_cards()
        assert list_id
        assert goal == "Breakfast run"
        assert "milk" in share.lower()

    def test_shopping_list_cards_refresh(self, app):
        app.db.add_inventory_lot(
            InventoryLot(
                canonical_name="bread",
                display_name="Bread",
                quantity=2.0,
                unit="loaf",
                storage_location_id="pantry",
            )
        )
        app.shopping_list_create("Pantry top-up", "bread")
        cards, list_html, _table, list_id, _goal, share = app._shopping_list_view_with_cards()
        assert "ShopStack list for today" in share
        assert list_id
        assert "Shopping List" in cards
        assert "Must Buy" in cards or "Skip" in cards


class TestModelBudgetView:
    def test_model_budget_view_renders(self, app):
        html = app.model_budget_view()
        assert "Selected Runtime Stack" in html
        assert "Candidate Models" in html
        assert "Active / Loaded" in html
        assert "Max Budget" in html

    def test_workflow_header_is_visible_markup(self, app):
        assert "Workflow Steps" in app._workflow_header(app.WORKFLOW_STEPS)


class TestAddPurchase:
    def test_adds_item(self, app):
        result = app.add_purchase_form("Paneer", 0.5, "kg", 120.0, "Local Store", "fridge",
                                       date.today().isoformat(), "Dairy")
        assert "Added" in result
        items = app.db.get_inventory()
        assert any(i.canonical_name == "paneer" for i in items)

    def test_negative_quantity(self, app):
        result = app.add_purchase_form("Salt", -1.0, "kg", 20.0, "Store", "fridge",
                                       date.today().isoformat(), "Spices")
        assert "Quantity must be 0 or more" in result

    def test_negative_price(self, app):
        result = app.add_purchase_form("Salt", 1.0, "kg", -20.0, "Store", "fridge",
                                       date.today().isoformat(), "Spices")
        assert "Price must be 0 or more" in result

    def test_with_price_records_observation(self, app):
        result = app.add_purchase_form("Butter", 0.2, "kg", 50.0, "Store A", "fridge",
                                       date.today().isoformat(), "Dairy")
        assert "Added" in result
        prices = app.db.conn.execute("SELECT * FROM price_observations").fetchall()
        assert len(prices) >= 1


class TestInventoryView:
    def test_empty(self, app):
        tbl = app.inventory_view()
        assert tbl == [["No data"]]

    def test_with_items(self, app):
        app.db.add_inventory_lot(InventoryLot(canonical_name="rice", display_name="Basmati Rice", quantity=2.0, unit="kg"))
        tbl = app.inventory_view()
        assert len(tbl) >= 2
        assert any("rice" in str(c).lower() for row in tbl for c in row)

    def test_search(self, app):
        app.db.add_inventory_lot(InventoryLot(canonical_name="rice", display_name="Basmati Rice", quantity=2.0, unit="kg"))
        app.db.add_inventory_lot(InventoryLot(canonical_name="dal", display_name="Toor Dal", quantity=1.0, unit="kg"))
        tbl = app.inventory_view(search="rice")
        assert len(tbl) == 2


class TestConsume:
    def test_consume_item(self, app):
        app.db.add_inventory_lot(InventoryLot(canonical_name="salt", display_name="Salt", quantity=1.0, unit="kg"))
        items = app.db.get_inventory()
        lot_id = items[0].lot_id
        result = app.consume_item(lot_id, 0.5)
        assert "Consumed" in result

    def test_consume_prefix_resolves(self, app):
        app.db.add_inventory_lot(InventoryLot(canonical_name="butter", display_name="Butter", quantity=2.0, unit="kg"))
        lot_id = app.db.get_inventory()[0].lot_id
        result = app.consume_item(lot_id[:6], 0.5)
        assert "Consumed" in result
        assert "1.5" in result

    def test_consume_unknown(self, app):
        result = app.consume_item("nonexistent", 1.0)
        assert "Error" in result

    def test_consume_negative(self, app):
        app.db.add_inventory_lot(InventoryLot(canonical_name="ghee", display_name="Ghee", quantity=2.0, unit="kg"))
        lot_id = app.db.get_inventory()[0].lot_id
        result = app.consume_item(lot_id, -1.0)
        assert "Quantity to consume" in result


class TestInventoryCardsView:
    def test_empty(self, app):
        html = app.inventory_cards_view()
        assert "Your inventory is empty" in html

    def test_with_items(self, app):
        app.db.add_inventory_lot(InventoryLot(canonical_name="rice", display_name="Basmati Rice", quantity=2.0, unit="kg", storage_location_id="pantry"))
        html = app.inventory_cards_view()
        assert "Basmati Rice" in html
        assert "Pantry" in html or "pantry" in html

    def test_search_filters(self, app):
        app.db.add_inventory_lot(InventoryLot(canonical_name="rice", display_name="Basmati Rice", quantity=2.0, unit="kg", storage_location_id="pantry"))
        app.db.add_inventory_lot(InventoryLot(canonical_name="dal", display_name="Toor Dal", quantity=1.0, unit="kg", storage_location_id="pantry"))
        html = app.inventory_cards_view(search="rice")
        assert "Basmati Rice" in html
        assert "Toor Dal" not in html


class TestAskShopStack:
    def test_ask_about_inventory(self, app):
        app.db.add_inventory_lot(
            InventoryLot(
                canonical_name="tomato",
                display_name="Tomato",
                quantity=2.0,
                unit="kg",
                storage_location_id="pantry",
            )
        )
        result = app.ask_shopstack("Do we have tomato?")
        assert "Location match" in result

    def test_ask_for_skip_candidates(self, app):
        app.db.add_inventory_lot(
            InventoryLot(
                canonical_name="onion",
                display_name="Onion",
                quantity=3.0,
                unit="kg",
                storage_location_id="pantry",
            )
        )
        result = app.ask_shopstack("What can I skip today?")
        assert "Likely skip today" in result
        assert "Onion" in result


class TestFieldNotesView:
    def test_initial_load(self, app):
        editor, preview, status = app.field_notes_view()
        assert isinstance(editor, str)
        assert editor == preview
        assert "No saved notes yet" in status

    def test_save_and_reload(self, app):
        editor, preview, status = app.field_notes_save("# My custom notes")
        assert "# My custom notes" in editor
        editor2, preview2, status2 = app.field_notes_view()
        assert "# My custom notes" in editor2
        assert "loaded saved" in status2.lower()


class TestUseSoonView:
    def test_empty(self, app):
        tbl = app.use_soon_view()
        assert isinstance(tbl, list)

    def test_with_old_item(self, app):
        app.db.add_inventory_lot(InventoryLot(canonical_name="old-spice", display_name="Old Spice", quantity=1.0, unit="unit"))
        tbl = app.use_soon_view()
        assert isinstance(tbl, list)


class TestHouseholdMap:
    def test_shows_header(self, app):
        result = app.household_map_view()
        assert "Household Storage Map" in result

    def test_lists_location_names(self, app):
        result = app.household_map_view()
        for loc in app.db.get_locations()[:3]:
            assert loc.name in result


class TestAgentTrace:
    def test_empty(self, app):
        tbl, trace_id = app.agent_trace_view()
        assert "No traces yet" in str(tbl)

    def test_with_data(self, app):
        app.db.save_trace(Trace(input_type="voice", user_goal="check inventory", final_response="ok"))
        app.db.save_trace(Trace(input_type="text", final_response="done"))
        tbl, trace_id = app.agent_trace_view()
        assert len(tbl) >= 2
        assert len(trace_id) > 0

    def test_detail_found(self, app):
        app.db.save_trace(Trace(input_type="voice", final_response="test"))
        traces = app.db.get_traces()
        tid = traces[0].trace_id
        detail = app.agent_trace_detail(tid)
        assert tid in detail

    def test_detail_not_found(self, app):
        detail = app.agent_trace_detail("nonexistent")
        assert "not found" in detail.lower()
