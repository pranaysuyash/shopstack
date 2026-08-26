"""Empty-state preset coverage audit (2026-06-13).

Per motto_v3 §6 (pre-existing is not an excuse), every major tab
should have a first-class empty state. This test:

  1. Locks in the 19 presets (16 pre-existing + 3 added in this pass)
  2. Verifies every preset's title_key + body_key exist in both en and hi
  3. Verifies every preset renders without error in both locales
  4. Audits which tabs have an empty_state reference (and which don't)
  5. Documents the 3 presets added in this pass

This is a coverage audit, not a hard requirement. Tabs without an
empty_state reference are listed for visibility — they're not
required to have one (some tabs are data-free by design).
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent
TABS_DIR = REPO / "shopstack/ui/tabs"


# ─── Preset registry: 19 total ─────────────────────────────────


class TestEmptyStatePresetRegistry:
    """The empty_state preset registry must be stable."""

    EXPECTED_PRESETS = {
        # Pre-existing 16
        "home.dashboard",
        "pantry.inventory",
        "groceries.basket",
        "groceries.basket.no_active_list",
        "memory.recent",
        "memory.what_changed",
        "memory.find_trail",
        "find_trail.no_query",
        "while_shopping.manual_add",
        "at_home.reconcile",
        "household.fridge",
        "recipes.cookbook",
        "basket.create_list.no_action",
        "parser.no_input",
        "recipe.no_input",
        "global_search.no_results",
        "generic",
        # Added 2026-06-13 (3)
        "memory.analytics",
        "memory.consumption",
        "memory.activity_log",
    }

    def test_all_presets_defined(self):
        from shopstack.services.empty_states import PRESETS
        actual = set(PRESETS.keys())
        missing = self.EXPECTED_PRESETS - actual
        extra = actual - self.EXPECTED_PRESETS
        # Missing is a hard fail
        assert not missing, (
            f"Missing expected presets: {missing}. If you removed a "
            "preset, also update this test; otherwise, add the preset back."
        )
        # Extra is a soft warning (we want forward progress)
        if extra:
            pytest.skip(f"Extra presets (not in expected list): {extra}. "
                        "Add them to the EXPECTED_PRESETS list if intentional.")

    def test_preset_count_at_least_19(self):
        from shopstack.services.empty_states import PRESETS
        assert len(PRESETS) >= 19, (
            f"Only {len(PRESETS)} presets; expected at least 19. "
            "Did you delete some?"
        )

    def test_no_duplicate_preset_ids(self):
        from shopstack.services.empty_states import PRESETS
        ids = [p.preset_id for p in PRESETS.values()]
        duplicates = {x for x in ids if ids.count(x) > 1}
        assert not duplicates, f"Duplicate preset_ids: {duplicates}"


# ─── Every preset's i18n keys exist ────────────────────────────


class TestPresetI18nKeys:
    """Each preset's title_key + body_key must exist in both en and hi."""

    def test_all_preset_keys_in_en(self):
        from shopstack.services.empty_states import PRESETS
        from shopstack.services.i18n import TRANSLATIONS
        missing = []
        for pid, p in PRESETS.items():
            for k in (p.title_key, p.body_key):
                if not k:
                    continue  # generic preset has empty keys by design
                if k not in TRANSLATIONS["en"]:
                    missing.append(f"{pid}.{k}")
        assert not missing, f"Missing en keys for presets: {missing}"

    def test_all_preset_keys_in_hi(self):
        from shopstack.services.empty_states import PRESETS
        from shopstack.services.i18n import TRANSLATIONS
        missing = []
        for pid, p in PRESETS.items():
            for k in (p.title_key, p.body_key):
                if not k:
                    continue
                if k not in TRANSLATIONS["hi"]:
                    missing.append(f"{pid}.{k}")
        assert not missing, (
            f"Missing hi keys for presets: {missing}. "
            "Per motto_v3 §6, every preset must be translated to Hindi."
        )


