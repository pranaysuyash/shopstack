"""Cookbook browser — Gradio screen adapters.

The underlying service (``shopstack.services.cookbook``) is fully built
and tested. This module is the thin Gradio-facing wrapper: it reads
filter values, calls the service, and returns HTML strings for the
cookbook grid and detail views.

The actual rendering lives in the service (``render_cookbook_grid_html``
and ``render_cookbook_detail_html``). This screen module adds:
  * Gradio-friendly function signatures (locale, all-returns-HTML).
  * Defensive handling of empty filter values.
  * Shop-missing action: push a recipe's missing ingredients to the
    active shopping list with a single click.
"""

from __future__ import annotations

import logging
from typing import Any

from shopstack.app_context import current_user_id, db
from shopstack.services.cookbook import (
    browse_recipes,
    list_cuisines,
    parse_filter,
    render_cookbook_detail_html,
    render_cookbook_grid_html,
    shop_missing,
)
from shopstack.services.i18n import DEFAULT_LOCALE, load_locale_preference
from shopstack.services.recipes import get_recipe, match_recipe
from shopstack.ui.components.primitives import home_card

logger = logging.getLogger(__name__)


def _safe_locale() -> str:
    """Resolve the user's current locale, with safe fallback to default.

    The locale preference is persisted per user. We never want a missing
    preference to break the page, so the fallback chain is:
        persisted → DEFAULT_LOCALE
    """
    try:
        uid = current_user_id() or ""
        return load_locale_preference(uid) or DEFAULT_LOCALE
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("Locale resolution failed, falling back to default: %s", exc)
        return DEFAULT_LOCALE


def _dietary_preference_from_signal() -> str:
    """Read household-level dietary preference from the preference signals.

    The dashboard service stores dietary as ``_diet:<value>`` signal
    canonical names. We resolve the same way here so the cookbook
    honors the same household rule as the rest of the app.
    """
    try:
        for sig in db.get_preference_signals(user_id=current_user_id() or ""):
            if sig.canonical_name and sig.canonical_name.startswith("_diet:"):
                return sig.canonical_name.split(":", 1)[1] or "omnivore"
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("Dietary preference read failed: %s", exc)
    return "omnivore"


def cookbook_browse(
    dietary: str | None = None,
    cuisine: str | None = None,
    quick_only: bool | str = False,
    search: str = "",
) -> str:
    """Render the cookbook grid for the current household.

    Args:
        dietary: 'all' / 'vegetarian' / 'vegan' / 'omnivore' (Gradio dropdown value).
        cuisine: 'all' / specific cuisine id (Gradio dropdown value).
        quick_only: True to filter to <30 min total.
        search: case-insensitive substring on recipe name + tags.

    Returns:
        HTML string for the full grid.
    """
    f = parse_filter(dietary=dietary, cuisine=cuisine, quick_only=quick_only, search=search)
    locale = _safe_locale()
    household_diet = _dietary_preference_from_signal()
    try:
        inventory = db.get_inventory(user_id=current_user_id() or "")
        matches = browse_recipes(inventory, f, dietary_preference=household_diet)
    except Exception as exc:
        logger.warning("Cookbook browse failed: %s", exc)
        matches = []
    return render_cookbook_grid_html(matches, locale)


def cookbook_view_recipe(
    recipe_id: str,
    dietary: str | None = None,
    cuisine: str | None = None,
    quick_only: bool | str = False,
    search: str = "",
) -> str:
    """Render the full detail (ingredients + instructions) for one recipe.

    Args:
        recipe_id: Recipe id (e.g. ``"dal_makhani"``). If empty/invalid,
            returns the browse grid instead so the user sees something
            rather than a blank card.
    """
    if not recipe_id:
        return cookbook_browse(dietary=dietary, cuisine=cuisine,
                                quick_only=quick_only, search=search)
    recipe = get_recipe(recipe_id)
    if recipe is None:
        logger.debug("Unknown recipe id requested: %s", recipe_id)
        return cookbook_browse(dietary=dietary, cuisine=cuisine,
                                quick_only=quick_only, search=search)

    locale = _safe_locale()
    try:
        f = parse_filter(dietary=dietary, cuisine=cuisine,
                         quick_only=quick_only, search=search)
        household_diet = _dietary_preference_from_signal()
        inventory = db.get_inventory(user_id=current_user_id() or "")
        match = match_recipe(recipe, inventory, None)
        # The match's dietary filter doesn't apply to the detail view;
        # if the user is in a strict household the browse hides it,
        # but a direct ``view_recipe`` call should still show the recipe.
        return render_cookbook_detail_html(recipe, match, locale)
    except Exception as exc:
        logger.warning("Cookbook detail render failed: %s", exc)
        return render_cookbook_detail_html(recipe, None, locale)


def cookbook_shop_missing(
    recipe_id: str,
    dietary: str | None = None,
    cuisine: str | None = None,
    quick_only: bool | str = False,
    search: str = "",
) -> str:
    """Push a recipe's missing ingredients to the active shopping list.

    The shopper sees a status HTML returned for the toast / status
    region of the cookbook detail view. The user stays on the detail
    page; the shopping list is updated in the background.

    Returns:
        HTML status string (success / nothing-to-add / not-found).
    """
    if not recipe_id:
        return home_card(style="border-left:3px solid var(--red);", body="⚠ No recipe selected.")
    recipe = get_recipe(recipe_id)
    if recipe is None:
        return home_card(
            style="border-left:3px solid var(--red);",
            body=f"⚠ Recipe <code>{recipe_id}</code> not found.",
        )
    from shopstack.ui.errors import safe_render_html
    return safe_render_html(
        lambda: _cookbook_shop_missing_inner(recipe, recipe_id),
        user_message="Could not update shopping list",
        icon="🍳",
        retry_label="",
    )


def _cookbook_shop_missing_inner(recipe, recipe_id: str) -> str:
    inventory = db.get_inventory(user_id=current_user_id() or "")
    result = shop_missing(
        db, recipe, inventory, user_id=current_user_id() or "",
    )
    if result.get("added") and result.get("count", 0) > 0:
        added = result["count"]
        return home_card(
            style="border-left:3px solid var(--green);",
            body=f"✓ Added {added} missing item{'s' if added != 1 else ''} from {recipe.name} to the active shopping list.",
        )
    if result.get("count", 0) == 0 and result.get("reason", "").startswith("Nothing missing"):
        return home_card(
            style="border-left:3px solid var(--green);",
            body=f"✓ You already have every ingredient for {recipe.name}.",
        )
    return home_card(
        style="border-left:3px solid var(--amber);",
        body=f"⚠ {result.get('reason', 'No items added yet — add ingredients manually.')} ({recipe.name})",
    )


def cookbook_cuisine_choices() -> list[tuple[str, str]]:
    """Gradio dropdown choices for the cuisine filter.

    Returns a list of (display_label, value_id) tuples. The "All" entry
    is always first so the filter starts in the unfiltered state.
    """
    return [("All", "all")] + [(c.replace("_", " ").title(), c) for c in list_cuisines()]


__all__ = [
    "cookbook_browse",
    "cookbook_view_recipe",
    "cookbook_shop_missing",
    "cookbook_cuisine_choices",
]
