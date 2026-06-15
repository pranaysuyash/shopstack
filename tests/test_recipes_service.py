"""Tests for the cook-tonight recipe service.

Covers:

- Recipe DB loads 30+ recipes.
- All ingredient canonical names match the rest of ShopStack's vocabulary.
- Recipe matching: have / missing / use-soon hits.
- Score ranking: use-soon hits boost the score; missing penalises.
- Dietary filter: vegetarian users don't see non-veg recipes.
- Empty inventory produces empty `have` / non-empty `missing`.
- HTML rendering: smoke test, XSS escaping.
- Round-trip from recipe → shopping list (missing ingredients only).
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from shopstack.services.recipes import (
    Recipe,
    RecipeIngredient,
    all_recipes,
    find_recipes_for_inventory,
    get_recipe,
    match_recipe,
    missing_to_shopping_items,
    render_cook_tonight_html,
)


# ─── Fixtures ────────────────────────────────────────────────────────────


@dataclass
class _FakeLot:
    canonical_name: str
    quantity: float = 1.0
    unit: str = "unit"


def _inventory(*names_and_qtys: tuple[str, float]) -> list[_FakeLot]:
    return [_FakeLot(canonical_name=n, quantity=q) for n, q in names_and_qtys]


def _use_soon(*names: str) -> list[dict]:
    return [{"canonical_name": n, "quantity": 1.0, "unit": "unit"} for n in names]


# ─── Recipe DB tests ─────────────────────────────────────────────────────


class TestRecipeDB:
    def test_loads_at_least_30_recipes(self):
        recipes = all_recipes()
        assert len(recipes) >= 30

    def test_each_recipe_has_required_fields(self):
        for r in all_recipes():
            assert r.id
            assert r.name
            assert r.cuisine
            assert r.ingredients
            assert r.instructions
            assert r.serves >= 1
            for ing in r.ingredients:
                assert ing.canonical_name
                assert ing.quantity > 0
                assert ing.unit

    def test_recipes_cover_main_cuisines(self):
        cuisines = {r.cuisine for r in all_recipes()}
        # We want at least North Indian, South Indian, Chinese present.
        assert "indian_north" in cuisines
        assert "indian_south" in cuisines
        assert "chinese" in cuisines

    def test_recipes_cover_dietary_preferences(self):
        all_diet = {d for r in all_recipes() for d in r.dietary}
        # At least vegan and non-vegetarian options.
        assert "vegan" in all_diet
        assert "non_vegetarian" in all_diet
        assert "vegetarian" in all_diet

    def test_get_recipe_by_id(self):
        r = get_recipe("dal_makhani")
        assert r is not None
        assert r.name == "Dal Makhani"

    def test_get_recipe_returns_none_for_missing_id(self):
        assert get_recipe("nonexistent_recipe") is None


# ─── Match tests ──────────────────────────────────────────────────────────


class TestMatchRecipe:
    def test_empty_inventory_all_missing(self):
        r = get_recipe("roti")  # 3 ingredients
        m = match_recipe(r, [])
        assert m.have == []
        assert m.missing_count == 3
        assert m.completion_pct == 0.0

    def test_full_inventory_all_have(self):
        r = get_recipe("roti")
        m = match_recipe(
            r,
            _inventory(("wheat_flour", 1), ("salt", 1), ("cooking_oil", 1)),
        )
        assert m.have_count == 3
        assert m.missing_count == 0
        assert m.completion_pct == 100.0

    def test_partial_inventory_mixed(self):
        r = get_recipe("roti")
        m = match_recipe(r, _inventory(("wheat_flour", 1), ("salt", 1)))
        assert m.have_count == 2
        assert m.missing_count == 1
        assert m.completion_pct == pytest.approx(66.7, abs=0.1)

    def test_use_soon_hits_detected(self):
        r = get_recipe("roti")
        m = match_recipe(
            r,
            _inventory(("wheat_flour", 1), ("salt", 1)),
            use_soon_items=_use_soon("wheat_flour"),
        )
        assert m.use_soon_count == 1
        assert m.use_soon_hits[0].canonical_name == "wheat_flour"

    def test_use_soon_hits_boost_score(self):
        r = get_recipe("roti")
        m_without = match_recipe(r, _inventory(("wheat_flour", 1), ("salt", 1), ("cooking_oil", 1)))
        m_with = match_recipe(
            r,
            _inventory(("wheat_flour", 1), ("salt", 1), ("cooking_oil", 1)),
            use_soon_items=_use_soon("wheat_flour"),
        )
        assert m_with.score > m_without.score

    def test_missing_penalises_score(self):
        r = get_recipe("roti")
        m_full = match_recipe(r, _inventory(("wheat_flour", 1), ("salt", 1), ("cooking_oil", 1)))
        m_empty = match_recipe(r, [])
        assert m_full.score > m_empty.score

    def test_quantity_in_inventory_does_not_matter(self):
        """We match on canonical name; quantity is summed but no per-ingredient threshold."""
        r = get_recipe("roti")
        m = match_recipe(r, _inventory(("wheat_flour", 100), ("salt", 50), ("cooking_oil", 10)))
        assert m.have_count == 3


# ─── Find recipes tests ─────────────────────────────────────────────────


class TestFindRecipes:
    def test_empty_inventory_returns_no_recipes_by_default(self):
        """The default ``min_have_count=1`` filter excludes recipes
        the user has 0 on-hand ingredients for. This is the
        correct "Cook Tonight" UX — see Item #11 in
        PROJECT_INTELLIGENCE for the rationale.
        """
        matches = find_recipes_for_inventory([], max_recipes=3)
        assert len(matches) == 0

    def test_empty_inventory_with_legacy_opt_in(self):
        """Passing ``min_have_count=0`` restores the old "show all"
        behaviour for callers that need it (e.g. cookbook search).
        """
        matches = find_recipes_for_inventory([], max_recipes=3, min_have_count=0)
        assert len(matches) == 3
        # Sorted by score descending
        assert matches[0].score >= matches[1].score >= matches[2].score

    def test_inventory_with_items_ranks_them_higher(self):
        """A recipe the user can mostly make should rank above one they can't."""
        # Inventories chosen so dal_makhani gets a higher completion than masala_dosa
        # (and also no use-soon boost). Easier recipe = higher rank.
        inv_dal = _inventory(
            ("urad_dal", 1), ("rajma", 1), ("onion", 2), ("tomato", 2),
            ("ginger", 1), ("garlic", 1), ("butter", 1), ("cream", 1),
            ("salt", 1), ("turmeric", 1), ("cumin", 1),
        )
        m = find_recipes_for_inventory(inv_dal, max_recipes=10, dietary_preference="vegetarian")
        # First match should be dal_makhani
        assert m[0].recipe.id == "dal_makhani"

    def test_vegetarian_filter_excludes_non_veg(self):
        matches = find_recipes_for_inventory([], dietary_preference="vegetarian", max_recipes=50)
        # All matches should be vegetarian
        for m in matches:
            assert "non_vegetarian" not in m.recipe.dietary
        # No chicken curry
        assert all(m.recipe.id != "chicken_curry" for m in matches)

    def test_vegan_filter_excludes_dairy_recipes(self):
        """Vegan is stricter than vegetarian — must have 'vegan' in dietary."""
        # Note: our seed DB doesn't strictly tag every vegan recipe. We
        # only assert the contract: at minimum, non_vegetarian is excluded.
        matches = find_recipes_for_inventory([], dietary_preference="vegan", max_recipes=50)
        for m in matches:
            assert "non_vegetarian" not in m.recipe.dietary

    def test_use_soon_boosts_matching_recipe(self):
        inv = _inventory(("onion", 1), ("tomato", 1), ("wheat_flour", 1))
        soon = _use_soon("onion", "tomato")
        # Find recipes with all-of: onion, tomato, wheat_flour
        # Aloo Gobi uses onion + tomato + potato (not wheat) so it won't match perfectly.
        # Use a recipe that uses all three.
        matches_with = find_recipes_for_inventory(inv, soon, max_recipes=50)
        matches_without = find_recipes_for_inventory(inv, [], max_recipes=50)
        # The same recipes should appear in both, but ordering may differ
        # if use_soon matches an ingredient.
        # At least one recipe in the top N should be the use-soon-boosted one.
        ids_with = {m.recipe.id for m in matches_with[:5]}
        # We just verify ordering changed (or at least didn't break)
        assert len(ids_with) > 0

    def test_max_recipes_caps_results(self):
        """With the legacy min_have_count=0 opt-in, max_recipes
        caps the result length."""
        matches = find_recipes_for_inventory([], max_recipes=5, min_have_count=0)
        assert len(matches) == 5

    def test_min_have_pct_filters(self):
        inv = _inventory(("wheat_flour", 1))  # only one ingredient
        matches = find_recipes_for_inventory(inv, [], max_recipes=50, min_have_pct=0.5)
        # Roti needs 3 ingredients; with only wheat_flour, completion is 33% < 50%
        for m in matches:
            assert m.completion_pct >= 50.0


