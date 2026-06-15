"""Tests for unified shopping flow, consumption logging, and substitution UI.

Covers:
  - UnifiedShoppingResult and ItemResult dataclasses
  - run_unified_shopping_flow: parsing, classification, enrichment
  - Unified shopping UI rendering (badge, price, substitution row rendering)
  - Consumption logging: quick_consume, batch_consume_with_context
  - Consumption rate computation
  - Substitution wiring into shopping flow
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from tests.conftest import _remove_db_with_sidecars


# ── Unified Shopping Service Tests ──────────────────────────────────────────


class TestUnifiedShoppingDataclasses:
    def test_item_result_to_dict(self):
        from shopstack.services.unified_shopping import ItemResult
        item = ItemResult(
            canonical_name="milk",
            display_name="Milk",
            decision="buy",
            reason="Running low",
            confidence=0.9,
            market_price=64.0,
            market_available=True,
            deal_score="good",
            deal_reason="Below average",
        )
        d = item.to_dict()
        assert d["canonical_name"] == "milk"
        assert d["decision"] == "buy"
        assert d["market_price"] == 64.0
        assert d["deal_score"] == "good"
        assert d["substitutions"] == []

    def test_item_result_substitutions(self):
        from shopstack.services.unified_shopping import ItemResult
        item = ItemResult(
            canonical_name="broccoli",
            display_name="Broccoli",
            decision="buy",
            reason="Need",
            substitutions=[
                {"canonical_name": "cauliflower", "display_name": "Cauliflower", "type": "category_alternative"},
            ],
        )
        d = item.to_dict()
        assert len(d["substitutions"]) == 1
        assert d["substitutions"][0]["canonical_name"] == "cauliflower"

    def test_unified_result_properties(self):
        from shopstack.services.unified_shopping import ItemResult, UnifiedShoppingResult
        result = UnifiedShoppingResult(
            goal="Weekly groceries",
            items=[
                ItemResult("milk", "Milk", "buy", "need"),
                ItemResult("rice", "Rice", "buy", "need", market_price=100.0),
                ItemResult("onion", "Onion", "skip", "plenty"),
                ItemResult("bread", "Bread", "use_soon", "expiring soon"),
                ItemResult("chips", "Chips", "optional", "nice to have"),
                ItemResult("broccoli", "Broccoli", "buy", "need", market_available=False),
            ],
        )
        assert len(result.buy) == 3
        assert len(result.skip) == 1
        assert len(result.use_soon) == 1
        assert len(result.optional) == 1
        assert len(result.sold_out) == 1
        assert result.estimated_total == 100.0
        assert result.has_substitutions is False

    def test_unified_result_to_dict_summary(self):
        from shopstack.services.unified_shopping import ItemResult, UnifiedShoppingResult
        result = UnifiedShoppingResult(
            goal="Test",
            items=[
                ItemResult("milk", "Milk", "buy", "need", market_price=50.0),
                ItemResult("bread", "Bread", "skip", "plenty"),
            ],
        )
        d = result.to_dict()
        assert d["goal"] == "Test"
        assert d["summary"]["buy"] == 1
        assert d["summary"]["skip"] == 1
        assert d["summary"]["estimated_total"] == 50.0
        assert d["graph_projection"] == {}

    def test_unified_result_to_dict_projection(self):
        from shopstack.services.unified_shopping import UnifiedShoppingResult
        result = UnifiedShoppingResult(goal="Test", graph_projection={"title": "Unified Shopping"})
        d = result.to_dict()
        assert d["graph_projection"]["title"] == "Unified Shopping"

    def test_empty_result(self):
        from shopstack.services.unified_shopping import UnifiedShoppingResult
        result = UnifiedShoppingResult(goal="Empty")
        assert result.buy == []
        assert result.skip == []
        assert result.use_soon == []
        assert result.optional == []
        assert result.sold_out == []
        assert result.estimated_total == 0.0
        assert result.has_substitutions is False


class TestParseItems:
    def test_comma_separated(self):
        from shopstack.services.unified_shopping import _parse_items
        items = _parse_items("milk, bread, tomato")
        assert len(items) == 3
        names = [i["canonical_name"] for i in items]
        assert "milk" in names
        assert "bread" in names

    def test_newline_separated(self):
        from shopstack.services.unified_shopping import _parse_items
        items = _parse_items("milk\nbread\ntomato")
        assert len(items) == 3

    def test_empty_input(self):
        from shopstack.services.unified_shopping import _parse_items
        assert _parse_items("") == []
        assert _parse_items(None) == []

    def test_single_item(self):
        from shopstack.services.unified_shopping import _parse_items
        items = _parse_items("milk")
        assert len(items) == 1
        assert items[0]["canonical_name"] == "milk"


class TestUnifiedFlowIntegration:
    """Integration test for the full unified shopping flow."""

    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.get_price_history.return_value = []
        return db

    @pytest.fixture
    def mock_inventory(self):
        inv = MagicMock()
        # classify_shopping_items will call methods on inventory
        # We need to mock the shopping service instead
        return inv

    def test_flow_returns_result(self, mock_db, mock_inventory):
        from shopstack.services.unified_shopping import run_unified_shopping_flow, UnifiedShoppingResult

        with patch("shopstack.services.shopping.classify_shopping_items") as mock_classify, \
             patch("shopstack.services.unified_shopping._parse_items") as mock_parse:
            mock_plan = MagicMock()
            mock_plan.must_buy = [{"canonical_name": "milk", "reason": "need", "confidence": 0.9, "swiggy_price": 64.0, "swiggy_available": True}]
            mock_plan.optional = []
            mock_plan.use_soon = []
            mock_plan.skipped = []
            mock_classify.return_value = mock_plan
            mock_parse.return_value = [{"canonical_name": "milk", "requested_quantity": 1.0, "unit": "unit"}]

            result = run_unified_shopping_flow("Weekly", "milk", mock_db, mock_inventory)
            assert isinstance(result, UnifiedShoppingResult)
            assert result.goal == "Weekly"
            assert len(result.items) == 1
            assert result.items[0].decision == "buy"
            assert result.items[0].market_price == 64.0

    def test_flow_empty_items(self, mock_db, mock_inventory):
        from shopstack.services.unified_shopping import run_unified_shopping_flow

        with patch("shopstack.services.unified_shopping._parse_items", return_value=[]):
            result = run_unified_shopping_flow("Weekly", "", mock_db, mock_inventory)
            assert result.items == []
            assert result.goal == "Weekly"

    def test_flow_with_substitutions(self, mock_db, mock_inventory):
        from shopstack.services.unified_shopping import run_unified_shopping_flow

        with patch("shopstack.services.shopping.classify_shopping_items") as mock_classify, \
             patch("shopstack.services.unified_shopping._parse_items") as mock_parse, \
             patch("shopstack.services.unified_shopping._enrich_substitutions") as mock_subs:
            mock_plan = MagicMock()
            mock_plan.must_buy = [{"canonical_name": "broccoli", "reason": "need", "swiggy_available": False}]
            mock_plan.optional = []
            mock_plan.use_soon = []
            mock_plan.skipped = []
            mock_classify.return_value = mock_plan
            mock_parse.return_value = [{"canonical_name": "broccoli", "requested_quantity": 1.0, "unit": "unit"}]

            def add_subs(items):
                for item in items:
                    if item.market_available is False:
                        item.substitutions.append({
                            "canonical_name": "cauliflower",
                            "display_name": "Cauliflower",
                            "type": "category_alternative",
                            "reason": "Similar texture",
                            "price_inr": 30.0,
                        })
            mock_subs.side_effect = add_subs

            result = run_unified_shopping_flow("Weekly", "broccoli", mock_db, mock_inventory)
            assert len(result.items) == 1
            assert result.items[0].market_available is False
            assert len(result.items[0].substitutions) == 1
            assert result.items[0].substitutions[0]["canonical_name"] == "cauliflower"


# ── Unified Shopping UI Tests ───────────────────────────────────────────────


class TestUnifiedShoppingUI:
    def test_decision_badge_rendering(self):
        from shopstack.ui.screens.unified_shopping import _decision_badge
        html = _decision_badge("buy")
        assert "BUY" in html
        assert "green" in html

    def test_deal_badge_great(self):
        from shopstack.ui.screens.unified_shopping import _deal_badge
        html = _deal_badge("great", "Best price seen")
        assert "GREAT" in html

    def test_deal_badge_empty(self):
        from shopstack.ui.screens.unified_shopping import _deal_badge
        assert _deal_badge("", "") == ""

    def test_price_str_none(self):
        from shopstack.ui.screens.unified_shopping import _price_str
        assert "--" in _price_str(None)

    def test_price_str_value(self):
        from shopstack.ui.screens.unified_shopping import _price_str
        html = _price_str(64.0)
        assert "64" in html

    def test_availability_tag_in_stock(self):
        from shopstack.ui.screens.unified_shopping import _availability_tag
        html = _availability_tag(True)
        assert "In stock" in html

    def test_availability_tag_sold_out(self):
        from shopstack.ui.screens.unified_shopping import _availability_tag
        html = _availability_tag(False)
        assert "Sold out" in html

    def test_availability_tag_unknown(self):
        from shopstack.ui.screens.unified_shopping import _availability_tag
        assert _availability_tag(None) == ""

    def test_render_item_row_with_substitution(self):
        from shopstack.ui.screens.unified_shopping import _render_item_row
        item = {
            "display_name": "Broccoli",
            "canonical_name": "broccoli",
            "decision": "buy",
            "reason": "need",
            "market_price": 50.0,
            "market_available": False,
            "deal_score": "fair",
            "deal_reason": "Average price",
            "substitutions": [
                {"display_name": "Cauliflower", "canonical_name": "cauliflower", "type": "category_alternative", "price_inr": 30.0, "reason": "Similar"},
            ],
        }
        html = _render_item_row(item)
        assert "Broccoli" in html
        assert "Sold out" in html
        assert "Cauliflower" in html
        assert "Substitutions" in html

    def test_render_item_row_no_market_data(self):
        from shopstack.ui.screens.unified_shopping import _render_item_row
        item = {
            "display_name": "Milk",
            "decision": "buy",
            "reason": "need",
            "market_price": None,
            "market_available": None,
            "substitutions": [],
        }
        html = _render_item_row(item)
        assert "Milk" in html
        assert "--" in html

    def test_render_summary_card(self):
        from shopstack.ui.screens.unified_shopping import _render_summary_card
        data = {
            "summary": {"buy": 5, "skip": 2, "use_soon": 1, "sold_out": 1, "estimated_total": 450.0},
        }
        html = _render_summary_card(data)
        assert "5" in html
        assert "450" in html

    def test_unified_plan_summary_empty(self):
        from shopstack.ui.screens.unified_shopping import unified_plan_summary
        html = unified_plan_summary()
        assert "Run Plan" in html


# ── Consumption Logging Tests ───────────────────────────────────────────────


class TestConsumptionLogging:
    @pytest.fixture
    def temp_db(self):
        from shopstack.persistence.database import Database
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database = Database(path)
        yield database
        _remove_db_with_sidecars(path)

    def test_quick_consume_no_lot(self):
        from shopstack.ui.screens.consumption import quick_consume
        result = quick_consume("", 1.0)
        assert "No lot ID" in result

    def test_quick_consume_zero_qty(self):
        from shopstack.ui.screens.consumption import quick_consume
        result = quick_consume("abc123", 0.0)
        assert "positive" in result

    def test_batch_consume_empty(self):
        from shopstack.ui.screens.consumption import batch_consume_with_context
        result = batch_consume_with_context("", "lunch", "")
        assert "at least one" in result.lower() or "no valid" in result.lower()

    def test_batch_consume_waste_context(self):
        """Test that waste flag is properly passed through."""
        from shopstack.ui.screens.consumption import batch_consume_with_context
        with patch("shopstack.ui.screens.consumption.tools") as mock_tools:
            mock_tools.consume_inventory_item.return_value = {
                "remaining": 0.5,
                "canonical_name": "milk",
            }
            result = batch_consume_with_context("abc123: 0.5", "dinner", "waste")
            assert "waste" in result.lower() or "wasted" in result.lower()

    def test_batch_consume_normal_context(self):
        from shopstack.ui.screens.consumption import batch_consume_with_context
        with patch("shopstack.ui.screens.consumption.tools") as mock_tools:
            mock_tools.consume_inventory_item.return_value = {
                "remaining": 1.0,
                "canonical_name": "bread",
            }
            result = batch_consume_with_context("abc123", "breakfast", "")
            assert "breakfast" in result.lower()


class TestConsumptionRates:
    def test_compute_rates_insufficient_data(self):
        """With fewer than 2 events per item, no rates should be returned."""
        with patch("shopstack.ui.screens.consumption.db") as mock_db:
            mock_event = MagicMock()
            mock_event.action = "consumed"
            mock_event.canonical_name = "milk"
            mock_event.quantity_delta = -1.0
            mock_event.timestamp = "2024-01-01T10:00:00"
            mock_db.get_inventory_events.return_value = [mock_event]
            from shopstack.ui.screens.consumption import _compute_consumption_rates
            rates = _compute_consumption_rates("user1")
            assert rates == []

    def test_compute_rates_with_data(self):
        with patch("shopstack.ui.screens.consumption.db") as mock_db:
            events = []
            for i in range(5):
                ev = MagicMock()
                ev.action = "consumed"
                ev.canonical_name = "milk"
                ev.quantity_delta = -1.0
                ev.timestamp = f"2024-01-{10+i:02d}T10:00:00"
                events.append(ev)
            mock_db.get_inventory_events.return_value = events
            from shopstack.ui.screens.consumption import _compute_consumption_rates
            rates = _compute_consumption_rates("user1")
            assert len(rates) == 1
            assert rates[0]["canonical_name"] == "milk"
            assert rates[0]["daily_rate"] > 0
            assert rates[0]["events"] == 5

    def test_consumption_rates_html(self):
        with patch("shopstack.ui.screens.consumption._compute_consumption_rates") as mock_rates:
            mock_rates.return_value = [
                {
                    "canonical_name": "milk",
                    "display_name": "Milk",
                    "total_consumed": 5.0,
                    "days_tracked": 4,
                    "daily_rate": 1.25,
                    "events": 5,
                },
            ]
            from shopstack.ui.screens.consumption import consumption_rates
            html = consumption_rates()
            assert "Milk" in html
            assert "1.25" in html


class TestConsumptionDashboard:
    def test_empty_inventory(self):
        with patch("shopstack.ui.screens.consumption.db") as mock_db:
            mock_db.get_inventory.return_value = []
            mock_db.get_inventory_events.return_value = []
            mock_db.get_locations.return_value = []
            from shopstack.ui.screens.consumption import consumption_dashboard
            grid, history, rates = consumption_dashboard()
            assert "No active inventory" in grid

    def test_with_active_items(self):
        with patch("shopstack.ui.screens.consumption.db") as mock_db:
            lot = MagicMock()
            lot.lot_id = "abc123"
            lot.canonical_name = "milk"
            lot.display_name = "Milk"
            lot.quantity = 2.0
            lot.unit = "litre"
            lot.status = "active"
            lot.storage_location_id = "fridge"
            lot.purchase_date = date.today()
            mock_db.get_inventory.return_value = [lot]
            mock_db.get_inventory_events.return_value = []
            mock_db.get_locations.return_value = [MagicMock(location_id="fridge", name="Fridge")]
            from shopstack.ui.screens.consumption import consumption_dashboard
            grid, history, rates = consumption_dashboard()
            assert "Milk" in grid
            assert "Quick Consume" in grid


# ── Substitution Engine Wiring Tests ────────────────────────────────────────


class TestSubstitutionWiring:
    def test_find_substitutions_import(self):
        from shopstack.services.substitution import find_substitutions
        assert callable(find_substitutions)

    def test_substitution_map_coverage(self):
        from shopstack.services.substitution import _SUBSTITUTE_MAP
        assert "broccoli" in _SUBSTITUTE_MAP
        assert "coriander" in _SUBSTITUTE_MAP
        assert len(_SUBSTITUTE_MAP) >= 25  # At least 25 item mappings

    def test_substitution_suggestions_structure(self):
        from shopstack.services.substitution import SubstitutionSuggestion
        s = SubstitutionSuggestion(
            original_canonical="broccoli",
            substitute_canonical="cauliflower",
            substitute_display="Cauliflower",
            substitution_type="category_alternative",
            reason="Similar texture and cooking method",
            confidence=0.8,
            price_inr=30.0,
            price_per_kg=30.0,
        )
        assert s.substitute_canonical == "cauliflower"
        assert s.substitution_type == "category_alternative"
        assert s.confidence == 0.8

    def test_enrich_substitutions_sold_out(self):
        """Test that sold-out items get substitutions enriched."""
        from shopstack.services.unified_shopping import ItemResult, _enrich_substitutions
        items = [
            ItemResult("broccoli", "Broccoli", "buy", "need", market_available=False),
            ItemResult("milk", "Milk", "buy", "need", market_available=True, market_price=64.0),
        ]
        with patch("shopstack.services.substitution.find_substitutions") as mock_find, \
             patch("shopstack.market.sources.swiggy.load_snapshot", return_value=MagicMock()):
            from shopstack.services.substitution import SubstitutionResult, SubstitutionSuggestion
            mock_find.return_value = SubstitutionResult(
                original_canonical="broccoli",
                original_display="Broccoli",
                suggestions=[
                    SubstitutionSuggestion("broccoli", "cauliflower", "Cauliflower", "category_alternative", "Similar", 0.8, price_inr=30.0, price_per_kg=30.0),
                ],
            )
            _enrich_substitutions(items)

        assert len(items[0].substitutions) == 1
        assert items[0].substitutions[0]["canonical_name"] == "cauliflower"
        assert len(items[1].substitutions) == 0  # milk is available, no subs needed

    def test_enrich_substitutions_no_snapshot(self):
        """When snapshot fails, substitutions should be skipped gracefully."""
        from shopstack.services.unified_shopping import ItemResult, _enrich_substitutions
        items = [ItemResult("broccoli", "Broccoli", "buy", "need", market_available=False)]
        with patch("shopstack.market.sources.swiggy.load_snapshot", side_effect=Exception("no data")):
            _enrich_substitutions(items)
        assert items[0].substitutions == []


class TestEnrichDealScores:
    def test_deal_score_applied(self):
        from shopstack.services.unified_shopping import ItemResult, _enrich_deal_scores

        items = [ItemResult("milk", "Milk", "buy", "need", market_price=50.0, market_price_per_kg=50.0)]
        mock_db = MagicMock()

        with patch("shopstack.services.price_memory.PriceMemoryService") as mock_pm_cls:
            mock_pm = MagicMock()
            mock_pm_cls.return_value = mock_pm
            mock_deal = MagicMock()
            mock_deal.score = "good"
            mock_deal.reason = "10% below average"
            mock_pm.score_deal.return_value = mock_deal

            _enrich_deal_scores(items, mock_db)

        assert items[0].deal_score == "good"
        assert items[0].deal_reason == "10% below average"

    def test_deal_score_skips_no_price(self):
        from shopstack.services.unified_shopping import ItemResult, _enrich_deal_scores
        items = [ItemResult("milk", "Milk", "buy", "need", market_price=None)]
        mock_db = MagicMock()
        _enrich_deal_scores(items, mock_db)
        assert items[0].deal_score == ""

    def test_deal_score_handles_error(self):
        from shopstack.services.unified_shopping import ItemResult, _enrich_deal_scores
        items = [ItemResult("milk", "Milk", "buy", "need", market_price=50.0)]
        with patch("shopstack.services.price_memory.PriceMemoryService", side_effect=Exception("no db")):
            _enrich_deal_scores(items, MagicMock())
        assert items[0].deal_score == ""
