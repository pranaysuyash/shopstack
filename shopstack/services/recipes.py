"""Cook tonight — recipe recommendations based on inventory + use-soon.

The Today dashboard surfaces items about to expire (the "use-soon" list).
This service turns that *guilt list* into an *actionable hook*: given
what's at home (including what's about to go bad), recommend recipes
that use those ingredients, list what's missing, and let the user
push the missing items straight to the shopping list.

Recipe database lives in ``shopstack/data/recipes.json`` (30 Indian
household staples spanning North Indian, South Indian, Chinese, Italian,
and breakfast / snack categories). All ingredient names use the same
canonical names as the rest of ShopStack, so the matcher is exact.

Ranking algorithm:

    score(recipe, inventory, use_soon) =
        use_soon_match_count * 5        # big weight — saves food
        + have_match_count * 1         # already-have bonus
        - missing_count * 2            # penalty for shopping
        - cook_minutes * 0.01           # mild preference for quick
        + (cuisine tag bonuses)         # future-proofing for prefs

The dietary filter is a hard filter, not a soft one: vegetarian
households never see non-vegetarian recipes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any

from shopstack.ui.components.primitives import home_card

logger = logging.getLogger(__name__)


# ─── Recipe dataclasses ──────────────────────────────────────────────────


@dataclass
class RecipeIngredient:
    """One ingredient line in a recipe."""

    canonical_name: str
    quantity: float
    unit: str


@dataclass
class Recipe:
    """A single recipe from the recipe database."""

    id: str
    name: str
    cuisine: str
    dietary: list[str] = field(default_factory=list)
    prep_minutes: int = 0
    cook_minutes: int = 0
    serves: int = 2
    tags: list[str] = field(default_factory=list)
    ingredients: list[RecipeIngredient] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)


@dataclass
class RecipeMatch:
    """A recipe's match against the household's inventory."""

    recipe: Recipe
    have: list[RecipeIngredient] = field(default_factory=list)
    missing: list[RecipeIngredient] = field(default_factory=list)
    use_soon_hits: list[RecipeIngredient] = field(default_factory=list)
    score: float = 0.0

    @property
    def total_ingredients(self) -> int:
        return len(self.recipe.ingredients)

    @property
    def have_count(self) -> int:
        return len(self.have)

    @property
    def missing_count(self) -> int:
        return len(self.missing)

    @property
    def use_soon_count(self) -> int:
        return len(self.use_soon_hits)

    @property
    def completion_pct(self) -> float:
        if not self.total_ingredients:
            return 0.0
        return round(self.have_count / self.total_ingredients * 100, 1)


# ─── Recipe DB loader ────────────────────────────────────────────────────


_RECIPES_PATH = Path(__file__).resolve().parent.parent / "data" / "recipes.json"
_RECIPES_CACHE: list[Recipe] | None = None


def _load_recipes() -> list[Recipe]:
    """Read and parse the recipe JSON file (cached)."""
    global _RECIPES_CACHE
    if _RECIPES_CACHE is not None:
        return _RECIPES_CACHE

    if not _RECIPES_PATH.is_file():
        logger.warning("Recipe DB not found at %s", _RECIPES_PATH)
        _RECIPES_CACHE = []
        return _RECIPES_CACHE

    try:
        with open(_RECIPES_PATH, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load recipe DB: %s", exc)
        _RECIPES_CACHE = []
        return _RECIPES_CACHE

    recipes: list[Recipe] = []
    for entry in raw:
        try:
            ingredients = [
                RecipeIngredient(
                    canonical_name=str(ing.get("canonical_name", "")).strip(),
                    quantity=float(ing.get("quantity", 1) or 1),
                    unit=str(ing.get("unit", "unit") or "unit").strip(),
                )
                for ing in entry.get("ingredients", [])
            ]
            recipes.append(Recipe(
                id=str(entry.get("id", "")),
                name=str(entry.get("name", "")),
                cuisine=str(entry.get("cuisine", "")),
                dietary=list(entry.get("dietary", [])),
                prep_minutes=int(entry.get("prep_minutes", 0) or 0),
                cook_minutes=int(entry.get("cook_minutes", 0) or 0),
                serves=int(entry.get("serves", 2) or 2),
                tags=list(entry.get("tags", [])),
                ingredients=ingredients,
                instructions=list(entry.get("instructions", [])),
            ))
        except Exception as exc:
            logger.debug("Skipping malformed recipe: %s", exc)
    _RECIPES_CACHE = recipes
    return _RECIPES_CACHE


def all_recipes() -> list[Recipe]:
    """Return the full recipe list (cached)."""
    return list(_load_recipes())


def get_recipe(recipe_id: str) -> Recipe | None:
    """Look up a recipe by id (e.g. ``"dal_makhani"``). Returns ``None`` if missing."""
    for r in _load_recipes():
        if r.id == recipe_id:
            return r
    return None


# ─── Matching ────────────────────────────────────────────────────────────


def _build_inventory_lookup(inventory: list[Any]) -> dict[str, float]:
    """Map canonical_name → total quantity in user-chosen base unit (assumed
    consistent with the recipe DB; the unit math is intentionally simple
    — we match on canonical name, not exact unit conversion).
    """
    out: dict[str, float] = {}
    for lot in inventory:
        cname = (getattr(lot, "canonical_name", "") or "").strip().lower()
        if not cname:
            continue
        qty = float(getattr(lot, "quantity", 0) or 0)
        out[cname] = out.get(cname, 0.0) + qty
    return out


def _build_use_soon_lookup(use_soon_items: list[dict] | None) -> set[str]:
    """Extract canonical names from use-soon items."""
    out: set[str] = set()
    for it in (use_soon_items or []):
        cname = (it.get("canonical_name") or "").strip().lower()
        if cname:
            out.add(cname)
    return out


def _matches_diet(recipe: Recipe, dietary_preference: str) -> bool:
    """True if the recipe satisfies the dietary preference."""
    if not dietary_preference or dietary_preference == "omnivore":
        return True  # no filter
    if dietary_preference in ("vegetarian", "vegan"):
        # Vegetarian must contain "vegetarian" in dietary list
        if "vegetarian" in recipe.dietary:
            return True
        return False
    return True  # unknown preference → permissive


def match_recipe(
    recipe: Recipe,
    inventory: list[Any],
    use_soon_items: list[dict] | None = None,
) -> RecipeMatch:
    """Compute the match for a single recipe against the household."""
    have_map = _build_inventory_lookup(inventory)
    use_soon_set = _build_use_soon_lookup(use_soon_items)

    have: list[RecipeIngredient] = []
    missing: list[RecipeIngredient] = []
    use_soon_hits: list[RecipeIngredient] = []
    for ing in recipe.ingredients:
        cname = ing.canonical_name.strip().lower()
        on_hand = have_map.get(cname, 0.0)
        if on_hand > 0:
            have.append(ing)
        else:
            missing.append(ing)
        if cname in use_soon_set:
            use_soon_hits.append(ing)

    # Score
    score = (
        len(use_soon_hits) * 5.0
        + len(have) * 1.0
        - len(missing) * 2.0
        - recipe.cook_minutes * 0.01
    )

    return RecipeMatch(
        recipe=recipe,
        have=have,
        missing=missing,
        use_soon_hits=use_soon_hits,
        score=score,
    )


def find_recipes_for_inventory(
    inventory: list[Any],
    use_soon_items: list[dict] | None = None,
    *,
    dietary_preference: str = "omnivore",
    max_recipes: int = 6,
    min_have_pct: float = 0.0,
    min_have_count: int = 1,
) -> list[RecipeMatch]:
    """Return the top recipes ranked for the household's current inventory.

    Args:
        inventory: List of InventoryLot-like objects (any object with
            ``canonical_name`` and ``quantity`` attributes).
        use_soon_items: List of use-soon dicts (each with
            ``canonical_name``). Boosted in ranking.
        dietary_preference: "vegetarian" / "vegan" / "omnivore". Hard
            filter — non-matching recipes are excluded entirely.
        max_recipes: Cap on the returned list length.
        min_have_pct: Drop recipes the user has < this fraction of
            ingredients for (0.0 = no filter, 0.5 = at least half-have).
        min_have_count: Drop recipes the user has fewer than this
            many on-hand ingredients for. Default 1 — "Cook Tonight"
            implies "I can make this NOW", so a recipe the user has
            zero ingredients for is excluded. The user can find
            those recipes via the cookbook search instead.
            Set to 0 to restore the old "show all" behaviour (only
            recommended when the user explicitly opts in).

    Note (motto_v3 §0.14 Product Reality):
        The previous default of ``min_have_pct=0.0`` meant a
        user with an empty pantry still saw 10 recipes ranked by
        "negative score" — a confusing UX where the cook-tonight
        card advertised meals the user couldn't actually cook.
        The new ``min_have_count=1`` default closes that hole
        without sacrificing the "use-soon boosted" ranking for
        recipes the user CAN cook.
    """
    matches: list[RecipeMatch] = []
    for recipe in _load_recipes():
        if not _matches_diet(recipe, dietary_preference):
            continue
        m = match_recipe(recipe, inventory, use_soon_items)
        if min_have_pct > 0 and m.completion_pct < min_have_pct * 100:
            continue
        if m.have_count < min_have_count:
            continue
        matches.append(m)
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:max_recipes]


def missing_to_shopping_items(matches: list[RecipeMatch]) -> list[dict[str, Any]]:
    """Flatten a list of ``RecipeMatch`` into a deduplicated list of
    shopping-list items (canonical_name, quantity, unit) for everything
    missing across the selected recipes. The first occurrence wins for
    quantity/unit (assumes similar recipes use similar amounts)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for m in matches:
        for ing in m.missing:
            cname = ing.canonical_name.strip().lower()
            if not cname or cname in seen:
                continue
            seen.add(cname)
            out.append({
                "canonical_name": ing.canonical_name,
                "requested_quantity": ing.quantity,
                "unit": ing.unit,
            })
    return out


