"""Contract tests for ``/api/v1/dashboard`` endpoints.

Coverage:
  * Auth-gating: GET /api/v1/dashboard/today requires a bearer token.
  * Response shape matches DashboardSnapshot schema.
  * Empty household returns default snapshot with zero counts.
  * Household with inventory returns populated counts.
  * Counts are non-negative.
  * Household scoping: only the caller's household data is reflected.
  * Timestamp is present and non-empty.
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
    from shopstack.api.v1.routers.dashboard import router as dashboard_router
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)
    # Ensure a default household exists so dashboard has context.
    db_handle.add_household("default_household", "Default")

    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db_handle)
    try:
        from shopstack.tools.registry import ToolRegistry
        monkey.setattr(app_context, "tools", ToolRegistry(db_handle), raising=False)
    except Exception:
        pass

    fastapi_app = FastAPI(title="shopstack-test-dashboard")
    fastapi_app.include_router(dashboard_router, prefix="/api/v1")
    yield fastapi_app
    monkey.undo()


@pytest.fixture
def client(v1_app):
    from fastapi.testclient import TestClient

    return TestClient(v1_app)


def _issue(db_handle, household: str = "default_household") -> str:
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)
    return auth_mod.issue_token(
        db_handle, device_id="dev_dash", household_id=household,
    )["token"]


def _seed_lot(
    db_handle,
    lot_id: str = "lot1",
    qty: float = 2.0,
    status: str = "active",
    household: str = "default_household",
) -> None:
    """Insert an inventory lot (matches pattern from test_api_v1.py)."""
    db_handle.conn.execute(
        """
        INSERT INTO inventory_lots (
            lot_id, canonical_name, display_name, category, quantity,
            unit, storage_location_id, status, user_id, created_at, updated_at
        ) VALUES (?, 'milk', 'Milk', 'Dairy', ?, 'L', '', ?, ?, ?, ?)
        """,
        (lot_id, qty, status, household, "2026-06-17T00:00:00Z", "2026-06-17T00:00:00Z"),
    )
    db_handle.conn.commit()


# ── Auth gating ──────────────────────────────────────────────────


class TestDashboardAuth:
    def test_today_requires_token(self, client):
        assert client.get("/api/v1/dashboard/today").status_code == 401


# ── GET /api/v1/dashboard/today ─────────────────────────────────


class TestTodayEndpoint:
    def test_empty_household_returns_defaults(self, client, db_handle):
        """A household with no data should return a snapshot with zero counts."""
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/dashboard/today",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["household_id"] == "default_household"
        assert body["pantry_count"] == 0
        assert body["use_soon_count"] == 0
        assert body["low_items_count"] == 0
        assert body["recent_purchases_count"] == 0
        assert body["use_soon_items"] == []
        assert body["low_items"] == []
        assert body["recent_purchases"] == []
        assert body["has_trip_recommendation"] is False

    def test_response_shape_matches_schema(self, client, db_handle):
        """Every field expected by DashboardSnapshot must be present."""
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/dashboard/today",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "household_id" in body
        assert "timestamp" in body
        assert "pantry_count" in body
        assert "use_soon_count" in body
        assert "low_items_count" in body
        assert "recent_purchases_count" in body
        assert "use_soon_items" in body
        assert "low_items" in body
        assert "recent_purchases" in body
        assert "has_trip_recommendation" in body

    def test_counts_are_non_negative(self, client, db_handle):
        """Count fields should never be negative (default to 0)."""
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/dashboard/today",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        for key in ("pantry_count", "use_soon_count", "low_items_count", "recent_purchases_count"):
            assert isinstance(body[key], int) and body[key] >= 0, f"{key} is {body[key]}"

    def test_timestamp_is_iso_format(self, client, db_handle):
        """The timestamp must be a non-empty ISO 8601 string."""
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/dashboard/today",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        ts = body["timestamp"]
        assert ts and isinstance(ts, str)
        assert "T" in ts

    def test_household_scoping(self, client, db_handle):
        """Data from a different household should not affect the caller's dashboard."""
        _seed_lot(db_handle, "lot_a", qty=2.0, household="household_A")
        token = _issue(db_handle, "default_household")
        r = client.get(
            "/api/v1/dashboard/today",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["household_id"] == "default_household"
        assert body["pantry_count"] == 0, (
            f"Expected 0, got {body['pantry_count']}. "
            "Data from other households should not leak."
        )

    def test_populated_household_has_counts(self, client, db_handle):
        """A household with inventory should see non-zero counts."""
        _seed_lot(db_handle, "lot_pop_1", qty=2.0, household="default_household")
        _seed_lot(db_handle, "lot_pop_2", qty=1.0, household="default_household")
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/dashboard/today",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["pantry_count"] == 2
        assert body["household_id"] == "default_household"

    def test_includes_trip_recommendation_flag(self, client, db_handle):
        """has_trip_recommendation should be a boolean (defaults to False)."""
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/dashboard/today",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["has_trip_recommendation"], bool)

    def test_query_string_token_works(self, client, db_handle):
        """The query-string token path is the escape hatch for Gradio."""
        token = _issue(db_handle)
        r = client.get(f"/api/v1/dashboard/today?token={token}")
        assert r.status_code == 200
        body = r.json()
        assert body["household_id"] == "default_household"
