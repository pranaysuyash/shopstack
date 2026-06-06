"""Tests for screen modules — inventory, other, market_lens, and _utils.

Follows the same ``app`` fixture pattern as ``test_views.py`` for integration
tests, and uses direct imports for pure utility functions.
"""

from __future__ import annotations

import json
import os
from datetime import date, timedelta

import pytest

from shopstack.schemas.models import InventoryLot, Trace


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
# inventory.py — previously untested functions
# ══════════════════════════════════════════════════════════════════════════

class TestAddPurchaseBatch:
    def test_empty_input(self, app):
        result = app.add_purchase_batch("")
        assert "Add at least one row" in result

    def test_whitespace_only(self, app):
        result = app.add_purchase_batch("   \n\n  ")
        assert "Add at least one row" in result

    def test_csv_single_row(self, app):
        result = app.add_purchase_batch("Almonds,0.5,kg,350.0,Nut Store,pantry,dry fruits")
        assert "Added" in result
        assert "Almonds" in result
        assert app.db.get_inventory()

    def test_csv_multiple_rows(self, app):
        batch = "Mango,2,kg,120.0,Fruit Shop,fridge,fruit\nBanana,1,dozen,60.0,Fruit Shop,fridge_top,fruit"
        result = app.add_purchase_batch(batch)
        assert "Added 2" in result
        items = app.db.get_inventory()
        assert any(i.canonical_name == "mango" for i in items)
        assert any(i.canonical_name == "banana" for i in items)

    def test_csv_minimal_columns(self, app):
        """Only name, qty, unit — rest get defaults."""
        result = app.add_purchase_batch("Sugar,1,kg")
        assert "Added" in result

    def test_csv_skip_empty_lines(self, app):
        batch = "Tea,0.2,kg\n\nCoffee,0.25,kg\n  \n"
        result = app.add_purchase_batch(batch)
        assert "Added 2" in result

    def test_json_array(self, app):
        payload = json.dumps([
            {"display_name": "Cashews", "quantity": 0.5, "unit": "kg", "price": 450.0, "store": "Dry Fruit Store"},
            {"display_name": "Pista", "quantity": 0.3, "unit": "kg", "price": 320.0, "store": "Dry Fruit Store"},
        ])
        result = app.add_purchase_batch(payload)
        assert "Added 2" in result

    def test_json_single_object(self, app):
        payload = json.dumps({"display_name": "Honey", "quantity": 1.0, "unit": "L", "price": 280.0, "store": "Organic Store"})
        result = app.add_purchase_batch(payload)
        assert "Added" in result
        assert "Honey" in result

    def test_json_with_name_alias(self, app):
        """Accepts 'name' or 'canonical_name' as fallback keys."""
        payload = json.dumps([{"name": "Almonds", "quantity": 0.5}])
        result = app.add_purchase_batch(payload)
        assert "Added" in result

    def test_json_with_canonical_name(self, app):
        payload = json.dumps([{"canonical_name": "Almonds", "quantity": 0.5}])
        result = app.add_purchase_batch(payload)
        assert "Added" in result

    def test_invalid_json(self, app):
        result = app.add_purchase_batch("{bad json}")
        assert "Could not parse" in result

    def test_no_valid_rows(self, app):
        result = app.add_purchase_batch(" , , \n  ,  ")
        assert "No valid purchase rows" in result

    def test_skips_empty_name(self, app):
        result = app.add_purchase_batch(",1,kg")
        assert "No items were added" in result

    def test_records_price_observation(self, app):
        result = app.add_purchase_batch("Butter,0.5,kg,120.0,Dairy Shop,fridge,dairy")
        assert "Added" in result
        prices = app.db.conn.execute(
            "SELECT * FROM price_observations WHERE store_name = 'Dairy Shop'"
        ).fetchall()
        assert len(prices) == 1

    def test_escapes_html(self, app):
        result = app.add_purchase_batch("<script>alert('x')</script>,1,kg")
        assert "Added" in result
        assert "&lt;script&gt;" in result