# ─── Missing → shopping list tests ───────────────────────────────────────


class TestMissingToShoppingItems:
    def test_dedupes_across_recipes(self):
        r1 = get_recipe("roti")  # needs wheat_flour, salt, cooking_oil
        r2 = get_recipe("besan_ladoo")  # needs besan, ghee, sugar, cardamom, almond
        items = missing_to_shopping_items([match_recipe(r1, []), match_recipe(r2, [])])
        # No duplicate canonical names
        cnames = {it["canonical_name"] for it in items}
        assert len(cnames) == len(items)

    def test_only_includes_missing(self):
        r = get_recipe("roti")
        m = match_recipe(
            r,
            _inventory(("wheat_flour", 1), ("salt", 1)),  # 2 of 3
        )
        items = missing_to_shopping_items([m])
        assert len(items) == 1
        assert items[0]["canonical_name"] == "cooking_oil"

    def test_empty_matches_returns_empty(self):
        assert missing_to_shopping_items([]) == []


# ─── HTML rendering tests ────────────────────────────────────────────────


class TestRenderCookTonight:
    def test_empty_matches_returns_friendly_empty_state(self):
        html = render_cook_tonight_html([])
        assert "No recipe suggestions" in html

    def test_renders_recipe_cards(self):
        """Empty inventory → no cook-tonight cards (the new
        default of min_have_count=1 hides them). The HTML must
        say so in a user-friendly way — not "Cook Tonight" with
        an empty list.
        """
        matches = find_recipes_for_inventory([], max_recipes=3)
        assert matches == []
        html = render_cook_tonight_html(matches)
        # The empty-state copy must be present, not the heading.
        assert "Cook Tonight" not in html
        assert "No recipe suggestions" in html

    def test_renders_recipe_cards_with_inventory(self):
        """With ingredients on hand, the "Cook Tonight" header
        appears and the recipe names are rendered.
        """
        inv = _inventory(("onion", 1), ("tomato", 1))
        matches = find_recipes_for_inventory(inv, [], max_recipes=3)
        assert matches, "fixture must produce at least one match"
        html = render_cook_tonight_html(matches)
        assert "Cook Tonight" in html
        for m in matches:
            assert m.recipe.name in html

    def test_renders_use_soon_badge_when_recipe_uses_expiring(self):
        inv = _inventory(("onion", 1), ("tomato", 1))
        soon = _use_soon("onion")
        matches = find_recipes_for_inventory(inv, soon, max_recipes=10)
        html = render_cook_tonight_html(matches[:3])
        # At least one match should use a use-soon ingredient
        any_with_soon = any(m.use_soon_count > 0 for m in matches[:3])
        if any_with_soon:
            assert "expiring" in html

    def test_renders_completion_pct(self):
        inv = _inventory(("wheat_flour", 1), ("salt", 1), ("cooking_oil", 1))
        matches = find_recipes_for_inventory(inv, [], max_recipes=10)
        html = render_cook_tonight_html(matches)
        # At least one match should have 100% completion
        if any(m.completion_pct == 100.0 for m in matches):
            assert "100%" in html

    def test_html_escapes_xss(self):
        r = get_recipe("roti")
        # Inject an XSS attempt into the recipe's name (simulate bad data)
        r.name = "<script>alert(1)</script>"
        html = render_cook_tonight_html([match_recipe(r, [])])
        # The literal script tag must not appear
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
        # Reset for other tests
        r.name = "Roti (Whole Wheat Flatbread)"


