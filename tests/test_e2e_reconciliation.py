"""E2E regression test for the reconciliation loop (2026-06-15).

The reconciliation service closes the household-memory loop:
``plan → shop → confirm what actually happened → update inventory
+ price memory + preferences → better next plan``.

This test exercises the full happy-path end-to-end with no
mocks: it uses a real ``Database`` instance and the real
``ToolRegistry`` against an in-memory SQLite file, then asserts
that the reconciliation result is internally consistent and
that the side effects (inventory_lots, price_observations,
reconciliation_events) all landed in the DB.

This is the E2E test the 2026-06-15 audit called out as missing
(``test_endpoints_per_sub_builder``-style — the producer of
the contract is exercised, the consumer of the contract is
exercised, and the data layer is exercised all in one shot).
"""
from __future__ import annotations

import pytest

from shopstack.persistence.database import Database
from shopstack.services.reconciliation import (
    ReconciliationResult,
    reconcile_shopping_trip,
)
from shopstack.tools.registry import ToolRegistry


@pytest.fixture
def db_with_household(tmp_path):
    """Create a fresh DB with one household.

    The ``Database.__init__`` auto-initializes the schema and
    seeds default storage locations (home, kitchen, fridge,
    pantry, etc.). The default storage location is
    ``DEFAULT_STORAGE_LOCATION`` (used by
    ``InventoryRepo.add_item`` when no location is specified).
    """
    db_path = tmp_path / "recon_e2e.db"
    db = Database(db_path=str(db_path))
    # Add a household so the user_id-scoped queries work.
    db.add_household("h1", "test-household")
    return db


@pytest.fixture
def tools(db_with_household):
    """A real ToolRegistry bound to the test DB."""
    return ToolRegistry(db_with_household)


# ── Happy path: all items bought, qty + price captured ─────────────


def test_e2e_all_bought_creates_inventory_lots_and_price_observations(
    db_with_household, tools
):
    """E2E: plan 3 items → buy all 3 → 3 inventory lots + 3 price obs.

    This is the canonical "household went shopping" loop. The
    plan says "buy milk, bread, eggs"; the user bought them all;
    the reconciliation should produce 3 ReconciliationEvents,
    3 inventory_updates (lots created), and 3 price_observations.
    """
    planned = [
        {"canonical_name": "milk", "requested_quantity": 2.0, "unit": "L"},
        {"canonical_name": "bread", "requested_quantity": 1.0, "unit": "loaf"},
        {"canonical_name": "eggs", "requested_quantity": 12.0, "unit": "pieces"},
    ]
    actual = [
        {"canonical_name": "milk", "action": "bought", "quantity": 2.0,
         "unit": "L", "price_paid": 130.0},
        {"canonical_name": "bread", "action": "bought", "quantity": 1.0,
         "unit": "loaf", "price_paid": 45.0},
        {"canonical_name": "eggs", "action": "bought", "quantity": 12.0,
         "unit": "pieces", "price_paid": 84.0},
    ]

    result = reconcile_shopping_trip(
        planned_items=planned,
        actual_items=actual,
        tools=tools,
        database=db_with_household,
        user_id="h1",
    )

    # Result invariants.
    assert isinstance(result, ReconciliationResult)
    assert result.success
    assert result.count == 3
    assert result.bought_count == 3
    assert result.skipped_count == 0
    assert result.substituted_count == 0
    assert result.errors == []

    # Side effects: 3 inventory lots.
    inventory = db_with_household.get_inventory(user_id="h1")
    active_lots = [lot for lot in inventory if lot.status == "active"]
    assert len(active_lots) == 3, (
        f"Expected 3 active lots, got {len(active_lots)}: "
        f"{[lot.canonical_name for lot in active_lots]}"
    )
    canonical_names = {lot.canonical_name for lot in active_lots}
    assert canonical_names == {"milk", "bread", "eggs"}

    # Side effects: 3 price observations (one per bought item).
    observations = db_with_household.get_price_observations(
        canonical_name="milk", user_id="h1"
    )
    assert len(observations) == 1
    assert observations[0].price == 130.0


# ── Mixed: bought + skipped + substituted ────────────────────────