# ─── HTML rendering ──────────────────────────────────────────────────────


def render_cook_tonight_html(matches: list[RecipeMatch]) -> str:
    """Render the cook-tonight card as XSS-safe HTML for a Gradio component."""
    if not matches:
        return home_card(
            style="text-align:center;padding:16px;color:var(--text-dim);",
            body=(
                "No recipe suggestions right now. Add some ingredients to your "
                "inventory, or run the Onboarding quiz to seed staples."
            ),
        )

    parts: list[str] = []
    for m in matches:
        use_soon_badge = ""
        if m.use_soon_count > 0:
            use_soon_names = ", ".join(
                escape(ing.canonical_name.replace("_", " ").title())
                for ing in m.use_soon_hits
            )
            use_soon_badge = (
                f"<div style='font-size: 0.6875rem;color:var(--amber);margin-top:2px;'>⏰ Uses expiring: {use_soon_names}</div>"
            )

        have_html = ""
        if m.have:
            have_names = ", ".join(
                escape(ing.canonical_name.replace("_", " ").title())
                for ing in m.have
            )
            have_html = (
                f"<div style='font-size: 0.6875rem;color:var(--green);margin-top:2px;'>✓ Have: {have_names}</div>"
            )
        missing_html = ""
        if m.missing:
            missing_names = ", ".join(
                escape(ing.canonical_name.replace("_", " ").title())
                for ing in m.missing
            )
            missing_html = (
                f"<div style='font-size: 0.6875rem;color:var(--red);margin-top:2px;'>✗ Need: {missing_names}</div>"
            )

        cuisine_label = m.recipe.cuisine.replace("_", " ").title()
        time_label = f"{m.recipe.prep_minutes + m.recipe.cook_minutes} min"

        parts.append(
            f"<div style='padding:8px 0;border-bottom:1px solid var(--border);'><div style='display:flex;justify-content:space-between;align-items:baseline;'>"
            f"<strong>{escape(m.recipe.name)}</strong><span style='font-size: 0.625rem;color:var(--text-dim);'>{escape(cuisine_label)} · {time_label} · serves {m.recipe.serves}</span>"
            f"</div>{use_soon_badge}"
            f"{have_html}{missing_html}"
            f"<div style='font-size: 0.625rem;color:var(--text-dim);margin-top:4px;'>Completion: {m.completion_pct:.0f}% · Score: {m.score:.1f}"
            f"</div></div>"
        )

    return home_card(
        style="margin-bottom:12px;",
        body=(
            f"<h3 style='margin:0 0 4px 0;'>🍳 Cook Tonight</h3>"
            f"<div style='font-size: 0.6875rem;color:var(--text-dim);margin-bottom:6px;'>Recipes that use what you have. ⏰ marks recipes that rescue expiring items."
            f"</div>{''.join(parts)}"
        ),
    )


__all__ = [
    "Recipe",
    "RecipeIngredient",
    "RecipeMatch",
    "all_recipes",
    "get_recipe",
    "match_recipe",
    "find_recipes_for_inventory",
    "missing_to_shopping_items",
    "render_cook_tonight_html",
]
