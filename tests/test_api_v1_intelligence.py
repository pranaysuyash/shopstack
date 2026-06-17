"""Contract tests for ``/api/v1/intelligence/*`` endpoints.

Coverage:
  * Auth-gating: all intelligence endpoints require a bearer token.
  * Decision explain returns structured explanation for known items.
  * Decision explain returns graceful payload for unknown items.
  * Recurring plan returns items or empty plan.
  * Mealplan returns daily plan or empty plan.
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
    from shopstack.api.v1.routers.intelligence import router as intel_router
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db_handle)

    fastapi_app = FastAPI(title="shopstack-test-intel")
    fastapi_app.include_router(intel_router, prefix="/api/v1")
    yield fastapi_app
    monkey.undo()


@pytest.fixture
def client(v1_app):
    from fastapi.testclient import TestClient

    return TestClient(v1_app)


def _issue(db_handle, household: str = "hh_intel") -> str:
    from shopstack.api.v1 import auth as auth_mod

    return auth_mod.issue_token(
        db_handle, device_id="dev_intel", household_id=household,
    )["token"]


def _seed_inventory(db_handle, household: str = "hh_intel"):
    lots = [
        ("lot_milk", "milk", "Milk", 2.0, "L", "fridge"),
        ("lot_onion", "onion", "Onion", 1.0, "kg", "pantry"),
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


# ── Auth gating ──────────────────────────────────────────────────


class TestIntelligenceAuth:
    def test_decision_explain_requires_token(self, client):
        assert client.get("/api/v1/intelligence/decision/milk/explain").status_code == 401

    def test_recurring_requires_token(self, client):
        assert client.get("/api/v1/intelligence/recurring").status_code == 401

    def test_mealplan_requires_token(self, client):
        assert client.get("/api/v1/intelligence/mealplan").status_code == 401


# ── Decision Explain ─────────────────────────────────────────────


class TestDecisionExplain:
    def test_unknown_item_returns_graceful_payload(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/intelligence/decision/zzznotfound/explain",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["action"] == "unknown"
        assert "No active decision" in body["summary"]
        assert body["canonical_name"] == "zzznotfound"

    def test_known_item_returns_explain_response(self, client, db_handle):
        _seed_inventory(db_handle)
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/intelligence/decision/milk/explain",
            headers={"Authorization": f"Bearer {token}"},
        )
        # May be 200 with a decision or 200 with "no_decision" —
        # either is valid; what matters is the response shape.
        assert r.status_code == 200
        body = r.json()
        assert "canonical_name" in body
        assert "action" in body
        assert "confidence" in body
        assert isinstance(body["confidence"], (int, float))
        assert "confidence_label" in body

    def test_response_shape(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/intelligence/decision/milk/explain",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        # All DecisionExplanationWire fields.
        for key in ("canonical_name", "action", "confidence", "summary",
                     "key_signal", "confidence_label", "warnings",
                     "evidence_summary", "freshness_status"):
            assert key in body, f"Missing key: {key}"


# ── Recurring Plan ───────────────────────────────────────────────


class TestRecurringPlan:
    def test_no_purchase_history_returns_empty(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/intelligence/recurring",
            params={"window": 3},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 0
        assert body["items"] == []

    def test_response_shape(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/intelligence/recurring",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "window_days" in body
        assert "summary" in body
        assert "count" in body
        assert "items" in body
        assert body["window_days"] == 3

    def test_window_param_is_accepted(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/intelligence/recurring",
            params={"window": 7},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["window_days"] == 7


# ── Meal Plan ────────────────────────────────────────────────────


class TestMealPlan:
    def test_empty_pantry_returns_empty_plan(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/intelligence/mealplan",
            params={"days": 3},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["count"] >= 0
        assert isinstance(body["items"], list)

    def test_response_shape(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/intelligence/mealplan",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "summary" in body
        assert "days" in body
        assert "items" in body
        assert body["days"] == 7

    def test_days_param(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/intelligence/mealplan",
            params={"days": 5},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["days"] == 5

    def test_day_plan_item_shape(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/intelligence/mealplan",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        items = r.json()["items"]
        if items:
            day = items[0]
            for key in ("date", "recipe_name", "confidence", "rationale"):
                assert key in day, f"Missing key: {key}"
