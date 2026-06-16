"""Tests for `shopstack.services.undo_mount` — the undo HTTP endpoint.

Verifies:
  * Missing household returns failure.
  * No recent entry returns failure.
  * Successful undo returns the entry details.
  * JSON parse failure is handled gracefully.
  * The mount function is best-effort.
"""
from __future__ import annotations

import json

import pytest
from unittest.mock import MagicMock

from shopstack.services.undo_ledger import UndoEntry
from shopstack.services.undo_mount import (
    _undo_endpoint,
    mount_undo_endpoint,
)


class _FakeRequest:
    def __init__(
        self,
        body: bytes = b"{}",
        params: dict[str, str] | None = None,
    ) -> None:
        self.body = body
        self.query_params = params or {}


# ── Endpoint ───────────────────────────────────────────────────────


class TestUndoEndpoint:
    def test_missing_household_returns_failure(self, monkeypatch):
        from shopstack.services import undo_mount

        monkeypatch.setattr(
            undo_mount, "current_user_id", lambda: "",
        )
        req = _FakeRequest()
        result = _undo_endpoint(req)
        assert result["success"] is False
        assert "household" in result["error"].lower()

    def test_no_recent_entry_returns_failure(self, monkeypatch):
        from shopstack.services import undo_mount

        monkeypatch.setattr(
            undo_mount, "current_user_id", lambda: "hh1",
        )
        monkeypatch.setattr(
            undo_mount, "get_ledger",
            lambda: _StubLedger(undo_last_returns=None),
        )
        req = _FakeRequest()
        result = _undo_endpoint(req)
        assert result["success"] is False

    def test_successful_undo_returns_entry(self, monkeypatch):
        from shopstack.services import undo_mount

        monkeypatch.setattr(
            undo_mount, "current_user_id", lambda: "hh1",
        )

        fake_entry = UndoEntry(
            entry_id="e1", household_id="hh1",
            kind="consume_inventory",
            before={"lot_id": "lot-1", "quantity": 2.0},
            description="Consumed 2 L of Milk",
        )
        monkeypatch.setattr(
            undo_mount, "get_ledger",
            lambda: _StubLedger(undo_last_returns=fake_entry),
        )
        req = _FakeRequest()
        result = _undo_endpoint(req)
        assert result["success"] is True
        assert result["entry"]["entry_id"] == "e1"
        assert result["entry"]["kind"] == "consume_inventory"

    def test_malformed_json_body_falls_back_to_params(self, monkeypatch):
        from shopstack.services import undo_mount

        monkeypatch.setattr(
            undo_mount, "current_user_id", lambda: "hh1",
        )
        monkeypatch.setattr(
            undo_mount, "get_ledger",
            lambda: _StubLedger(undo_by_id_returns=None),
        )
        req = _FakeRequest(body=b"not json", params={"entry_id": "e-xyz"})
        result = _undo_endpoint(req)
        # Malformed JSON is tolerated; params take over.
        assert result["success"] is False  # nothing to undo

    def test_undo_by_id_via_body(self, monkeypatch):
        from shopstack.services import undo_mount

        monkeypatch.setattr(
            undo_mount, "current_user_id", lambda: "hh1",
        )
        fake_entry = UndoEntry(
            entry_id="e-target", household_id="hh1",
            kind="consume_inventory",
            before={"lot_id": "lot-1", "quantity": 1.0},
        )
        monkeypatch.setattr(
            undo_mount, "get_ledger",
            lambda: _StubLedger(undo_by_id_returns=fake_entry),
        )
        req = _FakeRequest(body=json.dumps({"entry_id": "e-target"}).encode())
        result = _undo_endpoint(req)
        assert result["success"] is True
        assert result["entry"]["entry_id"] == "e-target"

    def test_ledger_exception_returns_failure(self, monkeypatch):
        from shopstack.services import undo_mount

        monkeypatch.setattr(
            undo_mount, "current_user_id", lambda: "hh1",
        )

        class _BoomLedger:
            def undo_last(self, *a, **kw):
                raise RuntimeError("simulated undo failure")

        monkeypatch.setattr(
            undo_mount, "get_ledger", lambda: _BoomLedger(),
        )
        req = _FakeRequest()
        result = _undo_endpoint(req)
        assert result["success"] is False
        assert "error" in result


class _StubLedger:
    def __init__(self, undo_last_returns=None, undo_by_id_returns=None) -> None:
        self._last = undo_last_returns
        self._by_id = undo_by_id_returns
        self.undo_last_calls: list[str] = []
        self.undo_by_id_calls: list[str] = []

    def undo_last(self, household_id, db, **kw):
        self.undo_last_calls.append(household_id)
        return self._last

    def undo_by_id(self, household_id, entry_id, db, **kw):
        self.undo_by_id_calls.append(entry_id)
        return self._by_id


# ── Store Mode Toggle endpoint ───────────────────────────────────


