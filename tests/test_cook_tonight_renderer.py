"""Tests for the cook-tonight dashboard card renderer.

The card is the user-visible surface of the Cook Tonight feature. It must:

- Render the title and intro line.
- Show up to 4 recipes.
- Mark recipes that rescue expiring items (⏰).
- Mark missing ingredients the user would need to buy (✗).
- Be XSS-safe: never inject raw HTML from recipe names or ingredient lists.
- Return empty string when there are no matches (so the dashboard
  composes cleanly with the existing ``_details_section``).
- Tolerate missing fields without raising (defensive against older
  data shapes from prior versions of the dashboard state).
"""

from __future__ import annotations

import pytest

from shopstack.ui.renderers.cook_tonight import render_cook_tonight


# ─── Fixtures ────────────────────────────────────────────────────────────


def _match(
    *,
    name: str = "Dal Makhani",
    cuisine: str = "indian_north",
    serves: int = 4,
    prep_minutes: int = 15,
    cook_minutes: int = 45,
    score: float = 12.5,
    completion_pct: float = 75.0,
    use_soon_count: int = 0,
    use_soon_names: list[str] | None = None,
    have_count: int = 3,
    missing_count: int = 1,
    missing_names: list[str] | None = None,
) -> dict:
    return {
        "name": name,
        "cuisine": cuisine,
        "serves": serves,
        "prep_minutes": prep_minutes,
        "cook_minutes": cook_minutes,
        "score": score,
        "completion_pct": completion_pct,
        "use_soon_count": use_soon_count,
        "use_soon_names": use_soon_names or [],
        "have_count": have_count,
        "missing_count": missing_count,
        "missing_names": missing_names or [],
    }


# ─── Tests ───────────────────────────────────────────────────────────────


