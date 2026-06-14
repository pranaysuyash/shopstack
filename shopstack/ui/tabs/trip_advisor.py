"""Trip Advisor tab — pre-trip advice: weather + inventory + expiry.

Thin tab builder wrapping :mod:`shopstack.ui.screens.trip_advisor` with
Gradio components: city input, refresh button, and HTML advice banner.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import loading_skeleton
from shopstack.ui.screens.trip_advisor import trip_advisor_screen
from shopstack.ui.tabs.context import TabContext


def build_trip_advisor_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Trip Advisor tab.

    Args:
        blocks: Alias for the parent gr.Blocks.
        app: The root gr.Blocks instance for ``app.load(...)`` handlers.
        ctx: Shared dependencies (unused, part of uniform builder signature).
    """
    with gr.Tab(_tab_label("trip_advisor"), id="trip_advisor"):
        gr.Markdown("### Trip Plans")
        gr.HTML(
            "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
            "Check what to buy, what to use soon, and what the weather is "
            "before heading to the store."
            "</div>"
        )
        with gr.Row():
            ta_city = gr.Textbox(
                label="City",
                value="mumbai",
                placeholder="e.g. mumbai, delhi, bangalore",
                scale=2,
            )
            ta_refresh = gr.Button("Refresh", elem_classes="secondary", scale=0)
        ta_output = gr.HTML(loading_skeleton("card"))

        ta_refresh.click(
            trip_advisor_screen,
            ta_city,
            ta_output,
            api_name="trip_advisor_refresh",
            api_description="Refresh trip advice",
        )
        app.load(trip_advisor_screen, inputs=ta_city, outputs=ta_output)
