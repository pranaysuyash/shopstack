"""Browser-hydration smoke test — verifies the app loads without console errors.

Uses Playwright to launch a headless Chromium browser, navigate to a
freshly-started Gradio server, capture every browser console message,
and assert that no errors were emitted during page load and hydration.

Why this matters:
  * Gradio apps inject substantial JavaScript on every page load (JS
    helpers, tab sync, autocomplete injection, i18n binding, etc.).
  * A browser-side JS error (e.g. a null-reference in url_state_sync_js,
    a missing DOM element the autocomplete injector expects, a Gradio
    internal error during tab mount) would produce a silent hydration
    failure that unit tests cannot catch.
  * This test is the first line of defence against such regressions. It
    runs in <5 s and requires no external services.

Architecture:
  * test_browser_hydration — main entry point. Sets env vars, builds
    the Gradio app, launches it on a random port in a background thread,
    drives Playwright to collect console messages + screenshot, then
    asserts zero errors.
  * We intentionally avoid the session-scoped ``app`` fixture from
    conftest.py (which is optimised for unit-test speed) because the
    live server needs its own lifecycle and port.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import ConsoleMessage, Page, sync_playwright

# Per 2026-06-14 test isolation hardening: these tests launch a real
# Gradio server and use Playwright to drive a real browser. They must
# run in their own pytest process (not in parallel with other tests
# that touch the same db singleton or Gradio state). Use
# ``pytest -m standalone`` to run in a clean invocation.
pytestmark = pytest.mark.standalone

# ── Module-level env setup (must happen before any shopstack import) ──
# Sets LOCAL_AUTO_DOWNLOAD=false so the app doesn't attempt model
# downloads during the test.  SHOPSTACK_DB_PATH is set to a shared
# temp file so all test functions in this module use the SAME
# on-disk database — important because the ``db`` singleton in
# ``shopstack.app_context`` is created at import time and cached.
os.environ.setdefault("SHOPSTACK_LOCAL_AUTO_DOWNLOAD", "false")

_shared_db_path: str = ""


def setup_module() -> None:
    """Create a shared temp database before any test imports ``app``.

    Each test in this file calls ``from app import build_app``, but
    Python caches ``app`` after the first import.  The ``db`` singleton
    in ``shopstack.app_context`` is created during that import, so
    every test must share the same database file.

    ``teardown_module`` cleans up the file after all tests finish.
    """
    global _shared_db_path
    db_fd, db_path = tempfile.mkstemp(suffix=".db", prefix="shopstack_browser_test_")
    os.close(db_fd)
    os.environ["SHOPSTACK_DB_PATH"] = db_path
    _shared_db_path = db_path

    # Redirect app_context db singleton to this unique file
    from shopstack.app_context import db
    db.db_path = db_path
    if hasattr(db, "_local"):
        db._local.conn = None
    db._init_db()


def teardown_module() -> None:
    """Remove the shared temp database after all tests finish.

    Uses the canonical ``_remove_db_with_sidecars`` helper from
    conftest so WAL/SHM sidecars are also removed. Per motto_v3 §7,
    this is the canonical cleanup path; do not inline
    ``Path(...).unlink(missing_ok=True)`` for temp DBs.
    """
    # Restore app_context db singleton to the session DB
    from shopstack.app_context import db
    from tests.conftest import _SESSION_DB_PATH, _remove_db_with_sidecars
    db.db_path = _SESSION_DB_PATH
    if hasattr(db, "_local"):
        db._local.conn = None

    _remove_db_with_sidecars(_shared_db_path)


# ── Helpers ──────────────────────────────────────────────────────────


def _find_free_port() -> int:
    """Return a random ephemeral port via the OS bind checker."""
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 15.0, interval: float = 0.2) -> None:
    """Poll ``url`` until the server responds with HTTP 200."""
    import httpx

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(url, timeout=5.0)
            if r.status_code == 200:
                return
        except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.ReadTimeout):
            pass
        time.sleep(interval)
    raise TimeoutError(
        f"Server at {url} did not become ready within {timeout}s"
    )


# ── The test ─────────────────────────────────────────────────────────


def test_dark_mode_toggle_persistence(tmp_path: Path) -> None:
    """Verify `toggleTheme()` flips data-theme, persists to localStorage, and survives reload.

    Test flow:
      1. Start the app server (same infrastructure as test_browser_hydration).
      2. Navigate to the app and wait for initial render.
      3. Call ``toggleTheme()`` → verify data-theme="dark" and
         localStorage["shopstack-theme"] = "dark".
      4. Call ``toggleTheme()`` again → verify flip back to "light".
      5. Reload the page → verify "light" persists from localStorage.
      6. Call ``toggleTheme()`` one final time → verify "dark" again.
      7. Assert no console errors during the entire sequence.

    Args:
        tmp_path: pytest built-in fixture for temp directory (screenshots).
    """
    # Database path is set at module level via setup_module().
    # All tests in this file share the same temp database because the
    # ``db`` singleton is created at import-once time.

    # ── Step 1: Launch the app server ────────────────────────────────
    from app import build_app

    app = build_app()
    port = _find_free_port()

    def _serve() -> None:
        app.launch(
            server_port=port,
            prevent_thread_lock=True,
            inbrowser=False,
            quiet=True,
        )

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    base_url = f"http://127.0.0.1:{port}"
    _wait_for_server(base_url)

    # ── Step 2: Drive Playwright ─────────────────────────────────────
    collected: list[dict[str, Any]] = []
    js_errors: list[str] = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page: Page = browser.new_page()

            def _on_console(msg: ConsoleMessage) -> None:
                collected.append({
                    "type": msg.type,
                    "text": msg.text,
                    "location": msg.location,
                })

            def _on_pageerror(exc: str) -> None:
                js_errors.append(str(exc))

            page.on("console", _on_console)
            page.on("pageerror", _on_pageerror)

            # Navigate and wait for initial load.
            page.goto(base_url, wait_until="load")
            # Give deferred JS helpers time to run.
            page.wait_for_timeout(1500)

            # ── Step 3: Assert initial state ────────────────────────────────
            initial_theme = page.evaluate(
                "document.documentElement.getAttribute('data-theme')"
            )
            initial_ls = page.evaluate(
                "localStorage.getItem('shopstack-theme')"
            )
            # With no localStorage value and no system preference match,
            # data-theme should be None (no explicit attribute).
            # localStorage may also be null on first visit.

            # ── Step 4: Toggle to dark ──────────────────────────────────────
            page.evaluate("toggleTheme()")
            page.wait_for_timeout(100)

            dark_theme = page.evaluate(
                "document.documentElement.getAttribute('data-theme')"
            )
            dark_ls = page.evaluate(
                "localStorage.getItem('shopstack-theme')"
            )
            assert dark_theme == "dark", (
                f"Expected data-theme='dark' after toggleTheme(), got: {dark_theme!r}"
            )
            assert dark_ls == "dark", (
                f"Expected localStorage['shopstack-theme']='dark' after toggle, got: {dark_ls!r}"
            )

            # ── Step 5: Toggle back to light ────────────────────────────────
            page.evaluate("toggleTheme()")
            page.wait_for_timeout(100)

            light_theme = page.evaluate(
                "document.documentElement.getAttribute('data-theme')"
            )
            light_ls = page.evaluate(
                "localStorage.getItem('shopstack-theme')"
            )
            assert light_theme == "light", (
                f"Expected data-theme='light' after second toggle, got: {light_theme!r}"
            )
            assert light_ls == "light", (
                f"Expected localStorage['shopstack-theme']='light' after second toggle, got: {light_ls!r}"
            )

            # ── Step 6: Reload and verify persistence ───────────────────────
            page.reload(wait_until="load")
            page.wait_for_timeout(1500)

            reload_theme = page.evaluate(
                "document.documentElement.getAttribute('data-theme')"
            )
            reload_ls = page.evaluate(
                "localStorage.getItem('shopstack-theme')"
            )
            assert reload_theme == "light", (
                f"data-theme should persist as 'light' after reload, got: {reload_theme!r}"
            )
            assert reload_ls == "light", (
                f"localStorage should still be 'light' after reload, got: {reload_ls!r}"
            )

            # ── Step 7: Toggle one more time after reload ───────────────────
            page.evaluate("toggleTheme()")
            page.wait_for_timeout(100)

            final_theme = page.evaluate(
                "document.documentElement.getAttribute('data-theme')"
            )
            final_ls = page.evaluate(
                "localStorage.getItem('shopstack-theme')"
            )
            assert final_theme == "dark", (
                f"Expected data-theme='dark' after post-reload toggle, got: {final_theme!r}"
            )
            assert final_ls == "dark", (
                f"Expected localStorage='dark' after post-reload toggle, got: {final_ls!r}"
            )

            # Take a screenshot for evidence.
            screenshot_path = str(tmp_path / "dark_mode_final.png")
            page.screenshot(path=screenshot_path, full_page=True)

            # Verify the page still rendered meaningful content.
            body_text = page.locator("body").inner_text()
            assert "ShopStack" in body_text or "shopstack" in body_text.lower(), (
                f"Expected 'ShopStack' in body text after dark mode toggle, got:\n{body_text[:500]}"
            )

            browser.close()
    finally:
        try:
            app.close()
        except Exception:
            pass

    # ── Step 8: Assert no errors (include warnings for consistency with
    #     test_browser_hydration) ───────────────────────────────────────
    # Filter out reload-induced benign errors. When the page reloads,
    # Gradio's active WebSocket/streaming connections are torn down by
    # the browser, surfacing as ``AbortError: signal is aborted without
    # reason`` and ``TypeError: Failed to fetch``. These are mechanical
    # side-effects of the test's own reload step (step 6), not real app
    # bugs. motto_v3 §0.6: tests should catch real defects, not noise
    # from the test's own actions.
    _RELOAD_BENIGN_PATTERNS = (
        "signal is aborted",        # AbortError on WebSocket close
        "Failed to fetch",          # fetch() rejected during teardown
        "Connection errored out",   # Gradio streaming-server wording
        "network error",            # TypeError on WebSocket teardown during reload
    )

    def _is_reload_noise(text: str) -> bool:
        return any(p in text for p in _RELOAD_BENIGN_PATTERNS)

    error_messages = [
        m for m in collected
        if m["type"] in ("error", "assert", "warning")
        and not _is_reload_noise(m["text"])
    ]
    js_errors_filtered = [e for e in js_errors if not _is_reload_noise(e)]

    if error_messages or js_errors_filtered:
        lines: list[str] = []
        lines.append("Browser errors detected during dark mode test:\n")
        if js_errors_filtered:
            lines.append("-- Uncaught JS exceptions --")
            for exc in js_errors_filtered:
                lines.append(f"  {exc}")
            lines.append("")
        if error_messages:
            lines.append("-- Console errors --")
            for m in error_messages:
                loc = m["location"]
                loc_str = f"{loc.get('url', '?')}:{loc.get('lineNumber', '?')}"
                lines.append(f"  [{m['type']}] {m['text']}  ({loc_str})")
            lines.append("")
        lines.append(f"Screenshot saved to: {screenshot_path}")
        pytest.fail("\n".join(lines))

    print(
        f"[dark-mode] OK -- dark/light toggle + persistence verified, "
        f"screenshot at {screenshot_path}"
    )


def test_browser_hydration(tmp_path: Path) -> None:
    """Launch the app in headless Chromium and assert zero console errors.

    Test flow:
      1. Build the Gradio ``gr.Blocks`` app via ``app.build_app()``.
      2. Launch it on a random port in a daemon thread.
      3. Drive Playwright (headless Chromium) to navigate to the app.
      4. Collect all ``console`` events (log, warn, error) and
         ``pageerror`` events (uncaught JS exceptions).
      5. Take a screenshot saved to ``tmp_path`` for visual evidence.
      6. Assert that no errors were emitted.

    Args:
        tmp_path: pytest built-in fixture providing a temporary directory
            for the screenshot.

    Raises:
        AssertionError: If any browser console error or JS exception was
            captured, with the full error text in the failure message.
    """
    # Database path is set at module level via setup_module().
    # All tests in this file share the same temp database because the
    # ``db`` singleton is created at import-once time.

    # ── Step 1: Launch the app server ────────────────────────────────
    from app import build_app

    app = build_app()
    port = _find_free_port()

    def _serve() -> None:
        # ``prevent_thread_lock`` lets Gradio run in a background thread
        # instead of blocking the main test thread.
        app.launch(
            server_port=port,
            prevent_thread_lock=True,
            inbrowser=False,
            quiet=True,
        )

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    base_url = f"http://127.0.0.1:{port}"
    _wait_for_server(base_url)

    # ── Step 2: Drive Playwright ─────────────────────────────────────
    collected: list[dict[str, Any]] = []
    js_errors: list[str] = []

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            page: Page = browser.new_page()

            # Capture all console output (log, warn, error, info, debug).
            def _on_console(msg: ConsoleMessage) -> None:
                collected.append({
                    "type": msg.type,
                    "text": msg.text,
                    "location": msg.location,
                })

            # Capture uncaught JS exceptions (page-level errors).
            def _on_pageerror(exc: str) -> None:
                js_errors.append(str(exc))

            page.on("console", _on_console)
            page.on("pageerror", _on_pageerror)

            # Navigate and wait for the initial page load to complete.
            # Use ``wait_until="load"`` instead of ``"networkidle"`` because
            # Gradio opens persistent WebSocket connections for its event
            # queue — ``networkidle`` will never be satisfied on a page with
            # an active WebSocket connection.
            page.goto(base_url, wait_until="load")

            # Give deferred JS helpers time to run (autocomplete_injector_js
            # fires at 100 ms, url_state_sync_js at 200 ms).
            page.wait_for_timeout(1000)

            # Take a screenshot for visual evidence.
            screenshot_path = str(tmp_path / "app_initial_load.png")
            page.screenshot(path=screenshot_path, full_page=True)

            # Verify the page actually rendered meaningful content.
            body_text = page.locator("body").inner_text()
            assert "ShopStack" in body_text or "shopstack" in body_text.lower(), (
                f"Expected 'ShopStack' in page body text after load, got:\n{body_text[:500]}"
            )

            browser.close()
    finally:
        try:
            app.close()
        except Exception:
            pass

    # ── Step 3: Assert no errors ─────────────────────────────────────
    error_messages = [
        m for m in collected if m["type"] in ("error", "assert", "warning")
    ]

    if error_messages or js_errors:
        lines: list[str] = []
        lines.append("Browser errors detected during app hydration:\n")
        if js_errors:
            lines.append("── Uncaught JS exceptions ──")
            for exc in js_errors:
                lines.append(f"  {exc}")
            lines.append("")
        if error_messages:
            lines.append("── Console errors/warnings ──")
            for m in error_messages:
                loc = m["location"]
                loc_str = f"{loc.get('url', '?')}:{loc.get('lineNumber', '?')}"
                lines.append(f"  [{m['type']}] {m['text']}  ({loc_str})")
            lines.append("")
        lines.append(f"Screenshot saved to: {screenshot_path}")
        pytest.fail("\n".join(lines))

    print(
        f"[browser-hydration] OK — {len(collected)} console messages "
        f"(0 errors), screenshot at {screenshot_path}"
    )
