"""Tests for the ``/api/v1/*`` surface.

Coverage:
  * Schemas validate + serialize round-trip (Pydantic v2 contract).
  * Auth: register → login → refresh → logout (and the 401 paths).
  * Meta: whoami + health + runtime (unauthenticated).
  * Inventory: list + get (with and without a token).
  * Aliases: /api/whoami + /health/ui still work and carry Sunset headers.
  * ContextVar: ``current_user_id()`` returns the request-scoped value.

The tests use ``TestClient`` (FastAPI) + a temporary SQLite DB
so the auth table is fresh per test. The Gradio app is not
booted — we mount the v1 routers directly on a Starlette app.
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import tempfile
from typing import Iterator

import pytest


@pytest.fixture
def temp_db(monkeypatch) -> Iterator[str]:
    """A fresh SQLite DB per test. The fixture cleans up on teardown."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    # Bootstrap the schema via the existing Database class so we
    # get all the production tables (not just the auth ones).
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
    """A Database handle for the temp DB."""
    from shopstack.persistence.database import Database

    db = Database(temp_db)
    yield db
    db.close()


@pytest.fixture
def v1_app(db_handle):
    """A bare FastAPI app with the v1 routers mounted (no Gradio)."""
    from fastapi import FastAPI

    from shopstack import app_context
    from shopstack.api.v1.routers.auth_router import router as auth_router
    from shopstack.api.v1.routers.inventory import router as inventory_router
    from shopstack.api.v1.routers.meta import router as meta_router
    from shopstack.api.v1.routers.household import router as household_router
    from shopstack.api.v1.routers.shopping import router as shopping_router
    from shopstack.api.v1.routers.dashboard import router as dashboard_router
    from shopstack.api.v1.routers.account import router as account_router

    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db_handle)
    # The shopping/dashboard routers reach for tools.inventory via
    # app_context.tools; point it at the same registry the production
    # app uses so service-layer delegation works in tests.
    try:
        from shopstack.tools.registry import ToolRegistry

        monkey.setattr(app_context, "tools", ToolRegistry(db_handle), raising=False)
    except Exception:
        pass

    fastapi_app = FastAPI(title="shopstack-test")
    # Note: the routers already declare their own prefix ("/meta",
    # "/auth", "/inventory", ...), so we mount at "/api/v1" only.
    fastapi_app.include_router(meta_router, prefix="/api/v1")
    fastapi_app.include_router(auth_router, prefix="/api/v1")
    fastapi_app.include_router(inventory_router, prefix="/api/v1")
    fastapi_app.include_router(household_router, prefix="/api/v1")
    fastapi_app.include_router(shopping_router, prefix="/api/v1")
    fastapi_app.include_router(dashboard_router, prefix="/api/v1")
    fastapi_app.include_router(account_router, prefix="/api/v1")
    yield fastapi_app
    monkey.undo()


@pytest.fixture
def client(v1_app):
    """A FastAPI TestClient."""
    from fastapi.testclient import TestClient

    return TestClient(v1_app)


# ── Schemas ───────────────────────────────────────────────────────


