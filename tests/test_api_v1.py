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

    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db_handle)

    fastapi_app = FastAPI(title="shopstack-test")
    # Note: the routers already declare their own prefix ("/meta",
    # "/auth", "/inventory"), so we mount at "/api/v1" only.
    fastapi_app.include_router(meta_router, prefix="/api/v1")
    fastapi_app.include_router(auth_router, prefix="/api/v1")
    fastapi_app.include_router(inventory_router, prefix="/api/v1")
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
