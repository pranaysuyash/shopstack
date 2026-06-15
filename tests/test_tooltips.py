"""Tests for `shopstack.services.tooltips` — the inline help registry.

Verifies:
  * The registry is well-formed: every entry has a non-empty
    title_key and body_key, no duplicate ids, and every key is
    translated in both en and hi.
  * `render_inline_help` returns the expected HTML structure for
    a known id and an empty string for an unknown one.
  * `render_help_for` wraps a field label in a `<label>` and
    inlines the help icon.
  * `tooltips_missing()` flags entries whose i18n keys are missing.
  * The click-toggle script is a valid `<script data-ss-exec>` block
    that registers a `data-pinned` attribute on the help target.
  * The output HTML escapes user-supplied content (no XSS vector
    even if a future entry embeds special chars).
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest

from shopstack.services.i18n import TRANSLATIONS
from shopstack.services.tooltips import (
    HELP_REGISTRY,
    render_help_for,
    render_help_toggle_script,
    render_inline_help,
    tooltips_missing,
)


# ── Registry sanity ────────────────────────────────────────────────


class TestHelpRegistry:
    def test_no_duplicate_ids(self):
        ids = list(HELP_REGISTRY.keys())
        assert len(ids) == len(set(ids))

    def test_every_entry_has_title_and_body_keys(self):
        for help_id, entry in HELP_REGISTRY.items():
            assert entry.title_key, f"{help_id} missing title_key"
            assert entry.body_key, f"{help_id} missing body_key"

    def test_known_entries_present(self):
        for must in (
            "lot_id",
            "batch_syntax",
            "expiry_date",
            "scene_type",
            "community_optin",
            "trace_retention",
            "global_search",
        ):
            assert must in HELP_REGISTRY, f"Missing registry entry: {must}"


# ── Translation coverage ───────────────────────────────────────────


class TestHelpI18nCoverage:
    def test_every_help_key_translated(self):
        """Every title/body key must be present in both en and hi."""
        en = TRANSLATIONS["en"]
        hi = TRANSLATIONS["hi"]
        missing: list[str] = []
        for entry in HELP_REGISTRY.values():
            for key in (entry.title_key, entry.body_key):
                if key not in en:
                    missing.append(f"en:{key}")
                if key not in hi:
                    missing.append(f"hi:{key}")
        assert not missing, f"Missing translations: {missing[:5]}"


# ── Renderer ───────────────────────────────────────────────────────


class _TagListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


def _tags(html: str) -> list[str]:
    p = _TagListParser()
    p.feed(html)
    return p.tags


class TestRenderInlineHelp:
    def test_known_id_renders_wrapper(self):
        html = render_inline_help("lot_id", locale="en")
        assert "help-target" in html
        assert "help-tooltip" in html
        assert "help-target-icon" in html
        # The consumer-friendly title (was "Lot ID", now "Batch")
        assert "Batch" in html
        # aria-describedby points at the tooltip
        assert 'aria-describedby="help-tip-lot_id"' in html

    def test_hindi_renders_hindi_title(self):
        html = render_inline_help("lot_id", locale="hi")
        assert "बैच" in html

    def test_custom_icon(self):
        html = render_inline_help("lot_id", icon="i")
        assert ">i</span>" in html

    def test_example_block_rendered_when_present(self):
        html = render_inline_help("batch_syntax", locale="en")
        assert "help-tooltip-example" in html
        # Example value from registry
        assert "inv-001: 3" in html

    def test_learn_more_link_rendered(self):
        html = render_inline_help("community_optin", locale="en")
        assert 'href="Docs/PRIVACY.md"' in html
        assert "Learn more" in html

    def test_escape_safety(self):
        """If an i18n string contains HTML, it must be escaped."""
        from shopstack.services import i18n

        original = i18n.TRANSLATIONS["en"].copy()
        i18n.TRANSLATIONS["en"]["help.lot_id.title"] = '<script>alert(1)</script>'
        try:
            html = render_inline_help("lot_id", locale="en")
            assert "<script>alert(1)</script>" not in html
            assert "&lt;script&gt;" in html
        finally:
            i18n.TRANSLATIONS["en"] = original


class TestRenderHelpFor:
    def test_label_wrapper(self):
        html = render_help_for("Lot ID", "lot_id", locale="en")
        assert "<label" in html
        assert "Lot ID" in html
        # Inlines the help icon
        assert "help-target" in html


# ── tooltips_missing static check ──────────────────────────────────


class TestTooltipsMissing:
    def test_flags_untranslated_keys(self):
        from shopstack.services import i18n

        original = i18n.TRANSLATIONS["en"].copy()
        # Remove a translation to simulate a developer that added
        # an entry but forgot to translate it.
        del i18n.TRANSLATIONS["en"]["help.lot_id.body"]
        try:
            missing = tooltips_missing()
            # One of the missing flags should be "lot_id:body"
            assert any("lot_id" in m for m in missing), f"Got: {missing}"
        finally:
            i18n.TRANSLATIONS["en"] = original

    def test_returns_empty_when_all_translated(self):
        # Baseline: with all translations present, no missing keys.
        missing = tooltips_missing()
        assert missing == [], f"Unexpectedly missing: {missing}"


# ── Click-toggle script ────────────────────────────────────────────


class TestToggleScript:
    def test_renders_script_tag(self):
        script = render_help_toggle_script()
        assert script.strip().startswith("<script")
        assert script.strip().endswith("</script>")
        assert 'data-ss-exec="true"' in script

    def test_registers_click_and_escape_handlers(self):
        script = render_help_toggle_script()
        # Click handler that toggles data-pinned
        assert "data-pinned" in script
        # Escape key un-pins
        assert "Escape" in script
        # IIFE pattern (won't pollute globals)
        assert "(function()" in script

    def test_no_globals_outside_iife(self):
        """The script must not declare loose `var` at the *outermost*
        level (a known cause of item #1 in the 2026-06-13 review).
        We allow `var` *inside* the IIFE wrapper — that scope is
        the function local, which is exactly what we want."""
        script = render_help_toggle_script()
        # Find the (function(){ ... })() block. Outside that block,
        # no `var` declarations should exist.
        iife_open = script.find("(function()")
        iife_close = script.rfind("})();")
        if iife_open >= 0 and iife_close > iife_open:
            outside = script[:iife_open] + script[iife_close:]
        else:
            outside = script
        m = re.search(r"^\s*var\s+\w+\s*=", outside, re.MULTILINE)
        assert m is None, f"Loose var declaration: {m.group(0)!r}"
