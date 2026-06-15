"""Tests for the branded hydration-recovery shell (PROJECT_INTELLIGENCE.md item #36).

If Gradio's JS bundle never hydrates `#main-content`, the default
experience is an infinite "Loading..." spinner with no recovery path.
`shopstack.ui.header.hydration_recovery_js()` injects a watchdog that
shows a branded shell with a reload button and diagnostics after a
timeout.

These tests cover:
  - The unit-level shape of the generated script (contract test).
  - A live browser test: with the app fully hydrated, the shell never
    appears (no false positives).
  - A live browser test: with `?hydration_timeout=0` and `#main-content`
    artificially emptied before the watchdog fires, the recovery shell
    appears with a working "Reload page" button.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

os.environ.setdefault("SHOPSTACK_LOCAL_AUTO_DOWNLOAD", "false")


def _find_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 15.0, interval: float = 0.2) -> None:
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
    raise TimeoutError(f"Server at {url} did not become ready within {timeout}s")


# ── Unit-level contract tests ───────────────────────────────────────


class TestHydrationRecoveryJs:
    def test_returns_script_tag(self):
        from shopstack.ui.header import hydration_recovery_js

        js = hydration_recovery_js()
        assert js.strip().startswith("<script")
        assert js.strip().endswith("</script>")
        assert 'data-ss-exec="true"' in js

    def test_checks_main_content_for_tabs(self):
        from shopstack.ui.header import hydration_recovery_js

        js = hydration_recovery_js()
        assert "main-content" in js
        assert "shopstack-recovery-shell" in js
        assert "Reload page" in js

    def test_respects_query_param_override(self):
        from shopstack.ui.header import hydration_recovery_js

        js = hydration_recovery_js()
        assert "hydration_timeout" in js

    def test_included_in_pwa_head_html(self):
        from shopstack.ui.header import pwa_head_html

        head = pwa_head_html()
        assert "shopstack-recovery-shell" in head


# ── Live browser tests ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def live_app_url():
    db_fd, db_path = tempfile.mkstemp(suffix=".db", prefix="shopstack_hydration_test_")
    os.close(db_fd)
    os.environ["SHOPSTACK_DB_PATH"] = db_path

    # Redirect app_context db singleton to this unique file
    from shopstack.app_context import db
    db.db_path = db_path
    if hasattr(db, "_local"):
        db._local.conn = None
    db._init_db()

    from app import build_app
    from shopstack.ui.header import pwa_head_html
    from shopstack.ui.pwa_mount import mount_pwa_static

    app = build_app()
    port = _find_free_port()

    def _serve() -> None:
        app.launch(
            server_port=port,
            prevent_thread_lock=True,
            inbrowser=False,
            quiet=True,
            head=pwa_head_html(),
        )
        # build_app()'s early mount_pwa_static() call mounts onto a
        # throwaway FastAPI app that launch() discards and recreates
        # (self.app = App.create_app(...)). Re-mount onto the real
        # app.app now that it exists.
        mount_pwa_static(app)

    t = threading.Thread(target=_serve, daemon=True)
    t.start()

    base_url = f"http://127.0.0.1:{port}"
    _wait_for_server(base_url)
    yield base_url

    try:
        app.close()
    except Exception:
        pass

    # Restore app_context db singleton to the session DB
    from tests.conftest import _SESSION_DB_PATH, _remove_db_with_sidecars
    db.db_path = _SESSION_DB_PATH
    if hasattr(db, "_local"):
        db._local.conn = None

    _remove_db_with_sidecars(db_path)


def test_recovery_shell_absent_on_normal_load(live_app_url):
    """When hydration succeeds, the recovery shell must never appear."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        # Give Gradio enough time to hydrate so the watchdog never fires.
        page.goto(f"{live_app_url}/?hydration_timeout=10000", wait_until="load")
        page.wait_for_timeout(3000)

        assert page.locator("#shopstack-recovery-shell").count() == 0
        browser.close()


def test_recovery_shell_appears_when_hydration_fails(live_app_url):
    """If #main-content never renders tabs, the branded shell appears with a reload button."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        # Simulate a hydration failure by making #main-content always look
        # empty to the watchdog's `hydrated()` check, regardless of what
        # Gradio actually renders.
        page.add_init_script("""
            const realGetElementById = document.getElementById.bind(document);
            document.getElementById = function(id) {
                const el = realGetElementById(id);
                if (id === 'main-content' && el) {
                    const fake = el.cloneNode(false);
                    return fake;
                }
                return el;
            };
        """)
        page.goto(f"{live_app_url}/?hydration_timeout=500", wait_until="load")
        page.wait_for_timeout(1500)

        shell = page.locator("#shopstack-recovery-shell")
        assert shell.count() == 1
        assert "having trouble loading" in shell.inner_text()
        assert page.locator("#shopstack-recovery-reload").count() == 1
        browser.close()