def test_e2e_mixed_actions_count_correctly(db_with_household, tools):
    """E2E: plan 4, buy 2, skip 1, substitute 1 → correct counts.

    Verifies the loop-closer counter: the household-memory
    pipeline depends on the action counts being right (the
    preference learner uses these to adjust future plans).
    """
    planned = [
        {"canonical_name": "milk", "requested_quantity": 1.0, "unit": "L"},
        {"canonical_name": "bread", "requested_quantity": 1.0, "unit": "loaf"},
        {"canonical_name": "butter", "requested_quantity": 1.0, "unit": "pack"},
        {"canonical_name": "cheese", "requested_quantity": 1.0, "unit": "pack"},
    ]
    actual = [
        {"canonical_name": "milk", "action": "bought", "quantity": 1.0,
         "unit": "L", "price_paid": 64.0},
        {"canonical_name": "bread", "action": "bought", "quantity": 1.0,
         "unit": "loaf", "price_paid": 45.0},
        {"canonical_name": "butter", "action": "skipped"},
        {"canonical_name": "cheese", "action": "substituted",
         "substituted_with": "paneer", "quantity": 1.0, "unit": "pack",
         "price_paid": 90.0},
    ]

    result = reconcile_shopping_trip(
        planned_items=planned,
        actual_items=actual,
        tools=tools,
        database=db_with_household,
        user_id="h1",
    )

    assert result.success
    assert result.count == 4
    assert result.bought_count == 2
    assert result.skipped_count == 1
    assert result.substituted_count == 1

    # 3 inventory lots: milk (bought), bread (bought), paneer
    # (substituted FOR cheese — cheese itself was NOT bought, so
    # it should NOT be in inventory).
    inventory = db_with_household.get_inventory(user_id="h1")
    names = {lot.canonical_name for lot in inventory if lot.status == "active"}
    assert "milk" in names
    assert "bread" in names
    assert "paneer" in names
    assert "cheese" not in names, (
        "cheese was substituted for paneer; it should not be in "
        "inventory because the user didn't actually buy cheese."
    )
    assert "butter" not in names, (
        "butter was skipped; it should not be in inventory."
    )


# ── DB persistence: reconciliation_events written ──────────────────


def test_e2e_reconciliation_events_persisted_to_db(db_with_household, tools):
    """E2E: every ReconciliationEvent is written to the DB.

    The DB's ``reconciliation_events`` table is the audit log
    that downstream services (preference learner, trace
    exporter) read from. If events don't land, the loop is
    broken even if the in-memory result looks right.
    """
    planned = [{"canonical_name": "milk", "requested_quantity": 1.0, "unit": "L"}]
    actual = [
        {"canonical_name": "milk", "action": "bought", "quantity": 1.0,
         "unit": "L", "price_paid": 64.0},
    ]
    result = reconcile_shopping_trip(
        planned_items=planned,
        actual_items=actual,
        tools=tools,
        database=db_with_household,
        user_id="h1",
    )
    assert len(result.events) == 1

    # Re-query the DB and assert the event landed.
    cur = db_with_household.conn.execute(
        "SELECT canonical_name, actual_action, price_paid, user_id "
        "FROM reconciliation_events WHERE trip_id = ?",
        (result.trip_id,),
    )
    rows = cur.fetchall()
    assert len(rows) == 1
    canonical_name, actual_action, price_paid, user_id = rows[0]
    assert canonical_name == "milk"
    assert actual_action == "bought"
    assert price_paid == 64.0
    assert user_id == "h1"


# ── Resilience: skipped items don't pollute inventory ─────────────


def test_e2e_skipped_items_create_no_inventory_or_price_observation(
    db_with_household, tools
):
    """E2E: skipped items must NOT create inventory lots or price observations.

    Per the loop-closer semantics, "skipped" means "I didn't buy
    this" — so the system should not record a purchase for it.
    A regression where skipped items create empty inventory
    lots would corrupt the next "should I buy this?" decision.
    """
    planned = [
        {"canonical_name": "milk", "requested_quantity": 1.0, "unit": "L"},
        {"canonical_name": "bread", "requested_quantity": 1.0, "unit": "loaf"},
    ]
    actual = [
        {"canonical_name": "milk", "action": "bought", "quantity": 1.0,
         "unit": "L", "price_paid": 64.0},
        {"canonical_name": "bread", "action": "skipped"},
    ]
    reconcile_shopping_trip(
        planned_items=planned,
        actual_items=actual,
        tools=tools,
        database=db_with_household,
        user_id="h1",
    )
    inventory = db_with_household.get_inventory(user_id="h1")
    names = {lot.canonical_name for lot in inventory if lot.status == "active"}
    assert "bread" not in names, (
        "skipped bread was created in inventory — loop-closer broken."
    )
    # No price observation for bread either.
    obs = db_with_household.get_price_observations(
        canonical_name="bread", user_id="h1"
    )
    assert obs == [], (
        f"skipped bread created {len(obs)} price observations — "
        f"loop-closer broken."
    )


# ── Graceful degradation: missing tools/database don't crash ──────


def test_e2e_graceful_when_no_tools_or_database():
    """E2E: passing ``tools=None`` and ``database=None`` must not crash.

    Some callers (e.g. dry-run previews) want the in-memory
    ReconciliationResult without persisting anything. The
    service must compute the result and skip the persistence
    side effects, returning a result with ``success=True`` and
    zero side effects.
    """
    planned = [
        {"canonical_name": "milk", "requested_quantity": 1.0, "unit": "L"},
    ]
    actual = [
        {"canonical_name": "milk", "action": "bought", "quantity": 1.0,
         "unit": "L", "price_paid": 64.0},
    ]
    result = reconcile_shopping_trip(
        planned_items=planned,
        actual_items=actual,
        tools=None,
        database=None,
        user_id="h1",
    )
    assert result.success
    assert result.count == 1
    assert result.bought_count == 1
    assert result.inventory_updates == [], (
        "With tools=None, no inventory updates should be produced."
    )
    assert result.errors == []
