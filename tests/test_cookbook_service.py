"""Tests for shopstack.services.cookbook (Phase 5 #20 cookbook browser)."""
from __future__ import annotations

import pytest

from shopstack.services.cookbook import (
    CookbookFilter,
    browse_recipes,
    filter_recipes,
    list_cuisines,
    parse_filter,
    render_cookbook_card_html,
    render_cookbook_detail_html,
    render_cookbook_grid_html,
    shop_missing,
)
from shopstack.services.recipes import (
    Recipe,
    RecipeIngredient,
    all_recipes,
    get_recipe,
    match_recipe,
)


# ── Filter parsing ──────────────────────────────────────────────────


def test_parse_filter_normalizes_dietary_all_to_none():
    f = parse_filter(dietary="all", cuisine="all")
    assert f.dietary is None
    assert f.cuisine is None


def test_parse_filter_accepts_string_quick_only():
    f = parse_filter(quick_only="true")
    assert f.quick_only is True
    f2 = parse_filter(quick_only="false")
    assert f2.quick_only is False
    f3 = parse_filter(quick_only="yes")
    assert f3.quick_only is True


def test_parse_filter_lowercases_search():
    f = parse_filter(search="DAL")
    assert f.search == "dal"


def test_parse_filter_defaults():
    f = parse_filter()
    assert f.dietary is None
    assert f.cuisine is None
    assert f.quick_only is False
    assert f.search == ""


# ── Recipe filter ──────────────────────────────────────────────────


def test_filter_recipes_no_filter_returns_all():
    f = CookbookFilter()
    assert len(filter_recipes(f)) == len(all_recipes())


def test_filter_recipes_by_vegetarian_excludes_non_veg():
    f = CookbookFilter(dietary="vegetarian")
    results = filter_recipes(f)
    # All results should have "vegetarian" in their dietary list
    for r in results:
        assert "vegetarian" in r.dietary


def test_filter_recipes_by_cuisine():
    cuisines = list_cuisines()
    assert cuisines, "recipe DB should have at least one cuisine"
    chosen = cuisines[0]
    f = CookbookFilter(cuisine=chosen)
    results = filter_recipes(f)
    for r in results:
        assert r.cuisine == chosen


def test_filter_recipes_quick_only():
    f = CookbookFilter(quick_only=True)
    for r in filter_recipes(f):
        assert r.prep_minutes + r.cook_minutes < 30


def test_filter_recipes_search_substring():
    # Search "dal" should match at least one recipe (e.g. "Dal Makhani")
    f = CookbookFilter(search="dal")
    results = filter_recipes(f)
    assert any("dal" in r.name.lower() for r in results)


def test_filter_recipes_combined():
    f = CookbookFilter(dietary="vegetarian", quick_only=True, search="paneer")
    results = filter_recipes(f)
    for r in results:
        assert "vegetarian" in r.dietary
        assert r.prep_minutes + r.cook_minutes < 30
        assert "paneer" in (r.name + " " + " ".join(r.tags)).lower()


def test_list_cuisines_sorted_unique():
    cuisines = list_cuisines()
    assert len(cuisines) == len(set(cuisines))
    assert cuisines == sorted(cuisines)
    assert all(isinstance(c, str) for c in cuisines)


# ── Inventory-aware browse ────────────────────────────────────────


class _Lot:
    def __init__(self, canonical_name: str, quantity: float = 1.0):
        self.canonical_name = canonical_name
        self.quantity = quantity


def test_browse_recipes_sorts_by_completion_desc():
    inventory = [_Lot("onion"), _Lot("tomato"), _Lot("garlic"),
                 _Lot("ginger"), _Lot("cooking_oil"), _Lot("turmeric"),
                 _Lot("cumin"), _Lot("salt")]
    f = CookbookFilter()
    matches = browse_recipes(inventory, f)
    assert matches, "expected non-empty matches"
    # Should be sorted descending by completion_pct
    for a, b in zip(matches, matches[1:]):
        assert a.completion_pct >= b.completion_pct
    # Top result should be well-matched (>= 50% ready)
    assert matches[0].completion_pct >= 50, (
        f"expected top match >= 50% ready, got {matches[0].completion_pct}"
    )


def test_browse_recipes_household_dietary_strict():
    inventory = []
    f = CookbookFilter()  # No filter
    # Even with permissive filter, vegetarian household must not see meat recipes
    matches = browse_recipes(inventory, f, dietary_preference="vegetarian")
    for m in matches:
        assert "vegetarian" in m.recipe.dietary


def test_browse_recipes_with_search():
    f = CookbookFilter(search="paneer")
    matches = browse_recipes([], f)
    assert all("paneer" in (m.recipe.name + " ".join(m.recipe.tags)).lower()
               for m in matches)


# ── Card rendering ──────────────────────────────────────────────


def test_render_cookbook_card_html_basic():
    inv = [_Lot("onion", 1), _Lot("tomato", 1)]
    f = CookbookFilter()
    matches = browse_recipes(inv, f)
    assert matches
    html = render_cookbook_card_html(matches[0])
    assert "cb-card" in html
    assert matches[0].recipe.name in html
    # XSS safety: no unescaped tags from recipe names
    assert "<script" not in html.lower()


def test_render_cookbook_card_html_uses_locale():
    inv = [_Lot("onion", 1)]
    f = CookbookFilter()
    matches = browse_recipes(inv, f)
    html_en = render_cookbook_card_html(matches[0], locale="en")
    html_hi = render_cookbook_card_html(matches[0], locale="hi")
    # Should be different
    assert html_en != html_hi
    # Hindi should include a Devanagari token
    assert any(0x0900 <= ord(c) <= 0x097F for c in html_hi)


