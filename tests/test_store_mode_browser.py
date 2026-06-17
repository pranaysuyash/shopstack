"""Tests for store mode toggle — verifies the view and API endpoint directly.

Test strategy:
  1. ``test_store_mode_view_renders_items`` — calls ``store_mode_view()``
     directly and verifies the HTML contains the seeded items with
     checkboxes. No server needed.
  2. ``test_store_mode_toggle_via_fastapi`` — uses Starlette's TestClient
     to test the ``_store_mode_toggle_endpoint`` function via a real FastAPI
     route. No Gradio server needed.
  3. ``test_store_mode_browser_smoke`` — launches the full Gradio app in a
     headless browser and verifies no console errors.

Architecture:
  * Follows the same pattern as ``tests/test_browser_hydration.py`` for
    the smoke test: module-level temp database, thread-based server,
    Playwright drive.
  * Seeds the database with an active shopping list containing test items.
  * Uses Starlette's TestClient for the API test to avoid depending on
    Gradio's post-launch route mounting.
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
from unittest.mock import MagicMock

from playwright.sync_api import ConsoleMessage, Page, sync_playwright

pytestmark = pytest.mark.standalone


# ── Module-level env setup ──────────────────────────────────────────

_shared_db_path: str = ""


def setup_module() -> None:
    """Create a shared temp database and seed it with an active shopping list.

    All tests in this file share the same database. ``teardown_module``
    cleans up.
    """
    global _shared_db_path
    db_fd, db_path = tempfile.mkstemp(suffix=".db", prefix="shopstack_store_mode_test_")
    os.close(db_fd)
    os.environ["SHOPSTACK_DB_PATH"] = db_path
    _shared_db_path = db_path

    # Redirect app_context db singleton to this unique file
    from shopstack.app_context import db
    db.db_path = db_path
    if hasattr(db, "_local"):
        db._local.conn = None
    db._init_db()

    # Seed an active shopping list with items for the default household
    _seed_shopping_list(db)


def _seed_shopping_list(db) -> None:
    """Create an active shopping list with test items so store mode has data."""
    uid = db.active_household_id or "default_household"

    # Ensure the household exists
    try:
        db.add_household(uid, "Default Household")
    except Exception:
        pass  # already exists
    try:
        db.add_household_member(uid, uid, role="owner")
    except Exception:
        pass  # already a member

    # Create a shopping list
    from shopstack.schemas.models import ShoppingListItem

    list_id = "test-list-001"
    items = [
        ShoppingListItem(
            list_item_id="li-1",
            canonical_name="milk",
            requested_quantity=2.0,
            unit="L",
            priority="must_buy",
            status="pending",
            linked_inventory_lots=[],
        ),
        ShoppingListItem(
            list_item_id="li-2",
            canonical_name="bread",
            requested_quantity=1.0,
            unit="loaf",
            priority="must_buy",
            status="pending",
            linked_inventory_lots=[],
        ),
        ShoppingListItem(
            list_item_id="li-3",
            canonical_name="eggs",
            requested_quantity=12.0,
            unit="pieces",
            priority="optional",
            status="pending",
            linked_inventory_lots=[],
        ),
    ]

    # First, deactivate any existing active list
    conn = db.conn
    conn.execute("UPDATE shopping_lists SET is_active = 0 WHERE user_id = ?", (uid,))

    # Insert the list
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    conn.execute(
        "INSERT OR REPLACE INTO shopping_lists (list_id, goal, is_active, created_at, updated_at, user_id) "
        "VALUES (?, ?, 1, ?, ?, ?)",
        (list_id, "Test groceries", now.isoformat(), now.isoformat(), uid),
    )

    # Insert items — DB column is ``item_id``; model field is ``list_item_id``.
    for item in items:
        conn.execute(
            "INSERT OR REPLACE INTO shopping_list_items "
            "(item_id, list_id, canonical_name, requested_quantity, unit, priority, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (item.item_id, list_id, item.canonical_name,
             item.requested_quantity, item.unit, item.priority, item.status),
        )
    conn.commit()

    # Verify seeding worked
    sl = db.get_active_shopping_list(user_id=uid)
    assert sl is not None, "Seeded shopping list should be active"
    assert len(sl.items) >= 3, f"Expected at least 3 items, got {len(sl.items) if sl.items else 0}"


def teardown_module() -> None:
    """Remove the shared temp database after all tests finish."""
    from shopstack.app_context import db
    from tests.conftest import _SESSION_DB_PATH, _remove_db_with_sidecars
    db.db_path = _SESSION_DB_PATH
    if hasattr(db, "_local"):
        db._local.conn = None

    _remove_db_with_sidecars(_shared_db_path)


# ── Helpers ──────────────────────────────────────────────────────────


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


# ── Tests ────────────────────────────────────────────────────────────


class TestStoreModeView:
    """Tests for the store mode view rendering (no server needed)."""

    def test_renders_items(self) -> None:
        """``store_mode_view()`` returns HTML with seeded items."""
        from shopstack.ui.screens.store_mode import store_mode_view

        html = store_mode_view()

        assert "In-store mode" in html, "Expected heading in store mode HTML"
        assert 'class="store-mode-checkbox"' in html, (
            "Expected checkbox elements in rendered HTML"
        )
        assert "milk" in html.lower(), "Expected 'milk' in rendered HTML"
        assert "bread" in html.lower(), "Expected 'bread' in rendered HTML"

        # Verify unchecked checkboxes (☐) are present
        assert "&#x2610;" in html, "Expected unchecked checkbox symbol (☐)"

    def test_empty_state(self) -> None:
        """``store_mode_view()`` returns empty state when no active list.

        Restores the active list after the assertion so subsequent
        tests are not affected.
        """
        from shopstack.app_context import db
        from shopstack.ui.screens.store_mode import store_mode_view

        # Save the active list id before deactivating
        row = db.conn.execute(
            "SELECT list_id FROM shopping_lists WHERE is_active = 1 LIMIT 1"
        ).fetchone()
        active_list_id = row["list_id"] if row else None

        try:
            db.conn.execute("UPDATE shopping_lists SET is_active = 0")
            db.conn.commit()

            html = store_mode_view()

            assert "No active shopping list" in html, (
                "Expected empty state message"
            )
        finally:
            if active_list_id:
                db.conn.execute(
                    "UPDATE shopping_lists SET is_active = 1 WHERE list_id = ?",
                    (active_list_id,),
                )
                db.conn.commit()


class TestStoreModeToggleAPI:
    """Tests for the /api/v1/account/store-mode/toggle endpoint via TestClient.

    Uses FastAPI's TestClient against the account v1 router (the legacy
    ``_store_mode_toggle_endpoint`` from ``undo_mount`` was removed in
    Pass 26). The test seeds an auth token so ``require_household``
    Depends passes.
    """

    @pytest.fixture(autouse=True)
    def _setup_client(self) -> None:
        """Build a TestClient for the account v1 router."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from shopstack import app_context
        from shopstack.api.v1 import auth as auth_mod
        from shopstack.api.v1.routers.account import router as account_router
        from shopstack.app_context import db

        auth_mod.ensure_auth_table(db)

        monkey = pytest.MonkeyPatch()
        monkey.setattr(app_context, "db", db)

        fastapi_app = FastAPI(title="shopstack-test-store-mode")
        fastapi_app.include_router(account_router, prefix="/api/v1")

        self.client = TestClient(fastapi_app)
        self.token = auth_mod.issue_token(
            db, device_id="dev_store_mode", household_id=db.active_household_id,
        )["token"]
        self.monkey = monkey

    @pytest.fixture(autouse=True)
    def _teardown(self) -> None:
        yield
        self.monkey.undo()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _call_toggle(self, item_id: str) -> dict:
        r = self.client.post(
            "/api/v1/account/store-mode/toggle",
            json={"item_id": item_id},
            headers=self._headers(),
        )
        return r.json()

    def test_toggle_bought(self) -> None:
        """Toggling a pending item returns new_status='bought'."""
        result = self._call_toggle("li-1")
        assert result["success"] is True, f"Toggle failed: {result}"
        assert result["new_status"] == "bought", f"Expected bought, got: {result}"

    def test_toggle_pending(self) -> None:
        """Toggling a bought item returns new_status='pending'."""
        # First toggle → bought
        r1 = self._call_toggle("li-2")
        assert r1["new_status"] == "bought"

        # Second toggle → pending
        r2 = self._call_toggle("li-2")
        assert r2["success"] is True
        assert r2["new_status"] == "pending"

    def test_toggle_nonexistent_item(self) -> None:
        """Toggling a non-existent item returns success=False."""
        result = self._call_toggle("no-such-item")
        assert result["success"] is False
        assert "not found" in result.get("message", "").lower()

    def test_toggle_multiple_items(self) -> None:
        """Multiple items can be toggled independently."""
        r1 = self._call_toggle("li-3")
        assert r1["new_status"] == "bought"

        r2 = self._call_toggle("li-3")
        assert r2["new_status"] == "pending"

    def test_toggle_updates_db(self) -> None:
        """After toggling, the DB reflects the new status."""
        from shopstack.app_context import db

        self._call_toggle("li-2")

        # Verify via direct DB query
        sl = db.get_active_shopping_list()
        assert sl is not None, "Active shopping list should exist"
        item = next(
            (i for i in (sl.items or []) if i.list_item_id == "li-2"),
            None,
        )
        assert item is not None, "li-2 should exist in active shopping list"
        assert item.status == "bought", (
            f"Expected li-2 status to be 'bought', got '{item.status}'"
        )


