"""Tests for the decision engine: BUY/SKIP/USE_SOON/OPTIONAL/WATCH classifications."""

from __future__ import annotations

import os
from datetime import date, datetime

import pytest


@pytest.fixture(autouse=True)
def _set_test_env():
    os.environ["SHOPSTACK_DB_PATH"] = ":memory:"
    yield


@pytest.fixture
def ctx():
    """Fresh app_context for each test with a clean :memory: DB."""
    import importlib
    import sys
    _preserved = {"shopstack.schemas", "shopstack.schemas.models", "shopstack.decisions"}
    for mod in list(sys.modules.keys()):
        if mod.startswith("shopstack") and mod not in _preserved:
            del sys.modules[mod]
    from shopstack import app_context
    return importlib.reload(app_context)


class TestDecisionClassification:
    def test_empty_inventory_returns_empty(self, ctx):
        from shopstack.decisions import classify_all, DecisionSet
        ds = classify_all(ctx.db, ctx.tools)
        assert isinstance(ds, DecisionSet)
        assert len(ds.decisions) == 0

    def test_out_of_stock_is_buy(self, ctx):
        from shopstack.decisions import classify_all, Decision
        ctx.tools.add_inventory_item(
            canonical_name="milk",
            display_name="Milk",
            quantity=0,
            unit="L",
            storage_location_id="fridge",
        )
        ds = classify_all(ctx.db, ctx.tools)
        milk = [d for d in ds.decisions if d.canonical_name == "milk"]
        assert len(milk) == 1
        assert milk[0].decision == Decision.BUY.value

    def test_low_stock_is_buy(self, ctx):
        from shopstack.decisions import classify_all, Decision
        ctx.tools.add_inventory_item(
            canonical_name="rice",
            display_name="Rice",
            quantity=0.3,
            unit="kg",
            storage_location_id="pantry",
        )
        ds = classify_all(ctx.db, ctx.tools)
        rice = [d for d in ds.decisions if d.canonical_name == "rice"]
        assert len(rice) == 1
        assert rice[0].decision == Decision.BUY.value

    def test_well_stocked_is_skip(self, ctx):
        from shopstack.decisions import classify_all, Decision
        ctx.tools.add_inventory_item(
            canonical_name="potato",
            display_name="Potato",
            quantity=2.0,
            unit="kg",
            storage_location_id="pantry",
        )
        ds = classify_all(ctx.db, ctx.tools)
        potato = [d for d in ds.decisions if d.canonical_name == "potato"]
        assert len(potato) == 1
        assert potato[0].decision == Decision.SKIP.value

    def test_on_list_with_stock_is_skip(self, ctx):
        from shopstack.decisions import classify_all, Decision
        ctx.tools.add_inventory_item(
            canonical_name="onion",
            display_name="Onion",
            quantity=1.5,
            unit="kg",
            storage_location_id="pantry",
        )
        from shopstack.schemas.models import ShoppingListItem
        sl = ctx.db.create_shopping_list(name="test", goal="test")
        ctx.db.add_list_item(sl.list_id, ShoppingListItem(canonical_name="onion", status="pending"))

        ds = classify_all(ctx.db, ctx.tools)
        onion = [d for d in ds.decisions if d.canonical_name == "onion"]
        assert len(onion) == 1
        assert onion[0].decision == Decision.SKIP.value

    def test_on_list_without_stock_is_buy(self, ctx):
        from shopstack.decisions import classify_all, Decision
        from shopstack.schemas.models import ShoppingListItem
        sl = ctx.db.create_shopping_list(name="test", goal="test")
        ctx.db.add_list_item(sl.list_id, ShoppingListItem(canonical_name="bread", status="pending"))

        ds = classify_all(ctx.db, ctx.tools)
        bread = [d for d in ds.decisions if d.canonical_name == "bread"]
        assert len(bread) == 1
        assert bread[0].decision == Decision.BUY.value


class TestDecisionSetProperties:
    def test_buy_property(self, ctx):
        from shopstack.decisions import classify_all
        ctx.tools.add_inventory_item(canonical_name="milk", display_name="Milk", quantity=0, unit="L")
        ctx.tools.add_inventory_item(canonical_name="rice", display_name="Rice", quantity=5, unit="kg")

        ds = classify_all(ctx.db, ctx.tools)
        assert len(ds.buy) == 1
        assert ds.buy[0].canonical_name == "milk"

    def test_skip_property(self, ctx):
        from shopstack.decisions import classify_all
        ctx.tools.add_inventory_item(canonical_name="milk", display_name="Milk", quantity=0, unit="L")
        ctx.tools.add_inventory_item(canonical_name="rice", display_name="Rice", quantity=5, unit="kg")

        ds = classify_all(ctx.db, ctx.tools)
        assert len(ds.skip) == 1
        assert ds.skip[0].canonical_name == "rice"

    def test_estimated_basket_total_no_market(self, ctx):
        from shopstack.decisions import classify_all
        ctx.tools.add_inventory_item(canonical_name="milk", display_name="Milk", quantity=0, unit="L")
        ds = classify_all(ctx.db, ctx.tools)
        assert ds.estimated_basket_total == 0


