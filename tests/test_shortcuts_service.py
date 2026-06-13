"""Tests for shopstack.services.shortcuts (Phase 5 #21 keyboard shortcuts)."""
from __future__ import annotations

import pytest

from shopstack.services.shortcuts import (
    SHORTCUTS,
    TAB_IDS,
    render_shortcuts_help_html,
    render_shortcuts_script,
)


# ── Shortcut table integrity ──────────────────────────────────────


def test_shortcut_table_is_non_empty():
    assert len(SHORTCUTS) > 0


def test_shortcut_table_has_required_keys():
    for s in SHORTCUTS:
        assert "key" in s
        assert "desc" in s
        assert "action" in s
        assert s["key"], "empty key"
        assert s["desc"], "empty desc"
        assert s["action"], "empty action"


def test_shortcut_table_covers_all_tabs():
    actions = {s["action"] for s in SHORTCUTS}
    # Every tab id should have a "tab:<id>" entry in the table
    for tid in TAB_IDS:
        assert f"tab:{tid}" in actions, f"missing tab shortcut for {tid!r}"


def test_tab_ids_match_today_basket_market_reconcile_memory():
    # The 6-tab daily loop.
    expected = {"today", "cookbook", "basket", "market", "reconcile", "memory"}
    assert set(TAB_IDS) == expected


def test_shortcut_keys_are_unique():
    keys = [s["key"] for s in SHORTCUTS]
    # Two-key combos can overlap with single keys (e.g. "g t" vs "t")
    # but the canonical form should be unique
    assert len(keys) == len(set(keys))


def test_help_shortcut_present():
    assert any(s["action"] == "help" for s in SHORTCUTS)


def test_escape_shortcut_present():
    assert any(s["action"] == "close" for s in SHORTCUTS)


def test_locale_and_theme_shortcuts_present():
    actions = {s["action"] for s in SHORTCUTS}
    assert "locale" in actions
    assert "theme" in actions


# ── HTML rendering ───────────────────────────────────────────────


def test_render_shortcuts_help_html_contains_dialog():
    html = render_shortcuts_help_html()
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html


def test_render_shortcuts_help_html_contains_all_shortcuts():
    html = render_shortcuts_help_html()
    for s in SHORTCUTS:
        # The key combo should appear in a <kbd> tag
        assert s["key"] in html, f"missing key combo {s['key']!r}"
        # And the description in a <span>
        assert s["desc"] in html, f"missing desc {s['desc']!r}"


def test_render_shortcuts_help_html_hides_overlay_by_default():
    html = render_shortcuts_help_html()
    assert "display: none" in html


def test_render_shortcuts_help_html_uses_escape_for_xss_safety():
    # Shortcut keys and descriptions are escaped, not raw
    html = render_shortcuts_help_html()
    # No raw script tags from descriptions
    assert "<script" not in html.lower()


# ── Script rendering ────────────────────────────────────────────


def test_render_shortcuts_script_contains_all_tab_ids():
    script = render_shortcuts_script()
    for tid in TAB_IDS:
        assert f'"{tid}"' in script, f"tab id {tid!r} missing from script"


def test_render_shortcuts_script_handles_help_toggle():
    script = render_shortcuts_script()
    assert "?" in script
    assert "toggleHelp" in script or "data-active" in script


def test_render_shortcuts_script_handles_escape_key():
    script = render_shortcuts_script()
    assert "Escape" in script


def test_render_shortcuts_script_handles_locale_toggle():
    script = render_shortcuts_script()
    assert "toggleLocale" in script
    assert "shopstack-locale" in script


def test_render_shortcuts_script_handles_theme_toggle():
    script = render_shortcuts_script()
    assert "toggleTheme" in script


def test_render_shortcuts_script_ignores_input_keystrokes():
    # When the user is typing, shortcuts should be ignored
    script = render_shortcuts_script()
    assert "INPUT" in script
    assert "TEXTAREA" in script


def test_render_shortcuts_script_handles_g_prefix():
    # The "g + letter" combos require a 2-key sequence
    script = render_shortcuts_script()
    assert "gPrefix" in script
    # g <letter> map for each tab
    for tid in TAB_IDS:
        first_letter = tid[0]
        # The map should contain the first letter of the tab id (lowercase or uppercase)
        # Some tab ids share the first letter, so just spot-check a few
        if tid in ("today", "cookbook", "basket", "market", "reconcile", "memory"):
            # The first letters are t, c, b, m, r, m — we expect m to appear twice
            assert f"'{first_letter}'" in script or f"'{first_letter.upper()}'" in script
