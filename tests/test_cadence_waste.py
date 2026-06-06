"""Tests for cadence detection, waste patterns, and Swiggy availability."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import pytest


@pytest.fixture(autouse=True)
def _set_test_env():
    os.environ["SHOPSTACK_DB_PATH"] = ":memory:"
    yield


@pytest.fixture
def ctx():
    import importlib
    import sys
    _preserved = {"shopstack.schemas", "shopstack.schemas.models"}
    for mod in list(sys.modules.keys()):
        if mod.startswith("shopstack") and mod not in _preserved:
            del sys.modules[mod]
    from shopstack import app_context
    return importlib.reload(app_context)


class TestPurchaseCadence:
    def test_empty_returns_empty(self, ctx):
        from shopstack.decisions import detect_purchase_cadence
        result = detect_purchase_cadence(ctx.db)
        assert result == {}

    def test_single_purchase_skipped(self, ctx):
        from shopstack.decisions import detect_purchase_cadence
        from shopstack.schemas.models import PurchaseEvent
        ctx.db.add_purchase_event(PurchaseEvent(
            canonical_name="milk", quantity=1, unit="L", total_price=60,
        ))
        result = detect_purchase_cadence(ctx.db)
        assert "milk" not in result

    def test_multiple_purchases_detects_interval(self, ctx):
        from shopstack.decisions import detect_purchase_cadence
        from shopstack.schemas.models import PurchaseEvent
        today = datetime.now()
        for days_ago in [0, 2, 4, 6]:
            pe = PurchaseEvent(
                canonical_name="milk",
                quantity=1,
                unit="L",
                total_price=60,
                timestamp=today - timedelta(days=days_ago),
            )
            ctx.db.add_purchase_event(pe)

        result = detect_purchase_cadence(ctx.db)
        assert "milk" in result
        info = result["milk"]
        assert abs(info["avg_interval_days"] - 2.0) < 0.5
        assert info["purchase_count"] >= 3

    def test_render_cadence_empty(self, ctx):
        from shopstack.decisions import render_cadence_insights
        html = render_cadence_insights(ctx.db)
        assert html == ""

    def test_render_cadence_with_data(self, ctx):
        from shopstack.decisions import render_cadence_insights
        from shopstack.schemas.models import PurchaseEvent
        today = datetime.now()
        for days_ago in [0, 2, 4]:
            ctx.db.add_purchase_event(PurchaseEvent(
                canonical_name="milk", quantity=1, unit="L", total_price=60,
                timestamp=today - timedelta(days=days_ago),
            ))
        html = render_cadence_insights(ctx.db)
        assert "Purchase Rhythm" in html
        assert "Milk" in html


class TestWasteDetection:
    def test_empty_returns_empty(self, ctx):
        from shopstack.decisions import detect_waste_patterns
        result = detect_waste_patterns(ctx.db)
        assert result == []

    def test_high_waste_risk_frequent_purchase(self, ctx):
        from shopstack.decisions import detect_waste_patterns
        from shopstack.schemas.models import PurchaseEvent
        today = datetime.now()
        for days_ago in [0, 1, 2, 3]:
            ctx.db.add_purchase_event(PurchaseEvent(
                canonical_name="coriander",
                quantity=1, unit="bunch", total_price=20,
                timestamp=today - timedelta(days=days_ago),
            ))
        ctx.tools.add_inventory_item(
            canonical_name="coriander",
            display_name="Coriander",
            quantity=2, unit="bunch",
            storage_location_id="fridge",
        )
        result = detect_waste_patterns(ctx.db)
        assert len(result) >= 1
        assert any(r["canonical_name"] == "coriander" for r in result)

    def test_render_waste_empty(self, ctx):
        from shopstack.decisions import render_waste_warnings
        html = render_waste_warnings(ctx.db)
        assert html == ""


class TestSwiggyAvailability:
    def test_check_known_vegetable(self):
        from shopstack.decisions import check_swiggy_availability
        result = check_swiggy_availability(["tomato"])
        assert "tomato" in result
        assert "available" in result["tomato"]
        assert "price" in result["tomato"]

    def test_check_unknown_item(self):
        from shopstack.decisions import check_swiggy_availability
        result = check_swiggy_availability(["unobtainium"])
        assert "unobtainium" not in result

    def test_soldout_items(self):
        from shopstack.decisions import check_swiggy_availability
        result = check_swiggy_availability(["capsicum"])
        if "capsicum" in result:
            assert "available" in result["capsicum"]

    def test_render_soldout_warning_empty(self):
        from shopstack.decisions import render_swiggy_soldout_warning
        html = render_swiggy_soldout_warning([])
        assert html == ""

    def test_render_soldout_warning_with_items(self):
        from shopstack.decisions import render_swiggy_soldout_warning
        html = render_swiggy_soldout_warning(["tomato", "unknown_item"])
        if "Sold out" in html:
            assert "Swiggy" in html


class TestShoppingListSwiggyEnrichment:
    def test_enrich_adds_swiggy_data(self, ctx):
        from shopstack.ui.screens.shopping import _enrich_items_with_swiggy
        items = [{"canonical_name": "tomato"}]
        result = _enrich_items_with_swiggy(items)
        assert "swiggy_price" in result[0]
        assert "swiggy_available" in result[0]

    def test_enrich_unknown_item(self, ctx):
        from shopstack.ui.screens.shopping import _enrich_items_with_swiggy
        items = [{"canonical_name": "unobtainium"}]
        result = _enrich_items_with_swiggy(items)
        assert result[0]["swiggy_price"] is None
        assert result[0]["swiggy_available"] is None

    def test_shopping_freshness_note(self, ctx):
        from shopstack.ui.screens.shopping import _swiggy_freshness_note
        html = _swiggy_freshness_note()
        assert "point-in-time" in html
        assert "Verify before checkout" in html