class TestMarketBasketRender:
    def test_empty_basket(self, ctx):
        from shopstack.decisions import classify_all, render_market_basket
        ds = classify_all(ctx.db, ctx.tools)
        html = render_market_basket(ds)
        assert "Nothing to buy" in html

    def test_basket_with_buy_items(self, ctx):
        from shopstack.decisions import classify_all, render_market_basket
        ctx.tools.add_inventory_item(canonical_name="milk", display_name="Milk", quantity=0, unit="L")
        ds = classify_all(ctx.db, ctx.tools)
        html = render_market_basket(ds)
        assert "Market Basket" in html
        assert "Milk" in html


class TestDecisionPanelRender:
    def test_empty_panel(self, ctx):
        from shopstack.decisions import classify_all, render_decision_panel
        ds = classify_all(ctx.db, ctx.tools)
        html = render_decision_panel(ds)
        assert "No decisions yet" in html

    def test_panel_with_items(self, ctx):
        from shopstack.decisions import classify_all, render_decision_panel
        ctx.tools.add_inventory_item(canonical_name="milk", display_name="Milk", quantity=0, unit="L")
        ctx.tools.add_inventory_item(canonical_name="rice", display_name="Rice", quantity=5, unit="kg")
        ds = classify_all(ctx.db, ctx.tools)
        html = render_decision_panel(ds)
        assert "Today's Decisions" in html
        assert "Milk" in html
        assert "Rice" in html


class TestWhatChangedRender:
    def test_empty(self, ctx):
        from shopstack.decisions import render_what_changed
        html = render_what_changed(ctx.db)
        assert html == ""

    def test_with_purchase(self, ctx):
        from shopstack.decisions import render_what_changed
        from shopstack.schemas.models import PurchaseEvent
        pe = PurchaseEvent(
            canonical_name="milk",
            quantity=1,
            unit="L",
            total_price=60,
            store_name="Local",
        )
        ctx.db.add_purchase_event(pe)
        html = render_what_changed(ctx.db)
        assert "What Changed" in html
        assert "Milk" in html


class TestNeedsConfirmationRender:
    def test_empty(self, ctx):
        from shopstack.decisions import render_needs_confirmation
        html = render_needs_confirmation(ctx.db)
        assert html == ""

    def test_old_item_shows(self, ctx):
        from shopstack.decisions import render_needs_confirmation
        from datetime import date, timedelta
        old_date = date.today() - timedelta(days=20)
        ctx.tools.add_inventory_item(
            canonical_name="spice",
            display_name="Old Spice",
            quantity=1,
            unit="pack",
            storage_location_id="pantry",
        )
        inv = ctx.db.get_inventory()
        lot = [l for l in inv if l.canonical_name == "spice"][0]
        ctx.db.conn.execute(
            "UPDATE inventory_lots SET purchase_date = ? WHERE lot_id = ?",
            (old_date.isoformat(), lot.lot_id),
        )
        ctx.db.conn.commit()

        html = render_needs_confirmation(ctx.db)
        assert html != ""
        assert "Old Spice" in html


class TestDecisionWithSwiggy:
    def test_market_prices_attached(self, ctx):
        from shopstack.decisions import classify_all
        from shopstack.market.sources.swiggy import load_snapshot
        snap = load_snapshot()

        ctx.tools.add_inventory_item(
            canonical_name="tomato",
            display_name="Tomato",
            quantity=0,
            unit="kg",
        )
        ds = classify_all(ctx.db, ctx.tools, snap)
        tomato = [d for d in ds.decisions if d.canonical_name == "tomato"]
        assert len(tomato) == 1
        assert tomato[0].market_price is not None
        assert tomato[0].market_price_per_kg is not None
        assert tomato[0].market_available is True

    def test_market_only_items_as_watch(self, ctx):
        from shopstack.decisions import classify_all
        from shopstack.market.sources.swiggy import load_snapshot
        snap = load_snapshot()

        ds = classify_all(ctx.db, ctx.tools, snap)
        assert len(ds.watch) > 0

    def test_basket_total_with_market(self, ctx):
        from shopstack.decisions import classify_all
        from shopstack.market.sources.swiggy import load_snapshot
        snap = load_snapshot()

        ctx.tools.add_inventory_item(
            canonical_name="tomato",
            display_name="Tomato",
            quantity=0,
            unit="kg",
        )
        ds = classify_all(ctx.db, ctx.tools, snap)
        assert ds.estimated_basket_total > 0