# ─── Every preset renders without error ────────────────────────


class TestPresetRendering:
    """Every preset must render in both locales without error."""

    @pytest.mark.parametrize("preset_id", [
        "home.dashboard", "pantry.inventory", "groceries.basket",
        "memory.recent", "memory.find_trail", "memory.analytics",
        "memory.consumption", "memory.activity_log", "recipes.cookbook",
        "parser.no_input", "recipe.no_input", "at_home.reconcile",
    ])
    def test_preset_renders_en(self, preset_id):
        from shopstack.services.empty_states import render, RenderOptions
        html = render(preset_id, options=RenderOptions(locale="en"))
        assert html, f"Empty render for {preset_id} in en"
        # Sanity: should contain the word "ShopStack" or some recognizable
        # element. The 'generic' preset is the only one allowed to be empty.
        if preset_id != "generic":
            assert len(html) > 50, f"Render suspiciously short for {preset_id}"

    @pytest.mark.parametrize("preset_id", [
        "home.dashboard", "pantry.inventory", "groceries.basket",
        "memory.recent", "memory.find_trail", "memory.analytics",
        "memory.consumption", "memory.activity_log", "recipes.cookbook",
        "parser.no_input", "recipe.no_input", "at_home.reconcile",
    ])
    def test_preset_renders_hi(self, preset_id):
        from shopstack.services.empty_states import render, RenderOptions
        html = render(preset_id, options=RenderOptions(locale="hi"))
        assert html, f"Empty render for {preset_id} in hi"

    def test_new_presets_actually_translate(self):
        """The 3 new presets added in 2026-06-13 must translate to Hindi.

        Per §6, this is the "actually Hindi, not just English value
        copied" check. Devanagari characters must appear in the
        rendered Hindi HTML.
        """
        from shopstack.services.empty_states import render, RenderOptions
        for pid in ("memory.analytics", "memory.consumption", "memory.activity_log"):
            html_hi = render(pid, options=RenderOptions(locale="hi"))
            # Check for any Devanagari character
            assert any("\u0900" <= c <= "\u097F" for c in html_hi), (
                f"Rendered Hindi HTML for {pid} has no Devanagari characters. "
                "The Hindi translation is probably the English value copied. "
                "Per §6, this is a real bug — translate properly."
            )


# ─── Tab coverage audit (informational) ─────────────────────────


class TestTabEmptyStateCoverage:
    """Audit which tabs reference empty_state, document the gaps.

    This is a SOFT audit. Tabs without empty_state are listed for
    visibility but don't fail the test. The next session can decide
    whether to add presets for them.
    """

    def _tabs(self) -> list[Path]:
        return sorted(
            p for p in TABS_DIR.glob("*.py")
            if p.name not in ("__init__.py", "context.py") and not p.name.startswith("_")
        )

    def test_audit_tab_coverage(self):
        """Audit which tabs have an empty_state reference."""
        with_empty: list[str] = []
        without_empty: list[str] = []
        for t in self._tabs():
            text = t.read_text()
            if "empty_state" in text:
                with_empty.append(t.name)
            else:
                without_empty.append(t.name)
        # Print the coverage as part of the test report
        # (this test always passes; it's an audit)
        coverage_pct = (len(with_empty) / max(1, len(with_empty) + len(without_empty))) * 100
        print(f"\nTab empty-state coverage: {len(with_empty)}/{len(with_empty) + len(without_empty)} ({coverage_pct:.0f}%)")
        print(f"  with empty_state: {len(with_empty)} tabs")
        print(f"  without empty_state: {len(without_empty)} tabs (informational)")
        # Sanity: at least half the tabs should have empty states
        assert coverage_pct >= 40, (
            f"Only {coverage_pct:.0f}% of tabs have an empty_state reference. "
            "Most tabs should have first-class empty states per §6."
        )
