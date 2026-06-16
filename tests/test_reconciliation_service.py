from __future__ import annotations

from shopstack.services.reconciliation import (
    ReconciliationResult,
    build_correction_event,
    reconcile_shopping_trip,
)


def test_reconciliation_empty_actuals():
    result = reconcile_shopping_trip(
        planned_items=[{"canonical_name": "milk", "action": "buy"}],
        actual_items=[],
    )
    assert result.count == 0
    assert result.success is True
    assert result.bought_count == 0


def test_reconciliation_bought_item():
    result = reconcile_shopping_trip(
        planned_items=[{"canonical_name": "milk", "action": "buy"}],
        actual_items=[{"canonical_name": "milk", "action": "bought", "quantity": 2.0}],
    )
    assert result.count == 1
    assert result.bought_count == 1
    assert result.skipped_count == 0
    assert result.events[0].actual_action == "bought"
    assert result.events[0].quantity == 2.0


def test_reconciliation_skipped_item():
    result = reconcile_shopping_trip(
        planned_items=[{"canonical_name": "milk", "action": "buy"}],
        actual_items=[{"canonical_name": "milk", "action": "skipped"}],
    )
    assert result.skipped_count == 1
    assert result.bought_count == 0


def test_reconciliation_substituted_item():
    result = reconcile_shopping_trip(
        planned_items=[{"canonical_name": "onion", "action": "buy"}],
        actual_items=[{"canonical_name": "onion", "action": "substituted", "substituted_with": "red_onion", "quantity": 1.0}],
    )
    assert result.substituted_count == 1
    assert result.events[0].substituted_with == "red_onion"


def test_reconciliation_inventory_scopes_to_user_id(db, tool_registry):
    # Phase 11 write paths verify household membership. ``house_a`` /
    # ``house_b`` are test-only households that must be pre-registered
    # before ``reconcile_shopping_trip`` can persist inventory as ``house_a``.
    for hid in ("house_a", "house_b"):
        db.add_household(hid, f"Test {hid}")
        db.add_household_member(hid, hid, role="owner")
    result = reconcile_shopping_trip(
        planned_items=[{"canonical_name": "bread", "action": "buy"}],
        actual_items=[{"canonical_name": "bread", "action": "bought", "quantity": 1.0}],
        tools=tool_registry,
        database=db,
        user_id="house_a",
    )
    assert result.count == 1

    assert len(db.get_inventory(canonical_name="bread", user_id="house_a")) == 1
    assert len(db.get_inventory(canonical_name="bread", user_id="house_b")) == 0
    assert len(db.get_price_history("bread", user_id="house_a")) == 1
    assert len(db.get_price_history("bread", user_id="house_b")) == 0
    assert len(db.get_reconciliation_events(canonical_name="bread", user_id="house_a")) == 1
    assert len(db.get_reconciliation_events(canonical_name="bread", user_id="house_b")) == 0


def test_reconciliation_with_tools_and_db(db, tool_registry):
    result = reconcile_shopping_trip(
        planned_items=[{"canonical_name": "bread", "action": "buy"}],
        actual_items=[{"canonical_name": "bread", "action": "bought", "quantity": 1.0, "price_paid": 40.0}],
        tools=tool_registry,
        database=db,
    )
    assert result.count == 1
    assert len(result.inventory_updates) == 1
    assert result.inventory_updates[0]["action"] == "added"

    # Verify reconciliation event is persisted
    db_events = db.get_reconciliation_events(limit=5)
    assert len(db_events) == 1
    assert db_events[0].canonical_name == "bread"
    assert db_events[0].actual_action == "bought"

    # Verify price observation is persisted
    db_prices = db.get_price_history("bread")
    assert len(db_prices) == 1
    assert db_prices[0].price == 40.0


def test_reconciliation_to_dict():
    result = reconcile_shopping_trip(
        planned_items=[],
        actual_items=[{"canonical_name": "rice", "action": "bought"}],
    )
    d = result.to_dict()
    assert "trip_id" in d
    assert d["events_count"] == 1
    assert d["bought"] == 1


def test_reconciliation_result_defaults():
    result = ReconciliationResult(trip_id="test")
    assert result.events == []
    assert result.inventory_updates == []
    assert result.price_observations == []
    assert result.errors == []
    assert result.success is True
    assert result.count == 0


