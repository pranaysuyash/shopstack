"""Tests for `shopstack.services.empty_states` — the empty-state service.

Verifies:
  * The preset registry is well-formed (every preset has a tier, title
    key, body key; no duplicates).
  * The renderer produces safe HTML (escapes, no obvious XSS vectors).
  * Smart mode downgrades first_time -> transient when the household
    already has data.
  * The compact renderer produces a one-liner (no CTAs, no icon).
  * Unknown preset ids fall back to a safe placeholder (never crash).
  * The CTA JSON serialises correctly so the JS handler can read it.
  * `render_empty_state_script()` returns valid `<script data-ss-exec>`.
"""
from __future__ import annotations

from html.parser import HTMLParser

import pytest

from shopstack.services.empty_states import (
    PRESETS,
    EmptyStateCTA,
    EmptyStatePreset,
    HouseholdContext,
    RenderOptions,
    build_household_context,
    render,
    render_empty_state_script,
)


# ── Registry sanity ────────────────────────────────────────────────


class TestPresetRegistry:
    def test_presets_have_unique_ids(self):
        ids = [p.preset_id for p in PRESETS.values()]
        assert len(ids) == len(set(ids)), f"Duplicate preset ids: {ids}"

    def test_presets_have_required_fields(self):
        for p in PRESETS.values():
            assert p.tier in {"first_time", "transient"}
            # The "generic" preset intentionally has empty
            # title/body/icon keys — it relies on override_*
            # arguments from the caller. All other presets
            # must have non-empty keys.
            if p.preset_id == "generic":
                continue
            assert p.title_key, f"{p.preset_id} missing title_key"
            assert p.body_key, f"{p.preset_id} missing body_key"

    def test_presets_include_known_sections(self):
        """Every section referenced by the renderer should exist."""
        expected = {
            "home.dashboard",
            "pantry.inventory",
            "groceries.basket",
            "memory.recent",
            "household.fridge",
            "recipes.cookbook",
        }
        actual = set(PRESETS.keys())
        assert expected.issubset(actual), (
            f"Missing: {expected - actual}"
        )


# ── i18n coverage ──────────────────────────────────────────────────


class TestI18nCoverage:
    def test_every_title_key_translated(self):
        """Each title key must be present in both en and hi (or
        gracefully fall back)."""
        from shopstack.services.i18n import TRANSLATIONS

        en = TRANSLATIONS["en"]
        hi = TRANSLATIONS["hi"]
        missing: list[str] = []
        for p in PRESETS.values():
            # Skip presets with no i18n keys (the "generic" preset
            # uses override arguments).
            if p.preset_id == "generic":
                continue
            if p.title_key not in en:
                missing.append(f"en:{p.title_key}")
            if p.body_key not in en:
                missing.append(f"en:{p.body_key}")
            if p.title_key not in hi:
                missing.append(f"hi:{p.title_key}")
            if p.body_key not in hi:
                missing.append(f"hi:{p.body_key}")
            for cta in (p.primary_cta, p.secondary_cta):
                if cta and cta.label not in en:
                    missing.append(f"en:cta:{cta.label}")
                if cta and cta.label not in hi:
                    missing.append(f"hi:cta:{cta.label}")
        assert not missing, f"Missing translations: {missing}"


# ── Renderer ───────────────────────────────────────────────────────