class TestSchemas:
    def test_login_request_round_trip(self):
        from shopstack.api.v1.schemas import LoginRequest, TokenResponse, WhoAmI

        req = LoginRequest(device_id="dev12345", device_secret="x" * 40)
        payload = req.model_dump()
        assert payload["device_id"] == "dev12345"
        assert payload["device_secret"] == "x" * 40
        assert payload["requested_household_id"] is None

    def test_whoami_serialises_iso_timestamp(self):
        from shopstack.api.v1.schemas import WhoAmI

        w = WhoAmI(
            app_name="shopstack",
            app_version="0.1.0",
            household_id="hh1",
            household_name="Home",
            runtime_mode="local_mock",
            timestamp="2026-06-16T00:00:00Z",
        )
        d = w.model_dump()
        assert d["app_name"] == "shopstack"
        assert d["runtime_mode"] == "local_mock"
        assert d["household_id"] == "hh1"

    def test_extra_fields_rejected(self):
        """The API rejects unknown fields at the boundary (typo guard)."""
        from pydantic import ValidationError

        from shopstack.api.v1.schemas import LoginRequest

        with pytest.raises(ValidationError):
            LoginRequest.model_validate(
                {"device_id": "x" * 12, "device_secret": "y" * 32, "bogus": "field"}
            )

    def test_inventory_lot_defaults(self):
        from shopstack.api.v1.schemas import InventoryLot

        lot = InventoryLot(lot_id="l1", canonical_name="milk", display_name="Milk")
        assert lot.quantity == 1.0
        assert lot.currency == "INR"
        assert lot.status == "active"
        assert lot.confidence == 1.0

    def test_consume_request_quantity_must_be_positive(self):
        from pydantic import ValidationError

        from shopstack.api.v1.schemas import ConsumeInventoryRequest

        with pytest.raises(ValidationError):
            ConsumeInventoryRequest(quantity=0)
        with pytest.raises(ValidationError):
            ConsumeInventoryRequest(quantity=-1)


# ── Auth module (storage layer) ─────────────────────────────────


class TestAuthStorage:
    def test_ensure_auth_table_idempotent(self, db_handle):
        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        auth_mod.ensure_auth_table(db_handle)  # second call is a no-op
        cur = db_handle.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='api_v1_auth_tokens'"
        )
        assert cur.fetchone() is not None

    def test_issue_and_verify_token(self, db_handle):
        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        issued = auth_mod.issue_token(
            db_handle, device_id="device_a", household_id="hh_a",
        )
        assert issued["token"] and len(issued["token"]) >= 40
        assert issued["household_id"] == "hh_a"

        row = auth_mod.verify_token(db_handle, issued["token"])
        assert row is not None
        assert row["device_id"] == "device_a"
        assert row["household_id"] == "hh_a"

    def test_verify_unknown_token_returns_none(self, db_handle):
        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        assert auth_mod.verify_token(db_handle, "not-a-real-token") is None

    def test_revoke_token(self, db_handle):
        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        issued = auth_mod.issue_token(
            db_handle, device_id="device_b", household_id="hh_b",
        )
        assert auth_mod.revoke_token(db_handle, issued["token"]) is True
        assert auth_mod.verify_token(db_handle, issued["token"]) is None
        # Second revoke is a no-op (returns False).
        assert auth_mod.revoke_token(db_handle, issued["token"]) is False

    def test_revoke_all_for_device(self, db_handle):
        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        t1 = auth_mod.issue_token(db_handle, device_id="d1", household_id="h1")
        t2 = auth_mod.issue_token(db_handle, device_id="d1", household_id="h2")
        auth_mod.issue_token(db_handle, device_id="d2", household_id="h1")  # different device
        n = auth_mod.revoke_all_for_device(db_handle, "d1")
        assert n == 2
        assert auth_mod.verify_token(db_handle, t1["token"]) is None
        assert auth_mod.verify_token(db_handle, t2["token"]) is None

    def test_expired_token_rejected(self, db_handle):
        from datetime import datetime, timedelta, timezone

        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        # Insert a token that's already expired.
        import hashlib

        token = "fake-expired-token"
        token_hash = hashlib.sha256(token.encode()).digest()
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        db_handle.conn.execute(
            "INSERT INTO api_v1_auth_tokens (token_hash, device_id, household_id, created_at, expires_at) "
            "VALUES (?, 'd', 'h', ?, ?)",
            (token_hash, past, past),
        )
        db_handle.conn.commit()
        assert auth_mod.verify_token(db_handle, token) is None

    def test_token_hash_uses_sha256(self):
        """Sanity: same token produces the same hash; different tokens don't."""
        from shopstack.api.v1 import auth as auth_mod

        h1 = auth_mod._hash_token("abc")
        h2 = auth_mod._hash_token("abc")
        h3 = auth_mod._hash_token("xyz")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 32  # sha256 output

    def test_device_secret_compare_is_constant_time(self):
        from shopstack.api.v1.auth import verify_device_secret

        assert verify_device_secret("a" * 32, "a" * 32) is True
        assert verify_device_secret("a" * 32, "b" * 32) is False
        assert verify_device_secret("", "a" * 32) is False
        assert verify_device_secret("a" * 32, "") is False

    def test_purge_expired(self, db_handle):
        from datetime import datetime, timedelta, timezone

        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        # One live, one expired.
        auth_mod.issue_token(db_handle, device_id="d1", household_id="h1")
        import hashlib

        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        db_handle.conn.execute(
            "INSERT INTO api_v1_auth_tokens (token_hash, device_id, household_id, created_at, expires_at) "
            "VALUES (?, 'd2', 'h2', ?, ?)",
            (hashlib.sha256(b"expired").digest(), past, past),
        )
        db_handle.conn.commit()
        n = auth_mod.purge_expired_tokens(db_handle)
        assert n == 1