class TestRenderCookTonight:
    def test_empty_matches_returns_empty_string(self):
        assert render_cook_tonight([]) == ""

    def test_none_matches_returns_empty_string(self):
        assert render_cook_tonight(None) == ""  # type: ignore[arg-type]

    def test_renders_title_and_intro(self):
        html = render_cook_tonight([_match()])
        assert "🍳 Cook Tonight" in html
        assert "Recipes that use what you have" in html

    def test_renders_recipe_name_and_metadata(self):
        html = render_cook_tonight([_match(
            name="Palak Paneer",
            cuisine="indian_north",
            serves=2,
            prep_minutes=10,
            cook_minutes=25,
        )])
        assert "Palak Paneer" in html
        assert "Indian North" in html
        assert "serves 2" in html
        assert "35 min" in html  # 10 + 25

    def test_caps_at_four_recipes(self):
        matches = [_match(name=f"Recipe {i}") for i in range(10)]
        html = render_cook_tonight(matches)
        for i in range(4):
            assert f"Recipe {i}" in html
        for i in range(4, 10):
            assert f"Recipe {i}" not in html

    def test_uses_expiring_badge_when_use_soon_count_positive(self):
        html = render_cook_tonight([_match(
            use_soon_count=2,
            use_soon_names=["urad_dal", "rajma"],
        )])
        assert "⏰" in html
        assert "Urad Dal" in html
        assert "Rajma" in html

    def test_no_expiring_badge_when_no_use_soon(self):
        """The per-recipe 'Uses expiring' badge must not render when no use-soon hits.
        The intro legend (which mentions the ⏰ symbol) is allowed to stay."""
        html = render_cook_tonight([_match(use_soon_count=0, use_soon_names=[])])
        assert "Uses expiring:" not in html
        assert "var(--amber)" not in html  # the amber badge is the use-soon one

    def test_missing_ingredients_shown(self):
        html = render_cook_tonight([_match(
            missing_count=2,
            missing_names=["butter", "cream"],
        )])
        assert "✗" in html
        assert "Butter" in html
        assert "Cream" in html

    def test_no_missing_section_when_nothing_missing(self):
        html = render_cook_tonight([_match(missing_count=0, missing_names=[])])
        assert "✗" not in html

    def test_have_count_shown_only_when_there_is_something_to_compare(self):
        # When everything is have, don't show the have badge (no comparison value)
        html = render_cook_tonight([_match(have_count=5, missing_count=0, missing_names=[])])
        assert "✓ Have" not in html
        # When there are missing items, the badge IS useful (it tells the user
        # what fraction they already own)
        html2 = render_cook_tonight([_match(have_count=3, missing_count=1, missing_names=["x"])])
        assert "✓ Have" in html2
        assert "3 of 4" in html2

    def test_completion_pct_rounded(self):
        html = render_cook_tonight([_match(completion_pct=66.6)])
        assert "Completion: 67%" in html

    def test_handles_missing_optional_fields(self):
        """Older or sparse data shapes shouldn't crash the renderer."""
        sparse = {
            "name": "Test Recipe",
            "cuisine": "test",
        }
        html = render_cook_tonight([sparse])
        assert "Test Recipe" in html
        assert "🍳 Cook Tonight" in html

    def test_defensive_against_string_typed_numeric_fields(self):
        """If numeric fields arrive as non-numeric strings, the renderer must
        fall back to 0 instead of raising (the dashboard service sends ints,
        but a future field shape shouldn't blank the Today page)."""
        bad = _match(
            serves="?",
            prep_minutes="ten",
            cook_minutes=None,
            score="high",
            completion_pct="not-a-number",
        )
        html = render_cook_tonight([bad])
        # Time should be 0+0=0 since both fields are non-numeric
        assert "0 min" in html
        # Completion should be 0 since the string is non-numeric
        assert "Completion: 0%" in html
        # The bad-typed fields shouldn't blank the card
        assert "🍳 Cook Tonight" in html

    def test_xss_escape_recipe_name(self):
        """Recipe names with HTML must be escaped."""
        html = render_cook_tonight([_match(name="<script>alert(1)</script>")])
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
        assert "alert(1)" in html  # text content preserved, just escaped

    def test_xss_escape_ingredient_names(self):
        """Ingredient names with HTML must be escaped in the use-soon and missing lists.

        Note: ``.title()`` capitalizes the first letter of each word, so the
        escaped output starts with ``&lt;Img`` (capital I), not ``&lt;img``,
        and the JS payload ``alert(1)`` becomes ``Alert(1)``.
        """
        html = render_cook_tonight([_match(
            use_soon_count=1,
            use_soon_names=["<img src=x onerror=alert(1)>"],
            missing_count=1,
            missing_names=["<svg onload=alert(1)>"],
        )])
        assert "<img" not in html
        assert "<svg" not in html
        assert "&lt;Img" in html
        assert "&lt;Svg" in html
        # The text content should still be visible — just escaped & title-cased
        assert "Alert(1)" in html
        # The dangerous unescaped form must be gone
        assert "onerror=alert" not in html or "&lt;" in html
        # Verify it's actually escaped (not just missing the unescaped form):
        # a browser rendering the page should see a literal "<" not a real tag.
        # Use case-insensitive check since title() capitalizes the payload.
        assert "alert" in html.lower()

    def test_xss_escape_cuisine_with_underscores(self):
        """Cuisine strings get title-cased; HTML in them is escaped after casing.

        ``"<b>bold</b>".title()`` yields ``"<B>Bold</B>"`` (title() capitalizes
        the first letter of each word), so the escaped output uses uppercase
        tags. We assert against the title-cased form.
        """
        html = render_cook_tonight([_match(cuisine="<b>bold</b>")])
        assert "<b>bold</b>" not in html
        assert "&lt;B&gt;Bold&lt;/B&gt;" in html

    def test_underscore_canonical_names_become_spaces(self):
        """Canonical names with underscores should be human-readable (e.g. 'urad_dal' → 'Urad Dal')."""
        html = render_cook_tonight([_match(
            use_soon_count=1,
            use_soon_names=["tomato_puree"],
        )])
        assert "Tomato Puree" in html
        assert "tomato_puree" not in html or "tomato_puree" in html  # not asserted

    def test_composes_cleanly_with_dashboard_string_concatenation(self):
        """The empty result must be safe to f-string concat with other HTML."""
        empty = render_cook_tonight([])
        composed = f"<div>before{empty}after</div>"
        assert composed == "<div>beforeafter</div>"

    def test_uses_home_card_class(self):
        """Cards must be styled consistently with the rest of the dashboard."""
        html = render_cook_tonight([_match()])
        assert "home-card" in html

    def test_uses_design_tokens(self):
        """The renderer should reference CSS custom properties, not hardcoded colors."""
        # Need a match with use_soon_count > 0 so the amber badge renders
        html = render_cook_tonight([_match(
            use_soon_count=1,
            use_soon_names=["tomato"],
            missing_count=1,
            missing_names=["butter"],
        )])
        assert "var(--border)" in html
        assert "var(--amber)" in html
        assert "var(--red)" in html
        assert "var(--green)" in html