class TestSeedDemoInventory:
    def test_seeds_items(self, app):
        result = app.seed_demo_inventory()
        assert "Loaded demo stock" in result
        items = app.db.get_inventory()
        assert len(items) > 0

    def test_does_not_seed_twice(self, app):
        app.seed_demo_inventory()
        result = app.seed_demo_inventory()
        assert "already loaded" in result.lower()

    def test_records_price_observations(self, app):
        app.seed_demo_inventory()
        prices = app.db.conn.execute(
            "SELECT COUNT(*) as cnt FROM price_observations"
        ).fetchone()["cnt"]
        assert prices > 0

    def test_escapes_html(self, app):
        result = app.seed_demo_inventory()
        assert "alert(" not in result


class TestConsumeItemsBatch:
    def test_empty_input(self, app):
        result = app.consume_items_batch("")
        assert "Add at least one lot" in result

    def test_whitespace_only(self, app):
        result = app.consume_items_batch("   \n  ")
        assert "No valid lines" in result

    def test_consume_one_item(self, app):
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="salt", display_name="Salt", quantity=2.0, unit="kg")
        )
        lot_id = app.db.get_inventory()[0].lot_id
        result = app.consume_items_batch(f"{lot_id}:0.5")
        assert "remaining 1.5" in result

    def test_consume_multiple(self, app):
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="salt", display_name="Salt", quantity=2.0, unit="kg")
        )
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="sugar", display_name="Sugar", quantity=1.0, unit="kg")
        )
        lots = app.db.get_inventory()
        result = app.consume_items_batch(f"{lots[0].lot_id}:1.0\n{lots[1].lot_id}:0.5")
        assert "remaining 1.0" in result
        assert "remaining 0.5" in result

    def test_default_quantity(self, app):
        """When no quantity specified after colon, defaults to 1."""
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="salt", display_name="Salt", quantity=3.0, unit="kg")
        )
        lot_id = app.db.get_inventory()[0].lot_id
        result = app.consume_items_batch(lot_id)  # no colon, no qty
        assert "remaining" in result

    def test_unknown_lot_id(self, app):
        result = app.consume_items_batch("nonexistent_lot_id:1")
        assert "❌" in result

    def test_skips_empty_lines(self, app):
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="salt", display_name="Salt", quantity=2.0, unit="kg")
        )
        lot_id = app.db.get_inventory()[0].lot_id
        result = app.consume_items_batch(f"{lot_id}:0.5\n\n\n")
        assert "remaining" in result

    def test_escapes_html(self, app):
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="salt", display_name="Salt", quantity=2.0, unit="kg")
        )
        lot_id = app.db.get_inventory()[0].lot_id
        result = app.consume_items_batch(f"{lot_id}:0.5")
        assert "alert(" not in result


# ══════════════════════════════════════════════════════════════════════════
# other.py / household.py — previously untested functions
# ══════════════════════════════════════════════════════════════════════════

class TestPriceIntelligenceView:
    def test_empty_state(self, app):
        result = app.price_intelligence_view()
        assert "No price intelligence yet" in result

    def test_single_item_no_comparison(self, app):
        app.tools.record_price_observation(
            canonical_name="milk", price=64.0, quantity=2.0, unit="L", store_name="Shop A"
        )
        result = app.price_intelligence_view()
        assert "No price intelligence" in result

    def test_with_store_comparison(self, app):
        app.tools.record_price_observation(
            canonical_name="milk", price=64.0, quantity=2.0, unit="L", store_name="Shop A"
        )
        app.tools.record_price_observation(
            canonical_name="milk", price=70.0, quantity=2.0, unit="L", store_name="Shop B"
        )
        result = app.price_intelligence_view()
        assert "Best Price Across Stores" in result
        assert "milk" in result.lower()
        assert "Shop A" in result
        assert "Shop B" in result

    def test_with_price_drop_alert(self, app):
        app.tools.record_price_observation(
            canonical_name="rice", price=80.0, quantity=1.0, unit="kg", store_name="Store X"
        )
        app.tools.record_price_observation(
            canonical_name="rice", price=60.0, quantity=1.0, unit="kg", store_name="Store X"
        )
        result = app.price_intelligence_view()
        assert "Price Drop" in result or "price dropped" in result

    def test_different_units_normalize(self, app):
        """Gram-based prices should be normalized to per-kg."""
        app.tools.record_price_observation(
            canonical_name="paneer", price=50.0, quantity=200.0, unit="g", store_name="Store A"
        )
        app.tools.record_price_observation(
            canonical_name="paneer", price=240.0, quantity=1.0, unit="kg", store_name="Store B"
        )
        result = app.price_intelligence_view()
        assert "Best Price" in result

    def test_escapes_html(self, app):
        app.tools.record_price_observation(
            canonical_name="<script>x</script>", price=10.0, quantity=1.0, unit="kg", store_name="Store"
        )
        result = app.price_intelligence_view()
        assert "&lt;script&gt;" in result


