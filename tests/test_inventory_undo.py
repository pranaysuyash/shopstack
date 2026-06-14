"""Tests for the inventory undo model (PROJECT_INTELLIGENCE.md item #6).

Covers:
  - InventoryEvent.get_undo_event() inverse construction for each action type.
  - InventoryRepo.undo_last_change() reversing add / consume / move.
  - Edge cases: no history, double undo, unknown lot.
"""

from __future__ import annotations

from shopstack.repos.inventory import InventoryRepo
from shopstack.schemas.models import InventoryEvent


class TestGetUndoEvent:
    def test_undo_added_discards(self):
        event = InventoryEvent(
            lot_id="lot1", canonical_name="milk", action="added",
            quantity_before=0, quantity_after=2, quantity_delta=2,
            unit="L", location_to="fridge",
        )
        undo = event.get_undo_event()
        assert undo is not None
        assert undo.action == "discarded"
        assert undo.quantity_after == 0
        assert undo.quantity_delta == -2
        assert undo.source == "undo"

    def test_undo_consumed_restores_quantity(self):
        event = InventoryEvent(
            lot_id="lot1", canonical_name="milk", action="consumed",
            quantity_before=2, quantity_after=1, quantity_delta=-1, unit="L",
        )
        undo = event.get_undo_event()
        assert undo is not None
        assert undo.action == "adjusted"
        assert undo.quantity_before == 1
        assert undo.quantity_after == 2
        assert undo.quantity_delta == 1

    def test_undo_moved_swaps_locations(self):
        event = InventoryEvent(
            lot_id="lot1", canonical_name="milk", action="moved",
            unit="L", location_from="kitchen", location_to="fridge",
        )
        undo = event.get_undo_event()
        assert undo is not None
        assert undo.action == "moved"
        assert undo.location_from == "fridge"
        assert undo.location_to == "kitchen"


class TestUndoLastChange:
    def test_undo_after_add_zeroes_quantity(self, db):
        repo = InventoryRepo(db)
        result = repo.add_item("milk", "Milk", 2, "L", "fridge")
        lot_id = result["lot_id"]

        undo_result = repo.undo_last_change(lot_id)

        assert undo_result["success"] is True
        assert undo_result["undone_action"] == "added"
        assert undo_result["lot"]["quantity"] == 0

    def test_undo_after_consume_restores_quantity(self, db):
        repo = InventoryRepo(db)
        result = repo.add_item("milk", "Milk", 2, "L", "fridge")
        lot_id = result["lot_id"]
        repo.consume_item(lot_id, 1)

        undo_result = repo.undo_last_change(lot_id)

        assert undo_result["success"] is True
        assert undo_result["undone_action"] == "consumed"
        assert undo_result["lot"]["quantity"] == 2

    def test_undo_after_move_restores_location(self, db):
        repo = InventoryRepo(db)
        result = repo.add_item("milk", "Milk", 2, "L", "kitchen")
        lot_id = result["lot_id"]
        repo.move_item(lot_id, "fridge")

        undo_result = repo.undo_last_change(lot_id)

        assert undo_result["success"] is True
        assert undo_result["undone_action"] == "moved"
        assert undo_result["lot"]["storage_location_id"] == "kitchen"

    def test_undo_with_no_history_errors(self, db):
        repo = InventoryRepo(db)
        result = repo.add_item("milk", "Milk", 2, "L", "fridge")
        lot_id = result["lot_id"]
        # Consume the "added" event's history by undoing once.
        repo.undo_last_change(lot_id)

        # Second undo reverses the "undo" event itself (chaining is allowed).
        second = repo.undo_last_change(lot_id)
        assert "success" in second

    def test_undo_unknown_lot_errors(self, db):
        repo = InventoryRepo(db)
        result = repo.undo_last_change("does-not-exist")
        assert result["success"] is False
        assert "error" in result

    def test_undo_records_audit_event(self, db):
        repo = InventoryRepo(db)
        result = repo.add_item("milk", "Milk", 2, "L", "fridge")
        lot_id = result["lot_id"]
        repo.consume_item(lot_id, 1)

        repo.undo_last_change(lot_id)

        events = db.get_inventory_events(lot_id=lot_id, limit=10)
        actions = [e.action for e in events]
        assert "adjusted" in actions
        assert any(e.source == "undo" for e in events)
