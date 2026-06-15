"""Tests for the per-intent SMS webhook handlers registry.

The default dispatcher in :mod:`shopstack.services.sms_webhook` now
delegates to a registry in
:mod:`shopstack.services.sms_intent_handlers`. These tests verify:

* Both documented intents (``add_inventory_item`` and
  ``consume_item``) are registered.
* Each handler is a callable that accepts ``(user_id, args, db)``
  and returns ``{"ok": bool, "message": str}``.
* The ``add_inventory_item`` handler builds a real ``InventoryLot``
  (the pre-fix code passed wrong kwargs that no DB API accepts).
* The ``consume_item`` handler resolves canonical_name → active
  lot via ``db.get_inventory`` (FIFO: oldest first) and refuses
  when there's no active lot.
* The registry is the single source of truth: no parallel
  branches elsewhere (motto_v3 §7).
* ``make_household_scoped_dispatcher`` honors the resolved
  ``user_id`` argument, falling back to the process default when
  the resolved id is empty (the local-dev Stub path).

Why this test file (motto_v3 §0.3):
The webhook tier is the SMS entry point. If a handler silently
breaks, every SMS-based inventory mutation breaks. Pure unit
tests against a fake DB catch the bug class that mocks with
``**kwargs`` used to hide (the previous session's Tier 2/3 gap).
"""
from __future__ import annotations

import os

# DB env must be set before any shopstack import.
os.environ.setdefault("SHOPSTACK_DB_PATH", ":memory:")
os.environ.setdefault("SHOPSTACK_LOCAL_AUTO_DOWNLOAD", "false")

from datetime import datetime, timezone
from typing import Any

import pytest

from shopstack.schemas.models import InventoryLot
from shopstack.services.sms_intent_handlers import (
    INTENT_HANDLERS,
    IntentHandler,
    make_household_scoped_dispatcher,
)


# ── Registry surface ───────────────────────────────────────────────


class TestRegistry:
    def test_expected_intents_registered(self):
        """The documented two intents must both be in the registry.

        motto_v3 §7: a single source of truth for which intents the
        webhook supports.
        """
        assert "add_inventory_item" in INTENT_HANDLERS
        assert "consume_item" in INTENT_HANDLERS

    def test_handlers_are_callables(self):
        for name, handler in INTENT_HANDLERS.items():
            assert isinstance(handler, type(lambda: None)), (
                f"{name} handler is not callable: {type(handler)}"
            )

    def test_no_unregistered_intents_leak(self):
        """Sanity: the registry shouldn't accidentally include
        intents we didn't intend to ship."""
        # If we add a new intent, this test should force us to
        # think about it (positive list, not negative).
        expected = {"add_inventory_item", "consume_item"}
        assert set(INTENT_HANDLERS.keys()) == expected


# ── add_inventory_item handler ──────────────────────────────────────


class _FakeDB:
    """Minimal DB stand-in that mirrors the real DB contract."""

    def __init__(self):
        self.add_calls: list[dict] = []
        self.consume_calls: list[dict] = []
        self._lots: list[InventoryLot] = []

    def add_inventory_lot(self, lot: InventoryLot, user_id: str = "") -> InventoryLot:
        # Real DB raises PermissionError on cross-household write;
        # the fake lets the test control whether the call succeeds
        # by setting _fail.
        if getattr(self, "_fail_add", False):
            raise RuntimeError("simulated add_inventory_lot failure")
        self.add_calls.append({"lot": lot, "user_id": user_id})
        return lot

    def consume_inventory(
        self, lot_id: str, quantity: float, user_id: str = ""
    ) -> Any:
        if getattr(self, "_fail_consume", False):
            raise RuntimeError("simulated consume_inventory failure")
        self.consume_calls.append({"lot_id": lot_id, "quantity": quantity, "user_id": user_id})
        return None

    def get_inventory(
        self,
        status: str | None = None,
        canonical_name: str | None = None,
        user_id: str = "",
        **kwargs: Any,
    ) -> list[InventoryLot]:
        out = []
        for lot in self._lots:
            if status and lot.status != status:
                continue
            if canonical_name and lot.canonical_name != canonical_name:
                continue
            out.append(lot)
        return out


