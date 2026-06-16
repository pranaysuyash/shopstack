"""Tests for the meal planning service + renderer (Pass 21).

**Why this exists (motto_v3 §0.14 product reality):**

The user needs a weekly meal plan based on what they have.
This module tests the smallest first-principles
implementation:
  - ``build_weekly_meal_plan`` picks a recipe per day,
    avoiding repeats.
  - ``DayPlan`` carries the structured data (recipe,
    ingredients, confidence, rationale).
  - The score-based confidence mapping (high / medium / low).
  - The "uses up your X" rationale when a use-soon item
    is matched.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from shopstack.services.meal_planning import (
    DayPlan,
    build_weekly_meal_plan,
    summarize_meal_plan,
)
from shopstack.services.recipes import (
    Recipe,
    RecipeIngredient,
    RecipeMatch,
)
from shopstack.ui.renderers.meal_plan import (
    render_meal_plan_html,
    render_meal_plan_text,
)


# ── Test helpers ────────────────────────────────────────────────


def _make_recipe(
    *,
    id: str = "r1",
    name: str = "Test Recipe",
    cuisine: str = "indian",
    cook_minutes: int = 20,
    ingredients: list[str] | None = None,
) -> Recipe:
    return Recipe(
        id=id,
        name=name,
        cuisine=cuisine,
        cook_minutes=cook_minutes,
        ingredients=[
            RecipeIngredient(canonical_name=name, quantity=1.0, unit="unit")
            for name in (ingredients or ["flour", "water", "salt"])
        ],
        instructions=["mix", "cook"],
    )


def _make_match(
    recipe: Recipe,
    *,
    have: list[str] | None = None,
    missing: list[str] | None = None,
    use_soon: list[str] | None = None,
    score: float = 5.0,
) -> RecipeMatch:
    return RecipeMatch(
        recipe=recipe,
        have=[
            RecipeIngredient(canonical_name=n, quantity=1.0, unit="unit")
            for n in (have or [])
        ],
        missing=[
            RecipeIngredient(canonical_name=n, quantity=1.0, unit="unit")
            for n in (missing or [])
        ],
        use_soon_hits=[
            RecipeIngredient(canonical_name=n, quantity=1.0, unit="unit")
            for n in (use_soon or [])
        ],
        score=score,
    )


# ── DayPlan schema ──────────────────────────────────────────────


class TestDayPlan:
    def test_day_plan_serializes_to_dict(self):
        d = DayPlan(
            date="2026-06-16",
            recipe_name="Rasam",
            recipe_id="rasam",
            cuisine="indian_south",
            cook_minutes=20,
            score=7.8,
            ingredients_used=["tomato", "coriander"],
            ingredients_missing=["tamarind"],
            confidence="high",
            rationale="Uses up your tomato before it spoils.",
        )
        # Pydantic v2: model_dump returns a dict.
        d_dict = d.model_dump(mode="json")
        assert d_dict["date"] == "2026-06-16"
        assert d_dict["recipe_name"] == "Rasam"
        assert d_dict["confidence"] == "high"

    def test_day_plan_with_no_recipe(self):
        """Empty day: all recipe fields are None or empty."""
        d = DayPlan(date="2026-06-16", rationale="No recipes match.")
        assert d.recipe_name is None
        assert d.ingredients_used == []
        assert d.ingredients_missing == []


# ── build_weekly_meal_plan ──────────────────────────────────────


class TestBuildWeeklyMealPlanEmpty:
    def test_empty_inventory_returns_empty_plan(self):
        """No pantry items → no recipe matches → empty plan days."""
        from shopstack.services.meal_planning import build_weekly_meal_plan

        plan = build_weekly_meal_plan(db=MagicMock(), 
            inventory=[], use_soon_items=[], days=7,
        )
        assert len(plan) == 7
        for d in plan:
            assert d.recipe_name is None

    def test_inventory_with_no_matching_recipes_returns_empty_plan(self):
        """Pantry items that don't match any recipe → empty plan."""
        from shopstack.services.meal_planning import build_weekly_meal_plan

        fake_lot = MagicMock(canonical_name="unicorn_meat")
        plan = build_weekly_meal_plan(db=MagicMock(), 
            inventory=[fake_lot], use_soon_items=[], days=3,
        )
        assert all(d.recipe_name is None for d in plan)


