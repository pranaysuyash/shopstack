"""Nutrition Coach tab — household nutrition coaching.

Thin tab builder wrapping :mod:`shopstack.ui.screens.nutrition_coach` with
Gradio components: household size input, dietary preference, refresh button,
and coaching HTML panel.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import loading_skeleton
from shopstack.ui.screens.nutrition_coach import nutrition_coach_screen
from shopstack.ui.tabs.context import TabContext


def build_nutrition_coach_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Nutrition Coach tab.

    Args:
        blocks: Alias for the parent gr.Blocks.
        app: The root gr.Blocks instance for ``app.load(...)`` handlers.
        ctx: Shared dependencies (unused, part of uniform builder signature).
    """
    with gr.Tab(_tab_label("nutrition"), id="nutrition"):
        gr.Markdown("### Nutrition Coach")
        gr.HTML(
            "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
            "Get nutrition coaching based on your current inventory, "
            "household size, and dietary preferences."
            "</div>"
        )
        with gr.Row():
            nc_size = gr.Number(label="Household size", value=4, precision=0, scale=1)
            nc_diet = gr.Dropdown(
                label="Dietary preference",
                choices=["vegetarian", "vegan", "omnivore"],
                value="vegetarian",
                scale=1,
            )
            nc_refresh = gr.Button("Refresh", elem_classes="secondary", scale=0)
        nc_output = gr.HTML(loading_skeleton("card"))

        nc_refresh.click(
            nutrition_coach_screen,
            [nc_size, nc_diet],
            nc_output,
            api_name="nutrition_coach_refresh",
            api_description="Refresh nutrition coaching panel",
        )
        app.load(nutrition_coach_screen, inputs=[nc_size, nc_diet], outputs=nc_output)
