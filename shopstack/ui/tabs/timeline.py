"""Timeline tab — Unified Timeline of household events.

Thin tab builder wrapping :mod:`shopstack.ui.screens.timeline` with
Gradio components: date-range slider, canonical-name filter, and
a refreshable HTML view.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import loading_skeleton
from shopstack.ui.screens.timeline import timeline_view
from shopstack.ui.tabs.context import TabContext


def build_timeline_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Timeline tab.

    Args:
        blocks: Alias for the parent gr.Blocks.
        app: The root gr.Blocks instance for ``app.load(...)`` handlers.
        ctx: Shared dependencies (unused, part of uniform builder signature).
    """
    with gr.Tab(_tab_label("timeline"), id="timeline"):
        gr.Markdown("### Unified Timeline")
        gr.HTML(
            "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
            "See every event across your household — purchases, consumption, "
            "movements, price observations, traces, and more."
            "</div>"
        )
        with gr.Row():
            tl_filter = gr.Textbox(
                label="Filter by item name",
                placeholder="e.g. milk, atta, rice",
                scale=2,
            )
            tl_days = gr.Number(label="Days back", value=30, precision=0, scale=1)
            tl_refresh = gr.Button("Refresh", elem_classes="secondary", scale=0)
        tl_output = gr.HTML(loading_skeleton("card"))

        tl_refresh.click(
            timeline_view,
            [tl_filter, tl_days],
            tl_output,
            api_name="timeline_refresh",
            api_description="Refresh the unified timeline view",
        )
        app.load(timeline_view, inputs=[tl_filter, tl_days], outputs=tl_output)
