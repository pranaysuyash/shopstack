"""Tests for ``/api/corrections`` HTTP endpoint (Pass 20)."""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_app() -> MagicMock:
    mock = MagicMock()
    mock.app = MagicMock()
    return mock


class TestMountCorrections:
    def test_mount_registers_routes(self):
        """Mounts both GET and POST on /api/corrections."""
        from shopstack.services.corrections_mount import mount_corrections_endpoint

        mock_app = _make_mock_app()
        mount_corrections_endpoint(mock_app)
        # Two routes: GET and POST.
        assert mock_app.app.add_route.call_count == 2
        # Both routes are at /api/corrections.
        paths = [c.args[0] for c in mock_app.app.add_route.call_args_list]
        assert paths == ["/api/corrections", "/api/corrections"]
        # One is GET, one is POST.
        methods = [c.kwargs["methods"] for c in mock_app.app.add_route.call_args_list]
        assert ["GET"] in methods
        assert ["POST"] in methods

    def test_mount_swallows_route_failures(self):
        from shopstack.services.corrections_mount import mount_corrections_endpoint

        mock_app = _make_mock_app()
        mock_app.app.add_route.side_effect = RuntimeError("simulated")
        # Must NOT raise.
        mount_corrections_endpoint(mock_app)


# ── Tier 3: integration via TestClient ─────────────────────────────


def _build_app_with_corrections():
    import gradio as gr
    from shopstack.services.corrections_mount import mount_corrections_endpoint

    with gr.Blocks() as app:
        gr.Markdown("test app for corrections")
    mount_corrections_endpoint(app)
    return app


class TestHttpRoute:
    def test_get_route_returns_200_with_list(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_corrections()
        client = TestClient(app.app)
        r = client.get("/api/corrections")
        assert r.status_code == 200
        body = r.json()
        for key in ("summary", "count", "items"):
            assert key in body
        assert isinstance(body["items"], list)

    def test_get_route_respects_limit_query_param(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_corrections()
        client = TestClient(app.app)
        r = client.get("/api/corrections?limit=5")
        assert r.status_code == 200

    def test_get_route_cache_control_header(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_corrections()
        client = TestClient(app.app)
        r = client.get("/api/corrections")
        assert r.headers.get("cache-control") == "no-store"

    def test_post_route_returns_201_with_valid_body(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_corrections()
        client = TestClient(app.app)
        body = {
            "canonical_name": "milk",
            "was_action": "buy",
            "should_be_action": "skip",
            "reason": "I have plenty",
        }
        r = client.post("/api/corrections", json=body)
        assert r.status_code == 201
        result = r.json()
        assert result["canonical_name"] == "milk"
        assert result["was_action"] == "buy"
        assert result["should_be_action"] == "skip"
        assert "event_id" in result

    def test_post_route_returns_400_on_validation_error(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_corrections()
        client = TestClient(app.app)
        # Same was/should-be → validation error.
        body = {
            "canonical_name": "milk",
            "was_action": "buy",
            "should_be_action": "buy",  # same
            "reason": "",
        }
        r = client.post("/api/corrections", json=body)
        assert r.status_code == 400
        result = r.json()
        assert result["error"] == "validation_failed"
        assert "errors" in result

    def test_post_route_returns_400_on_missing_fields(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_corrections()
        client = TestClient(app.app)
        # Missing canonical_name.
        body = {
            "was_action": "buy",
            "should_be_action": "skip",
        }
        r = client.post("/api/corrections", json=body)
        assert r.status_code == 400

    def test_post_route_returns_400_on_bad_json(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_corrections()
        client = TestClient(app.app)
        r = client.post(
            "/api/corrections",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400
        result = r.json()
        assert result["error"] == "bad_json"

    def test_get_route_handles_internal_failures(self):
        """If ``list_recent_corrections`` raises, the route returns 200
        with an ``error`` field (per the best-effort contract)."""
        from fastapi.testclient import TestClient

        app = _build_app_with_corrections()
        with patch(
            "shopstack.services.feedback.list_recent_corrections",
            side_effect=RuntimeError("simulated db crash"),
        ):
            client = TestClient(app.app)
            r = client.get("/api/corrections")
        # Still 200.
        assert r.status_code == 200
        body = r.json()
        assert body["error"] == "list_failed"
        assert "simulated db crash" in body["message"]
        assert body["items"] == []
