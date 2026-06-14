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

# ── Env setup (must happen before any shopstack import) ──────────────
# Sets LOCAL_AUTO_DOWNLOAD=false so the app doesn't attempt model
# downloads during the test. SHOPSTACK_DB_PATH is set inside the
# function body to a temp file (not ``:memory:``) because the
# Database class uses per-thread SQLite connections.
os.environ.setdefault("SHOPSTACK_LOCAL_AUTO_DOWNLOAD", "false")


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


def test_browser_hydration(tmp_path: Path) -> None:
    """Launch the app in headless Chromium and assert zero console errors.

    Test flow:
      1. Create a temp file for the SQLite database (file-based, not
         ``:memory:``, because the Database class uses per-thread
         connections and each Gradio worker gets its own connection).
      2. Build the Gradio ``gr.Blocks`` app via ``app.build_app()``.
      3. Launch it on a random port in a daemon thread.
      4. Drive Playwright (headless Chromium) to navigate to the app.
      5. Collect all ``console`` events (log, warn, error) and
         ``pageerror`` events (uncaught JS exceptions).
      6. Take a screenshot saved to ``tmp_path`` for visual evidence.
      7. Assert that no errors were emitted.

    Args:
        tmp_path: pytest built-in fixture providing a temporary directory
            for the screenshot.

    Raises:
        AssertionError: If any browser console error or JS exception was
            captured, with the full error text in the failure message.
    """
    # ── Step 0: Create a temp file for the database ──────────────────
    # Must use a file-based database, not ``:memory:``, because the
    # Database class uses ``threading.local()`` connections. Each worker
    # thread that Gradio spawns gets its OWN SQLite connection, and an
    # in-memory connection is a completely separate database — so tables
    # initialized on the main thread's connection are invisible to worker
    # threads. A file-based DB (even a temp file) works because all
    # threads share the same on-disk SQLite file and WAL mode serialises
    # writes across connections.
    db_fd, db_path = tempfile.mkstemp(suffix=".db", prefix="shopstack_test_")
    os.close(db_fd)
    os.environ["SHOPSTACK_DB_PATH"] = db_path

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

    # ── Step 3: Clean up temp DB ─────────────────────────────────────
    try:
        Path(db_path).unlink(missing_ok=True)
    except Exception:
        pass

    # ── Step 4: Assert no errors ─────────────────────────────────────
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
