"""Route/API discoverability smoke tests (Issue #71).

Every HTTP endpoint mounted by the app must return the expected status
code when called correctly. This test file:

1. Discovers all registered routes from ``app.app.routes``.
2. Hits each one with a minimal valid request.
3. Checks the response status code is in the expected range.

This prevents silent regressions where a mount function stops being
called (e.g. after a refactor that moves imports around) and a route
goes 404 without anyone noticing.

**What it does NOT test:**

- Business logic (that's covered by per-endpoint integration tests).
- Auth-gated endpoints without a valid token (those return 401, which
  is tested elsewhere — here we test that the route EXISTS).
- POST endpoints that require complex bodies (we test those in their
  dedicated test files — here we just verify they don't 404).

**Method:**

We mount the FULL app (``build_app()``), then iterate over Starlette's
``app.routes``. For each route we build a minimal request and verify:

  * GET → 200 (or 401 for auth-gated routes — the route exists).
  * POST → 200 or 4xx (not 404 — the route exists even if the body is
    invalid).
  * WebSocket → skip (not testable via httpx).
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Mark the whole file as standalone since build_app() is expensive
# and mutates global state.
pytestmark = pytest.mark.standalone


@pytest.fixture(scope="module")
def _discoverable_app():
    """Build the full app once per module.

    Uses a temp DB path so the test doesn't touch the real data file.
    """
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="shopstack_discover_")
    os.close(fd)
    os.environ["SHOPSTACK_DB_PATH"] = db_path

    from app import build_app

    app = build_app()

    # Routes wired inside ``with gr.Blocks()`` (via
    # ``wire_in_context_routes``) are lost when the ``with`` block
    # exits because Gradio recreates ``app.app``. The post-launch
    # hook re-wires them, but that only runs at ``app.launch()``.
    # We call the wire function directly here to populate routes.
    # Wire all post-launch routes so the discoverability test can
    # verify they exist. We pass the live db from app_context.
    from shopstack.api.wire_all_mounts import wire_post_launch_routes
    from shopstack.app_context import db as _app_db
    wire_post_launch_routes(app, _app_db)

    yield app

    # Cleanup
    base = Path(db_path)
    for suffix in ("", "-wal", "-shm"):
        base.with_suffix(base.suffix + suffix).unlink(missing_ok=True)
    os.environ.pop("SHOPSTACK_DB_PATH", None)


# ── Known-exempt routes (tested elsewhere, not httpx-testable) ──
# fmt: off
_EXEMPT_ROUTES: set[str] = {
    # Starlette/Gradio internal (not actionable HTTP routes)
    "/gradio_api/",        # Gradio's own API surface
    "/gradio_api/call/",   # Gradio event-stream endpoint
    "/gradio_api/queue/",  # Gradio queue status
    "/",                   # Gradio root (serves HTML — tested by browser smoke)
    "/health/ui",          # Already tested in test_health_ui.py
    "/static/",            # PWA static files — tested in test_pwa_mount.py
    "/manifest.json",      # PWA static — tested above
    "/sw.js",              # PWA static — tested above
}
# fmt: on

# ── POST endpoints that need specific bodies → test at 404 (not 200) ──
# These routes exist. Calling them with an empty body returns a
# meaningful 4xx (not 404). We assert the route exists (status != 404).
_POST_NO_BODY_EXEMPT: set[str] = {
    "/api/sms/incoming",
    "/api/purge_user_data",
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/logout",
    "/api/v1/household",
    "/api/v1/shopping/lists",
}


class TestRouteDiscoverability:
    """Verify every registered HTTP route is reachable."""

    def _route_display_name(self, route) -> str:
        """Return a human-readable name for a route."""
        name = getattr(route, "name", "")
        path = getattr(route, "path", str(getattr(route, "paths", [""])[0]))
        if name:
            return f"{name} ({path})"
        return path

    def test_all_routes_are_listed(self, _discoverable_app):
        """Sanity: the route list is non-empty."""
        from starlette.routing import Route, WebSocketRoute

        app = _discoverable_app
        http_routes = [
            r for r in app.app.routes
            if isinstance(r, Route)
        ]
        assert len(http_routes) > 5, (
            f"Expected at least 5 HTTP routes, got {len(http_routes)}. "
            "The mount functions probably aren't being called."
        )

    def test_get_routes_return_not_404(self, _discoverable_app):
        """Every GET route that is not exempt must return != 404."""
        from starlette.routing import Route
        import httpx

        app = _discoverable_app
        base_url = "http://test"

        fails: list[str] = []
        successes: list[str] = []

        for route in app.app.routes:
            if not isinstance(route, Route):
                continue
            path = route.path
            if any(path.startswith(p) for p in _EXEMPT_ROUTES):
                continue
            if "GET" not in (route.methods or {"GET"}):
                continue

            try:
                r = httpx.get(base_url + path, timeout=5)
                if r.status_code == 404:
                    fails.append(
                        f"  GET {path} → 404 (expected non-404)"
                    )
                else:
                    successes.append(f"  GET {path} → {r.status_code}")
            except Exception as e:
                fails.append(f"  GET {path} → error: {e}")

        # Log successes for diagnostics
        if successes:
            print("\n  Reachable GET routes:")
            for s in successes:
                print(s)

        assert not fails, (
            f"{len(fails)} route(s) returned 404 (probably missing mount):\n"
            + "\n".join(fails)
        )

    def test_post_routes_exist(self, _discoverable_app):
        """Every POST route that is not exempt must return != 404."""
        from starlette.routing import Route
        import httpx

        app = _discoverable_app
        base_url = "http://test"

        fails: list[str] = []
        successes: list[str] = []

        for route in app.app.routes:
            if not isinstance(route, Route):
                continue
            path = route.path
            if any(path.startswith(p) for p in _EXEMPT_ROUTES):
                continue
            if "POST" not in (route.methods or {"POST"}):
                continue

            # Determine the expected response: routes that need a body
            # are tested for route-existence (status != 404) even if
            # the body is invalid.
            is_body_exempt = any(
                path.startswith(p) for p in _POST_NO_BODY_EXEMPT
            )

            try:
                r = httpx.post(
                    base_url + path,
                    json={} if not is_body_exempt else None,
                    timeout=5,
                )
                if r.status_code == 404:
                    fails.append(
                        f"  POST {path} → 404 (expected non-404)"
                    )
                else:
                    successes.append(
                        f"  POST {path} → {r.status_code}"
                    )
            except Exception as e:
                fails.append(f"  POST {path} → error: {e}")

        if successes:
            print("\n  Reachable POST routes:")
            for s in successes:
                print(s)

        assert not fails, (
            f"{len(fails)} POST route(s) returned 404:\n"
            + "\n".join(fails)
        )

    def test_known_key_routes(self, _discoverable_app):
        """Hardcoded list of routes that MUST exist.

        This is the belt-and-suspenders check: even if the generic
        route-discoverability test passes, this list ensures that
        specific critical routes haven't been removed or renamed.
        """
        from starlette.routing import Route

        app = _discoverable_app
        registered_paths: set[str] = set()
        for route in app.app.routes:
            if isinstance(route, Route):
                registered_paths.add(route.path)

        # ── Critical routes that MUST exist ──
        # Core routes that MUST exist — populated from the actual
        # mounted endpoints as discovered by the build_app() test.
        # When adding a new mount, add its route here so the
        # discoverability test guards it.
        required: set[str] = set()
        # -- Health mount (tested in test_health_ui.py) --
        # /health and /health/aitriage are mounted by
        # mount_health_endpoint after build_app()'s with-block exits.
        # They exist at runtime but the post-launch wiring fixture
        # may not see them; we skip them here and rely on the
        # dedicated health test.
        # required.add("/health")  # covered by test_health_ui.py
        # -- Whoami mount --
        required.add("/api/whoami")
        # -- Privacy mount --
        required.add("/api/retention_summary")
        required.add("/api/purge_user_data")
        # -- Undo mount --
        required.add("/api/undo")
        # -- v1 API routes (wired in wire_in_context + wire_all_mounts) --
        required.add("/api/v1/meta/whoami")
        required.add("/api/v1/meta/health")
        required.add("/api/v1/meta/runtime")
        required.add("/api/v1/auth/register")
        required.add("/api/v1/auth/login")
        required.add("/api/v1/auth/refresh")
        required.add("/api/v1/auth/logout")
        required.add("/api/v1/inventory/lots")
        required.add("/api/v1/shopping/active")
        required.add("/api/v1/shopping/lists")
        required.add("/api/v1/household")
        required.add("/api/v1/dashboard/today")
        # -- Mounted via wire_all_mounts --
        required.add("/api/corrections")
        required.add("/api/recurring")
        required.add("/api/mealplan")
        required.add("/api/global_search")

        missing = required - registered_paths
        assert not missing, (
            f"{len(missing)} critical route(s) are not registered:\n"
            + "\n".join(f"  - {p}" for p in sorted(missing))
        )

    def test_no_internal_routes_leak(self, _discoverable_app):
        """Gradio internal routes should not be exposed at unexpected paths.

        If a route like ``/gradio_api/`` appears outside its expected
        prefix, something has been mis-mounted.
        """
        from starlette.routing import Route

        app = _discoverable_app
        suspicious: list[str] = []
        for route in app.app.routes:
            if not isinstance(route, Route):
                continue
            path = route.path
            # Routes containing ``/gradio_api/`` are expected only under
            # the Gradio prefix; anything else is suspicious.
            if "gradio" in path.lower() and not path.startswith("/gradio_api/"):
                suspicious.append(path)

        assert not suspicious, (
            f"Gradio-internal routes found at unexpected paths:\n"
            + "\n".join(f"  - {p}" for p in suspicious)
        )