class TestReconciliationUndoRegistrations:
    """Verify undo ledger entries are created during reconciliation when
    tools+database are provided, and suppressed when they aren"t."""

    def test_undo_registered_for_bought_item_inventory_and_price(self, db, tool_registry):
        """A bought item should register both add_inventory_lot and
        record_price undo entries."""
        from shopstack.services.undo_ledger import reset_ledger, get_ledger
        reset_ledger()
        ledger = get_ledger()

        for hid in ("house_a",):
            db.add_household(hid, f"Test {hid}")
            db.add_household_member(hid, hid, role="owner")

        reconcile_shopping_trip(
            planned_items=[{"canonical_name": "bread", "action": "buy"}],
            actual_items=[{
                "canonical_name": "bread", "action": "bought",
                "quantity": 2.0, "unit": "loaf", "price_paid": 50.0,
            }],
            tools=tool_registry,
            database=db,
            user_id="house_a",
        )

        recent = ledger.recent("house_a", limit=10)
        kinds = [e.kind for e in recent]
        assert "add_inventory_lot" in kinds, (
            f"Expected add_inventory_lot undo entry, got {kinds}"
        )
        assert "record_price" in kinds, (
            f"Expected record_price undo entry, got {kinds}"
        )

        # Check the add_inventory_lot entry carries the right metadata
        inv_entries = [e for e in recent if e.kind == "add_inventory_lot"]
        assert any(
            e.before.get("canonical_name") == "bread"
            and e.after.get("quantity") == 2.0
            and "after trip" in e.description
            for e in inv_entries
        ), "add_inventory_lot entry missing expected fields"

        # Check the record_price entry carries the right metadata
        price_entries = [e for e in recent if e.kind == "record_price"]
        assert any(
            e.before.get("canonical_name") == "bread"
            and e.after.get("price") == 50.0
            and e.after.get("quantity") == 2.0
            and "50.00" in e.description
            for e in price_entries
        ), "record_price entry missing expected fields"

    def test_undo_registered_for_substitution(self, db, tool_registry):
        """A substituted item should register an add_inventory_lot undo
        entry for the substituted-with item."""
        from shopstack.services.undo_ledger import reset_ledger, get_ledger
        reset_ledger()
        ledger = get_ledger()

        for hid in ("house_b",):
            db.add_household(hid, f"Test {hid}")
            db.add_household_member(hid, hid, role="owner")

        reconcile_shopping_trip(
            planned_items=[{"canonical_name": "onion", "action": "buy"}],
            actual_items=[{
                "canonical_name": "onion", "action": "substituted",
                "substituted_with": "red_onion", "quantity": 1.0,
            }],
            tools=tool_registry,
            database=db,
            user_id="house_b",
        )

        recent = ledger.recent("house_b", limit=10)
        assert any(
            e.kind == "add_inventory_lot"
            and e.before.get("canonical_name") == "red_onion"
            and "substitution" in e.description
            for e in recent
        ), "Substitution undo entry missing or has wrong fields"

    def test_no_undo_entries_when_tools_not_provided(self):
        """When tools+database are None (no persistence), no undo
        entries should be created."""
        from shopstack.services.undo_ledger import reset_ledger, get_ledger
        reset_ledger()
        ledger = get_ledger()

        reconcile_shopping_trip(
            planned_items=[{"canonical_name": "milk", "action": "buy"}],
            actual_items=[{
                "canonical_name": "milk", "action": "bought",
                "quantity": 1.0, "price_paid": 30.0,
            }],
        )

        assert ledger.recent("house_missing", limit=10) == []
        assert ledger.recent("", limit=10) == []

    def test_undo_registered_for_price_without_explicit_price(self, db, tool_registry):
        """Even when no price_paid is provided, a record_price undo
        entry is still created (price defaults to 0 or planned_price)."""
        from shopstack.services.undo_ledger import reset_ledger, get_ledger
        reset_ledger()
        ledger = get_ledger()

        for hid in ("house_c",):
            db.add_household(hid, f"Test {hid}")
            db.add_household_member(hid, hid, role="owner")

        reconcile_shopping_trip(
            planned_items=[{"canonical_name": "rice", "action": "buy", "market_price": 60.0}],
            actual_items=[{
                "canonical_name": "rice", "action": "bought",
                "quantity": 5.0,
                # no price_paid — falls back to planned_price
            }],
            tools=tool_registry,
            database=db,
            user_id="house_c",
        )

        recent = ledger.recent("house_c", limit=10)
        price_entries = [e for e in recent if e.kind == "record_price"]
        assert len(price_entries) >= 1
        # price should be the planned_price (60.0) since no price_paid
        assert price_entries[0].after.get("price") == 60.0, (
            f"Expected 60.0 (planned_price fallback), got {price_entries[0].after.get('price')}"
        )
        assert price_entries[0].after.get("quantity") == 5.0


def test_build_correction_event():
    event = build_correction_event(
        canonical_name="tomato",
        correction_type="alias",
        old_value="tomato",
        new_value="hybrid tomato",
    )
    assert event["canonical_name"] == "tomato"
    assert event["correction_type"] == "alias"
    assert event["old_value"] == "tomato"
    assert event["new_value"] == "hybrid tomato"
    assert "event_id" in event
