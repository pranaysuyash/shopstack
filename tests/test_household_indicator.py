"""Tests for the active-household header indicator (added 2026-06-13).

Closes a small UX gap: users had no persistent way to see which
household they're currently in. The household settings accordion
(``shopstack/ui/household_settings.py``) had the switcher, but it
was collapsed by default and the active name wasn't surfaced
elsewhere.

The fix: a small ``household_indicator_html()`` function in
``shopstack/ui/header.py`` that renders a badge like
``🏠 My Home`` in the header. Tests cover:

  * The badge is present in the rendered header HTML.
  * The display name is used (not the slug).
  * The fallback to household_id works if no display name.
  * An empty string is returned on resolution failure
    (defensive: never breaks the page).
"""

from __future__ import annotations

from unittest.mock import patch


class TestHouseholdIndicatorHtml:
    """The ``household_indicator_html()`` function is the core of the
    2026-06-13 household indicator. These tests pin the contract."""

    def test_returns_empty_when_no_active_household(self):
        from shopstack.ui.header import household_indicator_html
        with patch("shopstack.app_context.current_user_id", return_value=""):
            out = household_indicator_html()
        assert out == ""

    def test_renders_household_display_name(self):
        from shopstack.ui.header import household_indicator_html
        with patch(
            "shopstack.app_context.current_user_id",
            return_value="default_household",
        ), patch(
            "shopstack.app_context.list_households",
            return_value=[
                {"household_id": "default_household", "name": "My Home"},
                {"household_id": "beach", "name": "Beach House"},
            ],
        ):
            out = household_indicator_html()
        assert "My Home" in out
        assert "default_household" not in out  # display name used, not slug
        # Must have a recognizable house emoji
        assert "🏠" in out
        # Must be wrapped in a span with the hh-indicator class
        assert 'class="hh-indicator"' in out

    def test_aria_label_for_screen_readers(self):
        from shopstack.ui.header import household_indicator_html
        with patch(
            "shopstack.app_context.current_user_id",
            return_value="default_household",
        ), patch(
            "shopstack.app_context.list_households",
            return_value=[
                {"household_id": "default_household", "name": "My Home"},
            ],
        ):
            out = household_indicator_html()
        # ARIA label matches the display name (key for screen reader users)
        assert 'aria-label="Active household: My Home"' in out
        # Title for hover
        assert 'title="Active household: My Home"' in out

    def test_falls_back_to_id_when_no_name(self):
        from shopstack.ui.header import household_indicator_html
        with patch(
            "shopstack.app_context.current_user_id",
            return_value="my_house",
        ), patch(
            "shopstack.app_context.list_households",
            return_value=[
                {"household_id": "my_house", "name": ""},
            ],
        ):
            out = household_indicator_html()
        # Falls back to the slug when name is empty
        assert "my_house" in out

    def test_handles_missing_household_in_list(self):
        """If the active ID isn't in the list (race condition), fall back to the ID."""
        from shopstack.ui.header import household_indicator_html
        with patch(
            "shopstack.app_context.current_user_id",
            return_value="ghost_house",
        ), patch(
            "shopstack.app_context.list_households",
            return_value=[
                {"household_id": "default_household", "name": "My Home"},
            ],
        ):
            out = household_indicator_html()
        assert "ghost_house" in out

    def test_returns_empty_on_exception(self):
        """If anything raises, return empty string (never break the page)."""
        from shopstack.ui.header import household_indicator_html
        with patch(
            "shopstack.app_context.current_user_id",
            side_effect=RuntimeError("simulated db crash"),
        ):
            out = household_indicator_html()
        assert out == ""

    def test_xss_escape_household_name(self):
        """The display name must be escaped to prevent XSS via the household name."""
        from shopstack.ui.header import household_indicator_html
        with patch(
            "shopstack.app_context.current_user_id",
            return_value="hh1",
        ), patch(
            "shopstack.app_context.list_households",
            return_value=[
                {"household_id": "hh1", "name": "<script>alert(1)</script>"},
            ],
        ):
            out = household_indicator_html()
        # Malicious name should be escaped, not raw
        assert "<script>alert(1)</script>" not in out
        # The escaped form should be present
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out


class TestHeaderHtmlIncludesHouseholdIndicator:
    """The ``header_html()`` function must include the household badge."""

    def test_indicator_present_in_header_html(self):
        from shopstack.ui.header import header_html
        with patch(
            "shopstack.app_context.current_user_id",
            return_value="default_household",
        ), patch(
            "shopstack.app_context.list_households",
            return_value=[
                {"household_id": "default_household", "name": "My Home"},
            ],
        ):
            out = header_html("ShopStack", "Local-first", current_locale="en")
        # The badge content is in the rendered header
        assert "My Home" in out
        assert "🏠" in out

    def test_indicator_absent_when_no_active_household(self):
        from shopstack.ui.header import header_html
        with patch("shopstack.app_context.current_user_id", return_value=""):
            out = header_html("ShopStack", "Local-first", current_locale="en")
        # No badge, but the rest of the header still renders
        assert "ShopStack" in out
        # The hh-indicator class should NOT appear
        assert 'class="hh-indicator"' not in out


class TestModuleSurface:
    def test_household_indicator_html_is_exported(self):
        from shopstack.ui import header
        assert hasattr(header, "household_indicator_html")
        assert callable(header.household_indicator_html)
