"""Contract tests for ``/api/v1/traces/*`` endpoints.

Coverage:
  * Auth gating: all trace endpoints require a bearer token.
  * List returns household-scoped recent traces.
  * Detail returns the redacted payload for one trace.
  * Export returns a JSONL payload string.
  * Household scoping prevents cross-tenant leakage.
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
    from shopstack.api.v1.routers.traces import router as traces_router
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db_handle)

    fastapi_app = FastAPI(title="shopstack-test-traces")
    fastapi_app.include_router(traces_router, prefix="/api/v1")
    yield fastapi_app
    monkey.undo()


@pytest.fixture
def client(v1_app):
    from fastapi.testclient import TestClient

    return TestClient(v1_app)


def _issue(db_handle, household: str = "hh_traces") -> str:
    from shopstack.api.v1 import auth as auth_mod

    auth_mod.ensure_auth_table(db_handle)
    return auth_mod.issue_token(
        db_handle, device_id="dev_trace", household_id=household,
    )["token"]


def _seed_trace(db_handle, household: str = "hh_traces", goal: str = "add milk"):
    from shopstack.schemas.models import Trace, ToolCall

    trace = Trace(
        input_type="command",
        user_goal=goal,
        redacted_user_request=goal,
        perception={"source": "ui"},
        inventory_context={"items": 1},
        decision={"action": "add_to_list", "canonical_name": "milk"},
        proposed_tool_calls=[
            ToolCall(tool_name="add_to_list", args={"canonical_name": "milk"}, success=True),
        ],
        human_confirmation="confirmed-by-user",
        final_response="Added milk to the shopping list.",
    )
    db_handle.save_trace(trace, user_id=household)
    return trace


class TestTracesAuth:
    def test_list_requires_token(self, client):
        assert client.get("/api/v1/traces").status_code == 401

    def test_detail_requires_token(self, client):
        assert client.get("/api/v1/traces/trace_1").status_code == 401

    def test_export_requires_token(self, client):
        assert client.get("/api/v1/traces/trace_1/export").status_code == 401


class TestTraceList:
    def test_empty_list_returns_shape(self, client, db_handle):
        token = _issue(db_handle)
        r = client.get("/api/v1/traces", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 0
        assert body["items"] == []

    def test_list_returns_seeded_trace(self, client, db_handle):
        _seed_trace(db_handle)
        token = _issue(db_handle)
        r = client.get("/api/v1/traces", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        item = body["items"][0]
        assert item["trace_id"]
        assert item["user_goal"] == "add milk"
        assert item["action"] == "add_to_list"
        assert item["tool_call_count"] == 1

    def test_search_filters_results(self, client, db_handle):
        _seed_trace(db_handle, goal="add milk")
        _seed_trace(db_handle, goal="buy rice")
        token = _issue(db_handle)
        r = client.get(
            "/api/v1/traces",
            params={"search": "rice"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["count"] == 1


class TestTraceDetail:
    def test_detail_returns_trace_payload(self, client, db_handle):
        trace = _seed_trace(db_handle)
        token = _issue(db_handle)
        r = client.get(
            f"/api/v1/traces/{trace.trace_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "trace" in body
        payload = body["trace"]
        assert payload["trace_id"] == trace.trace_id
        assert payload["redacted_user_request"] == "add milk"
        assert payload["decision"]["action"] == "add_to_list"

    def test_detail_scoped_by_household(self, client, db_handle):
        trace = _seed_trace(db_handle, household="hh_other")
        token = _issue(db_handle, "hh_traces")
        r = client.get(
            f"/api/v1/traces/{trace.trace_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404


class TestTraceExport:
    def test_export_returns_jsonl_payload(self, client, db_handle):
        trace = _seed_trace(db_handle)
        token = _issue(db_handle)
        r = client.get(
            f"/api/v1/traces/{trace.trace_id}/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["trace_id"] == trace.trace_id
        assert body["redacted"] is True
        assert "\"trace_id\"" in body["jsonl"]

    def test_export_scoped_by_household(self, client, db_handle):
        trace = _seed_trace(db_handle, household="hh_other")
        token = _issue(db_handle, "hh_traces")
        r = client.get(
            f"/api/v1/traces/{trace.trace_id}/export",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 404