def test_render_cookbook_card_html_color_coding():
    # 100% complete → green
    recipe = Recipe(
        id="test_full", name="Test Full",
        cuisine="test", dietary=["vegetarian"],
        prep_minutes=5, cook_minutes=10, serves=2,
        ingredients=[
            RecipeIngredient(canonical_name="onion", quantity=1, unit="unit"),
        ],
    )
    m = match_recipe(recipe, [_Lot("onion", 5)])
    html = render_cookbook_card_html(m)
    assert "var(--green)" in html


def test_render_cookbook_grid_html_empty():
    html = render_cookbook_grid_html([])
    assert "No recipes" in html or "no_recipes" in html.lower() or "कुकबुक" in html


def test_render_cookbook_grid_html_multiple_cards():
    inv = [_Lot("onion", 1), _Lot("tomato", 1), _Lot("ginger", 1),
           _Lot("garlic", 1), _Lot("cooking_oil", 1), (_Lot("salt", 1))]
    f = CookbookFilter()
    matches = browse_recipes(inv, f)
    html = render_cookbook_grid_html(matches)
    # Use a more unique marker — "cb-card-head" only appears once per card
    assert html.count("cb-card-head") == len(matches)


# ── Detail rendering ────────────────────────────────────────────


def test_render_cookbook_detail_html_contains_ingredients_and_steps():
    recipe = get_recipe("dal_makhani") or all_recipes()[0]
    html = render_cookbook_detail_html(recipe, locale="en")
    assert recipe.name in html
    # Instructions
    assert "cb-steps" in html
    # Ingredients
    assert "cb-ings" in html


def test_render_cookbook_detail_html_marks_have_vs_missing():
    recipe = get_recipe("dal_makhani") or all_recipes()[0]
    inv = [  # Empty inventory → everything is missing
    ]
    m = match_recipe(recipe, inv)
    html = render_cookbook_detail_html(recipe, m, locale="en")
    # All ingredients should be marked missing
    assert html.count("cb-ing-miss") == len(recipe.ingredients)


def test_render_cookbook_detail_html_marks_have_when_present():
    recipe = get_recipe("dal_makhani") or all_recipes()[0]
    # Provide the first ingredient
    first_ing = recipe.ingredients[0].canonical_name
    inv = [_Lot(first_ing, 5)]
    m = match_recipe(recipe, inv)
    html = render_cookbook_detail_html(recipe, m, locale="en")
    # At least one "have" marker
    assert "cb-ing-have" in html


# ── Shopping-list wire-up ───────────────────────────────────────


class _FakeDB:
    """Minimal DB stub for shop_missing tests."""

    def __init__(self):
        self.lists = [{"list_id": "list-1", "name": "Main"}]
        self.added_items: list[dict] = []

    def get_shopping_lists(self, user_id=None):
        return self.lists

    def add_shopping_list_item(self, *, list_id, canonical_name, quantity, unit):
        self.added_items.append({
            "list_id": list_id,
            "canonical_name": canonical_name,
            "quantity": quantity,
            "unit": unit,
        })
        return {"ok": True}


def test_shop_missing_adds_to_first_list():
    db = _FakeDB()
    recipe = get_recipe("dal_makhani") or all_recipes()[0]
    inv = [_Lot(recipe.ingredients[0].canonical_name, 5)]
    result = shop_missing(db, recipe, inv, user_id="hh-1")
    assert result["added"] is True
    assert result["count"] == len(recipe.ingredients) - 1
    assert len(db.added_items) == result["count"]


def test_shop_missing_no_missing_returns_already_have():
    db = _FakeDB()
    recipe = Recipe(
        id="t", name="T", cuisine="t", dietary=["vegetarian"],
        ingredients=[RecipeIngredient(canonical_name="onion", quantity=1, unit="unit")],
    )
    inv = [_Lot("onion", 5)]
    result = shop_missing(db, recipe, inv, user_id="hh-1")
    assert result["added"] is False
    assert result["count"] == 0
    assert db.added_items == []


def test_shop_missing_no_list_returns_error():
    db = _FakeDB()
    db.lists = []
    recipe = all_recipes()[0]
    inv = []
    result = shop_missing(db, recipe, inv, user_id="hh-1")
    assert result["added"] is False
    assert "No shopping list" in result["reason"]


def test_shop_missing_uses_provided_list_id():
    db = _FakeDB()
    recipe = all_recipes()[0]
    inv = []
    result = shop_missing(db, recipe, inv, user_id="hh-1", list_id="custom-list")
    assert result["added"] is True
    assert all(it["list_id"] == "custom-list" for it in db.added_items)


def test_shop_missing_db_error_does_not_raise():
    class _BadDB:
        def get_shopping_lists(self, user_id=None):
            raise RuntimeError("db is down")

    recipe = all_recipes()[0]
    inv = []
    result = shop_missing(_BadDB(), recipe, inv, user_id="hh-1")
    assert result["added"] is False
    assert "Failed" in result["reason"] or "db" in result["reason"].lower()


# ── XSS safety ────────────────────────────────────────────────


def test_cookbook_renderers_escape_recipe_names():
    # If a recipe name contained a script tag, it must be escaped
    recipe = Recipe(
        id="xss", name="<script>alert(1)</script>",
        cuisine="t", dietary=["vegetarian"],
        ingredients=[RecipeIngredient(canonical_name="onion", quantity=1, unit="unit")],
    )
    inv = [_Lot("onion", 1)]
    m = match_recipe(recipe, inv)
    html = render_cookbook_card_html(m)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
