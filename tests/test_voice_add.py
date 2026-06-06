"""Tests for voice command parsing in ask_shopstack."""

from __future__ import annotations

import os
import sys

import pytest


@pytest.fixture(scope="module")
def fresh_app():
    os.environ["SHOPSTACK_DB_PATH"] = ":memory:"
    import importlib
    _preserved = {"shopstack.schemas", "shopstack.schemas.models"}
    for mod in list(sys.modules.keys()):
        if mod in ("app",) or (mod.startswith("shopstack") and mod not in _preserved):
            del sys.modules[mod]
    import app as _app
    return _app


class TestVoiceAddCommands:
    def test_add_simple_item(self, fresh_app):
        result = fresh_app.ask_shopstack("add milk")
        assert "Added" in result
        assert "milk" in result.lower()

    def test_add_with_quantity(self, fresh_app):
        result = fresh_app.ask_shopstack("add 6 eggs")
        assert "Added" in result
        assert "6" in result

    def test_add_with_unit(self, fresh_app):
        result = fresh_app.ask_shopstack("add 2 kg rice")
        assert "Added" in result
        assert "2" in result
        assert "kg" in result

    def test_add_with_liters(self, fresh_app):
        result = fresh_app.ask_shopstack("add 1 liter oil")
        assert "Added" in result
        assert "1" in result

    def test_bought_pattern(self, fresh_app):
        result = fresh_app.ask_shopstack("I bought bread")
        assert "Added" in result
        assert "bread" in result.lower()

    def test_we_bought_pattern(self, fresh_app):
        result = fresh_app.ask_shopstack("we bought 1 kg onion")
        assert "Added" in result

    def test_add_grams(self, fresh_app):
        result = fresh_app.ask_shopstack("add 500g flour")
        assert "Added" in result

    def test_add_creates_inventory_item(self, fresh_app):
        fresh_app.db.conn.execute("DELETE FROM inventory_lots").fetchone()
        fresh_app.ask_shopstack("add 2 kg sugar")
        items = fresh_app.db.get_inventory(canonical_name="sugar")
        assert any(i.quantity == 2.0 and i.unit == "kg" for i in items)

    def test_add_records_trace(self, fresh_app):
        fresh_app.ask_shopstack("add 1 kg salt")
        traces = fresh_app.db.get_traces(limit=5)
        assert any("voice_add_item" in (t.user_goal or "") for t in traces)

    def test_add_empty_is_handled(self, fresh_app):
        result = fresh_app.ask_shopstack("add")
        assert isinstance(result, str)

    def test_add_with_location_inference(self, fresh_app):
        fresh_app.ask_shopstack("add 1 bunch coriander")
        items = fresh_app.db.get_inventory(canonical_name="coriander")
        assert any(i.storage_location_id == "fridge_drawer" for i in items)


class TestPriceIntelligence:
    def test_returns_html_string(self, fresh_app):
        from shopstack.ui.screens.other import price_intelligence_view
        result = price_intelligence_view()
        assert isinstance(result, str)

    def test_shows_comparison_with_multiple_stores(self, fresh_app):
        from shopstack.ui.screens.other import price_intelligence_view
        fresh_app.tools.record_price_observation(
            canonical_name="test_item_pi", price=100, quantity=1, unit="kg", store_name="Store A",
        )
        fresh_app.tools.record_price_observation(
            canonical_name="test_item_pi", price=80, quantity=1, unit="kg", store_name="Store B",
        )
        result = price_intelligence_view()
        assert "test_item_pi" in result or "Best Price" in result

    def test_detects_price_drop(self, fresh_app):
        from datetime import date, timedelta
        from shopstack.schemas.models import PriceObservation
        today = date.today()
        old_obs = PriceObservation(
            canonical_name="drop_test_item",
            price=100.0, quantity=1, unit="kg",
            store_name="Store X",
            observation_date=today - timedelta(days=14),
        )
        new_obs = PriceObservation(
            canonical_name="drop_test_item",
            price=70.0, quantity=1, unit="kg",
            store_name="Store X",
            observation_date=today,
        )
        fresh_app.db.record_price(old_obs)
        fresh_app.db.record_price(new_obs)
        from shopstack.ui.screens.other import price_intelligence_view
        result = price_intelligence_view()
        assert "drop" in result.lower() or "Price Drop" in result
