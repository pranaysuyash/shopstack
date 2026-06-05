from __future__ import annotations

from datetime import date

import pytest

from shopstack.schemas.models import (
    HouseholdLocation,
    InventoryLot,
    MovementEvent,
    PriceObservation,
    PurchaseEvent,
    ShoppingList,
    ShoppingListItem,
    Trace,
)


class TestDatabaseInit:
    def test_db_creates_tables(self, db):
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = [r[0] for r in tables]
        assert "inventory_lots" in names
        assert "shopping_lists" in names
        assert "shopping_list_items" in names
        assert "household_locations" in names

    def test_seeds_locations(self, db):
        locs = db.get_locations()
        assert len(locs) >= 18

    def test_seeds_specific_locations(self, db):
        names = [l.name for l in db.get_locations()]
        assert "Kitchen" in names
        assert "Fridge" in names
        assert "Pantry" in names
        assert "Bathroom" in names


class TestInventoryCRUD:
    def test_add_lot(self, db):
        lot = InventoryLot(canonical_name="milk", display_name="Milk", quantity=2.0, unit="L", storage_location_id="fridge")
        db.add_inventory_lot(lot)
        loaded = db.get_inventory_lot(lot.lot_id)
        assert loaded is not None
        assert loaded.canonical_name == "milk"
        assert loaded.quantity == 2.0

    def test_get_inventory_all(self, db):
        db.add_inventory_lot(InventoryLot(canonical_name="a", display_name="A", quantity=1.0, unit="unit"))
        db.add_inventory_lot(InventoryLot(canonical_name="b", display_name="B", quantity=2.0, unit="unit"))
        items = db.get_inventory()
        assert len(items) == 2

    def test_get_inventory_filter_by_status(self, db):
        lot = InventoryLot(canonical_name="test", display_name="Test", quantity=0, unit="unit")
        db.add_inventory_lot(lot)
        db.consume_inventory(lot.lot_id, 0)
        used = db.get_inventory(status="used")
        assert len(used) == 1

    def test_update_lot(self, db):
        lot = InventoryLot(canonical_name="rice", display_name="Rice", quantity=5.0, unit="kg")
        db.add_inventory_lot(lot)
        updated = db.update_inventory_lot(lot.lot_id, {"quantity": 3.0})
        assert updated is not None
        assert updated.quantity == 3.0

    def test_consume_inventory(self, db):
        lot = InventoryLot(canonical_name="dal", display_name="Dal", quantity=2.0, unit="kg")
        db.add_inventory_lot(lot)
        updated = db.consume_inventory(lot.lot_id, 0.5)
        assert updated is not None
        assert updated.quantity == 1.5

    def test_consume_to_zero_marks_used(self, db):
        lot = InventoryLot(canonical_name="eggs", display_name="Eggs", quantity=1.0, unit="dozen")
        db.add_inventory_lot(lot)
        updated = db.consume_inventory(lot.lot_id, 1.0)
        assert updated.status == "used"

    def test_consume_more_than_available(self, db):
        lot = InventoryLot(canonical_name="butter", display_name="Butter", quantity=0.25, unit="kg")
        db.add_inventory_lot(lot)
        updated = db.consume_inventory(lot.lot_id, 1.0)
        assert updated is not None
        assert updated.quantity == 0

    def test_lot_with_category(self, db):
        lot = InventoryLot(canonical_name="chicken", display_name="Chicken", quantity=1.0, unit="kg", category="meat")
        db.add_inventory_lot(lot)
        loaded = db.get_inventory_lot(lot.lot_id)
        assert loaded.category == "meat"


class TestLocationCRUD:
    def test_get_location(self, db):
        loc = db.get_location("fridge")
        assert loc is not None
        assert loc.name == "Fridge"
        assert loc.location_type == "fridge"

    def test_get_location_unknown(self, db):
        loc = db.get_location("nonexistent")
        assert loc is None

    def test_get_locations_by_type(self, db):
        fridge_locs = [l for l in db.get_locations() if l.location_type == "fridge"]
        assert len(fridge_locs) >= 1


