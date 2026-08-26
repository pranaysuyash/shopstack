"""``/api/v1/intelligence/*`` — decision explain, recurring plan, meal plan.

**Why this exists (motto_v3 §0 first-principles):**

The legacy mounts in ``shopstack.services.decision_explain_mount``
attach routes directly to the FastAPI app via ``app.app.add_route``.
They work, but they are not versioned, not documented in OpenAPI,
and not reusable by the mobile app. This router ports them to the
``/api/v1/intelligence`` prefix with the standard FastAPI router
pattern.

**Three endpoints:**

1. ``GET /api/v1/intelligence/decision/{name}/explain`` — structured
   explanation of why the system made a decision for an item.
2. ``GET /api/v1/intelligence/recurring`` — items due in the user's
   shopping rhythm (recurring plan).
3. ``GET /api/v1/intelligence/mealplan`` — weekly meal plan based on
   pantry + cookbook.

**Pattern (per motto_v3 §0.15 three-layer rule):**

* HTTP boundary only.
* Delegates to the same service functions the legacy mounts use.
* Best-effort: sub-check failures return a partial payload with an
  ``error`` field rather than 5xx.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from shopstack.api.v1.deps import HouseholdContext, require_household
from shopstack.api.v1.schemas import (
    DecisionExplanationWire,
    MealPlanDayWire,
    MealPlanResponse,
    RecipeDetailResponse,
    RecipeIngredientWire,
    RecurringPlanItemWire,
    RecurringPlanResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get(
    "/decision/{name}/explain",
    response_model=DecisionExplanationWire,
    summary="Explain a decision for a specific item",
)
def decision_explain_endpoint(
    name: str,
    ctx: HouseholdContext = Depends(require_household),
) -> DecisionExplanationWire:
    """Return a structured explanation of why ShopStack decided
    to buy / skip / use-soon for ``name``.

    The explanation is composed from the decision engine's
    existing ``DecisionResult`` reasons and evidence — no new
    LLM call.

    Returns a partial payload with ``action=\"unknown\"`` and
    ``summary`` containing an error message when no decision
    is available for the item.
    """
    from shopstack.app_context import db, tools
    from shopstack.services.dashboard import build_dashboard_state
    from shopstack.services.explainability import (
        explain_decision as _explain,
    )
    from shopstack.services.explainability import (
        explanation_to_dict,
    )

    try:
        state = build_dashboard_state(db, tools.inventory, user_id=ctx.household_id)
        ds = state.decision_set
        all_decisions = (
            list(ds.buy) + list(ds.skip) + list(ds.use_soon)
            + list(ds.compare) + list(ds.substitute) + list(ds.wait)
        )
        matches = [d for d in all_decisions if d.canonical_name == name]
        if not matches:
            return DecisionExplanationWire(
                canonical_name=name,
                action="unknown",
                summary=f"No active decision for canonical_name={name!r}.",
                confidence=0.0,
                confidence_label="unknown",
            )
        matches.sort(key=lambda d: (-d.priority, -d.confidence))
        explanation = _explain(matches[0])
        raw = explanation_to_dict(explanation)
        return DecisionExplanationWire(**raw)
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.warning("decision_explain_endpoint failed for %s: %s", name, exc)
        return DecisionExplanationWire(
            canonical_name=name,
            action="error",
            summary=f"{type(exc).__name__}: {exc}",
            confidence=0.0,
            confidence_label="error",
        )


@router.get(
    "/recurring",
    response_model=RecurringPlanResponse,
    summary="Get items due in the user's shopping rhythm",
)
def recurring_plan(
    window: int = Query(3, ge=0, le=30, description="Days ahead to look"),
    ctx: HouseholdContext = Depends(require_household),
) -> RecurringPlanResponse:
    """Return items the user typically buys on a regular cadence
    that are due within ``window`` days.

    Uses ``detect_purchase_cadence`` to find purchase patterns and
    filters to items whose next expected buy date falls within the
    window. Results are ordered by imminence (most urgent first).
    """
    from shopstack.app_context import db
    from shopstack.services.recurring_shopping import (
        build_recurring_shopping_plan,
        summarize_plan,
    )

    try:
        plan = build_recurring_shopping_plan(
            db, user_id=ctx.household_id, window_days=window,
        )
        items = []
        for d in plan:
            items.append(RecurringPlanItemWire(
                canonical_name=d.canonical_name,
                display_name=d.display_name or d.canonical_name.replace("_", " ").title(),
                action=d.action,
                confidence=d.confidence,
                priority=d.priority,
                reasons=d.reasons,
                days_until_next=_extract_days_until_next(d.reasons),
                typical_interval_days=_extract_interval(d.reasons),
            ))
        return RecurringPlanResponse(
            window_days=window,
            summary=summarize_plan(plan),
            count=len(items),
            items=items,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.warning("recurring plan failed: %s", exc)
        return RecurringPlanResponse(
            window_days=window, summary=f"Error: {exc}", count=0,
        )


@router.get(
    "/mealplan",
    response_model=MealPlanResponse,
    summary="Get a weekly meal plan based on pantry + cookbook",
)
def meal_plan(
    days: int = Query(7, ge=1, le=28, description="Number of days to plan"),
    ctx: HouseholdContext = Depends(require_household),
) -> MealPlanResponse:
    """Return a meal plan for ``days`` days starting today.

    Suggests recipes based on the household's current inventory
    (matching available ingredients, prioritising use-soon items).
    Recipes are not repeated within the planning window.
    """
    from shopstack.app_context import db
    from shopstack.services.meal_planning import (
        build_weekly_meal_plan,
        summarize_meal_plan,
    )

    try:
        inventory = db.get_inventory(user_id=ctx.household_id) or []
        plan = build_weekly_meal_plan(
            db, user_id=ctx.household_id, days=days,
            inventory=inventory,
        )
        return MealPlanResponse(
            summary=summarize_meal_plan(plan),
            days=days,
            start_date=plan[0].date if plan else "",
            count=len(plan),
            items=[
                MealPlanDayWire(
                    date=d.date,
                    recipe_name=d.recipe_name,
                    recipe_id=d.recipe_id,
                    cuisine=d.cuisine,
                    cook_minutes=d.cook_minutes,
                    score=d.score,
                    ingredients_used=d.ingredients_used,
                    ingredients_missing=d.ingredients_missing,
                    confidence=d.confidence,
                    rationale=d.rationale,
                )
                for d in plan
            ],
        )
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.warning("meal plan failed: %s", exc)
        return MealPlanResponse(
            summary=f"Error: {exc}", days=days, count=0,
        )


@router.get(
    "/recipes/{recipe_id}",
    response_model=RecipeDetailResponse,
    summary="Get full recipe details by ID",
)
def recipe_detail(
    recipe_id: str,
    ctx: HouseholdContext = Depends(require_household),
) -> RecipeDetailResponse:
    """Return the full recipe for ``recipe_id`` including ingredients and instructions.

    Used by the mobile Cook tab to show a detail sheet for a suggested meal.
    """
    from shopstack.services.recipes import get_recipe

    recipe = get_recipe(recipe_id)
    if recipe is None:
        return RecipeDetailResponse(
            recipe_id=recipe_id,
            name="Recipe not found",
            found=False,
        )
    return RecipeDetailResponse(
        recipe_id=recipe.id,
        name=recipe.name,
        cuisine=recipe.cuisine,
        dietary=recipe.dietary,
        prep_minutes=recipe.prep_minutes,
        cook_minutes=recipe.cook_minutes,
        serves=recipe.serves,
        tags=recipe.tags,
        ingredients=[
            RecipeIngredientWire(
                canonical_name=ing.canonical_name,
                quantity=ing.quantity,
                unit=ing.unit,
            )
            for ing in recipe.ingredients
        ],
        instructions=recipe.instructions,
        found=True,
    )


# ── internal helpers ────────────────────────────────────────────────


def _extract_days_until_next(reasons: list[str]) -> int | None:
    """Pull days-until-next from decision reasons."""
    import re
    for r in reasons:
        if "due today" in r:
            return 0
        if "due tomorrow" in r:
            return 1
        m = re.search(r"due in (\d+) days", r)
        if m:
            return int(m.group(1))
        m = re.search(r"due (\d+) days ago", r)
        if m:
            return -int(m.group(1))
    return None


def _extract_interval(reasons: list[str]) -> float | None:
    """Pull typical interval from decision reasons."""
    import re
    for r in reasons:
        m = re.search(r"every ([\d.]+) days", r)
        if m:
            return float(m.group(1))
    return None


__all__ = ["router"]
