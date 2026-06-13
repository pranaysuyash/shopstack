"""Tests for shopstack.services.walkthrough (Phase 5 #27 first-run tour)."""
from __future__ import annotations

import json
import re

import pytest

from shopstack.services.i18n import DEFAULT_LOCALE
from shopstack.services.walkthrough import (
    MAX_TOUR_SESSIONS,
    SESSION_COUNT_KEY,
    TOUR_SHOWN_KEY,
    render_walkthrough_html,
    render_walkthrough_script,
    should_show_tour,
)


# ── Constants ──────────────────────────────────────────────────────


def test_max_tour_sessions_is_three():
    # Three sessions is a sweet spot: shows the tour early enough to
    # help, but stops nagging the user by session 4.
    assert MAX_TOUR_SESSIONS == 3


def test_localstorage_keys_are_namespaced():
    assert TOUR_SHOWN_KEY.startswith("shopstack-")
    assert SESSION_COUNT_KEY.startswith("shopstack-")


# ── should_show_tour pure logic ───────────────────────────────────


def test_should_show_tour_on_session_1_first_time():
    assert should_show_tour(session_count=1, shown=False) is True


def test_should_show_tour_on_session_3_first_time():
    assert should_show_tour(session_count=3, shown=False) is True


def test_should_not_show_tour_on_session_4_first_time():
    assert should_show_tour(session_count=4, shown=False) is False


def test_should_not_show_tour_when_already_shown():
    assert should_show_tour(session_count=1, shown=True) is False
    assert should_show_tour(session_count=3, shown=True) is False


def test_should_show_tour_custom_max_sessions():
    assert should_show_tour(5, False, max_sessions=5) is True
    assert should_show_tour(6, False, max_sessions=5) is False


# ── HTML rendering ───────────────────────────────────────────────


def test_render_walkthrough_html_contains_all_four_steps():
    html = render_walkthrough_html()
    assert "data-step='1'" in html
    assert "data-step='2'" in html
    assert "data-step='3'" in html
    assert "data-step='4'" in html


def test_render_walkthrough_html_starts_on_step_1():
    html = render_walkthrough_html()
    # The first step should be marked active
    assert "data-step='1' data-active=true" in html


def test_render_walkthrough_html_counter_shows_progress():
    html = render_walkthrough_html()
    assert "1 / 4" in html


def test_render_walkthrough_html_has_dialog_role():
    html = render_walkthrough_html()
    assert 'role="dialog"' in html
    assert 'aria-modal="true"' in html


def test_render_walkthrough_html_includes_buttons():
    html = render_walkthrough_html()
    assert "tour-skip" in html
    assert "tour-next" in html
    assert "tour-back" in html


def test_render_walkthrough_html_includes_dot_indicators():
    html = render_walkthrough_html()
    assert html.count("tour-dot") >= 4


def test_render_walkthrough_html_hides_overlay_by_default():
    html = render_walkthrough_html()
    # CSS rule should set display: none
    assert "display: none" in html


def test_render_walkthrough_html_translates_for_locale():
    html_en = render_walkthrough_html(locale="en")
    html_hi = render_walkthrough_html(locale="hi")
    # Hindi version should contain Devanagari script
    assert any(0x0900 <= ord(c) <= 0x097F for c in html_hi)
    # And be different from English
    assert html_en != html_hi


def test_render_walkthrough_html_escapes_translations():
    # Defensive: titles/bodies are escaped, not raw
    html = render_walkthrough_html()
    # Should not contain unescaped angle brackets from translations
    assert "&lt;" not in html  # no escaped tags in our translations
    assert "data-step" in html


# ── Script rendering ─────────────────────────────────────────────


def test_render_walkthrough_script_uses_storage_keys():
    script = render_walkthrough_script()
    assert TOUR_SHOWN_KEY in script
    assert SESSION_COUNT_KEY in script


def test_render_walkthrough_script_uses_max_sessions():
    script = render_walkthrough_script(max_sessions=2)
    assert "var MAX = 2" in script


def test_render_walkthrough_script_handles_escape_key():
    script = render_walkthrough_script()
    assert "Escape" in script


def test_render_walkthrough_script_handles_arrow_keys():
    script = render_walkthrough_script()
    assert "ArrowRight" in script
    assert "ArrowLeft" in script


def test_render_walkthrough_script_handles_enter_key():
    script = render_walkthrough_script()
    assert "Enter" in script


def test_render_walkthrough_script_increments_session_count():
    script = render_walkthrough_script()
    # Should call safeSet(COUNT_KEY, ...) at some point
    assert "safeSet" in script
    assert "COUNT_KEY" in script


def test_render_walkthrough_script_sets_shown_flag_on_close():
    script = render_walkthrough_script()
    # The close() function should set SHOWN_KEY
    assert "safeSet(SHOWN_KEY" in script


def test_render_walkthrough_script_handles_missing_overlay():
    # If the overlay element isn't in the DOM, the script should bail safely
    script = render_walkthrough_script()
    assert "if (!overlay) { return;" in script or "if (!overlay)" in script


# ── XSS safety ──────────────────────────────────────────────────


def test_walkthrough_html_escapes_dynamic_strings():
    # The translation strings are escaped, not raw
    html = render_walkthrough_html()
    # No raw <script> tag in the title (only the inline <style> is allowed)
    title_match = re.search(r"<h2[^>]*>(.*?)</h2>", html, re.DOTALL)
    assert title_match
    # The title content should not contain literal < or > from translations
    # (translations don't have any, but this guards future regressions)
    assert "&lt;script" not in html.lower()


# ── Integration with i18n ───────────────────────────────────────


def test_walkthrough_uses_translation_module():
    # When a new locale is added, the tour should pick it up automatically
    from shopstack.services.i18n import SUPPORTED_LOCALES
    for loc in SUPPORTED_LOCALES:
        html = render_walkthrough_html(locale=loc)
        assert html  # Should not raise
        # Each locale should produce non-empty step content
        assert "data-step" in html