class _TagListParser(HTMLParser):
    """Tiny HTML parser that captures every tag name seen."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


def _html_tags(html: str) -> list[str]:
    p = _TagListParser()
    p.feed(html)
    return p.tags


class TestRenderFull:
    def test_known_preset_returns_full_card(self):
        html = render("home.dashboard", options=RenderOptions(locale="en"))
        assert "Welcome home" in html
        assert "dashboard" in html.lower()
        # Has icon, title, body, CTA wrapper
        tags = _html_tags(html)
        assert "h3" in tags
        assert "button" in tags  # primary CTA rendered
        assert html.startswith('<div class="empty-state')

    def test_secondary_cta_also_renders(self):
        html = render("home.dashboard", options=RenderOptions(locale="en"))
        assert "empty-state-cta--primary" in html
        assert "empty-state-cta--secondary" in html

    def test_hindi_renders_hindi_text(self):
        html = render("home.dashboard", options=RenderOptions(locale="hi"))
        assert "घर पर स्वागत है" in html

    def test_unknown_preset_falls_back(self):
        html = render("nonexistent.preset", options=RenderOptions(locale="en"))
        assert "empty-state" in html
        # The fallback i18n key
        assert "Nothing here yet" in html


class TestRenderCompact:
    def test_compact_is_one_liner_no_cta(self):
        html = render(
            "home.dashboard",
            options=RenderOptions(locale="en", compact=True),
        )
        # Compact mode has no buttons, no icon
        tags = _html_tags(html)
        assert "button" not in tags
        assert "h3" not in tags
        assert "empty-state--compact" in html
        # Title still rendered inline
        assert "Welcome home" in html


class TestSmartDowngrade:
    def test_first_time_with_data_downgrades(self):
        # When the household has data, the "first_time" preset
        # should fall through to the transient sibling.
        ctx = HouseholdContext(item_count=42, has_any_data=True)
        html = render(
            "home.dashboard",
            options=RenderOptions(locale="en"),
            household=ctx,
        )
        # The transient sibling for home.dashboard is memory.what_changed
        # which renders "All caught up"
        assert "All caught up" in html
        # NOT the first-time onboarding copy
        assert "Welcome home" not in html

    def test_first_time_without_data_stays_first_time(self):
        ctx = HouseholdContext(item_count=0, has_any_data=False)
        html = render(
            "home.dashboard",
            options=RenderOptions(locale="en"),
            household=ctx,
        )
        assert "Welcome home" in html
        assert "All caught up" not in html


class TestEscapeSafety:
    def test_household_name_with_html_does_not_inject(self):
        """An i18n string with HTML special chars should escape them."""
        # Patch the i18n layer to return a string with HTML
        from shopstack.services import i18n

        original = i18n.TRANSLATIONS["en"].copy()
        i18n.TRANSLATIONS["en"]["empty.dashboard.title"] = '<script>alert(1)</script>'
        try:
            html = render("home.dashboard", options=RenderOptions(locale="en"))
            # The literal <script> tag must NOT be present in the output
            # (the html.escape in render_full should have escaped it).
            assert "<script>alert(1)</script>" not in html
            # The escaped version is fine
            assert "&lt;script&gt;" in html
        finally:
            i18n.TRANSLATIONS["en"] = original


# ── Household context builder ─────────────────────────────────────


class TestBuildHouseholdContext:
    def test_returns_empty_context_for_missing_user(self):
        ctx = build_household_context(database=None, user_id="")
        assert ctx.item_count == 0
        assert ctx.has_any_data is False

    def test_db_exception_yields_empty_context(self):
        class _BoomDb:
            def get_inventory(self, user_id=""):
                raise RuntimeError("simulated DB failure")

        ctx = build_household_context(database=_BoomDb(), user_id="x")
        assert ctx.item_count == 0
        assert ctx.has_any_data is False

    def test_populated_db_yields_nonempty_context(self):
        class _FakeDb:
            def get_inventory(self, user_id=""):
                from shopstack.schemas.models import InventoryLot

                return [
                    InventoryLot(
                        lot_id="lot-1", canonical_name="milk",
                        display_name="Milk", quantity=1.0, unit="L",
                        storage_location_id="fridge",
                    ),
                ]

            def get_active_shopping_list(self, user_id=""):
                return None

            def get_traces(self, limit=1, user_id=""):
                return []

        ctx = build_household_context(database=_FakeDb(), user_id="x")
        assert ctx.item_count == 1
        assert ctx.has_any_data is True


# ── Empty-state JS handler ────────────────────────────────────────


class TestEmptyStateScript:
    def test_renders_script_tag(self):
        script = render_empty_state_script()
        assert script.strip().startswith("<script")
        assert script.strip().endswith("</script>")
        # Must declare the data-ss-exec attribute so the bootstrap
        # picks it up.
        assert 'data-ss-exec="true"' in script

    def test_registers_global_handler(self):
        script = render_empty_state_script()
        assert "ssEmptyStateCta" in script
        # Handler must be a function expression, not a bare statement
        # (lesson from item #1 in the 2026-06-13 issue review).
        assert "function ssEmptyStateCta" in script


# ── CTA JSON serialisation ────────────────────────────────────────


class TestCtaJson:
    def test_cta_serialises_to_valid_json(self):
        from shopstack.services.empty_states import _cta_json

        cta = EmptyStateCTA(label="add", target_id="add-btn", target_tab="pantry")
        j = _cta_json(cta)
        import json

        data = json.loads(j)
        assert data["targetId"] == "add-btn"
        assert data["targetTab"] == "pantry"
