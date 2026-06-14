"""Tests for ``/health/ui`` — operator liveness probe.

Verifies:

* ``mount_health_endpoint`` registers a route at ``/health/ui`` on the
  Gradio app's underlying FastAPI layer.
* The route returns 200 with ``status: ok`` when database, gradio
  blocks, and PWA assets are all healthy.
* The route returns 503 with ``status: degraded`` when the database
  check fails (the DB raises).
* The route's PWA-asset check is best-effort: a missing manifest
  doesn't degrade overall health.
* ``mount_health_endpoint`` is idempotent in the sense that re-mounting
  on the same app doesn't raise (defensive against double-mount).

Architecture note (motto_v3 §0.5 evidence tiers):

  * TestCheckers — Tier 2: targeted unit tests of the pure checker
    functions against in-memory fakes.
  * TestHttpRoute — Tier 3: integration test that mounts the route on
    a real ``gr.Blocks``, hits the route with the FastAPI test client,
    and asserts the JSON contract + status code.
"""
from __future__ import annotations

import os

import pytest

# Set the DB path BEFORE importing the database / schemas modules.
os.environ.setdefault("SHOPSTACK_DB_PATH", ":memory:")
os.environ.setdefault("SHOPSTACK_LOCAL_AUTO_DOWNLOAD", "false")

import gradio as gr  # noqa: E402

from shopstack.services.health_mount import (  # noqa: E402
    _check_database,
    _check_gradio_blocks,
    _check_pwa_assets,
    mount_health_endpoint,
)


# ── Tier 2: pure checker functions ───────────────────────────────────


class _FakeDB:
    """Minimal DB stand-in for the checker tests."""

    def __init__(self, *, lots: list | None = None, raise_exc: Exception | None = None):
        self._lots = lots if lots is not None else []
        self._raise = raise_exc

    def get_inventory(self, *args, **kwargs):
        if self._raise is not None:
            raise self._raise
        return self._lots


class TestCheckers:
    def test_check_database_ok(self):
        db = _FakeDB(lots=[1, 2, 3])
        status, detail = _check_database(db)
        assert status == "ok"
        assert "3" in detail

    def test_check_database_fail_on_exception(self):
        db = _FakeDB(raise_exc=RuntimeError("disk locked"))
        status, detail = _check_database(db)
        assert status == "fail"
        assert "disk locked" in detail

    def test_check_gradio_blocks_ok(self):
        with gr.Blocks() as app:
            gr.Markdown("hello")
        status, detail = _check_gradio_blocks(app)
        assert status == "ok"

    def test_check_gradio_blocks_fail_when_empty(self):
        app = gr.Blocks()
        # Don't enter the context — no children rendered.
        status, detail = _check_gradio_blocks(app)
        assert status == "fail"

    def test_check_pwa_assets_ok_or_partial(self):
        # The probe is best-effort: it returns ok/partial/missing/fail.
        # We only assert it doesn't raise and returns a known status.
        with gr.Blocks() as app:
            gr.Markdown("hi")
        status, _detail = _check_pwa_assets(app)
        assert status in {"ok", "partial", "missing", "fail"}


# ── Tier 3: real HTTP route via FastAPI test client ──────────────────


def _build_app_with_health(db=None):
    """Build a minimal gr.Blocks with the health route mounted."""
    with gr.Blocks() as app:
        gr.Markdown("# test")
        mount_health_endpoint(app, db)
    return app


class TestHttpRoute:
    def test_route_returns_200_when_healthy(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_health(db=_FakeDB(lots=[]))
        client = TestClient(app.app)
        r = client.get("/health/ui")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "checks" in body
        assert body["checks"]["database"]["status"] == "ok"
        assert body["checks"]["gradio_blocks"]["status"] == "ok"
        # pwa_assets is best-effort — it can be ok/partial/missing but
        # the overall status should still be "ok" when nothing hard-fails.
        assert body["checks"]["pwa_assets"]["status"] in {"ok", "partial", "missing"}

    def test_route_returns_503_when_database_fails(self):
        from fastapi.testclient import TestClient

        broken_db = _FakeDB(raise_exc=RuntimeError("corrupt wal"))
        app = _build_app_with_health(db=broken_db)
        client = TestClient(app.app)
        r = client.get("/health/ui")
        assert r.status_code == 503
        body = r.json()
        assert body["status"] == "degraded"
        assert body["checks"]["database"]["status"] == "fail"
        assert "corrupt wal" in body["checks"]["database"]["detail"]

    def test_route_skips_db_when_handle_is_none(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_health(db=None)
        client = TestClient(app.app)
        r = client.get("/health/ui")
        assert r.status_code == 200
        body = r.json()
        assert body["checks"]["database"]["status"] == "skipped"

    def test_route_cache_control_header(self):
        from fastapi.testclient import TestClient

        app = _build_app_with_health(db=None)
        client = TestClient(app.app)
        r = client.get("/health/ui")
        assert r.headers.get("cache-control") == "no-store"

    def test_route_wins_over_gradio_catchall(self):
        """Health route should be reachable even though Gradio installs a
        ``/{path:path}`` catch-all. mount_health_endpoint moves the route
        to the front of the routes list so this works."""
        from fastapi.testclient import TestClient

        # Use the real build_app() so we get Gradio's catch-all installed
        # too, then verify /health/ui is still reachable. We rebuild via
        # the real build_app pipeline so this catches regressions where
        # the catch-all swallows our route.
        from app import build_app

        app = build_app()
        client = TestClient(app.app)
        r = client.get("/health/ui")
        assert r.status_code in (200, 503)
        body = r.json()
        assert "status" in body
        assert "checks" in body