class TestStoreModeToggleEndpoint:
    """Tests for ``_store_mode_toggle_endpoint`` in ``undo_mount``.

    The endpoint toggles a shopping list item's status between
    ``"pending"`` and ``"bought"`` via a POST with ``{"item_id": ...}``.
    """

    def test_toggle_requires_item_id(self, monkeypatch):
        """Missing item_id in the request body returns failure."""
        from shopstack.services.undo_mount import _store_mode_toggle_endpoint

        monkeypatch.setattr(
            "shopstack.app_context.current_user_id", lambda: "hh1",
        )
        req = _FakeRequest(body=b"{}")
        result = _store_mode_toggle_endpoint(req)
        assert result["success"] is False
        assert "item_id" in result["error"].lower()

    def test_toggle_no_active_list(self, monkeypatch):
        """When no active shopping list exists, the endpoint returns failure."""
        from shopstack.services.undo_mount import _store_mode_toggle_endpoint

        mock_db = MagicMock()
        mock_db.get_active_shopping_list.return_value = None
        monkeypatch.setattr(
            "shopstack.app_context.current_user_id", lambda: "hh1",
        )
        monkeypatch.setattr("shopstack.app_context.db", mock_db)
        req = _FakeRequest(body=json.dumps({"item_id": "item-1"}).encode())
        result = _store_mode_toggle_endpoint(req)
        assert result["success"] is False
        assert "active shopping list" in result["error"].lower()

    def test_toggle_item_not_found(self, monkeypatch):
        """Item ID not in the active list returns failure."""
        from shopstack.services.undo_mount import _store_mode_toggle_endpoint

        # List has items, but none matching the requested item_id
        mock_item = MagicMock()
        mock_item.item_id = "item-other"
        mock_item.status = "pending"
        mock_sl = MagicMock()
        mock_sl.items = [mock_item]
        mock_db = MagicMock()
        mock_db.get_active_shopping_list.return_value = mock_sl
        monkeypatch.setattr(
            "shopstack.app_context.current_user_id", lambda: "hh1",
        )
        monkeypatch.setattr("shopstack.app_context.db", mock_db)
        req = _FakeRequest(body=json.dumps({"item_id": "item-1"}).encode())
        result = _store_mode_toggle_endpoint(req)
        assert result["success"] is False
        assert "not found" in result["error"].lower()

    def test_toggle_marks_item_as_bought(self, monkeypatch):
        """Toggling a pending item sets status to 'bought'."""
        from shopstack.services.undo_mount import _store_mode_toggle_endpoint

        mock_item = MagicMock()
        mock_item.item_id = "item-1"
        mock_item.status = "pending"
        mock_sl = MagicMock()
        mock_sl.items = [mock_item]
        mock_db = MagicMock()
        mock_db.get_active_shopping_list.return_value = mock_sl
        monkeypatch.setattr(
            "shopstack.app_context.current_user_id", lambda: "hh1",
        )
        monkeypatch.setattr("shopstack.app_context.db", mock_db)
        req = _FakeRequest(body=json.dumps({"item_id": "item-1"}).encode())
        result = _store_mode_toggle_endpoint(req)
        assert result["success"] is True
        assert result["new_status"] == "bought"
        mock_db.update_list_item.assert_called_once_with(
            "item-1", {"status": "bought"},
        )

    def test_toggle_marks_bought_as_pending(self, monkeypatch):
        """Toggling a bought item reverts status to 'pending'."""
        from shopstack.services.undo_mount import _store_mode_toggle_endpoint

        mock_item = MagicMock()
        mock_item.item_id = "item-2"
        mock_item.status = "bought"
        mock_sl = MagicMock()
        mock_sl.items = [mock_item]
        mock_db = MagicMock()
        mock_db.get_active_shopping_list.return_value = mock_sl
        monkeypatch.setattr(
            "shopstack.app_context.current_user_id", lambda: "hh1",
        )
        monkeypatch.setattr("shopstack.app_context.db", mock_db)
        req = _FakeRequest(body=json.dumps({"item_id": "item-2"}).encode())
        result = _store_mode_toggle_endpoint(req)
        assert result["success"] is True
        assert result["new_status"] == "pending"
        mock_db.update_list_item.assert_called_once_with(
            "item-2", {"status": "pending"},
        )

    def test_toggle_malformed_json_handled_gracefully(self, monkeypatch):
        """Malformed JSON body does not crash the handler."""
        from shopstack.services.undo_mount import _store_mode_toggle_endpoint

        monkeypatch.setattr(
            "shopstack.app_context.current_user_id", lambda: "hh1",
        )
        req = _FakeRequest(body=b"{bad json}")
        result = _store_mode_toggle_endpoint(req)
        # Malformed JSON means empty body, so item_id is missing
        assert result["success"] is False

    def test_toggle_exception_returns_error(self, monkeypatch):
        """Any exception in the handler returns a failure response."""
        from shopstack.services.undo_mount import _store_mode_toggle_endpoint

        monkeypatch.setattr(
            "shopstack.app_context.current_user_id",
            MagicMock(side_effect=RuntimeError("boom")),
        )
        req = _FakeRequest(body=json.dumps({"item_id": "item-1"}).encode())
        result = _store_mode_toggle_endpoint(req)
        assert result["success"] is False
        assert "error" in result


# ── Mount is best-effort ─────────────────────────────────────────


class TestMountUndoEndpoint:
    def test_mount_handles_no_app(self):
        class _BadApp:
            pass
        mount_undo_endpoint(_BadApp())  # type: ignore — should not raise