class TestMovementCRUD:
    def test_record_movement(self, db):
        lot = InventoryLot(canonical_name="milk", display_name="Milk", quantity=1.0, unit="L")
        db.add_inventory_lot(lot)
        movement = MovementEvent(
            lot_id=lot.lot_id,
            from_location_id="kitchen",
            to_location_id="fridge",
            source="manual",
        )
        db.record_movement(movement)
        assert movement.movement_id

    def test_get_movements(self, db):
        lot = InventoryLot(canonical_name="juice", display_name="Juice", quantity=1.0, unit="L")
        db.add_inventory_lot(lot)
        db.record_movement(MovementEvent(lot_id=lot.lot_id, to_location_id="fridge", source="manual"))
        db.record_movement(MovementEvent(lot_id=lot.lot_id, to_location_id="pantry", source="manual"))
        movements = db.get_movements_for_lot(lot.lot_id)
        assert len(movements) == 2


class TestPriceCRUD:
    def test_record_price(self, db):
        obs = PriceObservation(
            canonical_name="basmati rice",
            price=120.0,
            quantity=5.0,
            unit="kg",
            store_name="Big Bazaar",
        )
        db.record_price(obs)

    def test_get_price_history(self, db):
        db.record_price(PriceObservation(canonical_name="milk", price=50.0, quantity=1.0, unit="L"))
        db.record_price(PriceObservation(canonical_name="milk", price=55.0, quantity=1.0, unit="L"))
        history = db.get_price_history("milk")
        assert len(history) == 2


class TestShoppingListCRUD:
    def test_create_list(self, db):
        sl = db.create_shopping_list(goal="weekly groceries")
        assert sl.list_id
        assert sl.is_active is True

    def test_add_item_to_list(self, db):
        sl = db.create_shopping_list()
        item = ShoppingListItem(canonical_name="milk", requested_quantity=2)
        db.add_list_item(sl.list_id, item)
        loaded = db.get_active_shopping_list()
        assert loaded is not None
        assert len(loaded.items) == 1
        assert loaded.items[0].canonical_name == "milk"

    def test_get_active_list(self, db):
        sl1 = db.create_shopping_list(goal="first")
        db.add_list_item(sl1.list_id, ShoppingListItem(canonical_name="a"))
        loaded = db.get_active_shopping_list()
        assert loaded is not None
        assert loaded.goal == "first"

    def test_mark_list_complete(self, db):
        sl = db.create_shopping_list()
        db.mark_list_complete(sl.list_id)
        loaded = db.get_active_shopping_list()
        assert loaded is None

    def test_update_list_item(self, db):
        sl = db.create_shopping_list()
        item = ShoppingListItem(canonical_name="milk")
        db.add_list_item(sl.list_id, item)
        db.update_list_item(item.list_item_id, {"status": "bought"})
        loaded = db.get_active_shopping_list()
        assert loaded is not None
        assert loaded.items[0].status == "bought"


class TestPurchaseCRUD:
    def test_record_purchase(self, db):
        event = PurchaseEvent(
            canonical_name="milk", quantity=1.0, unit="L", total_price=50.0,
            store_name="Big Bazaar",
        )
        db.add_purchase_event(event)

    def test_get_purchases(self, db):
        db.add_purchase_event(PurchaseEvent(canonical_name="a", quantity=1.0, unit="unit", total_price=10.0))
        db.add_purchase_event(PurchaseEvent(canonical_name="b", quantity=1.0, unit="unit", total_price=20.0))
        purchases = db.get_purchase_events()
        assert len(purchases) == 2


class TestTraceCRUD:
    def test_save_trace(self, db):
        trace = Trace(input_type="voice", final_response="added milk")
        db.save_trace(trace)

    def test_get_traces(self, db):
        for i in range(3):
            db.save_trace(Trace(input_type="text", final_response=f"trace {i}"))
        traces = db.get_traces(limit=10)
        assert len(traces) == 3

    def test_trace_limit(self, db):
        for i in range(5):
            db.save_trace(Trace(input_type="text", final_response=f"trace {i}"))
        traces = db.get_traces(limit=2)
        assert len(traces) == 2
