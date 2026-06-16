"""Tests for ``/api/recurring`` HTTP endpoint (Pass 19)."""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_app() -> MagicMock:
    mock = MagicMock()
    mock.app = MagicMock()
    return mock


class TestMountRecurring:
    def test_mount_registers_route_at_default_path(self):
        from shopstack.services.decision_explain_mount import mount_recurring_endpoint

        mock_app = _make_mock_app()
        mount_recurring_endpoint(mock_app)
        assert mock_app.app.add_route.call_count == 1
        call = mock_app.app.add_route.call_args
        assert call.args[0] == "/api/recurring"
        assert call.kwargs["methods"] == ["GET"]

    def test_mount_swallows_route_failures(self):
        from shopstack.services.decision_explain_mount import mount_recurring_endpoint

        mock_app = _make_mock_app()
        mock_app.app.add_route.side_effect = RuntimeError("simulated")
        # Must NOT raise.
        mount_recurring_endpoint(mock_app)


# ── Tier 3: integration via TestClient ─────────────────────────────


def _build_app_with_recurring():
    import gradio as gr
    from shopstack.services.decision_explain_mount import mount_recurring_endpoint

    with gr.Blocks() as app:
        gr.Markdown("test app for recurring")
    mount_recurring_endpoint(app)
    return app


class TestHttpRoute:
    def test_route_returns_200_with_plan(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_recurring()
        client = TestClient(app.app)
        r = client.get("/api/recurring")
        assert r.status_code == 200
        body = r.json()
        # The documented shape.
        assert "window_days" in body
        assert "summary" in body
        assert "count" in body
        assert "items" in body
        assert isinstance(body["items"], list)

    def test_route_respects_window_query_param(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_recurring()
        client = TestClient(app.app)
        r = client.get("/api/recurring?window=7")
        assert r.status_code == 200
        body = r.json()
        assert body["window_days"] == 7

    def test_route_falls_back_to_default_window_on_bad_param(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_recurring()
        client = TestClient(app.app)
        r = client.get("/api/recurring?window=notanumber")
        assert r.status_code == 200
        body = r.json()
        # Falls back to default (3).
        assert body["window_days"] == 3

    def test_route_cache_control_header(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_recurring()
        client = TestClient(app.app)
        r = client.get("/api/recurring")
        assert r.headers.get("cache-control") == "no-store"

    def test_route_handles_internal_failures(self):
        """If ``build_recurring_shopping_plan`` raises, the route returns
        200 with an ``error`` field (per the best-effort contract)."""
        from fastapi.testclient import TestClient

        app = _build_app_with_recurring()
        with patch(
            "shopstack.services.recurring_shopping.build_recurring_shopping_plan",
            side_effect=RuntimeError("simulated db crash"),
        ):
            client = TestClient(app.app)
            r = client.get("/api/recurring")
        # Still 200.
        assert r.status_code == 200
        body = r.json()
        assert body["error"] == "recurring_failed"
        assert "simulated db crash" in body["message"]
        # items is empty.
        assert body["items"] == []

    def test_route_items_include_days_until_next(self):
        """Each plan item includes ``days_until_next`` and ``typical_interval_days``."""
        from fastapi.testclient import TestClient

        app = _build_app_with_recurring()
        client = TestClient(app.app)
        r = client.get("/api/recurring?window=7")
        body = r.json()
        for item in body["items"]:
            # The days_until_next + typical_interval_days are extra
            # fields added on top of the DecisionExplanation dict.
            assert "days_until_next" in item
            assert "typical_interval_days" in item
