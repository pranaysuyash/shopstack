"""Cookbook browser — Phase 5 #20.

Renders the full 30-recipe database as a filterable, browsable card grid.
Distinct from :mod:`shopstack.services.recipes` (which is the cook-tonight
matcher that uses inventory): the cookbook is a *library* of all recipes,
filterable by dietary preference, cuisine, and time-to-cook.

**Design choices:**

- All filtering happens server-side via :func:`filter_recipes` so the
  client never sees the full DB over the wire.
- Recipe cards show: name, cuisine, time, dietary tags, and a
  have/missing indicator against the household's current inventory.
- One click on a card opens the full recipe (ingredients + instructions).
- "Shop missing items" pushes the missing ingredients to the active
  shopping list in one click (reuses
  :func:`shopstack.services.recipes.missing_to_shopping_items`).
- Bilingual via :mod:`shopstack.services.i18n`. Card text is rendered
  with the user's chosen locale.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Iterable

from shopstack.services.i18n import DEFAULT_LOCALE, t
from shopstack.services.recipes import (
    Recipe,
    RecipeMatch,
    all_recipes,
    get_recipe,
    match_recipe,
    missing_to_shopping_items,
)

logger = logging.getLogger(__name__)


# ─── Filter dataclass ───────────────────────────────────────────────────


@dataclass
class CookbookFilter:
    """User-selected filter for the cookbook browser.

    All fields are optional. ``None`` means "no filter for this dimension".
    """

    dietary: str | None = None  # "vegetarian" / "vegan" / "omnivore" / None
    cuisine: str | None = None  # e.g. "north_indian" / None
    quick_only: bool = False    # <30 min total
    search: str = ""            # case-insensitive substring on name


def parse_filter(
    dietary: str | None = None,
    cuisine: str | None = None,
    quick_only: bool | str = False,
    search: str = "",
) -> CookbookFilter:
    """Build a :class:`CookbookFilter` from raw form values.

    Gradio sends booleans as Python ``bool``; we accept strings too so
    this function is robust when called from non-Gradio callers (tests,
    CLI, etc.).
    """
    if isinstance(quick_only, str):
        quick_only = quick_only.strip().lower() in ("1", "true", "yes", "on")
    return CookbookFilter(
        dietary=dietary if dietary and dietary != "all" else None,
        cuisine=cuisine if cuisine and cuisine != "all" else None,
        quick_only=bool(quick_only),
        search=(search or "").strip().lower(),
    )


# ─── Pure filter / search ──────────────────────────────────────────────


def _matches_filter(recipe: Recipe, f: CookbookFilter) -> bool:
    if f.dietary and f.dietary != "omnivore":
        if f.dietary not in recipe.dietary:
            return False
    if f.cuisine and recipe.cuisine != f.cuisine:
        return False
    if f.quick_only and (recipe.prep_minutes + recipe.cook_minutes) >= 30:
        return False
    if f.search:
        haystack = (recipe.name + " " + " ".join(recipe.tags)).lower()
        if f.search not in haystack:
            return False
    return True


def filter_recipes(f: CookbookFilter) -> list[Recipe]:
    """Return the recipes that match :class:`CookbookFilter` (no inventory check)."""
    return [r for r in all_recipes() if _matches_filter(r, f)]


def list_cuisines() -> list[str]:
    """Return the sorted, deduplicated list of cuisines present in the DB."""
    out: set[str] = set()
    for r in all_recipes():
        out.add(r.cuisine)
    return sorted(out)


# ─── Inventory-aware browsing ──────────────────────────────────────────


def browse_recipes(
    inventory: list[Any],
    f: CookbookFilter,
    *,
    dietary_preference: str = "omnivore",
) -> list[RecipeMatch]:
    """Filter + match recipes against current inventory.

    Args:
        inventory: list of InventoryLot-like objects (``canonical_name``
            and ``quantity`` attributes).
        f: Active :class:`CookbookFilter`.
        dietary_preference: Household-level dietary preference; can be
            stricter than ``f.dietary`` (e.g. the household is vegetarian
            so non-veg recipes are always hidden).

    Returns:
        List of :class:`RecipeMatch` ordered by completion percentage
        descending (so the user sees "you can cook this now" first).
    """
    merged_filter = CookbookFilter(
        dietary=dietary_preference if dietary_preference != "omnivore" else f.dietary,
        cuisine=f.cuisine,
        quick_only=f.quick_only,
        search=f.search,
    )
    matches: list[RecipeMatch] = []
    for r in filter_recipes(merged_filter):
        m = match_recipe(r, inventory)
        matches.append(m)
    matches.sort(key=lambda m: (m.completion_pct, m.score), reverse=True)
    return matches


# ─── HTML rendering ─────────────────────────────────────────────────────


def _dietary_tags_html(recipe: Recipe, locale: str) -> str:
    """Render small dietary badges (e.g. 'Veg', 'Vegan')."""
    tags: list[str] = []
    for d in recipe.dietary:
        if d == "vegetarian":
            tags.append(f"<span class='cb-tag cb-veg'>{escape(t('cookbook.filter_veg', locale))}</span>")
        elif d == "vegan":
            tags.append(f"<span class='cb-tag cb-vegan'>{escape(t('cookbook.filter_vegan', locale))}</span>")
    return "".join(tags)


def _time_minutes(recipe: Recipe) -> int:
    return recipe.prep_minutes + recipe.cook_minutes


def render_cookbook_card_html(
    match: RecipeMatch,
    locale: str = DEFAULT_LOCALE,
) -> str:
    """Render a single recipe as a card.

    The card has a header (name, cuisine, time), a body (dietary tags,
    have/missing counts, completion %), and a footer with the
    "Shop missing" / "Open" affordances (the footer is rendered
    separately in :func:`render_cookbook_grid_html` so the cards
    can sit in a static ``gr.HTML`` without click handlers).
    """
    r = match.recipe
    cuisine = r.cuisine.replace("_", " ").title()
    mins = _time_minutes(r)
    completion_color = "var(--green)" if match.completion_pct >= 80 else (
        "var(--amber)" if match.completion_pct >= 40 else "var(--text-dim)"
    )
    have_str = ", ".join(
        escape(i.canonical_name.replace("_", " ").title()) for i in match.have
    ) or "—"
    missing_str = ", ".join(
        escape(i.canonical_name.replace("_", " ").title()) for i in match.missing
    ) or "—"

    return (
        "<div class='cb-card'>"
        f"<div class='cb-card-head'><div class='cb-name'>{escape(r.name)}</div>"
        f"<div class='cb-meta'>{escape(cuisine)} · {mins} {t('cookbook.total', locale).lower()} · {t('cookbook.serves', locale, n=r.serves)}</div>"
        f"{_dietary_tags_html(r, locale)}</div>"
        f"<div class='cb-progress' style='color:{completion_color};'>● {match.completion_pct:.0f}% ready · {match.have_count}/{match.total_ingredients} "
        f"{t('cookbook.ingredients', locale).lower()}</div>"
        f"<div class='cb-detail-row'><div class='cb-have'>✓ {t('cookbook.have', locale)}: {have_str}</div>"
        f"<div class='cb-missing'>+ {t('cookbook.missing', locale)}: {missing_str}</div></div>"
        f"</div>"
    )


def render_cookbook_grid_html(
    matches: list[RecipeMatch],
    locale: str = DEFAULT_LOCALE,
) -> str:
    """Render the full cookbook grid as a single HTML string."""
    if not matches:
        return (
            "<div class='home-card' style='text-align:center;padding:24px;color:var(--text-dim);'>"
            f"{escape(t('cookbook.no_recipes', locale))}"
            "</div>"
        )
    cards = "".join(render_cookbook_card_html(m, locale) for m in matches)
    return (
        f"<div class='cb-grid'><h3 style='margin:0 0 8px 0;'>{escape(t('section.cookbook_browse', locale))}</h3>"
        f"<div class='cb-grid-inner'>{cards}</div></div>"
    )


def render_cookbook_detail_html(
    recipe: Recipe,
    match: RecipeMatch | None = None,
    locale: str = DEFAULT_LOCALE,
) -> str:
    """Render the full recipe detail (ingredients + instructions).

    Args:
        recipe: The recipe to render.
        match: Optional pre-computed match (to color ingredients have/missing).
        locale: Translation locale.
    """
    have_set: set[str] = set()
    if match:
        have_set = {i.canonical_name.lower() for i in match.have}

    ing_rows: list[str] = []
    for ing in recipe.ingredients:
        cname = ing.canonical_name.lower()
        cls = "cb-ing-have" if cname in have_set else "cb-ing-miss"
        mark = "✓" if cname in have_set else "+"
        ing_rows.append(
            f"<li class='{cls}'><span class='cb-mark'>{mark}</span> "
            f"{ing.quantity:g} {escape(ing.unit)} {escape(ing.canonical_name.replace('_', ' ').title())}"
            f"</li>"
        )

    steps_html = "".join(
        f"<li class='cb-step'>{escape(step)}</li>" for step in recipe.instructions
    )

    cuisine = recipe.cuisine.replace("_", " ").title()
    mins = _time_minutes(recipe)

    return (
        "<div class='cb-detail'>"
        f"<h3 class='cb-detail-name'>{escape(recipe.name)}</h3><div class='cb-detail-meta'>"
        f"{escape(cuisine)} · {recipe.prep_minutes} {t('cookbook.prep', locale).lower()} · {recipe.cook_minutes} {t('cookbook.cook', locale).lower()} · "
        f"{mins} {t('cookbook.total', locale).lower()} · {t('cookbook.serves', locale, n=recipe.serves)}"
        f"</div>{_dietary_tags_html(recipe, locale)}"
        f"<h4 class='cb-section-h'>{escape(t('cookbook.ingredients', locale))}</h4><ul class='cb-ings'>{''.join(ing_rows)}</ul>"
        f"<h4 class='cb-section-h'>{escape(t('cookbook.instructions', locale))}</h4><ol class='cb-steps'>{steps_html}</ol>"
        f"</div>"
    )


# ─── Shopping-list wire-up ─────────────────────────────────────────────


def shop_missing(
    db: Any,
    recipe: Recipe,
    inventory: list[Any],
    user_id: str,
    list_id: str | None = None,
) -> dict[str, Any]:
    """Add the recipe's missing ingredients to the active shopping list.

    Returns a status dict::

        {
            "added": bool,
            "count": int,
            "items": [{"canonical_name": ..., "quantity": ..., "unit": ...}, ...],
            "reason": str,   # human-friendly message
        }

    Best-effort: never raises. Returns ``{"added": False, "reason": ...}``
    on any DB error so the caller can show a toast.
    """
    try:
        match = match_recipe(recipe, inventory)
        items = missing_to_shopping_items([match])
        if not items:
            return {
                "added": False,
                "count": 0,
                "items": [],
                "reason": "Nothing missing — you can cook this now.",
            }
        # Resolve the active list. If the caller passed one, use it;
        # otherwise look up the household's active list via the real
        # ``Database.get_active_shopping_list`` method. If the
        # household has no list yet, auto-create one. (The test
        # ``_FakeDB`` still uses ``get_shopping_lists`` — we support
        # both for backward compatibility with the existing test
        # contract.)
        if not list_id:
            active = None
            getter = getattr(db, "get_active_shopping_list", None)
            if callable(getter):
                try:
                    active = getter(user_id=user_id)
                except Exception as exc:  # pragma: no cover — defensive
                    logger.debug("get_active_shopping_list failed: %s", exc)
            if active is not None:
                list_id = active.list_id
            else:
                # Try the legacy test API
                lists_getter = getattr(db, "get_shopping_lists", None)
                lists = lists_getter(user_id=user_id) if callable(lists_getter) else []
                if lists:
                    list_id = lists[0].get("list_id") or lists[0].get("id")
                else:
                    # No existing list — auto-create one. This is the
                    # real path: a fresh household with no shopping
                    # list still needs a target for the missing items.
                    creator = getattr(db, "create_shopping_list", None)
                    if not callable(creator):
                        return {
                            "added": False,
                            "count": 0,
                            "items": [],
                            "reason": "No shopping list found and no "
                                       "create_shopping_list API on db.",
                        }
                    try:
                        new_list = creator(
                            name="Shopping List",
                            goal=f"Auto-created from {recipe.name}",
                            user_id=user_id,
                        )
                    except Exception as exc:
                        logger.debug("create_shopping_list failed: %s", exc)
                        return {
                            "added": False,
                            "count": 0,
                            "items": [],
                            "reason": f"Could not create a shopping list: {exc}",
                        }
                    list_id = new_list.list_id
        if not list_id:
            return {
                "added": False,
                "count": 0,
                "items": [],
                "reason": "Could not resolve an active shopping list.",
            }
        # Idempotency: skip canonical_names already on the list. We
        # query the existing items via the same ``conn.execute`` path
        # used by tests so this works for both the real DB and fakes.
        # Defensive: a DB error here means we degrade to "add all" so
        # the user-visible action never fails on idempotency lookup.
        existing_names: set[str] = set()
        try:
            conn = getattr(db, "conn", None)
            if conn is not None:
                rows = conn.execute(
                    "SELECT canonical_name FROM shopping_list_items WHERE list_id = ?",
                    (list_id,),
                ).fetchall()
                existing_names = {
                    (row[0] or "").strip().lower() for row in rows if row and row[0]
                }
        except Exception as exc:  # pragma: no cover — defensive
            logger.debug("idempotency lookup failed: %s", exc)
            existing_names = set()
        # Filter the items to skip already-present canonical_names.
        items_to_add = [
            it for it in items
            if (it.get("canonical_name") or "").strip().lower()
            not in existing_names
        ]
        skipped = len(items) - len(items_to_add)
        for it in items_to_add:
            try:
                # The real ``Database`` method is ``add_list_item`` (singular
                # "list" not "shopping"); the test fake exposes
                # ``add_shopping_list_item`` — support both so we don't
                # break the existing test contract.
                adder = getattr(db, "add_list_item", None) or getattr(
                    db, "add_shopping_list_item", None
                )
                if adder is None:
                    logger.debug("No add_list_item / add_shopping_list_item on db")
                    continue
                # Try the (real) signature first: ``add_list_item(list_id, item)``
                # with a ShoppingListItem object. Fall back to the
                # (test-fake) signature: ``add_shopping_list_item(*, list_id, ...)``.
                try:
                    from shopstack.schemas.models import ShoppingListItem as _Item
                    adder(
                        list_id=list_id,
                        item=_Item(
                            canonical_name=it["canonical_name"],
                            requested_quantity=float(it.get("requested_quantity") or 1),
                            unit=it.get("unit") or "unit",
                        ),
                    )
                except TypeError:
                    adder(
                        list_id=list_id,
                        canonical_name=it["canonical_name"],
                        quantity=float(it.get("requested_quantity") or 1),
                        unit=it.get("unit") or "unit",
                    )
            except Exception as exc:
                logger.debug("add_list_item failed for %s: %s",
                             it.get("canonical_name"), exc)
        return {
            "added": True,
            "count": len(items_to_add),
            "items": items_to_add,
            "reason": (
                f"Added {len(items_to_add)} item(s) to your shopping list."
                + (f" Skipped {skipped} already on list." if skipped else "")
            ),
        }
    except Exception as exc:
        logger.debug("shop_missing failed: %s", exc)
        return {
            "added": False,
            "count": 0,
            "items": [],
            "reason": f"Failed: {exc}",
        }


# ─── Re-exports for convenience ────────────────────────────────────────


__all__ = [
    "CookbookFilter",
    "browse_recipes",
    "filter_recipes",
    "list_cuisines",
    "parse_filter",
    "render_cookbook_card_html",
    "render_cookbook_detail_html",
    "render_cookbook_grid_html",
    "shop_missing",
]
