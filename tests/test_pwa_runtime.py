"""PWA runtime smoke test — verifies the PWA shell is actually served and installable.

This is the "actually mounts" half of ``tests/test_pwa_mount.py`` (whose
``test_mount_pwa_static_actually_mounts`` is skipped because it needs a
real running server) and the runtime half of ``tests/test_pwa_shell.py``
(which only checks static file contents and source-code references).

What this test catches that the others can't:
  * Whether ``mount_pwa_static`` actually wins the route race against
    Gradio 6.x's catch-all ``/static/*`` JSON-404 handler and its
    default ``/manifest.json``.
  * Whether the paths registered in ``header.py``'s service-worker
    registration script (``navigator.serviceWorker.register(...)``)
    actually resolve to 200, not 404.
  * Whether the browser successfully registers the service worker at
    runtime (no console warning/error from the registration promise).

Shares the launch pattern from ``tests/test_browser_hydration.py``
(random port, background thread, file-based temp DB, Playwright).
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import pytest
from playwright.sync_api import ConsoleMessage, Page, sync_playwright

os.environ.setdefault("SHOPSTACK_LOCAL_AUTO_DOWNLOAD", "false")


def _find_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 15.0, interval: float = 0.2) -> None:
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


@pytest.fixture(scope="module")
def live_app_url() -> str:
    """Launch the real Gradio app on a random port for the duration of this module."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db", prefix="shopstack_pwa_test_")
    os.close(db_fd)
    os.environ["SHOPSTACK_DB_PATH"] = db_path

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
    # Give the post-launch mount a brief moment relative to server readiness.
    time.sleep(0.3)

    yield base_url

    Path(db_path).unlink(missing_ok=True)


# ── HTTP-level: the PWA assets resolve at root paths ──────────────────


def test_manifest_served_at_root_path(live_app_url: str) -> None:
    """``/manifest.json`` must return our branded manifest, not Gradio's default."""
    r = httpx.get(f"{live_app_url}/manifest.json", timeout=10.0)
    assert r.status_code == 200
    data = r.json()
    assert data.get("name") == "ShopStack" or "ShopStack" in str(data.get("name", "")) or "ShopStack" in str(data.get("short_name", "")), (
        f"Expected branded manifest, got: {data}"
    )
    # Icon paths must be rewritten to root paths (not /static/...) since
    # /static/* is blocked by Gradio's catch-all.
    for icon in data.get("icons", []):
        assert not icon["src"].startswith("/static/"), (
            f"Manifest icon src should be a root path, got: {icon['src']}"
        )


def test_service_worker_served_at_root_path(live_app_url: str) -> None:
    """``/sw.js`` must return real JS, not Gradio's /static/* 404 handler."""
    r = httpx.get(f"{live_app_url}/sw.js", timeout=10.0)
    assert r.status_code == 200
    assert "application/javascript" in r.headers.get("content-type", "")
    assert "{" in r.text and "}" in r.text


def test_icons_served_at_root_path(live_app_url: str) -> None:
    for name in ("icon-192.svg", "icon-512.svg"):
        r = httpx.get(f"{live_app_url}/{name}", timeout=10.0)
        assert r.status_code == 200, f"{name} should be served at root path"
        assert "svg" in r.headers.get("content-type", "")


def test_static_prefixed_pwa_paths_are_not_used(live_app_url: str) -> None:
    """Sanity check: confirm the OLD (broken) /static/sw.js path is
    NOT what header.py points the browser at — i.e. there's no
    silent reliance on a path Gradio blocks.

    We don't assert /static/sw.js returns 404 (Gradio's behavior there
    is out of our control), only that the registration script in the
    rendered page does not reference it.
    """
    r = httpx.get(live_app_url, timeout=10.0)
    assert r.status_code == 200
    assert "/static/sw.js" not in r.text
    assert "/static/manifest.json" not in r.text


# ── Browser-level: the service worker actually registers ──────────────


def test_service_worker_registers_without_error(live_app_url: str) -> None:
    """Drive headless Chromium and confirm ``navigator.serviceWorker.register``
    resolves successfully — i.e. the PWA shell is genuinely installable,
    not just present-but-unreachable.
    """
    collected: list[dict[str, Any]] = []
    js_errors: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page: Page = browser.new_page()

        def _on_console(msg: ConsoleMessage) -> None:
            collected.append({"type": msg.type, "text": msg.text})

        def _on_pageerror(exc: str) -> None:
            js_errors.append(str(exc))

        page.on("console", _on_console)
        page.on("pageerror", _on_pageerror)

        page.goto(live_app_url, wait_until="load")
        page.wait_for_timeout(1000)

        sw_state = page.evaluate(
            """
            async () => {
                if (!('serviceWorker' in navigator)) return 'unsupported';
                const reg = await navigator.serviceWorker.getRegistration('/');
                return reg ? 'registered' : 'not-registered';
            }
            """
        )

        browser.close()

    sw_warnings = [m for m in collected if "service worker registration failed" in m["text"].lower()]
    assert not sw_warnings, f"Service worker registration failed: {sw_warnings}"
    assert not js_errors, f"Uncaught JS exceptions: {js_errors}"
    assert sw_state in ("registered", "unsupported"), f"Unexpected SW state: {sw_state}"