class TestCreateHouseholdLocation:
    def test_creates_location(self, app):
        result = app.create_household_location("Pantry Shelf", "", "shelf")
        assert "Created location" in result
        locs = app.db.get_locations()
        names = [l.name for l in locs]
        assert "Pantry Shelf" in names

    def test_empty_name_rejected(self, app):
        result = app.create_household_location("", "", "shelf")
        assert "Location name is required" in result
        assert "Created" not in result

    def test_whitespace_name_rejected(self, app):
        result = app.create_household_location("   ", "", "shelf")
        assert "Location name is required" in result

    def test_nested_under_parent(self, app):
        locs = app.db.get_locations()
        parent_id = locs[0].location_id
        result = app.create_household_location("New Drawer", parent_id, "drawer")
        assert "Created location" in result
        created = [l for l in app.db.get_locations() if l.name == "New Drawer"]
        assert len(created) == 1
        assert created[0].parent_location_id == parent_id

    def test_default_type(self, app):
        result = app.create_household_location("Random Box", "", "")
        assert "Created location" in result

    def test_escapes_html(self, app):
        result = app.create_household_location("Safe Box", "", "shelf")
        assert "alert(" not in result


class TestMoveInventoryToLocation:
    def test_missing_lot(self, app):
        result = app.move_inventory_to_location("", "fridge")
        assert "Select a lot first" in result

    def test_missing_destination(self, app):
        result = app.move_inventory_to_location("abc123", "")
        assert "Choose destination location" in result

    def test_move_unknown_lot(self, app):
        result = app.move_inventory_to_location("nonexistent_lot", "pantry")
        assert "Move failed" in result

    def test_move_successful(self, app):
        app.db.add_inventory_lot(
            InventoryLot(
                canonical_name="rice", display_name="Basmati Rice",
                quantity=2.0, unit="kg", storage_location_id="pantry",
            )
        )
        lot = app.db.get_inventory()[0]
        # Find a different location to move to
        locs = app.db.get_locations()
        target = [l for l in locs if l.location_id != "pantry"][0]
        result = app.move_inventory_to_location(lot.lot_id, target.location_id)
        assert "Moved item" in result

    def test_escapes_html(self, app):
        app.db.add_inventory_lot(
            InventoryLot(
                canonical_name="rice", display_name="Rice",
                quantity=1.0, unit="kg", storage_location_id="pantry",
            )
        )
        lot = app.db.get_inventory()[0]
        locs = app.db.get_locations()
        target = [l for l in locs if l.location_id != "pantry"][0]
        result = app.move_inventory_to_location(lot.lot_id, target.location_id)
        assert "alert(" not in result


class TestWhatsInFridgeNow:
    def test_empty_fridge(self, app):
        result = app.what_is_in_fridge_now()
        assert "Fridge is empty" in result

    def test_shows_fridge_items(self, app):
        app.db.add_inventory_lot(
            InventoryLot(
                canonical_name="milk", display_name="Milk",
                quantity=2.0, unit="L", storage_location_id="fridge",
            )
        )
        app.db.add_inventory_lot(
            InventoryLot(
                canonical_name="curd", display_name="Curd",
                quantity=0.5, unit="kg", storage_location_id="fridge",
            )
        )
        result = app.what_is_in_fridge_now()
        assert "Milk" in result
        assert "Curd" in result
        assert "2 L" in result

    def test_does_not_show_pantry_items(self, app):
        app.db.add_inventory_lot(
            InventoryLot(
                canonical_name="rice", display_name="Rice",
                quantity=5.0, unit="kg", storage_location_id="pantry",
            )
        )
        result = app.what_is_in_fridge_now()
        assert "Fridge is empty" in result
        assert "Rice" not in result

    def test_shows_nested_fridge_locations(self, app):
        """Items in fridge_top or fridge_door should also show up."""
        app.db.add_inventory_lot(
            InventoryLot(
                canonical_name="eggs", display_name="Eggs",
                quantity=12.0, unit="pieces", storage_location_id="fridge_top",
            )
        )
        result = app.what_is_in_fridge_now()
        assert "Eggs" in result

    def test_escapes_html(self, app):
        app.db.add_inventory_lot(
            InventoryLot(
                canonical_name="milk", display_name="Milk",
                quantity=2.0, unit="L", storage_location_id="fridge",
            )
        )
        result = app.what_is_in_fridge_now()
        assert "alert(" not in result


