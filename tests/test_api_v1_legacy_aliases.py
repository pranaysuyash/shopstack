"""Compatibility-route contracts for the Gradio-backed v1 mount.

These tests pin the boundary between the canonical FastAPI routers and the
legacy paths still used by the local Gradio shell. In particular, aliases
must retain FastAPI dependency resolution instead of becoming raw Starlette
routes.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def mounted_app(tmp_path, monkeypatch):
    from fastapi import FastAPI

    from shopstack import app_context
    from shopstack.api.v1.mount import mount_v1_routes
    from shopstack.persistence.database import Database

    db = Database(str(tmp_path / "legacy-aliases.db"))
    monkeypatch.setattr(app_context, "db", db)
    holder = type("GradioHolder", (), {"app": FastAPI()})()
    mount_v1_routes(holder)
    yield holder.app
    db.close()


def test_legacy_global_search_uses_local_household_context(mounted_app):
    from fastapi.testclient import TestClient

    response = TestClient(mounted_app).get(
        "/api/global_search",
        params={"q": "milk"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "milk"
    assert isinstance(body["results"], list)


def test_legacy_protected_alias_keeps_auth_dependency(mounted_app):
    from fastapi.testclient import TestClient

    response = TestClient(mounted_app).get("/api/corrections")

    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"


def test_versioned_global_search_remains_auth_gated(mounted_app):
    from fastapi.testclient import TestClient

    response = TestClient(mounted_app).get(
        "/api/v1/search/global",
        params={"q": "milk"},
    )

    assert response.status_code == 401
