"""Meal planning service — "what should I cook this week?"

**Why this exists (motto_v3 §0 first-principles + §0.14 product reality):**

The user has a pantry, a cookbook, and a sense of what
they'd like to eat. The decision engine surfaces "Cook
tonight!" for one-off meals, and the recurring shopping
plan (Pass 19) surfaces "buy this every 3 days" for restocking.
Neither answers the **weekly planning** question: "what
should I cook THIS WEEK, based on what I have?"

This module is the smallest first-principles fix:

  1. ``build_weekly_meal_plan(db, user_id, start_date, days)``
     returns a list of ``DayPlan`` objects, one per day.
     Each day has a suggested recipe, the ingredients it
     uses, the ingredients still missing, and a confidence.

  2. The plan reuses the existing
     ``find_recipes_for_inventory`` to score recipes
     (use-soon match +5, have match +1, missing -2, time
     penalty -0.01/min). No new scoring algorithm.

  3. **No repeats** within the planning window: a recipe
     used on Monday won't be suggested again on Tuesday.
     This matches how humans actually plan meals.

  4. **Mode-portable** per motto_v3 §0: the same ``DayPlan``
     data flows through the CLI (``python -m shopstack.cli
     mealplan``), the HTTP endpoint (``GET /api/mealplan``),
     and the dashboard's Recipes tab. The renderer is an
     adapter; the concept is mode-agnostic.

**Why a Pydantic model (not a dataclass):** the plan is
serialized to JSON for the CLI / API. Pydantic gives us
that for free, plus a typed schema for IDE autocomplete.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field

from shopstack.services.recipes import (
    Recipe,
    RecipeMatch,
    all_recipes,
    find_recipes_for_inventory,
)

logger = logging.getLogger(__name__)


# ── Schema ────────────────────────────────────────────────────────


class DayPlan(BaseModel):
    """One day in a weekly meal plan.

    Attributes:
        date: The date of this day (ISO format).
        recipe_name: Display name of the suggested recipe
            (e.g. "Tomato Rice"). ``None`` if no recipe was
            suggested (empty pantry).
        recipe_id: Stable identifier for the recipe
            (links back to the recipe database). ``None``
            if no recipe was suggested.
        cuisine: Recipe cuisine tag ("indian" / "chinese" /
            etc.). ``None`` if no recipe.
        cook_minutes: Estimated cooking time. ``None`` if
            no recipe.
        score: The recipe's match score (from
            ``find_recipes_for_inventory``). Higher is
            better. ``None`` if no recipe.
        ingredients_used: Canonical names of pantry
            ingredients the recipe uses.
        ingredients_missing: Canonical names of ingredients
            the recipe needs but the household doesn't have.
        confidence: "low" / "medium" / "high" — derived from
            the score. Used by the renderer to colour the
            day card.
        rationale: One-line explanation of why this recipe
            was suggested (e.g. "Uses up your tomatoes before
            they spoil").
    """

    date: str
    recipe_name: str | None = None
    recipe_id: str | None = None
    cuisine: str | None = None
    cook_minutes: int | None = None
    score: float | None = None
    ingredients_used: list[str] = Field(default_factory=list)
    ingredients_missing: list[str] = Field(default_factory=list)
    confidence: str = "low"
    rationale: str = ""


# ── Pure service ────────────────────────────────────────────────


def build_weekly_meal_plan(
    db: Any,
    user_id: str = "",
    *,
    start_date: date | None = None,
    days: int = 7,
    inventory: list[Any] | None = None,
    use_soon_items: list[dict[str, Any]] | None = None,
) -> list[DayPlan]:
    """Build a ``days``-day meal plan starting at ``start_date``.

    Args:
        db: The ``Database`` instance.
        user_id: The active household.
        start_date: First day of the plan. Default: today.
        days: Number of days. Default 7.
        inventory: Pre-fetched inventory list. If ``None``,
            the service fetches it from ``db.get_inventory``.
        use_soon_items: Pre-fetched use-soon items. If
            ``None``, the service fetches it from
            ``db.get_inventory`` (and filters for items
            about to expire).

    Returns:
        A list of ``DayPlan`` objects, one per day. The
        plan is empty (all ``DayPlan``s have ``recipe_name=None``)
        if the pantry is empty.

    The planning algorithm:
      1. Get the candidate recipes (those that match the
         current inventory, ranked by score).
      2. For each day, pick the highest-scoring recipe
         that hasn't been used in the last ``days`` days.
      3. If no recipe matches for a day, the ``DayPlan`` has
         ``recipe_name=None`` (the user has nothing to cook).

    This is intentionally simple: no preferences, no
    weeknight-vs-weekend, no serving-size. The first-
    principles design is "suggest a recipe per day, avoid
    repeats, done". Refinements can be additive later
    (per ``motto_v3`` §0.13 scope discipline).
    """
    start = start_date or date.today()

    # Fetch inventory + use-soon if not provided. Best-effort:
    # if the DB doesn't have these methods (e.g. in a test
    # with a fake DB), the plan is empty.
    if inventory is None:
        try:
            inventory = db.get_inventory(user_id=user_id or "")
        except Exception:
            inventory = []
    if use_soon_items is None:
        try:
            inventory = inventory or db.get_inventory(user_id=user_id or "")
            use_soon_items = [
                {"canonical_name": lot.canonical_name}
                for lot in inventory
                if getattr(lot, "estimated_use_by_date", None)
                and lot.estimated_use_by_date
                and (lot.estimated_use_by_date - start).days <= 7
            ]
        except Exception:
            use_soon_items = []

    # Get ranked recipe candidates. If the pantry is empty,
    # this returns an empty list.
    try:
        candidates: list[RecipeMatch] = find_recipes_for_inventory(
            inventory=inventory or [],
            use_soon_items=use_soon_items,
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("find_recipes_for_inventory failed: %s", exc)
        candidates = []

    # Track which recipe_ids have been used in this plan.
    used: set[str] = set()
    plan: list[DayPlan] = []

    for offset in range(days):
        day = start + timedelta(days=offset)
        # Find the best candidate that hasn't been used yet.
        best: RecipeMatch | None = None
        for c in candidates:
            if c.recipe.id in used:
                continue
            if best is None or c.score > best.score:
                best = c
        if best is not None:
            used.add(best.recipe.id)
            plan.append(_to_day_plan(day, best))
        else:
            # No candidate available — empty day.
            plan.append(DayPlan(
                date=day.isoformat(),
                rationale=(
                    "No recipes match your current pantry. "
                    "Shop or add inventory to plan meals."
                ),
            ))

    return plan


def _to_day_plan(day: date, match: RecipeMatch) -> DayPlan:
    """Convert a RecipeMatch + day into a DayPlan.

    The score is mapped to a confidence label:
      - score >= 5  → "high"   (use-soon match is dominant)
      - score >= 1  → "medium" (have match, few missing)
      - score <  1  → "low"    (mostly missing)
    """
    confidence = "low"
    if match.score >= 5:
        confidence = "high"
    elif match.score >= 1:
        confidence = "medium"

    # The rationale uses the first matching ingredient as
    # the hook (the use-soon item, if any).
    rationale = _build_rationale(match)

    # The used/missing lists are RecipeIngredient objects
    # on the RecipeMatch; flatten to canonical name strings
    # for the Pydantic schema.
    used_names = [ing.canonical_name for ing in match.have]
    missing_names = [ing.canonical_name for ing in match.missing]

    return DayPlan(
        date=day.isoformat(),
        recipe_name=match.recipe.name,
        recipe_id=match.recipe.id,
        cuisine=match.recipe.cuisine,
        cook_minutes=match.recipe.cook_minutes,
        score=match.score,
        ingredients_used=used_names,
        ingredients_missing=missing_names,
        confidence=confidence,
        rationale=rationale,
    )


def _build_rationale(match: RecipeMatch) -> str:
    """One-line explanation of why this recipe was suggested.

    Priority:
      1. If the recipe uses a use-soon ingredient, say so
         ("Uses up your tomatoes before they spoil").
      2. Otherwise, say it matches the pantry ("Matches
         your pantry").
      3. Otherwise, say it needs X items ("Needs a few
         items from the store").
    """
    if match.use_soon_hits:
        names = [ing.canonical_name for ing in match.use_soon_hits[:2]]
        return (
            f"Uses up your {', '.join(names)} before it spoils."
        )
    if match.have:
        return f"Matches your pantry ({len(match.have)} ingredients on hand)."
    return f"Needs a few items from the store ({len(match.missing)} to buy)."


# ── Convenience: summary for the dashboard ───────────────────────


def summarize_meal_plan(plan: list[DayPlan]) -> str:
    """One-line summary: '5 days planned, 2 days empty.'"""
    if not plan:
        return "No meal plan available."
    planned = sum(1 for d in plan if d.recipe_name is not None)
    empty = len(plan) - planned
    if empty == 0:
        return f"{planned} days of meals planned."
    return f"{planned} days planned, {empty} day{'s' if empty != 1 else ''} empty."
