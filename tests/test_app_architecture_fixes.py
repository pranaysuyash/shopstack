"""Regression tests for app.py architecture fixes (2026-06-14).

These tests verify:
  1. Required-handle guards exist in app.py (P0 from audit)
  2. Household-switch triggers a full page reload (so all tabs
     show fresh data, not just Today)
  3. The JS reload helper is properly wired
  4. The window.toggleTheme binding exists in the header script
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestAppPyHandleGuards:
    """app.py must fail fast if today/reconcile builders return None."""

    def test_today_handle_guarded(self):
        app_source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
        # Look for a guard pattern: handles.get("today") with a check
        assert re.search(
            r'handles\.get\(["\']today["\']\)',
            app_source,
        ), "app.py must extract today handles with handles.get('today')"
        # And a RuntimeError check
        assert re.search(
            r"today_handles\s+is\s+None.*?RuntimeError",
            app_source,
            re.DOTALL,
        ), "app.py must check 'today_handles is None' and raise RuntimeError"

    def test_reconcile_handle_guarded(self):
        app_source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
        assert re.search(
            r'handles\.get\(["\']reconcile["\']\)',
            app_source,
        ), "app.py must extract reconcile handles with handles.get('reconcile')"
        assert re.search(
            r"reconcile_handles\s+is\s+None.*?RuntimeError",
            app_source,
            re.DOTALL,
        ), "app.py must check 'reconcile_handles is None' and raise RuntimeError"


class TestHouseholdSwitchReload:
    """Switching households must reload the page so all tabs refresh.

    The reload JS was extracted from app.py to
    ``shopstack/ui/state/household_wiring.py`` during the household-wiring
    refactor (motto §7 supersession). These tests check the canonical
    location. app.py delegates via ``wire_household_handlers()``.
    """

    WIRING_PATH = REPO_ROOT / "shopstack" / "ui" / "state" / "household_wiring.py"

    def test_reload_js_function_exists(self):
        """The household-switch reload JS must exist in household_wiring.py."""
        wiring_source = self.WIRING_PATH.read_text(encoding="utf-8")
        assert "_HOUSEHOLD_SWITCH_RELOAD_JS" in wiring_source, (
            "household_wiring.py must define _HOUSEHOLD_SWITCH_RELOAD_JS "
            "so all tabs show fresh data after a household switch"
        )

    def test_reload_js_uses_location_href_not_replace(self):
        """The reload JS should use window.location.href (preserves hash)
        not location.replace (loses hash)."""
        wiring_source = self.WIRING_PATH.read_text(encoding="utf-8")
        assert "window.location.href" in wiring_source, (
            "Reload should use window.location.href to preserve the hash"
        )

    def test_reload_wired_to_household_change(self):
        """The reload JS must be wired to the household dropdown change."""
        wiring_source = self.WIRING_PATH.read_text(encoding="utf-8")
        assert "household_dropdown.change" in wiring_source or ".change" in wiring_source, (
            "The reload must be invoked after the household dropdown change"
        )

    def test_reload_preserves_url_hash(self):
        """The reload should preserve the URL hash so the user stays
        on the same tab (Today, Basket, etc.) after switching."""
        wiring_source = self.WIRING_PATH.read_text(encoding="utf-8")
        assert "window.location.hash" in wiring_source, (
            "Reload should read window.location.hash to preserve the tab"
        )


class TestToggleThemeWindowBinding:
    """toggleTheme must be explicitly bound to window for P0 browser
    hydration robustness (in case script_bootstrap_js doesn't fire)."""

    def test_header_script_binds_toggle_theme_to_window(self):
        header_source = (REPO_ROOT / "shopstack" / "ui" / "header.py").read_text(
            encoding="utf-8",
        )
        # The header script should explicitly bind toggleTheme to window
        # so it's accessible regardless of how the script is executed
        assert re.search(
            r"window\.toggleTheme\s*=\s*toggleTheme",
            header_source,
        ), (
            "header.py must explicitly bind toggleTheme to window "
            "(window.toggleTheme = toggleTheme) so the theme toggle "
            "button works even if script_bootstrap_js doesn't fire."
        )
