"""Contract tests for ``/api/v1/search/*`` endpoints.

Coverage:
  * Auth-gating: search requires a bearer token.
  * Global search returns results for matching inventory.
  * Inventory search returns semantic/prefix matches.
  * Voice-intent parser normalizes aliases and scene hints.
  * Empty query returns empty results.
  * Schema: response matches SearchResponse shape.
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
    """A bare FastAPI app with the search v1 router mounted."""
    from fastapi import FastAPI

    from shopstack import app_context
    from shopstack.api.v1.routers.search import router as search_router
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db_handle)

    fastapi_app = FastAPI(title="shopstack-test-search")
    fastapi_app.include_router(search_router, prefix="/api/v1")
    yield fastapi_app
    monkey.undo()


@pytest.fixture
def client(v1_app):
    from fastapi.testclient import TestClient

    return TestClient(v1_app)


def _issue(db_handle, household: str = "hh_search") -> str:
    from shopstack.api.v1 import auth as auth_mod

    return auth_mod.issue_token(
        db_handle, device_id="dev_search", household_id=household,
    )["token"]


def _seed_inventory(db_handle, household: str = "hh_search"):
    """Seed inventory items for a household so search has data."""
    lots = [
        ("lot_milk", "milk", "Milk", 2.0, "L", "fridge"),
        ("lot_rice", "rice", "Basmati Rice", 5.0, "kg", "pantry"),
        ("lot_dal", "dal", "Toor Dal", 1.0, "kg", "pantry"),
    ]
    for lot_id, cname, dname, qty, unit, loc in lots:
        db_handle.conn.execute(
            """INSERT INTO inventory_lots
               (lot_id, canonical_name, display_name, quantity, unit,
                storage_location_id, status, user_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)""",
            (lot_id, cname, dname, qty, unit, loc, household,
             "2026-06-17T00:00:00Z", "2026-06-17T00:00:00Z"),
        )
    db_handle.conn.commit()


# ── Contract tests ───────────────────────────────────────────────


class TestSearchAuth:
    def test_global_search_requires_token(self, client):
        assert client.get("/api/v1/search/global", params={"q": "milk"}).status_code == 401

    def test_inventory_search_requires_token(self, client):
        assert client.get("/api/v1/search/inventory", params={"q": "milk"}).status_code == 401


class TestSearchGlobal:
    def test_empty_query_rejected_as_invalid(self, client, db_handle):
        _seed_inventory(db_handle)
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/search/global",
            params={"q": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        # The router uses Query(..., min_length=1), so empty is rejected at validation.
        assert r.status_code == 422
        body = r.json()
        assert "detail" in body
        assert any("q" in str(err).lower() for err in body["detail"])

    def test_match_inventory_by_prefix(self, client, db_handle):
        _seed_inventory(db_handle)
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/search/global",
            params={"q": "mil"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["query"] == "mil"
        assert len(body["results"]) >= 1
        kinds = {res["kind"] for res in body["results"]}
        assert "inventory" in kinds

    def test_match_inventory_by_exact_name(self, client, db_handle):
        _seed_inventory(db_handle)
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/search/global",
            params={"q": "rice"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["count"] >= 1
        assert any("rice" in res["title"].lower() for res in body["results"])

    def test_response_shape(self, client, db_handle):
        _seed_inventory(db_handle)
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/search/global",
            params={"q": "milk"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "query" in body
        assert "results" in body
        assert "count" in body
        assert isinstance(body["results"], list)
        assert isinstance(body["count"], int)

    def test_result_wire_shape(self, client, db_handle):
        _seed_inventory(db_handle)
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/search/global",
            params={"q": "milk"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        results = r.json()["results"]
        if results:
            item = results[0]
            assert "kind" in item
            assert "title" in item
            assert "score" in item
            assert isinstance(item["score"], float)


class TestSearchInventory:
    def test_inventory_search_by_prefix(self, client, db_handle):
        _seed_inventory(db_handle)
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/search/inventory",
            params={"q": "dal"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["count"] >= 1

    def test_inventory_search_no_match_returns_empty(self, client, db_handle):
        _seed_inventory(db_handle)
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/search/inventory",
            params={"q": "zzzznotfound"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_inventory_search_response_shape(self, client, db_handle):
        _seed_inventory(db_handle)
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/search/inventory",
            params={"q": "milk"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "query" in body
        assert "results" in body
        assert "count" in body
        if body["count"] > 0:
            assert body["results"][0]["kind"] == "inventory"


class TestVoiceIntent:
    def test_voice_intent_public_and_normalized(self, client):
        r = client.post(
            "/api/v1/search/voice-intent",
            json={"text": "add 2 kg pyaaz for the fridge", "language": "en"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["original_text"] == "add 2 kg pyaaz for the fridge"
        assert body["language"] == "en"
        assert body["action"] == "add"
        assert "onion" in body["canonical_items"]
        assert body["target_scene"] == "fridge"
        assert body["confidence"] > 0.0

    def test_voice_intent_rejects_empty_text(self, client):
        r = client.post(
            "/api/v1/search/voice-intent",
            json={"text": "", "language": "en"},
        )
        assert r.status_code == 422
        body = r.json()
        assert "detail" in body