class TestStoreModeBrowserSmoke:
    """Smoke test — launch the full app in a browser and check for console errors."""

    def test_app_loads_without_errors(self, tmp_path: Path) -> None:
        """Navigate to the app and verify no JavaScript errors.

        This is a smoke test only — the store mode view and API are
        tested directly in :class:`TestStoreModeView` and
        :class:`TestStoreModeToggleAPI`.
        """
        # Prevent the post-launch middleware re-install from crashing.
        import app as _app_module
        _app_module._install_permissions_policy_middleware = lambda _app: None  # type: ignore[method-assign]

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

        screenshot_path = str(tmp_path / "store_mode_smoke.png")
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

                page.goto(base_url, wait_until="load", timeout=30000)
                page.wait_for_timeout(3000)

                page.screenshot(path=screenshot_path, full_page=True)

                browser.close()
        finally:
            try:
                app.close()
            except Exception:
                pass

        # Assert no severe console errors
        severe = [m for m in collected if m["type"] in ("error", "assert")]

        if severe or js_errors:
            lines: list[str] = []
            lines.append("Browser errors detected during smoke test:\n")
            if js_errors:
                lines.append("── Uncaught JS exceptions ──")
                for exc in js_errors:
                    lines.append(f"  {exc}")
            if severe:
                lines.append("── Console errors ──")
                for m in severe:
                    loc = m["location"]
                    loc_str = f"{loc.get('url', '?')}:{loc.get('lineNumber', '?')}"
                    lines.append(f"  [{m['type']}] {m['text']}  ({loc_str})")
            pytest.fail("\n".join(lines))

        print(
            f"[store-mode-smoke] OK — app loaded, "
            f"screenshot at {screenshot_path}"
        )
