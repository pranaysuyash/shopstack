"""Cookbook filter row sub-builder.

Extracted from ``build_cookbook_tab`` so the filter row (cuisine,
dietary, quick-only, search, recipe selector) is independently
testable and reusable. The sub-builder returns a
``CookbookFilterHandles`` dataclass exposing all 5 components so the
parent tab builder (and the event wirings) can reference them.

The filter row components are:
- ``cuisine_filter`` — cuisine dropdown (Indian, Italian, Chinese, ...)
- ``dietary_filter`` — vegetarian / vegan / omnivore
- ``quick_only`` — checkbox for recipes under 30 minutes
- ``search_box`` — text search by recipe name or ingredient
- ``recipe_selector`` — dropdown to open a recipe for detail view
- ``refresh_recipes`` — button to force a refresh of the grid
"""
from __future__ import annotations

from dataclasses import dataclass

import gradio as gr

from shopstack.ui.screens.cookbook import cookbook_cuisine_choices


# Filter values are the strings parse_filter() recognizes. Keep in sync
# with shopstack.services.cookbook.parse_filter.
_DIETARY_CHOICES: list[tuple[str, str]] = [
    ("All", "all"),
    ("Vegetarian", "vegetarian"),
    ("Vegan", "vegan"),
    ("Omnivore", "omnivore"),
]


@dataclass
class CookbookFilterHandles:
    """Components that other parts of the cookbook tab reference.

    All five interactive controls funnel into the same handler so a
    change in any of them re-renders the grid. Selecting a recipe
    (via ``recipe_selector``) renders the detail panel.
    """
    cuisine_filter: gr.Dropdown
    dietary_filter: gr.Dropdown
    quick_only: gr.Checkbox
    search_box: gr.Textbox
    recipe_selector: gr.Dropdown
    refresh_recipes: gr.Button


def build_cookbook_filter_row() -> CookbookFilterHandles:
    """Build the cookbook filter row and the recipe selector.

    Adds (to the current Gradio context):
    - A ``gr.Row`` with cuisine / dietary / quick-only / search controls.
    - A second ``gr.Row`` with the recipe selector and refresh button.

    Returns a ``CookbookFilterHandles`` dataclass exposing all 5
    interactive components for event wiring in the parent tab builder.
    """
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
            choices=_DIETARY_CHOICES,
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
            # Gradio 6.x emits a UserWarning when the value is not in
            # choices. We start with an empty choices list and inject
            # the real ones via the initial-load handler. ``allow_custom_value``
            # silences the warning and lets us keep the "Open recipe"
            # placeholder behavior until the grid finishes loading.
            allow_custom_value=True,
            scale=2,
        )
        refresh_recipes = gr.Button("Refresh list", elem_classes="secondary", scale=1)

    return CookbookFilterHandles(
        cuisine_filter=cuisine_filter,
        dietary_filter=dietary_filter,
        quick_only=quick_only,
        search_box=search_box,
        recipe_selector=recipe_selector,
        refresh_recipes=refresh_recipes,
    )
