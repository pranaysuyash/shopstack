"""Contract tests for ``/api/v1/account/*`` endpoints.

Coverage:
  * Auth-gating: all account endpoints require a bearer token.
  * Privacy purge returns success/failure shape.
  * Retention summary returns policy shape.
  * Update retention returns success.
  * Undo returns success or "nothing to undo".
  * Store-mode toggle returns success or error for missing item.
  * Response shapes match wire schemas.
"""
from __future__ import annotations

import os
import tempfile
from typing import Iterator

import pytest


@pytest.fixture
def temp_db(monkeypatch) -> Iterator[str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from shopstack.persistence.database import Database

    db = Database(path)
    yield path
    db.close()
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def db_handle(temp_db: str):
    from shopstack.persistence.database import Database

    db = Database(temp_db)
    yield db
    db.close()


@pytest.fixture
def v1_app(db_handle):
    from fastapi import FastAPI

    from shopstack import app_context
    from shopstack.api.v1.routers.account import router as account_router
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db_handle)

    fastapi_app = FastAPI(title="shopstack-test-account")
    fastapi_app.include_router(account_router, prefix="/api/v1")
    yield fastapi_app
    monkey.undo()


@pytest.fixture
def client(v1_app):
    from fastapi.testclient import TestClient

    return TestClient(v1_app)


def _issue(db_handle, household: str = "hh_account") -> str:
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)
    return auth_mod.issue_token(
        db_handle, device_id="dev_acct", household_id=household,
    )["token"]


# ── Auth gating ──────────────────────────────────────────────────


class TestAccountAuth:
    def test_purge_requires_token(self, client):
        assert client.post("/api/v1/account/privacy/purge").status_code == 401

    def test_retention_summary_requires_token(self, client):
        assert client.get("/api/v1/account/privacy/retention-summary").status_code == 401

    def test_undo_requires_token(self, client):
        assert client.post("/api/v1/account/undo", json={}).status_code == 401

    def test_store_toggle_requires_token(self, client):
        assert client.post("/api/v1/account/store-mode/toggle", json={"item_id": "x"}).status_code == 401


# ── Privacy: Purge Data ──────────────────────────────────────────


class TestPurgeData:
    def test_purge_returns_success_shape(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/account/privacy/purge",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "success" in body
        assert isinstance(body["success"], bool)
        # PurgeResult fields.
        for key in ("traces_purged", "community_observations_purged",
                     "sms_registry_cleared", "voice_memos_purged", "backups_purged"):
            assert key in body, f"Missing key: {key}"
            assert isinstance(body[key], int)

    def test_purge_errors_is_list(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/account/privacy/purge",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert isinstance(r.json()["errors"], list)


# ── Privacy: Retention Summary ───────────────────────────────────


class TestRetentionSummary:
    def test_returns_policy_shape(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/account/privacy/retention-summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "summary" in body
        s = body["summary"]
        for key in ("trace_ttl_days", "community_pool_retention_days",
                     "voice_memo_retention_days", "locale_persistence",
                     "community_optin"):
            assert key in s, f"Missing key: {key}"

    def test_defaults_are_sensible(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/account/privacy/retention-summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        s = r.json()["summary"]
        assert s["trace_ttl_days"] == 30
        assert s["community_pool_retention_days"] == 90
        assert s["voice_memo_retention_days"] == 7
        assert s["locale_persistence"] is True
        assert s["community_optin"] is False


# ── Privacy: Update Retention ────────────────────────────────────


class TestUpdateRetention:
    def test_unknown_key_returns_false(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/account/privacy/update-retention",
            json={"key": "bogus.key", "value": "30"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["success"] is False

    def test_valid_key_returns_true(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/account/privacy/update-retention",
            json={"key": "retention.trace_ttl_days", "value": "14"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["success"] is True


# ── Undo ─────────────────────────────────────────────────────────


class TestUndo:
    def test_no_recent_entry_returns_noop(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/account/undo",
            json={},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert "Nothing to undo" in body["message"]

    def test_response_shape(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/account/undo",
            json={"entry_id": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "success" in body
        assert "entry_id" in body
        assert "kind" in body
        assert "message" in body


# ── Store Mode Toggle ────────────────────────────────────────────


class TestStoreModeToggle:
    def _seed_active_list(self, db_handle) -> str:
        """Create a household with an active shopping list and one item.
        Returns the item_id so tests can toggle it.
        """
        from shopstack.schemas.models import ShoppingListItem

        # Register the household + owner so permission checks pass.
        db_handle.add_household("hh_account", "Account Test HH")
        db_handle.add_household_member("hh_account", "hh_account", role="owner")

        sl = db_handle.create_shopping_list(
            name="Store List", user_id="hh_account",
        )
        item = ShoppingListItem(canonical_name="Milk", requested_quantity=1.0)
        db_handle.add_list_item(sl.list_id, item, user_id="hh_account")
        return item.list_item_id

    def test_missing_item_id_returns_error(self, client, db_handle):
        token = _issue(db_handle)
        self._seed_active_list(db_handle)
        r = client.post(
            "/api/v1/account/store-mode/toggle",
            json={"item_id": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert "not found" in body["message"].lower() and "item" in body["message"].lower()

    def test_unknown_item_id_returns_error(self, client, db_handle):
        token = _issue(db_handle)
        self._seed_active_list(db_handle)
        r = client.post(
            "/api/v1/account/store-mode/toggle",
            json={"item_id": "no_such_item"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False

    def test_toggle_pending_to_bought(self, client, db_handle):
        """Seed an active list and toggle a real item from pending → bought."""
        token = _issue(db_handle)
        item_id = self._seed_active_list(db_handle)
        r = client.post(
            "/api/v1/account/store-mode/toggle",
            json={"item_id": item_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["new_status"] == "bought"
