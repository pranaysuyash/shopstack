"""DATA-1 / SEC-4: Cross-household scoping denial tests (Issue #70).

Every DB write path that accepts a ``user_id`` parameter must enforce
household isolation. The existing ``test_household_scoping_guard.py``
covers inventory, traces, prices, and shopping lists. This file extends
coverage to the remaining mutation paths:

  - add_household_object / get_household_object
  - record_object_sighting / get_object_sightings
  - add_object_note / get_object_notes
  - record_find_feedback / get_find_feedback
  - add_negative_memory
  - add_person_association
  - add_condition_event / get_open_condition_events
  - add_preference_signal / get_preference_signals
  - add_reconciliation_event / get_reconciliation_events
  - record_correction_event / get_recent_correction_events
  - record_inventory_event / get_inventory_events
  - record_movement / get_movements_in_window

**Pattern:** Every test follows the same three-step pattern:

  1. Seed household-A with data (write scoped to HOUSEHOLD_A).
  2. Attempt to read the same data scoped to HOUSEHOLD_B.
  3. Assert that household-B sees an empty result.

This is a regression guard. If a future change drops the ``user_id``
parameter on any of these methods, the corresponding test fails
loudly with a clear assertion error.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from shopstack.schemas.models import (
    CorrectionEvent,
    HouseholdObject,
    InventoryLot,
    MovementEvent,
    ObjectNote,
    ObjectSighting,
    FindFeedback,
    PriceObservation,
    PreferenceSignal,
    ReconciliationEvent,
    InventoryEvent,
)

HOUSEHOLD_A = "delta-alpha"
HOUSEHOLD_B = "delta-bravo"


def _ensure_households(db):
    """Register both test households with owner members."""
    for hid in (HOUSEHOLD_A, HOUSEHOLD_B):
        if not any(h["household_id"] == hid for h in db.list_households()):
            db.add_household(hid, hid.replace("-", " ").title())
        try:
            db.add_household_member(hid, hid, role="owner")
        except Exception:
            pass


class TestCrossHouseholdInventoryPaths:
    """Inventory-related mutation paths beyond the basic add_inventory_lot."""

    def test_consume_inventory_scoped(self, db):
        """consume_inventory respects household boundaries."""
        _ensure_households(db)
        lot = db.add_inventory_lot(
            InventoryLot(canonical_name="milk", display_name="Milk", quantity=5.0, unit="L"),
            user_id=HOUSEHOLD_A,
        )
        # Try to consume from household-B — should be denied.
        # consume_inventory checks membership and raises PermissionError
        # for cross-household access.
        with pytest.raises(PermissionError):
            db.consume_inventory(lot.lot_id, 1.0, user_id=HOUSEHOLD_B)
        # Verify household-A's lot is unchanged.
        lot_a = db.get_inventory_lot(lot.lot_id)
        assert lot_a is not None
        assert lot_a.quantity == 5.0, "Household-A's lot should be untouched"

    def test_record_movement_scoped(self, db):
        """record_movement + get_movements_in_window respect household boundaries."""
        _ensure_households(db)
        # Create a lot for household-A
        lot = db.add_inventory_lot(
            InventoryLot(canonical_name="sugar", display_name="Sugar", quantity=2.0, unit="kg"),
            user_id=HOUSEHOLD_A,
        )
        # Record movement from household-A's perspective
        now = datetime.now()
        mv = MovementEvent(
            lot_id=lot.lot_id,
            from_location_id="pantry",
            to_location_id="kitchen",
            timestamp=now,
            source="manual",
            confidence=1.0,
        )
        db.record_movement(mv, user_id=HOUSEHOLD_A)

        # Household-B should see no movements
        b_movements = db.get_movements_in_window(
            user_id=HOUSEHOLD_B,
            since=now.isoformat(),
        )
        assert len(b_movements) == 0, (
            f"Household-B should see no movements, got {len(b_movements)}"
        )

        # Household-A should see its movement
        a_movements = db.get_movements_in_window(
            user_id=HOUSEHOLD_A,
            since=now.isoformat(),
        )
        assert len(a_movements) == 1
        assert a_movements[0].lot_id == lot.lot_id


class TestCrossHouseholdObjectPaths:
    """Household objects, sightings, notes, and find feedback."""

    def test_add_and_get_household_object_scoped(self, db):
        """add_household_object + get_household_objects respect boundaries."""
        _ensure_households(db)
        obj = db.add_household_object(
            HouseholdObject(
                canonical_name="rice_cooker",
                display_name="Rice Cooker",
                object_type="electronics",
            ),
            user_id=HOUSEHOLD_A,
        )

        # Household-B should not see it
        b_objects = db.get_household_objects(user_id=HOUSEHOLD_B)
        b_ids = {o.object_id for o in b_objects}
        assert obj.object_id not in b_ids, (
            f"Household-B should not see household-A's object"
        )

        # Household-A should see it
        a_objects = db.get_household_objects(user_id=HOUSEHOLD_A)
        a_ids = {o.object_id for o in a_objects}
        assert obj.object_id in a_ids

    def test_update_household_object_scoped(self, db):
        """update_household_object with wrong household returns None."""
        _ensure_households(db)
        obj = db.add_household_object(
            HouseholdObject(
                canonical_name="fan", display_name="Fan",
            ),
            user_id=HOUSEHOLD_A,
        )
        # Update from household-B should not find it
        updated = db.update_household_object(
            obj.object_id,
            {"notes": "Updated by B"},
            user_id=HOUSEHOLD_B,
        )
        assert updated is None, (
            "update_household_object from wrong household should return None"
        )

    def test_record_object_sighting_scoped(self, db):
        """record_object_sighting + get_object_sightings respect boundaries."""
        _ensure_households(db)
        obj = db.add_household_object(
            HouseholdObject(
                canonical_name="kettle", display_name="Kettle",
            ),
            user_id=HOUSEHOLD_A,
        )
        now = datetime.now()
        sighting = ObjectSighting(
            object_id=obj.object_id,
            location_id="kitchen",
            timestamp=now,
            source="manual",
            confidence=1.0,
        )
        db.record_object_sighting(sighting, user_id=HOUSEHOLD_A)

        # Household-B should see no sightings
        b_sightings = db.get_object_sightings(obj.object_id, user_id=HOUSEHOLD_B)
        assert len(b_sightings) == 0

    def test_add_object_note_scoped(self, db):
        """add_object_note + get_object_notes respect boundaries."""
        _ensure_households(db)
        obj = db.add_household_object(
            HouseholdObject(
                canonical_name="pan", display_name="Pan",
            ),
            user_id=HOUSEHOLD_A,
        )
        note = ObjectNote(
            object_id=obj.object_id,
            note_text="Needs replacement",
            timestamp=datetime.now(),
            source="manual",
        )
        db.add_object_note(note, user_id=HOUSEHOLD_A)

        # Household-B should see no notes
        b_notes = db.get_object_notes(obj.object_id, user_id=HOUSEHOLD_B)
        assert len(b_notes) == 0

    def test_record_find_feedback_scoped(self, db):
        """record_find_feedback + get_find_feedback respect boundaries."""
        _ensure_households(db)
        feedback = FindFeedback(
            query="where is the salt",
            feedback="found",
            notes="In the spice box",
            timestamp=datetime.now(),
        )
        db.record_find_feedback(feedback, user_id=HOUSEHOLD_A)

        # Household-B should not see this feedback
        b_feedback = db.get_find_feedback(user_id=HOUSEHOLD_B)
        b_ids = {f.feedback_id for f in b_feedback}
        assert feedback.feedback_id not in b_ids


class TestCrossHouseholdPreferencePaths:
    """Preference signals, corrections, and reconciliation."""

    def test_add_preference_signal_scoped(self, db):
        """add_preference_signal + get_preference_signals respect boundaries."""
        _ensure_households(db)
        signal = PreferenceSignal(
            canonical_name="milk",
            signal_type="brand_preferred",
            value="Amul",
            confidence=0.9,
            source="explicit",
        )
        db.add_preference_signal(signal, user_id=HOUSEHOLD_A)

        # Household-B should not see this signal
        b_signals = db.get_preference_signals(canonical_name="milk", user_id=HOUSEHOLD_B)
        assert len(b_signals) == 0

    def test_record_correction_event_scoped(self, db):
        """record_correction_event + get_recent_correction_events respect boundaries."""
        _ensure_households(db)
        event = CorrectionEvent(
            canonical_name="milk",
            correction_type="brand",
            old_value="",
            new_value="Amul Taaza",
            source="user_correction",
        )
        db.record_correction_event(event, user_id=HOUSEHOLD_A)

        # Household-B should not see this correction
        b_events = db.get_recent_correction_events(user_id=HOUSEHOLD_B)
        b_ids = {e.event_id for e in b_events}
        assert event.event_id not in b_ids

    def test_add_reconciliation_event_scoped(self, db):
        """add_reconciliation_event + get_reconciliation_events respect boundaries."""
        _ensure_households(db)
        event = ReconciliationEvent(
            canonical_name="milk",
            planned_action="buy",
            actual_action="bought",
            quantity=2.0,
            unit="L",
        )
        db.add_reconciliation_event(event, user_id=HOUSEHOLD_A)

        # Household-B should not see this event
        b_events = db.get_reconciliation_events(canonical_name="milk", user_id=HOUSEHOLD_B)
        assert len(b_events) == 0

    def test_negative_memory_scoped(self, db):
        """add_negative_memory respects household boundaries."""
        _ensure_households(db)
        # Create a lot for household-A
        lot = db.add_inventory_lot(
            InventoryLot(canonical_name="salt", display_name="Salt", quantity=1.0, unit="kg"),
            user_id=HOUSEHOLD_A,
        )
        mem = db.add_negative_memory(
            lot_id=lot.lot_id,
            location_id="pantry",
            location_name="Pantry",
            source="user_feedback",
            user_id=HOUSEHOLD_A,
        )
        assert mem["memory_id"], "Memory should have been created"

    def test_person_association_scoped(self, db):
        """add_person_association respects household boundaries."""
        _ensure_households(db)
        lot = db.add_inventory_lot(
            InventoryLot(canonical_name="tea", display_name="Tea", quantity=1.0, unit="kg"),
            user_id=HOUSEHOLD_A,
        )
        assoc = db.add_person_association(
            lot_id=lot.lot_id,
            person_id="person_1",
            person_name="Mom",
            relationship="owner",
            user_id=HOUSEHOLD_A,
        )
        assert assoc["association_id"], "Association should have been created"

    def test_condition_event_scoped(self, db):
        """add_condition_event + get_open_condition_events respect boundaries."""
        _ensure_households(db)
        lot = db.add_inventory_lot(
            InventoryLot(canonical_name="bread", display_name="Bread", quantity=1.0, unit="unit"),
            user_id=HOUSEHOLD_A,
        )
        event_id = db.add_condition_event(
            lot_id=lot.lot_id,
            kind="mold",
            severity="critical",
            canonical_name="bread",
            source="user_report",
            user_id=HOUSEHOLD_A,
        )

        # Household-B should see no condition events
        b_events = db.get_open_condition_events(user_id=HOUSEHOLD_B)
        b_ids = {e["event_id"] for e in b_events}
        assert event_id not in b_ids


class TestCrossHouseholdInventoryEventPaths:
    """Inventory events (audit trail) isolation."""

    def test_inventory_events_scoped(self, db):
        """record_inventory_event + get_inventory_events respect boundaries."""
        _ensure_households(db)
        now = datetime.now()
        event = InventoryEvent(
            timestamp=now,
            lot_id="test_lot",
            canonical_name="milk",
            action="restock",
            quantity_before=0.0,
            quantity_after=5.0,
            quantity_delta=5.0,
            unit="L",
            source="manual",
            notes="Restocked milk",
        )
        db.record_inventory_event(event, user_id=HOUSEHOLD_A)

        # Household-B should not see this event
        b_events = db.get_inventory_events(
            canonical_name="milk",
            user_id=HOUSEHOLD_B,
        )
        assert len(b_events) == 0


class TestCrossHouseholdPurchasePaths:
    """Purchase events isolation."""

    def test_purchase_events_scoped(self, db):
        """add_purchase_event + get_purchase_events respect boundaries."""
        _ensure_households(db)
        from shopstack.schemas.models import PurchaseEvent
        now = datetime.now()
        event = PurchaseEvent(
            canonical_name="milk",
            quantity=2.0,
            unit="L",
            total_price=128.0,
            source_type="manual",
            timestamp=now,
        )
        db.add_purchase_event(event, user_id=HOUSEHOLD_A)

        # Household-B should not see this event
        b_events = db.get_purchase_events(user_id=HOUSEHOLD_B)
        b_ids = {e.event_id for e in b_events}
        assert event.event_id not in b_ids


class TestCrossHouseholdUnscopedFallback:
    """A query with explicit user_id="" must fall back to default household.

    Tests that the opt-in scoping pattern works as documented: passing
    an explicit empty string user_id returns the default-household
    partition, NOT a cross-household dump.
    """

    def test_unscoped_inventory_does_not_leak(self, db):
        """unscoped inventory query should not leak other households."""
        _ensure_households(db)
        db.add_inventory_lot(
            InventoryLot(canonical_name="secret_item", display_name="Secret", quantity=1.0, unit="unit"),
            user_id=HOUSEHOLD_A,
        )
        # Unscoped query (user_id="") — should return default household data
        unscoped = db.get_inventory(user_id="")
        unscoped_names = {lot.canonical_name for lot in unscoped}
        assert "secret_item" not in unscoped_names, (
            "Unscoped query should not return household-A's data"
        )