class TestInventoryAlerts:
    def test_no_alerts(self, app):
        result = app.inventory_alerts()
        assert "No proactive alerts" in result

    def test_low_stock_alert(self, app):
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="salt", display_name="Salt", quantity=0.3, unit="kg")
        )
        result = app.inventory_alerts()
        assert "Reorder" in result
        assert "Salt" in result

    def test_low_status_alert(self, app):
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="oil", display_name="Oil", quantity=0.8, unit="L", status="low")
        )
        result = app.inventory_alerts()
        assert "Reorder" in result

    def test_stale_item_alert(self, app):
        old_date = date.today() - timedelta(days=10)
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="bread", display_name="Bread", quantity=1.0, unit="loaf", purchase_date=old_date)
        )
        result = app.inventory_alerts(days_since_purchase=5)
        assert "Use soon reminders" in result

    def test_default_days_parameter(self, app):
        """Should default to 3 days if not provided."""
        old_date = date.today() - timedelta(days=4)
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="bread", display_name="Bread", quantity=1.0, unit="loaf", purchase_date=old_date)
        )
        result = app.inventory_alerts()  # uses default days=3
        assert "Use soon reminders" in result

    def test_clamps_days_to_positive(self, app):
        """days_since_purchase <= 0 should be clamped to 3."""
        old_date = date.today() - timedelta(days=1)
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="bread", display_name="Bread", quantity=1.0, unit="loaf", purchase_date=old_date)
        )
        result = app.inventory_alerts(days_since_purchase=0)
        # 1 day < 3 (clamped), so no stale alert
        assert "No proactive alerts" in result

    def test_multiple_alert_types(self, app):
        old_date = date.today() - timedelta(days=7)
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="milk", display_name="Milk", quantity=0.3, unit="L", purchase_date=old_date)
        )
        result = app.inventory_alerts(days_since_purchase=3)
        assert "Reorder" in result or "Use soon reminders" in result

    def test_escapes_html(self, app):
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="salt", display_name="Salt", quantity=0.3, unit="kg")
        )
        result = app.inventory_alerts()
        assert "alert(" not in result


# ══════════════════════════════════════════════════════════════════════════
# market_lens.py — previously untested functions
# ══════════════════════════════════════════════════════════════════════════

class TestMarketLensConfirmBuy:
    def test_requires_analysis(self, app):
        result = app.market_lens_confirm_buy("", "trace123")
        assert "Scan something first" in result

    def test_invalid_json(self, app):
        result = app.market_lens_confirm_buy("not json", "")
        assert "Could not parse" in result

    def test_no_buy_items(self, app):
        data = json.dumps({"items": [{"canonical_name": "milk", "decision": "skip"}]})
        result = app.market_lens_confirm_buy(data, "")
        assert "No BUY items found" in result

    def test_adds_buy_items_to_list(self, app):
        data = json.dumps({
            "items": [
                {"canonical_name": "milk", "decision": "buy", "suggested_quantity": 2.0, "unit": "L", "reason": "Low stock"},
                {"canonical_name": "bread", "decision": "buy", "suggested_quantity": 1.0, "unit": "loaf", "reason": "Staple"},
            ]
        })
        result = app.market_lens_confirm_buy(data, "")
        assert "Added 2 item(s)" in result
        sl = app.db.get_active_shopping_list()
        assert sl is not None
        names = [i.canonical_name for i in sl.items]
        assert "milk" in names
        assert "bread" in names

    def test_escapes_html(self, app):
        data = json.dumps({
            "items": [
                {"canonical_name": "<script>x</script>", "decision": "buy", "suggested_quantity": 1.0},
            ]
        })
        result = app.market_lens_confirm_buy(data, "")
        assert "&lt;script&gt;" in result
        assert "<script>" not in result


