"""Contract tests for ``/api/v1/household`` endpoints.

Coverage:
  * Auth-gating: all three endpoints require a bearer token.
  * GET returns list of households with correct active flag.
  * GET response shape matches HouseholdListResponse schema.
  * POST creates a household with derived or explicit id.
  * POST duplicate returns 409 conflict.
  * POST response shape matches Household schema.
  * POST /switch re-scopes the token to the target household.
  * POST /switch to unknown household returns 404.
  * Switch response shape matches TokenResponse.
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
    from shopstack.api.v1.routers.household import router as household_router
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)
    # The household router reads/writes via app_context.db
    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db_handle)

    fastapi_app = FastAPI(title="shopstack-test-household")
    fastapi_app.include_router(household_router, prefix="/api/v1")
    yield fastapi_app
    monkey.undo()


@pytest.fixture
def client(v1_app):
    from fastapi.testclient import TestClient

    return TestClient(v1_app)


def _issue(db_handle, household: str = "default_household") -> str:
    """Issue a bearer token scoped to *household*."""
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)
    return auth_mod.issue_token(
        db_handle, device_id="dev_hh", household_id=household,
    )["token"]


def _hdr(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _list(client, token: str):
    """Helper: GET /api/v1/household and return the JSON body."""
    r = client.get("/api/v1/household", headers=_hdr(token))
    assert r.status_code == 200
    return r.json()


# ── Auth gating ──────────────────────────────────────────────────


class TestHouseholdAuth:
    def test_list_requires_token(self, client):
        assert client.get("/api/v1/household").status_code == 401

    def test_create_requires_token(self, client):
        assert client.post(
            "/api/v1/household", json={"name": "Test"},
        ).status_code == 401

    def test_switch_requires_token(self, client):
        assert client.post(
            "/api/v1/household/some_id/switch",
        ).status_code == 401


# ── GET /api/v1/household ────────────────────────────────────────


class TestListHouseholds:
    def test_empty_list_returns_default(self, client, db_handle):
        """A fresh DB has a 'default_household' seeded by Database()."""
        token = _issue(db_handle)
        body = _list(client, token)
        assert "items" in body
        assert "active_household_id" in body
        ids = [h["household_id"] for h in body["items"]]
        assert "default_household" in ids
        # Exactly one household should be active.
        active = [h for h in body["items"] if h["is_active"]]
        assert len(active) == 1

    def test_response_shape(self, client, db_handle):
        """Response matches HouseholdListResponse schema."""
        token = _issue(db_handle)
        body = _list(client, token)
        assert "items" in body
        assert isinstance(body["items"], list)
        assert "active_household_id" in body
        assert isinstance(body["active_household_id"], str)
        if body["items"]:
            h = body["items"][0]
            assert "household_id" in h
            assert "name" in h
            assert "is_active" in h
            assert isinstance(h["is_active"], bool)

    def test_multiple_households_shows_correct_active(self, client, db_handle):
        """After creating a second household, the list shows both with one active."""
        token = _issue(db_handle, "default_household")
        # Create a second household.
        client.post("/api/v1/household", json={"name": "Vacation"}, headers=_hdr(token))
        body = _list(client, token)
        assert len(body["items"]) >= 2
        ids = {h["household_id"] for h in body["items"]}
        assert "default_household" in ids
        # 'Vacation' slug is 'vacation' or 'vacation_hh' depending on _slug()
        active = [h for h in body["items"] if h["is_active"]]
        assert len(active) == 1
        # The active household is the one our token is scoped to.
        assert active[0]["household_id"] == "default_household"

    def test_household_item_shape(self, client, db_handle):
        """Each item in the list matches the Household schema."""
        token = _issue(db_handle)
        body = _list(client, token)
        for h in body["items"]:
            assert "household_id" in h
            assert "name" in h
            assert "is_active" in h
            assert isinstance(h["household_id"], str)
            assert isinstance(h["name"], str)
            assert isinstance(h["is_active"], bool)
            assert len(h["household_id"]) > 0
            assert len(h["name"]) > 0


# ── POST /api/v1/household ───────────────────────────────────────


class TestCreateHousehold:
    def test_create_with_auto_id(self, client, db_handle):
        """Creating a household with just a name derives the id from a slug."""
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/household",
            json={"name": "Beach House"},
            headers=_hdr(token),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "Beach House"
        assert body["household_id"]  # Should be auto-derived (e.g. 'beach_house')
        assert body["is_active"] is False  # New household is not active

    def test_create_with_explicit_id(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/household",
            json={"household_id": "hh_mountain", "name": "Mountain Cabin"},
            headers=_hdr(token),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["household_id"] == "hh_mountain"
        assert body["name"] == "Mountain Cabin"
        assert body["is_active"] is False

    def test_create_duplicate_is_409(self, client, db_handle):
        token = _issue(db_handle)
        client.post(
            "/api/v1/household",
            json={"household_id": "hh_dup", "name": "First"},
            headers=_hdr(token),
        )
        r = client.post(
            "/api/v1/household",
            json={"household_id": "hh_dup", "name": "Second"},
            headers=_hdr(token),
        )
        assert r.status_code == 409
        body = r.json()
        assert body["detail"]["code"] == "household_exists"

    def test_create_response_shape(self, client, db_handle):
        """Response matches the Household schema."""
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/household",
            json={"name": "Shape Test"},
            headers=_hdr(token),
        )
        assert r.status_code == 201
        body = r.json()
        assert "household_id" in body
        assert "name" in body
        assert "is_active" in body
        assert body["name"] == "Shape Test"
        assert body["is_active"] is False

    def test_create_with_notes(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/household",
            json={"name": "With Notes", "notes": "Some notes about this household"},
            headers=_hdr(token),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["name"] == "With Notes"

    def test_create_missing_name_returns_422(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/household",
            json={},
            headers=_hdr(token),
        )
        assert r.status_code == 422

    def test_new_household_appears_in_list(self, client, db_handle):
        """After creating a household, it appears in the list."""
        token = _issue(db_handle)
        client.post(
            "/api/v1/household",
            json={"name": "Newly Created"},
            headers=_hdr(token),
        )
        body = _list(client, token)
        names = {h["name"] for h in body["items"]}
        assert "Newly Created" in names


# ── POST /api/v1/household/{id}/switch ───────────────────────────


class TestSwitchHousehold:
    def test_switch_to_existing_returns_200(self, client, db_handle):
        token = _issue(db_handle, "default_household")
        # Create a second household.
        client.post(
            "/api/v1/household",
            json={"household_id": "hh_target", "name": "Target"},
            headers=_hdr(token),
        )
        r = client.post("/api/v1/household/hh_target/switch", headers=_hdr(token))
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["household_id"] == "hh_target"
        assert body["household_name"] == "Target"

    def test_switch_response_shape(self, client, db_handle):
        """Response matches TokenResponse schema."""
        token = _issue(db_handle, "default_household")
        client.post(
            "/api/v1/household",
            json={"household_id": "hh_shape", "name": "Shape"},
            headers=_hdr(token),
        )
        r = client.post("/api/v1/household/hh_shape/switch", headers=_hdr(token))
        assert r.status_code == 200
        body = r.json()
        assert "token" in body
        assert "expires_at" in body
        assert "household_id" in body
        assert "household_name" in body
        assert body["household_id"] == "hh_shape"
        assert len(body["token"]) > 0

    def test_switch_to_unknown_is_404(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post("/api/v1/household/no_such_household/switch", headers=_hdr(token))
        assert r.status_code == 404
        body = r.json()
        assert body["detail"]["code"] == "household_not_found"

    def test_switch_re_scopes_token(self, client, db_handle):
        """The new token is scoped to the switched household."""
        token = _issue(db_handle, "default_household")
        client.post(
            "/api/v1/household",
            json={"household_id": "hh_scoped", "name": "Scoped"},
            headers=_hdr(token),
        )
        r = client.post("/api/v1/household/hh_scoped/switch", headers=_hdr(token))
        assert r.status_code == 200
        new_token = r.json()["token"]

        # Use the new token to GET /api/v1/household — the active household
        # should now be hh_scoped.
        body = _list(client, new_token)
        active = [h for h in body["items"] if h["is_active"]]
        assert len(active) == 1
        assert active[0]["household_id"] == "hh_scoped"

    def test_switch_updates_server_active_state(self, client, db_handle):
        """After switch, db.active_household_id is updated server-side."""
        token = _issue(db_handle, "default_household")
        client.post(
            "/api/v1/household",
            json={"household_id": "hh_state", "name": "State"},
            headers=_hdr(token),
        )
        client.post("/api/v1/household/hh_state/switch", headers=_hdr(token))
        body = _list(client, token)
        active = [h for h in body["items"] if h["is_active"]]
        assert active[0]["household_id"] == "hh_state"

    def test_switch_old_token_still_valid(self, client, db_handle):
        """The old token remains valid after switching."""
        old_token = _issue(db_handle, "default_household")
        client.post(
            "/api/v1/household",
            json={"household_id": "hh_oldok", "name": "Old OK"},
            headers=_hdr(old_token),
        )
        client.post("/api/v1/household/hh_oldok/switch", headers=_hdr(old_token))
        # The old token should still be usable (not revoked).
        body = _list(client, old_token)
        assert "items" in body