class TestBuildWeeklyMealPlanAssignment:
    def test_plan_assigns_recipe_per_day(self):
        """When candidates exist, each day gets a recipe."""
        from shopstack.services.meal_planning import build_weekly_meal_plan

        # Mock the recipes + match.
        r1 = _make_recipe(id="r1", name="Rasam", cook_minutes=20)
        r2 = _make_recipe(id="r2", name="Tomato Rice", cook_minutes=20)
        r3 = _make_recipe(id="r3", name="Biryani", cook_minutes=45)
        # Patch the internal find_recipes_for_inventory.
        import shopstack.services.meal_planning as mp
        original_find = mp.find_recipes_for_inventory
        try:
            mp.find_recipes_for_inventory = lambda **kw: [
                _make_match(r3, score=8.0),
                _make_match(r1, score=7.5),
                _make_match(r2, score=6.0),
            ]
            plan = build_weekly_meal_plan(db=MagicMock(), 
                inventory=[], use_soon_items=[], days=3,
            )
            assert len(plan) == 3
            assert plan[0].recipe_id == "r3"  # highest score first
            assert plan[1].recipe_id == "r1"
            assert plan[2].recipe_id == "r2"
        finally:
            mp.find_recipes_for_inventory = original_find

    def test_plan_avoids_repeating_recipes(self):
        """No recipe appears twice in the plan."""
        from shopstack.services.meal_planning import build_weekly_meal_plan

        # Only 2 recipes, 5 days → first 2 days get recipes, rest empty.
        r1 = _make_recipe(id="r1", name="R1")
        r2 = _make_recipe(id="r2", name="R2")
        import shopstack.services.meal_planning as mp
        original_find = mp.find_recipes_for_inventory
        try:
            mp.find_recipes_for_inventory = lambda **kw: [
                _make_match(r1, score=7.0),
                _make_match(r2, score=5.0),
            ]
            plan = build_weekly_meal_plan(db=MagicMock(), 
                inventory=[], use_soon_items=[], days=5,
            )
            recipe_ids = [d.recipe_id for d in plan if d.recipe_id]
            # No recipe appears twice.
            assert len(recipe_ids) == len(set(recipe_ids))
            # First 2 days have recipes, last 3 are empty.
            assert sum(1 for d in plan if d.recipe_name) == 2
        finally:
            mp.find_recipes_for_inventory = original_find

    def test_plan_with_more_recipes_than_days(self):
        """When there are more recipes than days, only the top N are used."""
        from shopstack.services.meal_planning import build_weekly_meal_plan

        recipes = [
            _make_recipe(id=f"r{i}", name=f"R{i}")
            for i in range(5)
        ]
        import shopstack.services.meal_planning as mp
        original_find = mp.find_recipes_for_inventory
        try:
            mp.find_recipes_for_inventory = lambda **kw: [
                _make_match(recipes[i], score=10.0 - i)
                for i in range(5)
            ]
            plan = build_weekly_meal_plan(db=MagicMock(), 
                inventory=[], use_soon_items=[], days=3,
            )
            # Only 3 of the 5 recipes are used.
            used_ids = [d.recipe_id for d in plan]
            assert len(used_ids) == 3
            assert set(used_ids) == {"r0", "r1", "r2"}
        finally:
            mp.find_recipes_for_inventory = original_find

    def test_plan_with_fewer_recipes_than_days(self):
        """When there are fewer recipes than days, remaining days are empty."""
        from shopstack.services.meal_planning import build_weekly_meal_plan

        r1 = _make_recipe(id="r1", name="R1")
        import shopstack.services.meal_planning as mp
        original_find = mp.find_recipes_for_inventory
        try:
            mp.find_recipes_for_inventory = lambda **kw: [
                _make_match(r1, score=5.0),
            ]
            plan = build_weekly_meal_plan(db=MagicMock(), 
                inventory=[], use_soon_items=[], days=4,
            )
            # 1 day has a recipe, 3 are empty.
            assert sum(1 for d in plan if d.recipe_name) == 1
            assert plan[0].recipe_id == "r1"
        finally:
            mp.find_recipes_for_inventory = original_find

    def test_custom_start_date(self):
        """The plan starts at the specified date."""
        from shopstack.services.meal_planning import build_weekly_meal_plan

        start = date(2026, 7, 1)
        plan = build_weekly_meal_plan(db=MagicMock(), 
            inventory=[], use_soon_items=[], days=3, start_date=start,
        )
        assert plan[0].date == "2026-07-01"
        assert plan[1].date == "2026-07-02"
        assert plan[2].date == "2026-07-03"

    def test_default_start_date_is_today(self):
        """When no start_date is given, the plan starts today."""
        from shopstack.services.meal_planning import build_weekly_meal_plan

        plan = build_weekly_meal_plan(db=MagicMock(), 
            inventory=[], use_soon_items=[], days=1,
        )
        assert plan[0].date == date.today().isoformat()


# ── Confidence mapping ─────────────────────────────────────────