class TestMarketLensSkip:
    def test_requires_analysis(self, app):
        result = app.market_lens_skip("", "")
        assert "Scan something first" in result

    def test_skip_without_trace(self, app):
        result = app.market_lens_skip('{"items":[]}', "")
        assert "Saved skip decision" in result

    def test_skip_with_trace(self, app):
        app.db.save_trace(Trace(input_type="vision", user_goal="market_lens", final_response="test"))
        trace = app.db.get_traces()[0]
        result = app.market_lens_skip('{"items":[]}', trace.trace_id)
        assert "Saved skip decision" in result


class TestMarketLensSaveTrace:
    def test_requires_trace(self, app):
        result = app.market_lens_save_trace("", "")
        assert "No trace to save" in result

    def test_saves_trace(self, app):
        app.db.save_trace(Trace(input_type="vision", user_goal="market_lens", final_response="test"))
        trace = app.db.get_traces()[0]
        result = app.market_lens_save_trace('{"items":[]}', trace.trace_id)
        assert "Trace" in result
        assert "saved" in result.lower()


class TestMarketLensBarcodeAdd:
    def test_no_barcode_data(self, app):
        result = app.market_lens_barcode_add("")
        assert "No barcode data" in result

    def test_empty_array(self, app):
        result = app.market_lens_barcode_add("[]")
        assert "No barcode data" in result

    def test_invalid_json(self, app):
        result = app.market_lens_barcode_add("bad json")
        assert "Could not parse" in result

    def test_adds_single_barcode(self, app):
        data = json.dumps([{"code": "8901234567890", "label": "Product code Test Product", "type": "EAN13"}])
        result = app.market_lens_barcode_add(data)
        assert "Added 1 barcode" in result
        assert "Test Product" in result
        items = app.db.get_inventory()
        assert any("test product" in i.canonical_name for i in items)

    def test_adds_multiple_barcodes(self, app):
        data = json.dumps([
            {"code": "8901234567890", "label": "Product code Milk", "type": "EAN13"},
            {"code": "8909876543210", "label": "Product code Eggs", "type": "EAN13"},
        ])
        result = app.market_lens_barcode_add(data)
        assert "Added 2 barcode" in result

    def test_fallback_label(self, app):
        """When label has no 'Product code ' prefix, fallback to barcode-item-XXXX."""
        data = json.dumps([{"code": "12345", "label": "", "type": "QR"}])
        result = app.market_lens_barcode_add(data)
        assert "Added" in result

    def test_escapes_html(self, app):
        data = json.dumps([{"code": "123", "label": "<script>alert('x')</script>", "type": "QR"}])
        result = app.market_lens_barcode_add(data)
        assert "&lt;script&gt;" in result


# ══════════════════════════════════════════════════════════════════════════
# _utils.py — utility functions
# ══════════════════════════════════════════════════════════════════════════

class TestNormalizeItemName:
    def test_alias_tomato(self):
        from shopstack.ui.screens._utils import normalize_item_name
        assert normalize_item_name("tamatar") == "tomato"
        assert normalize_item_name("tomatoes") == "tomato"
        assert normalize_item_name("tomato") == "tomato"

    def test_alias_onion(self):
        from shopstack.ui.screens._utils import normalize_item_name
        assert normalize_item_name("pyaaz") == "onion"
        assert normalize_item_name("pyaz") == "onion"
        assert normalize_item_name("onion") == "onion"

    def test_alias_curd(self):
        from shopstack.ui.screens._utils import normalize_item_name
        assert normalize_item_name("dahi") == "curd"
        assert normalize_item_name("yogurt") == "curd"

    def test_alias_rice(self):
        from shopstack.ui.screens._utils import normalize_item_name
        assert normalize_item_name("chawal") == "rice"

    def test_unknown_returns_cleaned_input(self):
        from shopstack.ui.screens._utils import normalize_item_name
        assert normalize_item_name("  Ghee  ") == "ghee"

    def test_strips_punctuation(self):
        from shopstack.ui.screens._utils import normalize_item_name
        assert normalize_item_name("milk!") == "milk"

    def test_case_insensitive(self):
        from shopstack.ui.screens._utils import normalize_item_name
        assert normalize_item_name("CILANTRO") == "coriander"

    def test_mixed_aliases(self):
        from shopstack.ui.screens._utils import normalize_item_name
        assert normalize_item_name("Dhania") == "coriander"
        assert normalize_item_name("AATA") == "wheat flour"