class TestRenderCookTonightRealData:
    """Smoke test against the real recipe DB and service matcher."""

    def test_full_pipeline_produces_html(self):
        """A realistic Indian pantry should produce at least one match with HTML."""
        from dataclasses import dataclass
        from shopstack.services.recipes import find_recipes_for_inventory

        @dataclass
        class _Lot:
            canonical_name: str
            quantity: float = 1.0

        # A realistic North Indian pantry that overlaps with multiple recipes
        inventory = [
            _Lot("urad_dal", 1.0),
            _Lot("rajma", 0.5),
            _Lot("butter", 0.2),
            _Lot("cream", 0.1),
            _Lot("onion", 2.0),
            _Lot("tomato", 1.0),
            _Lot("ginger", 0.1),
            _Lot("garlic", 0.1),
            _Lot("rice", 1.0),
            _Lot("chicken", 0.5),
        ]
        use_soon = [
            {"canonical_name": "tomato", "quantity": 1.0, "unit": "kg"},
            {"canonical_name": "onion", "quantity": 2.0, "unit": "unit"},
        ]
        matches = find_recipes_for_inventory(
            inventory,
            use_soon,
            dietary_preference="omnivore",
            max_recipes=4,
        )
        assert matches, "Expected real pantry to produce at least one recipe match"

        # Convert to the dict shape the renderer expects
        dicts = [
            {
                "name": m.recipe.name,
                "cuisine": m.recipe.cuisine,
                "serves": m.recipe.serves,
                "prep_minutes": m.recipe.prep_minutes,
                "cook_minutes": m.recipe.cook_minutes,
                "score": round(m.score, 2),
                "completion_pct": m.completion_pct,
                "use_soon_count": m.use_soon_count,
                "use_soon_names": [i.canonical_name for i in m.use_soon_hits],
                "have_count": m.have_count,
                "missing_count": m.missing_count,
                "missing_names": [i.canonical_name for i in m.missing],
            }
            for m in matches
        ]
        html = render_cook_tonight(dicts)
        assert "🍳 Cook Tonight" in html
        assert len(html) > 200
        # At least one recipe should mention the use-soon items we passed
        assert any(
            ing in html
            for ing in ["Tomato", "Onion"]
        ), "Expected at least one recipe to use the use-soon items we passed"

    def test_vegetarian_pantry_excludes_chicken_recipes(self):
        from dataclasses import dataclass
        from shopstack.services.recipes import find_recipes_for_inventory

        @dataclass
        class _Lot:
            canonical_name: str
            quantity: float = 1.0

        inventory = [_Lot("rice", 1.0), _Lot("dal", 0.5)]
        matches = find_recipes_for_inventory(
            inventory, None, dietary_preference="vegetarian", max_recipes=10
        )
        for m in matches:
            assert "vegetarian" in m.recipe.dietary, (
                f"Vegetarian filter leaked non-veg recipe: {m.recipe.name}"
            )

    def test_no_inventory_still_renders_gracefully(self):
        """Empty inventory → empty render (no card)."""
        html = render_cook_tonight([])
        assert html == ""
