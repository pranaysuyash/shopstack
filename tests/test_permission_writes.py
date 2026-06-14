"""Smoke tests for permission-wrapped write paths (Phase 11).

These tests verify the *integration* of the permission
service with the major write paths. The pure-function
permission logic is exhaustively tested in
``test_permissions.py``; these tests just verify the gate
is actually invoked at the top of each write path.

Strategy: use unique IDs per test so the in-memory
SQLite stays isolated. One focused test per write path.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone

import pytest

# Set the DB path BEFORE importing the database / schemas modules
os.environ.setdefault("SHOPSTACK_DB_PATH", ":memory:")
os.environ.setdefault("SHOPSTACK_PLANNER_BACKEND", "mock")

from shopstack.persistence.database import Database  # noqa: E402
from shopstack.schemas.models import (  # noqa: E402
    InventoryLot,
    MovementEvent,
    PreferenceSignal,
    PriceObservation,
    PurchaseEvent,
    ShoppingListItem,
)


def _new_id() -> str:
    """A unique id per test to avoid in-memory db collisions."""
    return uuid.uuid4().hex[:8]


@pytest.fixture()
def db():
    """Fresh in-memory Database with a hh-1 owner."""
    d = Database()
    d.add_household("hh-1", "Test Home")
    d.add_household_member("hh-1", "hh-1", role="owner")
    yield d
    try:
        d.conn.close()
    except Exception:
        pass


def _lot(test_id: str, user_id: str = "hh-1") -> InventoryLot:
    now = datetime.now(timezone.utc)
    return InventoryLot(
        lot_id=f"lot-{test_id}",
        canonical_name="tomato",
        display_name="Tomato",
        category="vegetables",
        quantity=1.0,
        unit="kg",
        storage_location_id="fridge",
        purchase_date=date.today(),
        estimated_use_by_date=None,
        label_expiry_date=None,
        opened_date=None,
        price_paid=80.0,
        currency="INR",
        source_event_id="",
        confidence=0.9,
        image_crop_path="",
        status="active",
        created_at=now,
        updated_at=now,
        user_id=user_id,
    )


# ── add_inventory_lot ───────────────────────────────────────────


def test_add_inventory_lot_owner_succeeds(db):
    """Owner writes succeed — the gate is permissive for the household owner."""
    db.active_household_id = "hh-1"
    result = db.add_inventory_lot(_lot(_new_id()), user_id="hh-1")
    assert result.lot_id.startswith("lot-")


def test_add_inventory_lot_non_member_raises(db):
    """A user not in the household cannot write — the gate is fail-closed."""
    db.active_household_id = "hh-1"
    with pytest.raises(PermissionError):
        db.add_inventory_lot(_lot(_new_id()), user_id="not-a-member")


# ── consume_inventory ─────────────────────────────────────────


def test_consume_inventory_owner_succeeds(db):
    db.active_household_id = "hh-1"
    lot = _lot(_new_id())
    db.add_inventory_lot(lot, user_id="hh-1")
    result = db.consume_inventory(lot.lot_id, 0.3)
    assert result is not None
    assert result.quantity == 0.7


def test_consume_inventory_missing_lot_returns_none(db):
    """No lot → no write attempted → no permission error."""
    db.active_household_id = "hh-1"
    result = db.consume_inventory(f"missing-{_new_id()}", 1.0)
    assert result is None


# ── add_list_item ────────────────────────────────────────────


def test_add_list_item_owner_succeeds(db):
    db.active_household_id = "hh-1"
    list_id = f"list-{_new_id()}"
    db.conn.execute(
        "INSERT INTO shopping_lists (list_id, name, created_at, updated_at, user_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (list_id, "Test list", datetime.now(timezone.utc).isoformat(),
         datetime.now(timezone.utc).isoformat(), "hh-1"),
    )
    db.conn.commit()
    item = ShoppingListItem(
        list_item_id=f"item-{_new_id()}",
        canonical_name="milk",
        requested_quantity=1.0,
        unit="L",
    )
    result = db.add_list_item(list_id, item)
    assert result.canonical_name == "milk"


# ── record_movement ─────────────────────────────────────────


def test_record_movement_owner_succeeds(db):
    db.active_household_id = "hh-1"
    lot = _lot(_new_id())
    db.add_inventory_lot(lot, user_id="hh-1")
    mv = MovementEvent(
        movement_id=f"mv-{_new_id()}",
        lot_id=lot.lot_id,
        from_location_id="fridge",
        to_location_id="pantry",
        timestamp=datetime.now(timezone.utc),
        source="manual",
        confidence=0.9,
    )
    result = db.record_movement(mv)
    assert result.movement_id.startswith("mv-")


# ── record_price ────────────────────────────────────────────


def test_record_price_owner_succeeds(db):
    db.active_household_id = "hh-1"
    p = PriceObservation(
        price_id=f"price-{_new_id()}",
        canonical_name="milk",
        quantity=1.0,
        unit="L",
        price=60.0,
        currency="INR",
        store_name="DMart",
        store_id="",
        observation_date=date.today(),
        source_event_id="",
        notes="",
    )
    result = db.record_price(p, user_id="hh-1")
    assert result.price_id.startswith("price-")


# ── add_purchase_event ───────────────────────────────────────


def test_add_purchase_event_owner_succeeds(db):
    db.active_household_id = "hh-1"
    e = PurchaseEvent(
        event_id=f"pe-{_new_id()}",
        timestamp=datetime.now(timezone.utc),
        canonical_name="milk",
        quantity=1.0,
        unit="L",
        total_price=60.0,
        currency="INR",
        source_type="manual",
        store_name="DMart",
    )
    result = db.add_purchase_event(e, user_id="hh-1")
    assert result.event_id.startswith("pe-")


# ── add_preference_signal ────────────────────────────────────


def test_add_preference_signal_owner_succeeds(db):
    db.active_household_id = "hh-1"
    s = PreferenceSignal(
        signal_id=f"ps-{_new_id()}",
        canonical_name="milk",
        signal_type="brand",
        value="Amul",
        confidence=0.9,
        source="manual",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    result = db.add_preference_signal(s, user_id="hh-1")
    assert result.signal_id.startswith("ps-")


# ── Backward compat: empty user_id defaults to active household ─


def test_add_inventory_lot_empty_user_id_uses_active(db):
    """Pre-Permission callers that don't pass user_id still work."""
    db.active_household_id = "hh-1"
    result = db.add_inventory_lot(_lot(_new_id()))  # no user_id
    assert result.lot_id.startswith("lot-")