class TestConfidenceMapping:
    def test_high_confidence_for_score_5_or_above(self):
        from shopstack.services.meal_planning import _to_day_plan

        r = _make_recipe()
        m = _make_match(r, score=7.0)
        d = _to_day_plan(date.today(), m)
        assert d.confidence == "high"

    def test_medium_confidence_for_score_1_to_5(self):
        from shopstack.services.meal_planning import _to_day_plan

        r = _make_recipe()
        m = _make_match(r, score=3.0)
        d = _to_day_plan(date.today(), m)
        assert d.confidence == "medium"

    def test_low_confidence_for_score_below_1(self):
        from shopstack.services.meal_planning import _to_day_plan

        r = _make_recipe()
        m = _make_match(r, score=0.5)
        d = _to_day_plan(date.today(), m)
        assert d.confidence == "low"


# ── Rationale generation ────────────────────────────────────────


class TestRationale:
    def test_rationale_mentions_use_soon_ingredient(self):
        from shopstack.services.meal_planning import _to_day_plan

        r = _make_recipe()
        m = _make_match(
            r, use_soon=["tomato", "coriander"],
        )
        d = _to_day_plan(date.today(), m)
        assert "Uses up" in d.rationale
        assert "tomato" in d.rationale
        assert "coriander" in d.rationale

    def test_rationale_says_pantry_match_when_no_use_soon(self):
        from shopstack.services.meal_planning import _to_day_plan

        r = _make_recipe()
        m = _make_match(r, have=["rice", "onion"])
        d = _to_day_plan(date.today(), m)
        assert "pantry" in d.rationale.lower()
        assert "2 ingredients" in d.rationale

    def test_rationale_says_needs_items_when_nothing_matches(self):
        from shopstack.services.meal_planning import _to_day_plan

        r = _make_recipe()
        m = _make_match(r, missing=["specialty_ingredient"])
        d = _to_day_plan(date.today(), m)
        assert "store" in d.rationale.lower() or "buy" in d.rationale.lower()


# ── summarize_meal_plan ─────────────────────────────────────────


class TestSummarizeMealPlan:
    def test_empty_plan_summary(self):
        assert summarize_meal_plan([]) == "No meal plan available."

    def test_all_days_planned(self):
        plan = [
            DayPlan(date=f"2026-06-{16 + i}", recipe_name="R", confidence="high")
            for i in range(5)
        ]
        assert summarize_meal_plan(plan) == "5 days of meals planned."

    def test_mixed_plan_summary(self):
        plan = [
            DayPlan(date="2026-06-16", recipe_name="R", confidence="high"),
            DayPlan(date="2026-06-17", recipe_name=None, rationale="empty"),
        ]
        assert summarize_meal_plan(plan) == "1 days planned, 1 day empty."


# ── Renderer tests ─────────────────────────────────────────────


class TestRenderMealPlanHtml:
    def test_renders_meal_plan_section(self):
        plan = [
            DayPlan(date="2026-06-16", recipe_name="Rasam",
                    recipe_id="rasam", cuisine="indian_south",
                    cook_minutes=20, score=7.8,
                    ingredients_used=["tomato", "coriander"],
                    ingredients_missing=["tamarind"],
                    confidence="high",
                    rationale="Uses up your tomato before it spoils."),
        ]
        html = render_meal_plan_html(plan)
        assert html.startswith("<section class='meal-plan'")
        assert "Rasam" in html
        assert "2026-06-16" in html
        assert "high" in html
        assert "tomato" in html

    def test_renders_empty_day(self):
        plan = [DayPlan(date="2026-06-16",
                        rationale="No recipes match your pantry.")]
        html = render_meal_plan_html(plan)
        assert "day-empty" in html
        assert "No recipes match" in html

    def test_renderer_is_xss_safe(self):
        plan = [
            DayPlan(
                date="2026-06-16",
                recipe_name="<script>alert('xss')</script>",
                rationale="<img src=x onerror=alert(1)>",
                ingredients_used=["<script>"],
            ),
        ]
        html = render_meal_plan_html(plan)
        assert "<script>alert" not in html
        assert "&lt;script&gt;" in html

    def test_renderer_includes_ingredients_section(self):
        plan = [
            DayPlan(
                date="2026-06-16",
                recipe_name="Rasam",
                recipe_id="rasam",
                ingredients_used=["tomato", "coriander"],
                ingredients_missing=["tamarind"],
                confidence="high",
            ),
        ]
        html = render_meal_plan_html(plan)
        # The used + missing sections are in <details> elements.
        assert "2 on hand" in html
        assert "1 to buy" in html


class TestRenderMealPlanText:
    def test_text_output_is_multiline(self):
        plan = [
            DayPlan(date="2026-06-16", recipe_name="Rasam", confidence="high"),
        ]
        text = render_meal_plan_text(plan)
        assert "\n" in text
        assert "Rasam" in text
        assert "high" in text

    def test_text_output_includes_day_names(self):
        plan = [DayPlan(date="2026-06-16", recipe_name="Rasam")]
        text = render_meal_plan_text(plan)
        # 2026-06-16 is a Tuesday.
        assert "Tuesday" in text
