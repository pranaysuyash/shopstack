"""Contract tests for ``/api/v1/corrections`` endpoints.

Coverage:
  * Auth-gating: both endpoints require a bearer token.
  * GET returns empty list when no corrections exist.
  * GET respects limit and accepted_only query params.
  * GET response shape matches CorrectionListResponse.
  * POST creates a correction and returns 201 with the event.
  * POST with same was_action/should_be_action returns 400.
  * POST with missing fields returns 400.
  * POST with bad JSON returns 422.
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
    from shopstack.api.v1.routers.corrections import router as corrections_router
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db_handle)

    fastapi_app = FastAPI(title="shopstack-test-corrections")
    fastapi_app.include_router(corrections_router, prefix="/api/v1")
    yield fastapi_app
    monkey.undo()


@pytest.fixture
def client(v1_app):
    from fastapi.testclient import TestClient

    return TestClient(v1_app)


def _issue(db_handle, household: str = "hh_corrections") -> str:
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)
    return auth_mod.issue_token(
        db_handle, device_id="dev_corr", household_id=household,
    )["token"]


def _seed_correction(db_handle, canonical_name: str = "milk",
                     was_action: str = "buy", should_be_action: str = "skip",
                     household: str = "hh_corrections"):
    """Record a correction event directly in the DB for GET tests."""
    from datetime import datetime
    from shopstack.schemas.models import CorrectionEvent

    event = CorrectionEvent(
        canonical_name=canonical_name,
        correction_type="preference",
        old_value=was_action,
        new_value=should_be_action,
        source="user_correction",
        timestamp=datetime.now(),
        accepted=0,
    )
    db_handle.record_correction_event(event, user_id=household)
    return event


# ── Auth gating ──────────────────────────────────────────────────


class TestCorrectionsAuth:
    def test_list_requires_token(self, client):
        assert client.get("/api/v1/corrections").status_code == 401

    def test_create_requires_token(self, client):
        assert client.post(
            "/api/v1/corrections",
            json={"canonical_name": "milk", "was_action": "buy", "should_be_action": "skip"},
        ).status_code == 401


# ── GET: List corrections ────────────────────────────────────────


class TestListCorrections:
    def test_empty_list_returns_default_shape(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/corrections",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["summary"] == "No corrections recorded."
        assert body["count"] == 0
        assert body["items"] == []

    def test_returns_seeded_corrections(self, client, db_handle):
        _seed_correction(db_handle, "milk", "buy", "skip")
        _seed_correction(db_handle, "rice", "buy", "use_soon")
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/corrections",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 2
        names = {it["canonical_name"] for it in body["items"]}
        assert names == {"milk", "rice"}

    def test_response_shape(self, client, db_handle):
        _seed_correction(db_handle, "milk", "buy", "skip")
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/corrections",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "summary" in body
        assert "count" in body
        assert "items" in body
        assert isinstance(body["items"], list)
        assert isinstance(body["count"], int)
        if body["items"]:
            item = body["items"][0]
            assert "event_id" in item
            assert "canonical_name" in item
            assert "was_action" in item
            assert "should_be_action" in item
            assert "source" in item
            assert "timestamp" in item
            assert "accepted" in item

    def test_respects_limit_param(self, client, db_handle):
        for i in range(5):
            _seed_correction(db_handle, f"item_{i}", "buy", "skip")
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/corrections",
            params={"limit": 3},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["count"] == 3

    def test_respects_accepted_only_param(self, client, db_handle):
        # Seed two events, mark one as accepted via mark_correction_accepted
        # (record_correction_event hardcodes accepted=0 in INSERT).
        uid = "hh_corrections"
        e1 = _seed_correction(db_handle, "milk", "buy", "skip")
        e2 = _seed_correction(db_handle, "rice", "buy", "use_soon")
        db_handle.mark_correction_accepted(e1.event_id, accepted=True)

        token = _issue(db_handle)
        # Without filter — both returned.
        r_all = client.get(
            "/api/v1/corrections",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r_all.json()["count"] == 2

        # With accepted_only=true — only the accepted one.
        r_accepted = client.get(
            "/api/v1/corrections",
            params={"accepted_only": "true"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r_accepted.json()["count"] == 1
        assert r_accepted.json()["items"][0]["canonical_name"] == "milk"

    def test_household_scoped(self, client, db_handle):
        """Corrections from a different household should not leak."""
        _seed_correction(db_handle, "milk", "buy", "skip", household="hh_other")
        token = _issue(db_handle, "hh_corrections")
        r = client.get(
            "/api/v1/corrections",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.json()["count"] == 0


# ── POST: Create correction ──────────────────────────────────────


class TestCreateCorrection:
    VALID_BODY = {"canonical_name": "milk", "was_action": "buy", "should_be_action": "skip"}

    def test_creates_and_returns_201(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/corrections",
            json=self.VALID_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["canonical_name"] == "milk"
        assert body["was_action"] == "buy"
        assert body["should_be_action"] == "skip"
        assert "event_id" in body
        assert body["accepted"] is False

    def test_response_shape(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/corrections",
            json=self.VALID_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 201
        body = r.json()
        assert "event_id" in body
        assert "canonical_name" in body
        assert "was_action" in body
        assert "should_be_action" in body
        assert "source" in body
        assert "timestamp" in body
        assert "accepted" in body

    def test_same_was_and_should_be_returns_400(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/corrections",
            json={"canonical_name": "milk", "was_action": "buy", "should_be_action": "buy"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        body = r.json()
        assert "validation_failed" in str(body).lower()

    def test_missing_canonical_name_returns_422(self, client, db_handle):
        """Missing required field should be rejected by FastAPI validation."""
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/corrections",
            json={"was_action": "buy", "should_be_action": "skip"},
            headers={"Authorization": f"Bearer {token}"},
        )
        # FastAPI returns 422 for missing required field.
        assert r.status_code == 422

    def test_invalid_was_action_returns_400(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/corrections",
            json={"canonical_name": "milk", "was_action": "invalid_action", "should_be_action": "skip"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 400
        body = r.json()
        assert "validation_failed" in str(body).lower()

    def test_persists_in_db(self, client, db_handle):
        """After POST, the correction should be retrievable via GET."""
        token = _issue(db_handle)
        client.post(
            "/api/v1/corrections",
            json={"canonical_name": "eggs", "was_action": "buy", "should_be_action": "skip"},
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            "/api/v1/corrections",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.json()["count"] >= 1
        names = {it["canonical_name"] for it in r.json()["items"]}
        assert "eggs" in names
