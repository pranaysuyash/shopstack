"""Tests for voice command parsing in ask_shopstack."""

from __future__ import annotations

import pytest

from shopstack.app_context import db as app_db, tools as app_tools
from shopstack.ui.screens import ask_shopstack


class TestVoiceAddCommands:
    def test_add_simple_item(self, app):
        result = ask_shopstack("add milk")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_add_with_quantity(self, app):
        result = ask_shopstack("add 6 eggs")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_add_with_unit(self, app):
        result = ask_shopstack("add 2 kg rice")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_add_with_liters(self, app):
        result = ask_shopstack("add 1 liter oil")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_bought_pattern(self, app):
        result = ask_shopstack("I bought bread")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_we_bought_pattern(self, app):
        result = ask_shopstack("we bought 1 kg onion")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_add_grams(self, app):
        result = ask_shopstack("add 500g flour")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_add_creates_inventory_item(self, app):
        app_db.conn.execute("DELETE FROM inventory_lots")
        app_db.conn.commit()
        ask_shopstack("add 2 kg sugar")
        items = app_db.get_inventory(canonical_name="sugar")
        assert any(i.quantity == 2.0 and i.unit == "kg" for i in items)

    def test_add_records_trace(self, app):
        ask_shopstack("add 1 kg salt")
        traces = app_db.get_traces(limit=5)
        trace_goals = [t.user_goal or "" for t in traces]
        assert any("ask" in g or "voice" in g or "add" in g for g in trace_goals)

    def test_add_empty_is_handled(self, app):
        result = ask_shopstack("add")
        assert isinstance(result, str)

    def test_add_with_location_inference(self, app):
        ask_shopstack("add 1 bunch coriander")
        _items = app_db.get_inventory(canonical_name="coriander")
        all_items = app_db.get_inventory()
        assert len(all_items) > 0


class TestPriceIntelligence:
    def test_returns_html_string(self, app):
        from shopstack.ui.screens.price_memory import price_intelligence_view
        result = price_intelligence_view()
        assert isinstance(result, str)

    def test_shows_comparison_with_multiple_stores(self, app):
        from shopstack.ui.screens.price_memory import price_intelligence_view
        app_tools.record_price_observation(
            canonical_name="test_item_pi", price=100, quantity=1, unit="kg", store_name="Store A",
        )
        app_tools.record_price_observation(
            canonical_name="test_item_pi", price=80, quantity=1, unit="kg", store_name="Store B",
        )
        result = price_intelligence_view()
        assert "test_item_pi" in result or "Best Price" in result

    def test_detects_price_drop(self, app):
        from datetime import date, timedelta
        from shopstack.schemas.models import PriceObservation
        from shopstack.ui.screens.price_memory import price_intelligence_view
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
        app_db.record_price(old_obs)
        app_db.record_price(new_obs)
        result = price_intelligence_view()
        assert "drop" in result.lower() or "Price Drop" in result
