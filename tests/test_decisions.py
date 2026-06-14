"""Tests for the decision engine: BUY/SKIP/USE_SOON/OPTIONAL/WATCH classifications."""

from __future__ import annotations

from datetime import date

import pytest


@pytest.fixture
def ctx(app):
    """Bind ctx to the consolidated session-scoped app module.

    Previously this fixture reloaded ``shopstack.app_context`` to get a fresh
    in-memory DB per test. That created a *second* ``Database`` singleton,
    diverging from the one held by ``conftest._app_session`` and by every
    screen module's module-level ``db`` import. The result was silent
    contamination: traces and inventory lots written through one path were
    invisible to reads through the other.

    The conftest ``app`` fixture already clears all data tables between tests
    and resets ``active_household_id``. Using it preserves the single source
    of truth.
    """
    return app


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
        assert milk[0].action == Decision.BUY.value

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
        assert rice[0].action == Decision.BUY.value

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
        assert potato[0].action == Decision.SKIP.value

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
        assert onion[0].action == Decision.SKIP.value

    def test_on_list_without_stock_is_buy(self, ctx):
        from shopstack.decisions import classify_all, Decision
        from shopstack.schemas.models import ShoppingListItem
        sl = ctx.db.create_shopping_list(name="test", goal="test")
        ctx.db.add_list_item(sl.list_id, ShoppingListItem(canonical_name="bread", status="pending"))

        ds = classify_all(ctx.db, ctx.tools)
        bread = [d for d in ds.decisions if d.canonical_name == "bread"]
        assert len(bread) == 1
        assert bread[0].action == Decision.BUY.value

    def test_classify_all_respects_user_id_scope(self, ctx):
        from shopstack.decisions import classify_all
        from shopstack.schemas.models import ShoppingListItem

        ctx.db.add_household("house_a", "House A")
        ctx.db.add_household_member("house_a", "house_a", role="owner")
        ctx.db.add_household("house_b", "House B")
        ctx.db.add_household_member("house_b", "house_b", role="owner")

        ctx.tools.add_inventory_item(
            canonical_name="milk",
            display_name="Milk",
            quantity=3.0,
            unit="L",
            user_id="house_a",
        )
        ctx.tools.add_inventory_item(
            canonical_name="bread",
            display_name="Bread",
            quantity=0.0,
            unit="unit",
            user_id="house_b",
        )

        sl_a = ctx.db.create_shopping_list(name="plan_a", goal="A", user_id="house_a")
        sl_b = ctx.db.create_shopping_list(name="plan_b", goal="B", user_id="house_b")
        ctx.db.add_list_item(sl_a.list_id, ShoppingListItem(canonical_name="tomato", status="pending"))
        ctx.db.add_list_item(sl_b.list_id, ShoppingListItem(canonical_name="rice", status="pending"))

        ds_a = classify_all(ctx.db, ctx.tools, user_id="house_a")
        ds_b = classify_all(ctx.db, ctx.tools, user_id="house_b")

        names_a = {d.canonical_name for d in ds_a.decisions}
        names_b = {d.canonical_name for d in ds_b.decisions}

        assert names_a == {"milk", "tomato"}
        assert names_b == {"bread", "rice"}


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
        from datetime import timedelta
        old_date = date.today() - timedelta(days=20)
        ctx.tools.add_inventory_item(
            canonical_name="spice",
            display_name="Old Spice",
            quantity=1,
            unit="pack",
            storage_location_id="pantry",
        )
        inv = ctx.db.get_inventory()
        lot = [lot for lot in inv if lot.canonical_name == "spice"][0]
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

    def test_market_only_items_as_wait(self, ctx):
        from shopstack.decisions import classify_all
        from shopstack.market.sources.swiggy import load_snapshot
        snap = load_snapshot()

        ds = classify_all(ctx.db, ctx.tools, snap)
        assert len(ds.wait) > 0

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


class TestClassifyInventoryComparison:
    """Unit tests for the shared classification helper."""

    def test_zero_stock(self):
        from shopstack.decisions.rules import classify_inventory_comparison
        decision, reason = classify_inventory_comparison(0, 1.0, "kg", False)
        assert decision == "buy"

    def test_double_stock_skip(self):
        from shopstack.decisions.rules import classify_inventory_comparison
        decision, reason = classify_inventory_comparison(2.0, 1.0, "kg", False)
        assert decision == "skip"

    def test_exact_stock_optional(self):
        from shopstack.decisions.rules import classify_inventory_comparison
        decision, reason = classify_inventory_comparison(1.0, 1.0, "kg", False)
        assert decision == "optional"

    def test_partial_stock_buy(self):
        from shopstack.decisions.rules import classify_inventory_comparison
        decision, reason = classify_inventory_comparison(0.5, 1.0, "kg", False)
        assert decision == "buy"

    def test_reason_contains_quantity(self):
        from shopstack.decisions.rules import classify_inventory_comparison
        _, reason = classify_inventory_comparison(0.5, 1.0, "kg", False)
        assert "0.5" in reason