class TestAddInventoryItem:
    def test_happy_path_adds_lot(self):
        db = _FakeDB()
        result = INTENT_HANDLERS["add_inventory_item"](
            "user-1",
            {"canonical_name": "milk", "quantity": 2.0, "unit": "L"},
            db,
        )
        assert result["ok"] is True
        assert "Added milk" in result["message"]
        assert len(db.add_calls) == 1
        assert db.add_calls[0]["user_id"] == "user-1"
        assert isinstance(db.add_calls[0]["lot"], InventoryLot)
        assert db.add_calls[0]["lot"].canonical_name == "milk"
        assert db.add_calls[0]["lot"].quantity == 2.0
        assert db.add_calls[0]["lot"].unit == "L"

    def test_uses_canonical_as_display_name_fallback(self):
        db = _FakeDB()
        INTENT_HANDLERS["add_inventory_item"](
            "user-1", {"canonical_name": "bread"}, db
        )
        assert db.add_calls[0]["lot"].display_name == "bread"

    def test_explicit_display_name_wins(self):
        db = _FakeDB()
        INTENT_HANDLERS["add_inventory_item"](
            "user-1",
            {"canonical_name": "bread", "display_name": "Whole wheat bread"},
            db,
        )
        assert db.add_calls[0]["lot"].display_name == "Whole wheat bread"

    def test_missing_canonical_name_is_noop(self):
        """No canonical_name → no dispatch. Matches the legacy
        contract: the guard belongs in the handler so each
        intent owns its required args.
        """
        db = _FakeDB()
        result = INTENT_HANDLERS["add_inventory_item"](
            "user-1", {"quantity": 2.0}, db
        )
        assert result["ok"] is True
        assert "no action" in result["message"]
        assert len(db.add_calls) == 0

    def test_db_error_returns_ok_false(self):
        db = _FakeDB()
        db._fail_add = True
        result = INTENT_HANDLERS["add_inventory_item"](
            "user-1", {"canonical_name": "milk"}, db
        )
        assert result["ok"] is False
        assert "DB error" in result["message"]


# ── consume_item handler ───────────────────────────────────────────


def _make_lot(test_id: str, name: str, created_at: datetime) -> InventoryLot:
    return InventoryLot(
        lot_id=f"lot-{test_id}",
        canonical_name=name,
        display_name=name.title(),
        quantity=3.0,
        unit="L",
        status="active",
        created_at=created_at,
    )


class TestConsumeItem:
    def test_no_active_lot_returns_no_match(self):
        db = _FakeDB()
        result = INTENT_HANDLERS["consume_item"](
            "user-1", {"canonical_name": "milk"}, db
        )
        assert result["ok"] is False
        assert "No active milk" in result["message"]
        assert len(db.consume_calls) == 0

    def test_consumes_oldest_active_lot(self, monkeypatch):
        """FIFO: oldest first. Newest lot is skipped even though
        it's still active."""
        now = datetime.now(timezone.utc)
        lots = [
            _make_lot("newer", "milk", now),
            _make_lot("older", "milk", now.replace(year=now.year - 1)),
        ]
        db = _FakeDB()
        db._lots = lots
        result = INTENT_HANDLERS["consume_item"](
            "user-1", {"canonical_name": "milk", "quantity": 1.0}, db
        )
        assert result["ok"] is True
        assert len(db.consume_calls) == 1
        assert db.consume_calls[0]["lot_id"] == "lot-older"
        assert db.consume_calls[0]["quantity"] == 1.0
        assert db.consume_calls[0]["user_id"] == "user-1"

    def test_missing_canonical_name_is_noop(self):
        db = _FakeDB()
        result = INTENT_HANDLERS["consume_item"](
            "user-1", {"quantity": 1.0}, db
        )
        assert result["ok"] is True
        assert "no action" in result["message"]
        assert len(db.consume_calls) == 0

    def test_db_error_returns_ok_false(self):
        lot = _make_lot("err", "milk", datetime.now(timezone.utc))
        db = _FakeDB()
        db._lots = [lot]
        db._fail_consume = True
        result = INTENT_HANDLERS["consume_item"](
            "user-1", {"canonical_name": "milk"}, db
        )
        assert result["ok"] is False
        assert "DB error" in result["message"]


# ── make_household_scoped_dispatcher ────────────────────────────────


class TestHouseholdScopedDispatcher:
    def test_passes_through_resolved_user_id(self):
        db = _FakeDB()
        dispatcher = make_household_scoped_dispatcher(db, fallback_user_id="default")
        dispatcher("resolved-uid", {"intent": "add_inventory_item", "args": {"canonical_name": "milk"}})
        assert db.add_calls[0]["user_id"] == "resolved-uid"

    def test_falls_back_when_resolved_user_id_empty(self):
        """The local-dev Stub adapter passes empty user_id; the
        dispatcher must fall back to the process default in that
        case, preserving the previous behavior.
        """
        db = _FakeDB()
        dispatcher = make_household_scoped_dispatcher(db, fallback_user_id="default")
        dispatcher("", {"intent": "add_inventory_item", "args": {"canonical_name": "milk"}})
        assert db.add_calls[0]["user_id"] == "default"

    def test_unknown_intent_returns_no_action(self):
        """The wrapper should preserve the base dispatcher's
        ack-but-no-action behavior for future intents.
        """
        db = _FakeDB()
        dispatcher = make_household_scoped_dispatcher(db, fallback_user_id="default")
        result = dispatcher("uid", {"intent": "future_intent", "args": {}})
        assert result["ok"] is True
        assert "no action" in result["message"]
        assert len(db.add_calls) == 0