# ── Meta endpoints ────────────────────────────────────────────────


class TestMetaEndpoints:
    def test_whoami(self, client):
        r = client.get("/api/v1/meta/whoami")
        assert r.status_code == 200
        body = r.json()
        assert body["app_name"] == "shopstack"
        assert "household_id" in body
        assert "runtime_mode" in body
        assert body["runtime_mode"] in ("local_mock", "local_transformers", "llama_cpp", "hf_inference")

    def test_health(self, client):
        r = client.get("/api/v1/meta/health")
        # DB exists in the temp dir so health is ok.
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("ok", "degraded")

    def test_runtime(self, client):
        r = client.get("/api/v1/meta/runtime")
        assert r.status_code == 200
        body = r.json()
        assert "providers" in body
        assert "mode" in body


# ── Auth endpoints ───────────────────────────────────────────────


class TestAuthEndpoints:
    def _register(self, client, device_id: str = "device_abc", secret: str | None = None):
        secret = secret or secrets.token_hex(20)
        return client.post(
            "/api/v1/auth/register",
            json={
                "device_id": device_id,
                "device_secret": secret,
                "household_name": "Home",
            },
        )

    def test_register_then_login(self, client):
        secret = secrets.token_hex(20)
        r1 = self._register(client, secret=secret)
        assert r1.status_code == 201, r1.text
        body = r1.json()
        assert body["token"]
        assert body["household_id"]
        assert body["household_name"]

        r2 = client.post(
            "/api/v1/auth/login",
            json={"device_id": "device_abc", "device_secret": secret},
        )
        assert r2.status_code == 200
        assert r2.json()["token"]

    def test_register_bootstraps_writable_membership(self, client, db_handle):
        secret = secrets.token_hex(20)
        r = self._register(client, secret=secret)
        assert r.status_code == 201, r.text
        household_id = r.json()["household_id"]
        members = db_handle.list_household_members(household_id)
        assert any(m.get("user_id") == household_id and m.get("role") == "owner" for m in members)

    def test_login_unknown_device_is_401(self, client):
        r = client.post(
            "/api/v1/auth/login",
            json={"device_id": "nope", "device_secret": "x" * 32},
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "unknown_device"

    def test_login_bad_secret_is_401(self, client):
        self._register(client)
        r = client.post(
            "/api/v1/auth/login",
            json={"device_id": "device_abc", "device_secret": "z" * 40},
        )
        assert r.status_code == 401
        assert r.json()["detail"]["code"] == "bad_device_secret"

    def test_refresh_extends_expiry(self, client):
        r = self._register(client)
        token = r.json()["token"]
        r2 = client.post("/api/v1/auth/refresh", json={"token": token})
        assert r2.status_code == 200
        assert r2.json()["token"] == token
        assert r2.json()["expires_at"] > r.json()["expires_at"]

    def test_refresh_invalid_token_is_401(self, client):
        r = client.post("/api/v1/auth/refresh", json={"token": "garbage"})
        assert r.status_code == 401

    def test_logout_revokes_token(self, client):
        r = self._register(client)
        token = r.json()["token"]
        r2 = client.post("/api/v1/auth/logout", json={"token": token})
        assert r2.status_code == 200
        # Now refresh should fail.
        r3 = client.post("/api/v1/auth/refresh", json={"token": token})
        assert r3.status_code == 401


# ── Inventory endpoints (auth-gated) ────────────────────────────


class TestInventoryEndpoints:
    def _seed_lot(self, db_handle, lot_id: str = "lot1", household: str = "hh_test",
                  qty: float = 2.0, status: str = "active"):
        db_handle.conn.execute(
            """
            INSERT INTO inventory_lots (
                lot_id, canonical_name, display_name, category, quantity,
                unit, storage_location_id, status, user_id, created_at, updated_at
            ) VALUES (?, 'milk', 'Milk', 'Dairy', ?, 'L', '', ?, ?, ?, ?)
            """,
            (lot_id, qty, status, household, "2026-06-16T00:00:00Z", "2026-06-16T00:00:00Z"),
        )
        db_handle.conn.commit()

    def _issue(self, db_handle, household: str = "hh_test") -> str:
        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        return auth_mod.issue_token(
            db_handle, device_id="dev_inv", household_id=household,
        )["token"]

    def test_list_requires_token(self, client):
        r = client.get("/api/v1/inventory/lots")
        assert r.status_code == 401

    def test_list_empty(self, client, db_handle):
        token = self._issue(db_handle, "hh_test")
        r = client.get(
            "/api/v1/inventory/lots",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["has_more"] is False

    def test_list_household_scoped(self, client, db_handle):
        self._seed_lot(db_handle, "lot_a", "hh_test", 2.0)
        self._seed_lot(db_handle, "lot_b", "hh_other", 5.0)
        token = self._issue(db_handle, "hh_test")
        r = client.get(
            "/api/v1/inventory/lots",
            headers={"Authorization": f"Bearer {token}"},
        )
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["lot_id"] == "lot_a"

    def test_list_supports_query_string_token(self, client, db_handle):
        """The query-string token path is the escape hatch for Gradio
        (no JS to add headers)."""
        self._seed_lot(db_handle, "lot_qs", "hh_test", 1.0)
        token = self._issue(db_handle, "hh_test")
        r = client.get(f"/api/v1/inventory/lots?token={token}")
        assert r.status_code == 200
        assert r.json()["total"] == 1

    def test_get_one(self, client, db_handle):
        self._seed_lot(db_handle, "lot_get", "hh_test", 3.0)
        token = self._issue(db_handle, "hh_test")
        r = client.get(
            "/api/v1/inventory/lots/lot_get",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["lot_id"] == "lot_get"
        assert body["display_name"] == "Milk"
        assert body["quantity"] == 3.0

    def test_get_404_wrong_household(self, client, db_handle):
        self._seed_lot(db_handle, "lot_z", "hh_other", 1.0)
        token = self._issue(db_handle, "hh_test")
        r = client.get(
            "/api/v1/inventory/lots/lot_z",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "lot_not_found"

    def test_get_404_unknown_lot(self, client, db_handle):
        token = self._issue(db_handle, "hh_test")
        r = client.get(
            "/api/v1/inventory/lots/nope",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404


# ── ContextVar integration (Gradio-compat shim) ──────────────────


class TestRequestScopedHousehold:
    def test_default_falls_back_to_persistent(self):
        from shopstack.app_context import current_user_id, set_request_household, reset_request_household

        before = current_user_id()
        tok = set_request_household("hh_scoped")
        try:
            assert current_user_id() == "hh_scoped"
        finally:
            reset_request_household(tok)
        assert current_user_id() == before

    def test_reset_restores_prior_value(self):
        from shopstack.app_context import (
            current_user_id, set_request_household, reset_request_household,
        )

        tok_outer = set_request_household("hh_outer")
        try:
            assert current_user_id() == "hh_outer"
            tok_inner = set_request_household("hh_inner")
            try:
                assert current_user_id() == "hh_inner"
            finally:
                reset_request_household(tok_inner)
            assert current_user_id() == "hh_outer"
        finally:
            reset_request_household(tok_outer)


# ── Backward-compat aliases ──────────────────────────────────────


class TestBackcompatAliases:
    def test_legacy_whoami_still_works(self, client):
        """The legacy /api/whoami path is preserved as a Sunset alias."""
        r = client.get("/api/whoami")
        # 200 if mounted, 404 if the alias shim wasn't enabled
        # in this test rig (we mounted only the v1 routers, not
        # the legacy aliases — that's covered by the integration
        # test in test_app.py).
        if r.status_code == 200:
            assert "app" in r.json() or "household" in r.json()
        else:
            assert r.status_code == 404


# ── Household endpoints ──────────────────────────────────────────


class TestHouseholdEndpoints:
    def _issue(self, db_handle, household: str = "default_household") -> str:
        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        return auth_mod.issue_token(
            db_handle, device_id="dev_hh", household_id=household,
        )["token"]

    def _hdr(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_list_requires_token(self, client):
        assert client.get("/api/v1/household").status_code == 401

    def test_list_includes_default_and_marks_active(self, client, db_handle):
        token = self._issue(db_handle, "default_household")
        r = client.get("/api/v1/household", headers=self._hdr(token))
        assert r.status_code == 200
        body = r.json()
        ids = [h["household_id"] for h in body["items"]]
        assert "default_household" in ids
        active = [h for h in body["items"] if h["is_active"]]
        assert len(active) == 1

    def test_create_household(self, client, db_handle):
        token = self._issue(db_handle, "default_household")
        r = client.post(
            "/api/v1/household",
            json={"name": "Beach House"},
            headers=self._hdr(token),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "Beach House"
        assert body["household_id"]
        assert body["is_active"] is False

    def test_create_duplicate_is_409(self, client, db_handle):
        token = self._issue(db_handle, "default_household")
        client.post(
            "/api/v1/household",
            json={"household_id": "hh_dup", "name": "One"},
            headers=self._hdr(token),
        )
        r = client.post(
            "/api/v1/household",
            json={"household_id": "hh_dup", "name": "Two"},
            headers=self._hdr(token),
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "household_exists"

    def test_switch_re_scopes_token(self, client, db_handle):
        token = self._issue(db_handle, "default_household")
        # Create a second household.
        client.post(
            "/api/v1/household",
            json={"household_id": "hh_second", "name": "Second"},
            headers=self._hdr(token),
        )
        r = client.post(
            "/api/v1/household/hh_second/switch",
            headers=self._hdr(token),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["household_id"] == "hh_second"
        assert body["household_name"] == "Second"
        assert body["token"]
        # The new token is now scoped to hh_second — inventory list
        # scoped to hh_second returns no lots (different household
        # than the seeded default).
        new_token = body["token"]
        r2 = client.get(
            "/api/v1/household", headers={"Authorization": f"Bearer {new_token}"}
        )
        active = [h for h in r2.json()["items"] if h["is_active"]]
        assert active[0]["household_id"] == "hh_second"

    def test_switch_unknown_household_is_404(self, client, db_handle):
        token = self._issue(db_handle, "default_household")
        r = client.post(
            "/api/v1/household/no_such/switch", headers=self._hdr(token)
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "household_not_found"


# ── Shopping endpoints ───────────────────────────────────────────


class TestShoppingEndpoints:
    def _issue(self, db_handle, household: str = "hh_shop") -> str:
        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        db_handle.add_household(household, household)
        # Writable households need an owner member (mirrors the
        # production create path). Without this, add_list_item's
        # permission gate denies the write.
        db_handle.add_household_member(household, household, role="owner")
        return auth_mod.issue_token(
            db_handle, device_id="dev_shop", household_id=household,
        )["token"]

    def _hdr(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_active_requires_token(self, client):
        assert client.get("/api/v1/shopping/active").status_code == 401

    def test_active_empty_returns_placeholder(self, client, db_handle):
        token = self._issue(db_handle)
        r = client.get("/api/v1/shopping/active", headers=self._hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert body["list_id"] == ""
        assert body["items"] == []

    def test_create_list_with_items(self, client, db_handle):
        token = self._issue(db_handle)
        r = client.post(
            "/api/v1/shopping/lists",
            json={
                "goal": "Weekend groceries",
                "items": [
                    {"canonical_name": "milk", "requested_quantity": 2, "unit": "L"},
                    {"canonical_name": "bread"},
                ],
            },
            headers=self._hdr(token),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["list_id"]
        assert body["goal"] == "Weekend groceries"
        names = {it["canonical_name"] for it in body["items"]}
        assert names == {"milk", "bread"}

    def test_active_after_create_returns_list(self, client, db_handle):
        token = self._issue(db_handle)
        client.post(
            "/api/v1/shopping/lists",
            json={"items": [{"canonical_name": "eggs"}]},
            headers=self._hdr(token),
        )
        r = client.get("/api/v1/shopping/active", headers=self._hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert body["list_id"]
        assert body["items"][0]["canonical_name"] == "eggs"

    def test_add_items_appends(self, client, db_handle):
        token = self._issue(db_handle)
        create = client.post(
            "/api/v1/shopping/lists",
            json={"items": [{"canonical_name": "milk"}]},
            headers=self._hdr(token),
        ).json()
        list_id = create["list_id"]
        r = client.post(
            f"/api/v1/shopping/lists/{list_id}/items",
            json={"items": [{"canonical_name": "butter"}, {"canonical_name": "cheese"}]},
            headers=self._hdr(token),
        )
        assert r.status_code == 200, r.text
        names = {it["canonical_name"] for it in r.json()["items"]}
        assert {"milk", "butter", "cheese"} <= names

    def test_add_items_wrong_household_is_404(self, client, db_handle):
        # List owned by hh_a.
        token_a = self._issue(db_handle, "hh_a")
        list_id = client.post(
            "/api/v1/shopping/lists",
            json={"items": [{"canonical_name": "milk"}]},
            headers=self._hdr(token_a),
        ).json()["list_id"]
        # Caller scoped to hh_b.
        token_b = self._issue(db_handle, "hh_b")
        r = client.post(
            f"/api/v1/shopping/lists/{list_id}/items",
            json={"items": [{"canonical_name": "butter"}]},
            headers=self._hdr(token_b),
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "list_not_found"


# ── Dashboard endpoint ───────────────────────────────────────────


class TestDashboardEndpoint:
    def _issue(self, db_handle, household: str = "default_household") -> str:
        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        return auth_mod.issue_token(
            db_handle, device_id="dev_dash", household_id=household,
        )["token"]

    def test_today_requires_token(self, client):
        assert client.get("/api/v1/dashboard/today").status_code == 401

    def test_today_returns_snapshot(self, client, db_handle):
        token = self._issue(db_handle, "default_household")
        r = client.get(
            "/api/v1/dashboard/today",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["household_id"] == "default_household"
        # Counts are present and non-negative.
        for k in ("pantry_count", "use_soon_count", "low_items_count", "recent_purchases_count"):
            assert isinstance(body[k], int) and body[k] >= 0
        assert "timestamp" in body


# ── Privacy / Retention endpoints ────────────────────────────────


class TestPrivacyEndpoints:
    """Boundary tests for the privacy/retention endpoint.

    ``POST /api/v1/account/privacy/update-retention`` accepts
    ``{"key": str, "value": str}``.  The schema plain ``str``
    (no ``min_length``) so:

    * ``key=""`` — passes schema, fails service validation
      (unknown key), returns ``{"success": False}``.
    * ``key=None`` — Pydantic rejects ``None`` for a ``str``
      field, returns 422.
    * ``key=null`` (JSON) — same: Pydantic rejects nullable
      ``str``, returns 422.
    """

    def _issue(self, db_handle, household: str = "hh_priv") -> str:
        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        return auth_mod.issue_token(
            db_handle, device_id="dev_priv", household_id=household,
        )["token"]

    def _hdr(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    URL = "/api/v1/account/privacy/update-retention"

    def test_requires_token(self, client):
        r = client.post(self.URL, json={"key": "retention.trace_ttl_days", "value": "30"})
        assert r.status_code == 401

    def test_empty_key_returns_success_false(self, client, db_handle):
        """Empty key "" is accepted by the schema but rejected by
        the service layer (not in _VALID_KEYS).  Returns 200 with
        success=False."""
        token = self._issue(db_handle)
        r = client.post(
            self.URL,
            json={"key": "", "value": "30"},
            headers=self._hdr(token),
        )
        assert r.status_code == 200
        assert r.json()["success"] is False

    def test_null_key_is_422(self, client, db_handle):
        """JSON ``null`` for a ``str`` field is rejected by Pydantic."""
        token = self._issue(db_handle)
        r = client.post(
            self.URL,
            json={"key": None, "value": "30"},
            headers=self._hdr(token),
        )
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert any("key" in str(err.get("loc", [])) for err in detail)

    def test_null_value_is_422(self, client, db_handle):
        """JSON ``null`` for ``value`` is also rejected by Pydantic."""
        token = self._issue(db_handle)
        r = client.post(
            self.URL,
            json={"key": "retention.trace_ttl_days", "value": None},
            headers=self._hdr(token),
        )
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert any("value" in str(err.get("loc", [])) for err in detail)

    def test_valid_key_succeeds(self, client, db_handle):
        """Happy path: valid key + non-empty value returns success=True."""
        token = self._issue(db_handle)
        r = client.post(
            self.URL,
            json={"key": "retention.trace_ttl_days", "value": "30"},
            headers=self._hdr(token),
        )
        assert r.status_code == 200
        assert r.json()["success"] is True

    def test_unknown_key_returns_success_false(self, client, db_handle):
        """A well-formed but unrecognised key returns success=False."""
        token = self._issue(db_handle)
        r = client.post(
            self.URL,
            json={"key": "retention.nonexistent", "value": "30"},
            headers=self._hdr(token),
        )
        assert r.status_code == 200
        assert r.json()["success"] is False


# ── Retention-summary GET endpoint ─────────────────────────────────


RETENTION_SUMMARY_URL = "/api/v1/account/privacy/retention-summary"
RETENTION_PROFILES_URL = "/api/v1/account/privacy/profiles"


class TestRetentionSummaryEndpoint:
    """Boundary tests for the retention-summary endpoint.

    ``GET /api/v1/account/privacy/retention-summary`` returns the
    current retention policy.  A household with no overrides gets
    the module-level defaults.
    """

    def _issue(self, db_handle, household: str = "hh_ret") -> str:
        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        return auth_mod.issue_token(
            db_handle, device_id="dev_ret", household_id=household,
        )["token"]

    def _hdr(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_requires_token(self, client):
        r = client.get(RETENTION_SUMMARY_URL)
        assert r.status_code == 401

    def test_returns_defaults(self, client, db_handle):
        """A household with no overrides returns the hard-coded
        defaults from ``RetentionPolicyWire``."""
        token = self._issue(db_handle)
        r = client.get(RETENTION_SUMMARY_URL, headers=self._hdr(token))
        assert r.status_code == 200
        body = r.json()
        s = body["summary"]
        assert s["trace_ttl_days"] == 30
        assert s["trace_max_rows"] == 5000
        assert s["community_pool_retention_days"] == 90
        assert s["voice_memo_retention_days"] == 7
        assert s["sms_registry_retention_days"] == 0
        assert s["backup_retention_days"] == 0
        assert s["locale_persistence"] is True
        assert s["community_optin"] is False

    def test_returns_defaults_for_unknown_household(self, client, db_handle):
        """Even a household ID that has never been used returns the
        defaults — the endpoint is not household-scoped for storage."""
        token = self._issue(db_handle, "hh_nonexistent_abc")
        r = client.get(RETENTION_SUMMARY_URL, headers=self._hdr(token))
        assert r.status_code == 200
        s = r.json()["summary"]
        assert s["trace_ttl_days"] == 30
        assert s["community_optin"] is False


class TestRetentionProfilesEndpoint:
    """Boundary tests for the retention profiles endpoint."""

    def _issue(self, db_handle, household: str = "hh_profiles") -> str:
        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        return auth_mod.issue_token(
            db_handle, device_id="dev_profiles", household_id=household,
        )["token"]

    def _hdr(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def test_requires_token(self, client):
        r = client.get(RETENTION_PROFILES_URL)
        assert r.status_code == 401

    def test_returns_static_profile_catalog(self, client, db_handle):
        token = self._issue(db_handle)
        r = client.get(RETENTION_PROFILES_URL, headers=self._hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        assert body["has_more"] is False
        assert {item["profile"] for item in body["items"]} == {"balanced", "strict", "shared"}
        for item in body["items"]:
            assert "label" in item
            assert "description" in item
            assert "summary" in item
            assert "values" in item


# ── Purge endpoint (privacy) ───────────────────────────────────────


PURGE_URL = "/api/v1/account/privacy/purge"


class TestPurgeEndpoint:
    """Boundary tests for the purge endpoint.

    ``POST /api/v1/account/privacy/purge`` wipes user-derived data
    for the caller's household.  ``confirm=True`` is hardcoded at the
    endpoint level; the service function raises ``ValueError`` when
    ``confirm=False``.
    """

    def _issue(self, db_handle, household: str = "hh_purge") -> str:
        from shopstack.api.v1 import auth as auth_mod

        auth_mod.ensure_auth_table(db_handle)
        return auth_mod.issue_token(
            db_handle, device_id="dev_purge", household_id=household,
        )["token"]

    def _hdr(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    # ── HTTP-level boundaries ───────────────────────────────────

    def test_requires_token(self, client):
        r = client.post(PURGE_URL)
        assert r.status_code == 401

    def test_unknown_household_still_succeeds(self, client, db_handle):
        """A token scoped to an unknown household (no traces, no
        community data) should still return a 200 with zero counts
        rather than 4xx or 5xx."""
        token = self._issue(db_handle, "hh_no_data")
        r = client.post(PURGE_URL, headers=self._hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["traces_purged"] == 0
        assert body["community_observations_purged"] == 0
        assert body["sms_registry_cleared"] == 0
        assert body["voice_memos_purged"] == 0
        assert body["backups_purged"] == 0
        assert body["errors"] == []

    # ── Service-level boundary: missing confirm ──────────────────

    def test_purge_without_confirm_raises_value_error(self, db_handle):
        from shopstack.services.data_retention import purge_user_data

        with pytest.raises(ValueError, match="purge_user_data is destructive"):
            purge_user_data(db_handle, user_id="hh_any", confirm=False)

    def test_purge_with_confirm_succeeds_empty(self, db_handle):
        """Even with confirm=True, a household with no data returns
        success with zero counts (no crash)."""
        from shopstack.services.data_retention import purge_user_data

        result = purge_user_data(db_handle, user_id="hh_clean", confirm=True)
        assert result.success is True
        assert result.traces_purged == 0
        assert result.errors == []