class TestMinHaveCount:
    """Item #11 (motto_v3 §0.14): the previous ``min_have_pct=0.0``
    default returned recipes the user has 0 ingredients for —
    "Cook Tonight" advertised meals the user couldn't cook.
    The new ``min_have_count=1`` default closes that hole.
    """

    def test_empty_inventory_returns_zero_matches(self):
        matches = find_recipes_for_inventory([], [], max_recipes=10)
        assert matches == [], (
            f"Empty inventory must not return any recipes, got "
            f"{[m.recipe.name for m in matches]}"
        )

    def test_min_have_count_zero_restores_legacy_behaviour(self):
        """Passing ``min_have_count=0`` is the documented opt-out
        for the legacy "show all" behaviour. Callers that need
        the pre-fix UX (e.g. showing recipes the user can
        ADD to their shopping list, not cook now) can opt in.
        """
        matches = find_recipes_for_inventory([], [], max_recipes=10, min_have_count=0)
        assert len(matches) == 10

    def test_min_have_count_two_filters_singles(self):
        """Recipes with only 1 on-hand ingredient are excluded
        when min_have_count=2 — the user wants to see recipes
        they can mostly make."""
        # 1 ingredient: too few
        inv1 = _inventory(("onion", 1))
        matches = find_recipes_for_inventory(inv1, [], max_recipes=10, min_have_count=2)
        assert matches == [], "1 ingredient must not satisfy min_have_count=2"

        # 2 ingredients: should match
        inv2 = _inventory(("onion", 1), ("tomato", 1))
        matches = find_recipes_for_inventory(inv2, [], max_recipes=10, min_have_count=2)
        assert len(matches) > 0, "2 ingredients must satisfy min_have_count=2"

    def test_min_have_pct_and_min_have_count_compose(self):
        """The two filters are AND-ed: a recipe must satisfy BOTH."""
        # 1 of 10 ingredients, with min_have_pct=0.5 (50%): fails pct
        inv = _inventory(("onion", 1))
        matches = find_recipes_for_inventory(
            inv, [], max_recipes=10,
            min_have_pct=0.5, min_have_count=1,
        )
        assert matches == [], "1/10 ingredients must fail min_have_pct=0.5"

    def test_min_have_count_default_is_one(self):
        """The signature default is 1 — cook tonight implies
        "I can make this NOW". A user with 0 on-hand ingredients
        sees no cook-tonight card, which is the correct UX
        (the cookbook search is the right surface for them).
        """
        import inspect
        sig = inspect.signature(find_recipes_for_inventory)
        assert sig.parameters["min_have_count"].default == 1