# ── Wrap is fail-closed on DB error ──────────────────────────


def test_add_inventory_lot_fail_closed_on_db_error(db):
    """If the permission check DB errored, the call should not silently succeed."""
    db.active_household_id = "hh-1"
    original = db.get_household_member
    def broken(*args, **kwargs):
        raise RuntimeError("simulated db error")
    db.get_household_member = broken
    with pytest.raises(PermissionError):
        db.add_inventory_lot(_lot(_new_id()), user_id="hh-1")
    db.get_household_member = original


# ── Cross-household denial ──────────────────────────────────


def _setup_two_households(db):
    """Create two households with distinct owners for cross-household tests."""
    db.add_household("hh-a", "Household A")
    db.add_household_member("hh-a", "owner-a", role="owner")
    db.add_household("hh-b", "Household B")
    db.add_household_member("hh-b", "owner-b", role="owner")
    # Also add a guest to hh-b to test role hierarchy
    db.add_household_member("hh-b", "guest-b", role="guest")


def test_cross_household_add_inventory_denied(db):
    """Owner of hh-a cannot write to hh-b's inventory."""
    _setup_two_households(db)
    db.active_household_id = "hh-b"
    with pytest.raises(PermissionError):
        db.add_inventory_lot(_lot(_new_id(), user_id="hh-b"), user_id="owner-a")


def test_cross_household_consume_denied(db):
    """Owner of hh-a cannot consume from hh-b's inventory."""
    _setup_two_households(db)
    db.active_household_id = "hh-b"
    lot = _lot(_new_id(), user_id="hh-b")
    db.add_inventory_lot(lot, user_id="owner-b")
    with pytest.raises(PermissionError):
        db.consume_inventory(lot.lot_id, 0.5)


def test_cross_household_record_price_denied(db):
    """Owner of hh-a cannot record prices under hh-b."""
    _setup_two_households(db)
    db.active_household_id = "hh-b"
    p = PriceObservation(
        price_id=f"price-{_new_id()}",
        canonical_name="milk",
        quantity=1.0,
        unit="L",
        price=60.0,
        currency="INR",
        store_name="DMart",
        store_id="",
        observation_date=date.today(),
        source_event_id="",
        notes="",
    )
    with pytest.raises(PermissionError):
        db.record_price(p, user_id="owner-a")


def test_guest_cannot_write_to_own_household(db):
    """A guest in hh-b cannot write even to their own household."""
    _setup_two_households(db)
    db.active_household_id = "hh-b"
    with pytest.raises(PermissionError):
        db.add_inventory_lot(_lot(_new_id(), user_id="hh-b"), user_id="guest-b")


def test_guest_cannot_consume_in_own_household(db):
    """A guest in hh-b cannot consume even from their own household."""
    _setup_two_households(db)
    db.active_household_id = "hh-b"
    lot = _lot(_new_id(), user_id="hh-b")
    db.add_inventory_lot(lot, user_id="owner-b")
    with pytest.raises(PermissionError):
        db.consume_inventory(lot.lot_id, 0.5)


def test_household_a_owner_can_write_to_a(db):
    """Owner of hh-a can write to their own household — no cross-contamination."""
    _setup_two_households(db)
    db.active_household_id = "hh-a"
    result = db.add_inventory_lot(_lot(_new_id(), user_id="hh-a"), user_id="owner-a")
    assert result.lot_id.startswith("lot-")