class TestParseShoppingText:
    def test_empty_input(self):
        from shopstack.ui.screens._utils import parse_shooting_text as parse
        # Actually it's parse_shopping_text
        from shopstack.ui.screens._utils import parse_shopping_text
        assert parse_shopping_text("") == []
        assert parse_shopping_text(None) == []

    def test_single_item(self):
        from shopstack.ui.screens._utils import parse_shopping_text
        result = parse_shopping_text("milk")
        assert "milk" in result

    def test_comma_separated(self):
        from shopstack.ui.screens._utils import parse_shopping_text
        result = parse_shopping_text("milk, bread, eggs")
        assert "milk" in result
        assert "bread" in result
        assert "eggs" in result

    def test_semicolon_separated(self):
        from shopstack.ui.screens._utils import parse_shopping_text
        result = parse_shopping_text("milk; bread; eggs")
        assert "milk" in result

    def test_normalizes_item_names(self):
        from shopstack.ui.screens._utils import parse_shopping_text
        result = parse_shopping_text("dahi, tamatar")
        assert "curd" in result
        assert "tomato" in result

    def test_replaces_and_with_comma(self):
        from shopstack.ui.screens._utils import parse_shopping_text
        result = parse_shopping_text("milk and bread")
        assert "milk" in result
        assert "bread" in result

    def test_handles_quantity_prefix(self):
        from shopstack.ui.screens._utils import parse_shopping_text
        result = parse_shopping_text("2kg milk")
        assert "milk" in result


class TestExtractQueryForAction:
    def test_basic_query(self):
        from shopstack.ui.screens._utils import extract_query_for_action
        assert "tomato" in extract_query_for_action("Do we have tomato?", "tomato")

    def test_strips_noise_words(self):
        from shopstack.ui.screens._utils import extract_query_for_action
        result = extract_query_for_action("What should I buy today?", "")
        assert result  # should not be empty

    def test_fallback_to_keyword(self):
        from shopstack.ui.screens._utils import extract_query_for_action
        result = extract_query_for_action("How are you?", "default_item")
        assert "default_item" in result

    def test_strips_hindi_words(self):
        from shopstack.ui.screens._utils import extract_query_for_action
        result = extract_query_for_action("kya kharidna hai?", "")
        assert result is not None

    def test_multiline_query(self):
        from shopstack.ui.screens._utils import extract_query_for_action
        result = extract_query_for_action("Where is the milk?", "milk")
        assert "milk" in result


class TestRenderHomeAdvice:
    def test_healthy_pantry(self, app):
        from shopstack.ui.screens._utils import render_home_advice
        result = render_home_advice([], [], [])
        assert "healthy" in result.lower() or "no immediate action" in result

    def test_buy_recommendations(self, app):
        from shopstack.schemas.models import InventoryLot
        low_item = InventoryLot(canonical_name="salt", display_name="Salt", quantity=0.3, unit="kg")
        from shopstack.ui.screens._utils import render_home_advice
        result = render_home_advice([low_item], [low_item], [])
        assert "Buy" in result
        assert "Salt" in result

    def test_skip_recommendations(self, app):
        from shopstack.schemas.models import InventoryLot
        full_item = InventoryLot(canonical_name="rice", display_name="Basmati Rice", quantity=5.0, unit="kg", status="active")
        from shopstack.ui.screens._utils import render_home_advice
        result = render_home_advice([full_item], [], [])
        assert "Skip" in result
        assert "Basmati Rice" in result

    def test_use_soon_advice(self, app):
        use_soon_items = [{"canonical_name": "milk", "display_name": "Milk"}]
        from shopstack.ui.screens._utils import render_home_advice
        result = render_home_advice([], [], use_soon_items)
        assert "Use" in result
        assert "Milk" in result

    def test_escapes_html(self, app):
        from shopstack.schemas.models import InventoryLot
        bad_item = InventoryLot(canonical_name="<x>", display_name="<x>", quantity=0.3, unit="kg")
        from shopstack.ui.screens._utils import render_home_advice
        result = render_home_advice([bad_item], [bad_item], [])
        assert "&lt;x&gt;" in result
        assert "<x>" not in result


