"""Contract tests for ``/api/v1/command/execute``.

This route is the HTTP counterpart to the unified Today-tab command
surface. It parses a typed command deterministically and dispatches
through the shared command handlers.
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
    from shopstack.api.v1 import auth as auth_mod
    from shopstack.api.v1.routers.command import router as command_router
    from shopstack.api.v1.routers.auth_router import router as auth_router

    auth_mod.ensure_auth_table(db_handle)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db_handle)
    try:
        from shopstack.tools.registry import ToolRegistry

        monkey.setattr(app_context, "tools", ToolRegistry(db_handle), raising=False)
    except Exception:
        pass

    fastapi_app = FastAPI(title="shopstack-test-command")
    fastapi_app.include_router(auth_router, prefix="/api/v1")
    fastapi_app.include_router(command_router, prefix="/api/v1")
    yield fastapi_app
    monkey.undo()


@pytest.fixture
def client(v1_app):
    from fastapi.testclient import TestClient

    return TestClient(v1_app)


def _issue(db_handle, household: str = "hh_command") -> str:
    from shopstack.api.v1 import auth as auth_mod

    db_handle.add_household(household, household.replace("_", " ").title())
    db_handle.add_household_member(household, household, role="owner")
    return auth_mod.issue_token(
        db_handle, device_id="dev_command", household_id=household,
    )["token"]


class TestCommandAuth:
    def test_execute_requires_token(self, client):
        r = client.post("/api/v1/command/execute", json={"text": "add milk"})
        assert r.status_code == 401

    def test_preview_is_public(self, client):
        r = client.post("/api/v1/command/preview", json={"text": "add milk"})
        assert r.status_code == 200


class TestCommandExecute:
    def test_empty_text_is_rejected(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/command/execute",
            json={"text": "   "},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    def test_add_to_list_round_trip(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/command/execute",
            json={"text": "add milk"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["household_id"] == "hh_command"
        assert body["original_text"] == "add milk"
        assert body["intent"]["action"] == "add_to_list"
        assert body["intent"]["canonical_name"] == "milk"
        assert body["result"]["success"] is True
        assert body["result"]["action"] == "add_to_list"
        assert "shopping list" in body["result"]["message"].lower()
        assert "<div class='toast" in body["result"]["toast_html"]

        active = db_handle.get_active_shopping_list(user_id="hh_command")
        assert active is not None
        assert any(item.canonical_name == "milk" for item in active.items)

    def test_log_purchase_round_trip(self, client, db_handle):
        token = _issue(db_handle)
        r = client.post(
            "/api/v1/command/execute",
            json={"text": "I bought rice"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["intent"]["action"] == "log_purchase"
        assert body["result"]["success"] is True
        assert body["result"]["canonical_name"] == "rice"

        inventory = db_handle.get_inventory(user_id="hh_command")
        assert any(lot.canonical_name == "rice" for lot in inventory)


class TestCommandPreview:
    def test_preview_returns_parse_only_shape(self, client):
        r = client.post(
            "/api/v1/command/preview",
            json={"text": "I bought rice"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["original_text"] == "I bought rice"
        assert body["intent"]["action"] == "log_purchase"
        assert body["would_mutate"] is True
        assert body["route_kind"] == "mutate"
        assert "would log rice" in body["summary"].lower()

    def test_preview_routes_questions_to_ask(self, client):
        r = client.post(
            "/api/v1/command/preview",
            json={"text": "what did we buy last week?"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["intent"]["action"] == "ask"
        assert body["would_mutate"] is False
        assert body["route_kind"] == "ask"


class TestCommandRecent:
    def test_recent_returns_command_history(self, client, db_handle):
        token = _issue(db_handle)
        client.post(
            "/api/v1/command/execute",
            json={"text": "add milk"},
            headers={"Authorization": f"Bearer {token}"},
        )
        client.post(
            "/api/v1/command/execute",
            json={"text": "I bought rice"},
            headers={"Authorization": f"Bearer {token}"},
        )
        r = client.get(
            "/api/v1/command/recent",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["count"] >= 2
        assert all(item["input_type"] == "command" for item in body["items"])
        assert any(item["action"] == "add_to_list" for item in body["items"])

    def test_recent_requires_token(self, client):
        r = client.get("/api/v1/command/recent")
        assert r.status_code == 401
