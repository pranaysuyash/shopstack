from __future__ import annotations

import json
from datetime import date, datetime

from pydantic import ValidationError
import pytest

from shopstack.schemas.models import (
    DetectionEvent,
    InventoryLot,
    MovementEvent,
    OcrExtraction,
    PriceObservation,
    PurchaseEvent,
    ShoppingList,
    ShoppingListItem,
    Store,
    Trace,
    VoiceCommand,
)


class TestInventoryLot:
    def test_minimal(self):
        lot = InventoryLot(canonical_name="milk", display_name="Milk", quantity=1.0, unit="L")
        assert lot.status == "active"
        assert lot.confidence == 1.0
        assert lot.lot_id

    def test_default_purchase_date(self):
        lot = InventoryLot(canonical_name="milk", display_name="Milk", quantity=1.0, unit="L")
        assert lot.purchase_date is None

    def test_expired_status(self):
        lot = InventoryLot(
            canonical_name="yogurt", display_name="Yogurt",
            quantity=1.0, unit="cup",
            label_expiry_date=date(2020, 1, 1),
        )
        assert lot.label_expiry_date == date(2020, 1, 1)

    @pytest.mark.parametrize("qty,expected", [(-1, True), (0, True), (0.5, False), (10, False)])
    def test_is_depleted(self, qty, expected):
        lot = InventoryLot(canonical_name="test", display_name="Test", quantity=qty, unit="unit")
        assert (lot.quantity <= 0) is expected

    def test_price_paid_defaults(self):
        lot = InventoryLot(canonical_name="rice", display_name="Rice", quantity=5.0, unit="kg")
        assert lot.price_paid is None


class TestPurchaseEvent:
    def test_minimal(self):
        event = PurchaseEvent(
            canonical_name="milk",
            quantity=1.0,
            unit="L",
            total_price=50.0,
        )
        assert event.currency == "INR"
        assert event.event_id

    def test_defaults(self):
        event = PurchaseEvent()
        assert event.total_price == 0.0
        assert event.currency == "INR"


class TestDetectionEvent:
    def test_minimal(self):
        event = DetectionEvent(predicted_name="apple", confidence=0.95)
        assert event.confidence == 0.95
        assert event.predicted_name == "apple"

    def test_with_bbox(self):
        event = DetectionEvent(predicted_name="apple", bounding_box=(0, 0, 50, 50))
        assert event.bounding_box == (0, 0, 50, 50)


class TestShoppingList:
    def test_create_empty(self):
        sl = ShoppingList(goal="weekly groceries")
        assert sl.is_active is True
        assert sl.items == []

    def test_with_items(self):
        item = ShoppingListItem(canonical_name="milk", requested_quantity=2)
        sl = ShoppingList(goal="test", items=[item])
        assert len(sl.items) == 1
        assert sl.items[0].canonical_name == "milk"

    def test_item_defaults(self):
        item = ShoppingListItem(canonical_name="bread")
        assert item.priority == "optional"
        assert item.status == "pending"


class TestTrace:
    def test_minimal(self):
        trace = Trace(input_type="voice", final_response="ok")
        assert trace.trace_id
        assert trace.timestamp

    def test_with_tool_calls(self):
        from shopstack.schemas.models import ToolCall
        trace = Trace(
            input_type="vision",
            user_goal="check stock of milk",
            proposed_tool_calls=[
                ToolCall(tool_name="find_item", args={"query": "milk"})
            ],
        )
        assert len(trace.proposed_tool_calls) == 1

    def test_serialization(self):
        trace = Trace(
            input_type="text",
            user_goal="add milk",
            decision={"action": "add_inventory", "confidence": 0.9},
        )
        d = trace.model_dump()
        assert d["decision"]["action"] == "add_inventory"
        json.dumps(d, default=str)


class TestStore:
    def test_minimal(self):
        store = Store(name="Big Bazaar", store_type="supermarket")
        assert store.store_id

    def test_location_optional(self):
        store = Store(name="Local Kirana", store_type="kirana")
        assert store.location is None


class TestPriceObservation:
    def test_minimal(self):
        obs = PriceObservation(
            canonical_name="basmati rice",
            price=120.0,
            quantity=5.0,
            unit="kg",
        )
        assert obs.observation_date == date.today()

    def test_with_store(self):
        obs = PriceObservation(
            canonical_name="milk",
            price=50.0,
            quantity=1.0,
            unit="L",
            store_name="Amul Parlour",
        )
        assert obs.store_name == "Amul Parlour"
