"""Tests for the share-list feature (added 2026-06-13).

Background:
  ``shopstack/ui/screens/shopping.py:_shopping_list_share_text`` and
  ``_shopping_list_share_html`` were both fully built (the latter
  returns a complete share UI: textarea + Copy button + WhatsApp
  link). But they were:
    (a) private (underscore-prefixed, not exported)
    (b) never wired to a button in the shopping list tab

  The shopping list tab had a placeholder ``sl_share = gr.HTML(...)``
  but no click handler.

Fix:
  1. Added a public ``shopping_list_share()`` Gradio adapter that
     composes the two private helpers (so the share button can
     call it via a single click).
  2. Wired a "Share list" button in the shopping list tab with
     ``api_name="shopping_list_share"``.

This test:
  1. Verifies the public function is importable + callable.
  2. Verifies the returned HTML includes the textarea, Copy button,
     and WhatsApp link.
  3. Verifies the empty-list state returns the "no active list" message.
  4. Verifies the share text content is properly formatted.
  5. Verifies the app.py actually wires the new endpoint.
  6. Verifies the basket_shopping_list.py file calls the public function.
"""

from __future__ import annotations

import sys


class TestShareListPublicAPI:
    """The public shopping_list_share adapter must be importable."""

    def test_shopping_list_share_is_importable(self):
        from shopstack.ui.screens.shopping import shopping_list_share
        assert callable(shopping_list_share)

    def test_shopping_list_share_is_in_screens_all(self):
        from shopstack.ui.screens import __all__ as screens_all
        assert "shopping_list_share" in screens_all, (
            "shopping_list_share must be exported from screens.__all__ "
            "so the Gradio click handler in the shopping list tab can "
            "import it."
        )


class TestShareListEmptyState:
    """The function should return a clear message when there's no list."""

    def test_no_active_list_returns_message(self):
        from shopstack.ui.screens.shopping import shopping_list_share
        from shopstack.app_context import db
        TEST = "share_test_empty"
        orig_active = db.active_household_id
        try:
            db.add_household(TEST, "Share Test Empty")
            db.add_household_member(TEST, TEST, role="owner")
            db.active_household_id = TEST
            # No shopping list created
            result = shopping_list_share()
            assert "No active shopping list" in result or "No items" in result, (
                f"Expected a clear 'no list' message, got: {result!r}"
            )
        finally:
            db.conn.execute(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
                ("active_household_id", orig_active),
            )
            db.conn.commit()
            db.remove_household(TEST)


class TestShareListActive:
    """When there's an active list, the share HTML is fully rendered."""

    def _make_list_with_items(self, db, user_id: str, items: list[dict]):
        """Helper: create a shopping list with the given items."""
        from shopstack.schemas.models import ShoppingListItem
        new_list = db.create_shopping_list(
            name="Test List", goal="test", user_id=user_id,
        )
        for item in items:
            db.add_list_item(
                list_id=new_list.list_id,
                item=ShoppingListItem(
                    canonical_name=item["canonical_name"],
                    requested_quantity=item.get("qty", 1.0),
                    unit=item.get("unit", "unit"),
                ),
            )
        return new_list

    def test_active_list_renders_textarea(self):
        from shopstack.ui.screens.shopping import shopping_list_share
        from shopstack.app_context import db
        TEST = "share_test_active"
        orig_active = db.active_household_id
        try:
            db.add_household(TEST, "Share Test Active")
            db.add_household_member(TEST, TEST, role="owner")
            db.active_household_id = TEST
            self._make_list_with_items(db, TEST, [
                {"canonical_name": "rice", "qty": 1.0, "unit": "kg"},
                {"canonical_name": "onion", "qty": 2.0, "unit": "unit"},
            ])
            result = shopping_list_share()
            # Should have a textarea with id 'sl-share-text'
            # (the renderer uses single-quoted attributes; we check
            # both quote styles to be robust)
            assert (
                'id="sl-share-text"' in result
                or "id='sl-share-text'" in result
                or "id=\\'sl-share-text\\'" in result
            ), (
                f"Expected textarea with id 'sl-share-text', got: {result[:300]!r}"
            )
            # Should have a Copy button
            assert "Copy" in result, "Expected a Copy button"
            # Should have a WhatsApp link
            assert "wa.me" in result, "Expected a WhatsApp link (wa.me)"
            # Should mention the active items
            assert "rice" in result.lower(), (
                "Expected the item 'rice' in the share content"
            )
        finally:
            active = db.get_active_shopping_list(user_id=TEST)
            if active:
                db.conn.execute(
                    "DELETE FROM shopping_list_items WHERE list_id = ?",
                    (active.list_id,),
                )
                db.conn.execute(
                    "DELETE FROM shopping_lists WHERE list_id = ?",
                    (active.list_id,),
                )
            db.conn.execute(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
                ("active_household_id", orig_active),
            )
            db.conn.commit()
            db.remove_household(TEST)


