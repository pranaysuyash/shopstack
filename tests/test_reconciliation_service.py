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
