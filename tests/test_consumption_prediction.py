"""Tests for consumption prediction and restock prediction logic.

Covers:
  - predict_restock_needs: basic prediction with cadence data
  - predict_restock_needs: urgency classification (overdue, due_today, due_soon)
  - predict_restock_needs: skip items with plenty in stock
  - predict_restock_needs: skip items with insufficient purchase history
  - should_buy with purchase_cadence_days: predictive restock
  - should_buy without cadence: no restock for well-stocked items
  - PreferenceService: add, get, delete signals
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pytest


@dataclass
class MockLot:
    canonical_name: str
    quantity: float = 1.0
    unit: str = "unit"
    status: str = "active"


# ── predict_restock_needs tests ──────────────────────────────────────────────


class TestPredictRestockNeeds:
    @pytest.fixture
    def cadence_data(self):
        today = date.today()
        return {
            "milk": {
                "avg_interval_days": 3,
                "last_bought": today - timedelta(days=3),
                "typical_qty": 1.0,
                "typical_unit": "litre",
                "purchase_count": 5,
            },
            "bread": {
                "avg_interval_days": 4,
                "last_bought": today - timedelta(days=2),
                "typical_qty": 1.0,
                "typical_unit": "unit",
                "purchase_count": 4,
            },
            "rice": {
                "avg_interval_days": 14,
                "last_bought": today - timedelta(days=12),
                "typical_qty": 5.0,
                "typical_unit": "kg",
                "purchase_count": 6,
            },
            "egg": {
                "avg_interval_days": 7,
                "last_bought": today - timedelta(days=10),
                "typical_qty": 6.0,
                "typical_unit": "unit",
                "purchase_count": 8,
            },
        }

    def test_overdue_item(self, cadence_data):
        from shopstack.services.decision_engine import predict_restock_needs
        inventory = [MockLot("milk", quantity=0.2)]
        predictions = predict_restock_needs(cadence_data, inventory, days_ahead=2)
        milk = next((p for p in predictions if p["canonical_name"] == "milk"), None)
        assert milk is not None
        assert milk["urgency"] == "overdue"
        assert milk["days_until_restock"] <= 0

    def test_due_soon_item(self, cadence_data):
        from shopstack.services.decision_engine import predict_restock_needs
        inventory = [MockLot("rice", quantity=1.0)]
        predictions = predict_restock_needs(cadence_data, inventory, days_ahead=2)
        rice = next((p for p in predictions if p["canonical_name"] == "rice"), None)
        assert rice is not None
        assert rice["urgency"] == "due_soon"

    def test_skip_plenty_in_stock(self, cadence_data):
        from shopstack.services.decision_engine import predict_restock_needs
        # Rice has 10kg but typical buy is 5kg → 2x → skip
        inventory = [MockLot("rice", quantity=10.0)]
        predictions = predict_restock_needs(cadence_data, inventory, days_ahead=2)
        rice = next((p for p in predictions if p["canonical_name"] == "rice"), None)
        assert rice is None  # plenty in stock

    def test_skip_insufficient_history(self):
        from shopstack.services.decision_engine import predict_restock_needs
        cadence = {
            "exotic_item": {
                "avg_interval_days": 10,
                "last_bought": date.today(),
                "typical_qty": 1.0,
                "typical_unit": "unit",
                "purchase_count": 1,  # only 1 purchase → skip
            }
        }
        predictions = predict_restock_needs(cadence, [], days_ahead=2)
        assert all(p["canonical_name"] != "exotic_item" for p in predictions)

    def test_empty_cadence(self):
        from shopstack.services.decision_engine import predict_restock_needs
        predictions = predict_restock_needs({}, [])
        assert predictions == []

    def test_sorted_by_urgency(self, cadence_data):
        from shopstack.services.decision_engine import predict_restock_needs
        inventory = [
            MockLot("milk", quantity=0.1),
            MockLot("bread", quantity=0.5),
            MockLot("egg", quantity=0.0),
        ]
        predictions = predict_restock_needs(cadence_data, inventory, days_ahead=2)
        if len(predictions) >= 2:
            # Most urgent (lowest days_until) should come first
            assert predictions[0]["days_until_restock"] <= predictions[-1]["days_until_restock"]

    def test_quantity_at_home_included(self, cadence_data):
        from shopstack.services.decision_engine import predict_restock_needs
        inventory = [MockLot("milk", quantity=0.3)]
        predictions = predict_restock_needs(cadence_data, inventory, days_ahead=2)
        milk = next((p for p in predictions if p["canonical_name"] == "milk"), None)
        assert milk is not None
        assert milk["quantity_at_home"] == 0.3


# ── should_buy with cadence tests ────────────────────────────────────────────


class TestShouldBuyWithCadence:
    def test_predictive_restock_recommendation(self):
        from shopstack.services.decision_engine import should_buy
        result = should_buy(
            canonical_name="milk",
            display_name="Milk",
            quantity_at_home=1.0,  # not low
            unit="litre",
            purchase_cadence_days=3,
            last_purchase_date=date.today() - timedelta(days=2),
        )
        assert result is not None
        assert result.action == "buy"
        assert any("restock" in r.lower() or "cadence" in r.lower() or "usually" in r.lower() for r in result.reasons)

    def test_no_restock_if_not_approaching(self):
        from shopstack.services.decision_engine import should_buy
        result = should_buy(
            canonical_name="rice",
            display_name="Rice",
            quantity_at_home=2.0,
            unit="kg",
            purchase_cadence_days=14,
            last_purchase_date=date.today() - timedelta(days=2),
        )
        # Not approaching restock date (2 days into 14-day cycle)
        assert result is None

    def test_no_restock_without_cadence(self):
        from shopstack.services.decision_engine import should_buy
        result = should_buy(
            canonical_name="rice",
            display_name="Rice",
            quantity_at_home=2.0,
            unit="kg",
            purchase_cadence_days=None,
            last_purchase_date=date.today() - timedelta(days=10),
        )
        # No cadence data → no restock recommendation
        assert result is None


# ── PreferenceService tests ──────────────────────────────────────────────────


class TestPreferenceService:
    @pytest.fixture
    def pref_db(self):
        from shopstack.persistence.database import Database
        import tempfile
        import os

        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        database = Database(path)
        yield database
        os.unlink(path)

    def test_add_and_get_signal(self, pref_db):
        from shopstack.services.preference import PreferenceService
        svc = PreferenceService(pref_db)
        signal = svc.record_signal("milk", "staple", "true", source="test", confidence=1.0)
        assert signal.canonical_name == "milk"
        assert signal.signal_type == "staple"

        signals = svc.get_preferences(canonical_name="milk")
        assert len(signals) >= 1
        assert signals[0].canonical_name == "milk"

    def test_delete_signal(self, pref_db):
        from shopstack.services.preference import PreferenceService
        svc = PreferenceService(pref_db)
        signal = svc.record_signal("onion", "disliked", "avoid", source="test")
        assert svc.delete_signal(signal.signal_id) is True
        # After deletion, should not find it
        signals = svc.get_preferences(canonical_name="onion")
        assert not any(s.signal_id == signal.signal_id for s in signals)

    def test_delete_nonexistent(self, pref_db):
        from shopstack.services.preference import PreferenceService
        svc = PreferenceService(pref_db)
        assert svc.delete_signal("nonexistent_id") is False

    def test_get_staples(self, pref_db):
        from shopstack.services.preference import PreferenceService
        svc = PreferenceService(pref_db)
        svc.record_signal("milk", "staple", "true")
        svc.record_signal("bread", "staple", "true")
        svc.record_signal("bitter_gourd", "disliked", "avoid")
        staples = svc.get_staples()
        assert "milk" in staples
        assert "bread" in staples
        assert "bitter_gourd" not in staples

    def test_get_disliked(self, pref_db):
        from shopstack.services.preference import PreferenceService
        svc = PreferenceService(pref_db)
        svc.record_signal("bitter_gourd", "disliked", "avoid")
        disliked = svc.get_disliked()
        assert "bitter_gourd" in disliked

    def test_get_avoided_includes_wasted(self, pref_db):
        from shopstack.services.preference import PreferenceService
        svc = PreferenceService(pref_db)
        svc.record_signal("coriander", "often_wasted", "true")
        avoided = svc.get_avoided()
        assert "coriander" in avoided
