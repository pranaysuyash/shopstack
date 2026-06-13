"""Cookbook tab — Phase 5 #20.

The Cookbook is a *library* of all recipes (30 Indian staples) with
filterable, browsable cards. Distinct from the Cook Tonight card on
the Today dashboard (which shows a top-4 ranked subset):

  * Today → 🍳 Cook Tonight → 4 recommendations, ranked, "use these
    tonight" framing.
  * Cookbook tab → all recipes, filterable by cuisine / dietary /
    quick / search, with detail view and "shop missing" action.

Both share the same recipe database (``shopstack/services/recipes.py``)
and the same matcher (``match_recipe``). The difference is the user
journey: Cook Tonight is a daily hook; the Cookbook is a discovery
surface for when the user has more time.

The service side (``shopstack/services/cookbook.py``) is fully built
and tested. This tab is a thin Gradio adapter: filter row + grid +
detail + shop-missing status.
"""
from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.screens.cookbook import (
    cookbook_browse,
    cookbook_cuisine_choices,
    cookbook_shop_missing,
    cookbook_view_recipe,
)
from shopstack.ui.tabs.context import TabContext


def _DIETARY_CHOICES() -> list[tuple[str, str]]:
    # The values are the strings the parse_filter helper recognizes.
    return [
        ("All", "all"),
        ("Vegetarian", "vegetarian"),
        ("Vegan", "vegan"),
        ("Omnivore", "omnivore"),
    ]


def build_cookbook_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Cookbook tab inside the parent's ``gr.Tabs`` context.

    Layout:
      * Filter row (cuisine dropdown, dietary dropdown, quick-only
        checkbox, search text).
      * Grid (HTML) — list of recipe cards with completion %.
      * Detail (HTML) — selected recipe ingredients + instructions.
      * Status (HTML) — toast area for the shop-missing action.

    All four interactive controls funnel into the same handler so a
    change in any of them re-renders the grid. Selecting a recipe
    (via its Dropdown) renders the detail. The shop-missing button
    posts the missing ingredients to the active list and shows a
    status toast.
    """
    with gr.Tab(_tab_label("cookbook"), id="cookbook"):
        gr.Markdown("### Browse recipes")
        gr.Markdown(
            "All 30 recipes in the ShopStack library. Filter by cuisine, "
            "dietary preference, time, or search. Click a recipe to see "
            "ingredients and instructions, then push missing items to the "
            "shopping list in one click."
        )

        with gr.Row():
            cuisine_filter = gr.Dropdown(
                label="Cuisine",
                choices=cookbook_cuisine_choices(),
                value="all",
                allow_custom_value=False,
                scale=1,
            )
            dietary_filter = gr.Dropdown(
                label="Dietary",
                choices=_DIETARY_CHOICES(),
                value="all",
                allow_custom_value=False,
                scale=1,
            )
            quick_only = gr.Checkbox(
                label="Quick (<30 min)",
                value=False,
                scale=1,
            )
            search_box = gr.Textbox(
                label="Search",
                placeholder="e.g. dal, paneer, chicken...",
                scale=2,
            )

        # Hidden state to pass filter values into the detail and
        # shop-missing actions without forcing the user to re-apply.
        with gr.Row():
            recipe_selector = gr.Dropdown(
                label="Open recipe",
                choices=[],
                value="",
                allow_custom_value=False,
                scale=2,
            )
            refresh_recipes = gr.Button("Refresh list", elem_classes="secondary", scale=1)

        grid_html = gr.HTML("<div class='home-card'>Loading recipes…</div>")
        detail_html = gr.HTML("<div class='home-card'>Select a recipe above to see ingredients and steps.</div>")
        status_html = gr.HTML("")

        # Re-render the grid + recipe selector whenever any filter changes.
        for comp in (cuisine_filter, dietary_filter, quick_only, search_box):
            comp.change(
                _refresh_grid_and_selector,
                [cuisine_filter, dietary_filter, quick_only, search_box],
                [grid_html, recipe_selector],
                api_name="cookbook_filter",
                api_description="Re-render the cookbook grid + recipe selector with the new filter.",
            )

        # Selecting a recipe from the dropdown renders the detail.
        recipe_selector.change(
            cookbook_view_recipe,
            [recipe_selector, cuisine_filter, dietary_filter, quick_only, search_box],
            detail_html,
            api_name="cookbook_open",
            api_description="Open the selected recipe and render ingredients + instructions.",
        )

        # Shop-missing action: push missing items to active list.
        shop_btn = gr.Button("Add missing items to my shopping list", variant="primary")
        shop_btn.click(
            cookbook_shop_missing,
            [recipe_selector, cuisine_filter, dietary_filter, quick_only, search_box],
            status_html,
            api_name="cookbook_shop_missing",
            api_description="Add the selected recipe's missing ingredients to the active shopping list.",
        )

        # Refresh button: rebuild grid + selector from current filters.
        refresh_recipes.click(
            _refresh_grid_and_selector,
            [cuisine_filter, dietary_filter, quick_only, search_box],
            [grid_html, recipe_selector],
            api_name="cookbook_refresh",
            api_description="Force a refresh of the cookbook grid + selector.",
        )

        # Initial population on page load.
        app.load(
            _refresh_grid_and_selector,
            [cuisine_filter, dietary_filter, quick_only, search_box],
            [grid_html, recipe_selector],
        )


def _refresh_grid_and_selector(
    dietary: str | None,
    cuisine: str | None,
    quick_only: bool | str,
    search: str,
) -> tuple[str, list[tuple[str, str]]]:
    """Re-render the cookbook grid AND rebuild the recipe-selector choices.

    Returns a tuple ``(grid_html, recipe_choices)`` so the same handler
    can feed both the grid component and the dropdown that drives
    detail rendering. We run the filter once and pass the resulting
    match list to the selector builder — no duplicate browse.
    """
    from shopstack.app_context import current_user_id, db
    from shopstack.services.cookbook import browse_recipes, parse_filter
    from shopstack.ui.screens.cookbook import (
        _dietary_preference_from_signal,
        cookbook_browse as _browse,
    )

    grid = _browse(dietary=dietary, cuisine=cuisine, quick_only=quick_only, search=search)

    # Build the selector list from the SAME filtered set so the user
    # can only open recipes that pass their filter. We re-derive the
    # match list (one extra ``match_recipe`` pass per recipe) — cheap
    # for 30 recipes and keeps the public ``cookbook_browse`` contract
    # simple (returns just HTML, not a match list).
    try:
        f = parse_filter(
            dietary=dietary, cuisine=cuisine, quick_only=quick_only, search=search
        )
        household_diet = _dietary_preference_from_signal()
        inventory = db.get_inventory(user_id=current_user_id() or "")
        matches = browse_recipes(inventory, f, dietary_preference=household_diet)
        choices = [(m.recipe.name, m.recipe.id) for m in matches]
    except Exception:
        choices = []

    if not choices:
        # Provide a single disabled placeholder so the Dropdown still
        # has a non-empty ``choices`` list (Gradio warns on empty).
        choices = [("(no recipes match)", "")]

    return grid, choices