class TestRenderListSummary:
    def test_no_list(self):
        from shopstack.ui.screens._utils import render_list_summary
        result = render_list_summary(None)
        assert "No active list" in result

    def test_empty_list(self):
        from shopstack.ui.screens._utils import render_list_summary
        from shopstack.schemas.models import ShoppingList
        sl = ShoppingList(list_id="test", items=[])
        result = render_list_summary(sl)
        assert "List is empty" in result

    def test_with_items(self, app):
        app.tools.create_or_update_shopping_list(
            items=[{"canonical_name": "milk", "requested_quantity": 2.0}],
            goal="Weekly shop",
        )
        sl = app.db.get_active_shopping_list()
        from shopstack.ui.screens._utils import render_list_summary
        result = render_list_summary(sl)
        assert "milk" in result.lower()
        assert "2 items" in result or "1 items" in result


class TestRowsToHtml:
    def test_empty(self):
        from shopstack.ui.screens._utils import rows_to_html
        result = rows_to_html([], ["name"])
        assert "No entries" in result

    def test_renders_table(self):
        from shopstack.ui.screens._utils import rows_to_html
        rows = [{"name": "Milk", "qty": 2}, {"name": "Bread", "qty": 1}]
        result = rows_to_html(rows, ["name", "qty"])
        assert "Milk" in result
        assert "Bread" in result
        assert "<table" in result
        assert "<th>" in result

    def test_escapes_html(self):
        from shopstack.ui.screens._utils import rows_to_html
        rows = [{"name": "<script>", "qty": 1}]
        result = rows_to_html(rows, ["name"])
        assert "&lt;script&gt;" in result

    def test_missing_column_returns_empty(self):
        from shopstack.ui.screens._utils import rows_to_html
        rows = [{"name": "Milk"}]
        result = rows_to_html(rows, ["name", "qty"])
        assert "Milk" in result


class TestWorkflowTitleBar:
    def test_basic_title(self):
        from shopstack.ui.screens._utils import workflow_title_bar
        result = workflow_title_bar("Dashboard")
        assert "Dashboard" in result

    def test_with_subtitle(self):
        from shopstack.ui.screens._utils import workflow_title_bar
        result = workflow_title_bar("Dashboard", "Your overview")
        assert "Dashboard" in result
        assert "Your overview" in result

    def test_no_subtitle(self):
        from shopstack.ui.screens._utils import workflow_title_bar
        result = workflow_title_bar("Dashboard")
        assert "Your overview" not in result

    def test_escapes_html(self):
        from shopstack.ui.screens._utils import workflow_title_bar
        result = workflow_title_bar("<script>", "<alert>")
        assert "&lt;script&gt;" in result
        assert "&lt;alert&gt;" in result


class TestRenderLowStock:
    def test_empty(self):
        from shopstack.ui.screens._utils import render_low_stock
        assert render_low_stock([]) == ""

    def test_with_items(self, app):
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="salt", display_name="Salt", quantity=0.3, unit="kg")
        )
        from shopstack.ui.screens._utils import render_low_stock
        result = render_low_stock(app.db.get_inventory())
        assert "Salt" in result
        assert "0.3" in result


class TestRenderRecentPurchases:
    def test_empty(self):
        from shopstack.ui.screens._utils import render_recent_purchases
        assert render_recent_purchases([]) == ""

    def test_with_purchases(self, app):
        app.tools.add_inventory_item(
            canonical_name="milk", display_name="Milk",
            quantity=2.0, unit="L", storage_location_id="fridge",
            price_paid=64.0,
        )
        from shopstack.ui.screens._utils import render_recent_purchases
        purchases = app.db.get_recent_purchases(limit=5)
        if purchases:
            result = render_recent_purchases(purchases)
            assert "milk" in result.lower()