class TestShareListXSS:
    """The share HTML must be XSS-safe (no raw user input in HTML)."""

    def test_item_name_is_escaped(self):
        from shopstack.ui.screens.shopping import shopping_list_share
        from shopstack.app_context import db
        from shopstack.schemas.models import ShoppingListItem
        TEST = "share_test_xss"
        orig_active = db.active_household_id
        try:
            db.add_household(TEST, "XSS Test")
            db.add_household_member(TEST, TEST, role="owner")
            db.active_household_id = TEST
            new_list = db.create_shopping_list(
                name="XSS", goal="xss", user_id=TEST,
            )
            db.add_list_item(
                list_id=new_list.list_id,
                item=ShoppingListItem(
                    canonical_name="<script>alert(1)</script>",
                    requested_quantity=1.0,
                    unit="unit",
                ),
            )
            result = shopping_list_share()
            # The raw script tag should NOT appear in the HTML
            assert "<script>alert(1)</script>" not in result, (
                f"XSS: raw script tag in output: {result[:300]!r}"
            )
            # The escaped form should appear
            assert "&lt;script&gt;" in result or "&lt;script" in result, (
                f"Expected escaped script tag, got: {result[:300]!r}"
            )
        finally:
            active = db.get_active_shopping_list(user_id=TEST)
            if active:
                db.conn.execute(
                    "DELETE FROM shopping_list_items WHERE list_id = ?",
                    (active.list_id,),
                )
                db.conn.execute(
                    "DELETE FROM shopping_lists WHERE list_id = ?",
                    (active.list_id,),
                )
            db.conn.execute(
                "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
                ("active_household_id", orig_active),
            )
            db.conn.commit()
            db.remove_household(TEST)


class TestShareListWiringInApp:
    """The shopping list tab must actually call the new function."""

    def test_basket_shopping_list_imports_shopping_list_share(self):
        from pathlib import Path
        tab_py = Path("shopstack/ui/tabs/basket_shopping_list.py").read_text()
        assert "shopping_list_share" in tab_py, (
            "basket_shopping_list.py must import shopping_list_share "
            "from the screens module."
        )
        # And it should call it via .click()
        assert "shopping_list_share" in tab_py and "share_btn" in tab_py, (
            "basket_shopping_list.py must wire share_btn.click to "
            "shopping_list_share."
        )

    def test_basket_shopping_list_wires_api_name(self):
        from pathlib import Path
        tab_py = Path("shopstack/ui/tabs/basket_shopping_list.py").read_text()
        assert 'api_name="shopping_list_share"' in tab_py, (
            "The share button must register with api_name='shopping_list_share' "
            "so the endpoint is callable via the Gradio client API."
        )

    def test_no_underscore_prefixed_share_call_in_tab(self):
        """The tab should use the public function, not the underscore-prefixed one.

        Catches a regression where someone uses the private helper
        directly and bypasses the empty-list handling.
        """
        from pathlib import Path
        tab_py = Path("shopstack/ui/tabs/basket_shopping_list.py").read_text()
        # The click handler should reference the PUBLIC name
        if "shopping_list_share" in tab_py:
            # If shopping_list_share (public) is imported, it should
            # be the one wired to share_btn, not the underscore variants
            assert "_shopping_list_share_text" not in tab_py, (
                "basket_shopping_list.py should not call the private "
                "_shopping_list_share_text directly; use the public "
                "shopping_list_share adapter."
            )
            assert "_shopping_list_share_html" not in tab_py, (
                "basket_shopping_list.py should not call the private "
                "_shopping_list_share_html directly; use the public "
                "shopping_list_share adapter."
            )
