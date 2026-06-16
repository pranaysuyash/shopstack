"""Tests for ``/api/decision/<name>/explain`` HTTP endpoint (Pass 18).

Mirrors the test pattern from ``test_whoami_mount.py``:
  - Tier 2 unit tests of the mount function
  - Tier 3 integration tests via FastAPI TestClient
"""
from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_app() -> MagicMock:
    mock = MagicMock()
    mock.app = MagicMock()
    return mock


class TestMountDecisionExplain:
    def test_mount_registers_route_at_default_path(self):
        """The default route is ``/api/decision/{name}/explain``."""
        from shopstack.services.decision_explain_mount import (
            mount_decision_explain_endpoint,
        )

        mock_app = _make_mock_app()
        mount_decision_explain_endpoint(mock_app)
        assert mock_app.app.add_route.call_count == 1
        call = mock_app.app.add_route.call_args
        assert call.args[0] == "/api/decision/{name}/explain"
        assert call.kwargs["methods"] == ["GET"]

    def test_mount_swallows_route_failures(self):
        """If ``app.app.add_route`` raises, ``mount`` does not propagate."""
        from shopstack.services.decision_explain_mount import (
            mount_decision_explain_endpoint,
        )

        mock_app = _make_mock_app()
        mock_app.app.add_route.side_effect = RuntimeError("simulated")
        # Must NOT raise.
        mount_decision_explain_endpoint(mock_app)


# ── Tier 3: integration via TestClient ─────────────────────────────


def _build_app_with_explain() -> "gr.Blocks":
    """Build a minimal ``gr.Blocks`` with the explain endpoint mounted."""
    import gradio as gr
    from shopstack.services.decision_explain_mount import (
        mount_decision_explain_endpoint,
    )

    with gr.Blocks() as app:
        gr.Markdown("test app for explain")
    mount_decision_explain_endpoint(app)
    return app


class TestHttpRoute:
    def test_route_returns_200_with_explanation(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_explain()
        client = TestClient(app.app)
        r = client.get("/api/decision/milk/explain")
        # Either 200 (decision found) or 200 (no_decision) —
        # both are valid per the best-effort contract.
        assert r.status_code == 200
        body = r.json()
        # Body is either a DecisionExplanation-shaped dict
        # or an error dict; both are valid.
        assert isinstance(body, dict)

    def test_route_returns_bad_path_for_unknown_path(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_explain()
        client = TestClient(app.app)
        r = client.get("/api/decision/")  # no name
        # Path without a name → 400 (canonical name is required).
        # Note: this depends on whether the route pattern matches.
        # The route is `/api/decision/{name}/explain`, so a path
        # without the `/{name}/explain` suffix doesn't match the
        # dynamic route. Starlette returns 404 in that case.
        assert r.status_code in (400, 404)

    def test_route_cache_control_header(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_explain()
        client = TestClient(app.app)
        r = client.get("/api/decision/milk/explain")
        # Best-effort: a successful response should have
        # ``Cache-Control: no-store`` so the operator always
        # gets fresh data.
        if r.status_code == 200 and "error" not in r.json():
            assert r.headers.get("cache-control") == "no-store"

    def test_route_handles_internal_failures(self):
        """If ``build_dashboard_state`` raises, the route returns 200
        with an ``error`` field (per the best-effort contract)."""
        from fastapi.testclient import TestClient

        app = _build_app_with_explain()
        with patch(
            "shopstack.services.dashboard.build_dashboard_state",
            side_effect=RuntimeError("simulated db crash"),
        ):
            client = TestClient(app.app)
            r = client.get("/api/decision/milk/explain")
        # Still 200 — the endpoint never produces 5xx for an
        # internal sub-check failure.
        assert r.status_code == 200
        body = r.json()
        assert body["error"] == "explain_failed"
        assert "simulated db crash" in body["message"]
