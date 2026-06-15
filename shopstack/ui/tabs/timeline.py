"""Timeline tab — Unified Timeline of household events.

Thin tab builder wrapping :mod:`shopstack.ui.screens.timeline` with
Gradio components: date-range slider, canonical-name filter, and
a refreshable HTML view.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import loading_skeleton
from shopstack.ui.screens.inventory import undo_last_change
from shopstack.ui.screens.timeline import timeline_view
from shopstack.ui.tabs.context import TabContext


def _timeline_refresh(canonical_name: str, days: int) -> str:
    """Bridge Gradio's positional (name, days) inputs to timeline_view's
    keyword args — timeline_view's 2nd positional param is ``lot_id``,
    not ``days``, so positional dispatch would pass ``days`` as ``lot_id``.
    """
    return timeline_view(canonical_name=canonical_name, days=days)


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
            _timeline_refresh,
            [tl_filter, tl_days],
            tl_output,
            api_name="timeline_refresh",
            api_description="Refresh the unified timeline view",
        )
        app.load(_timeline_refresh, inputs=[tl_filter, tl_days], outputs=tl_output)

        gr.Markdown("### Undo last change")
        gr.HTML(
            "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
            "Made a mistake adding, consuming, or moving an item? Paste its "
            "lot id below to reverse the most recent change."
            "</div>"
        )
        with gr.Row():
            tl_undo_lot_id = gr.Textbox(
                label="Lot id", placeholder="lot id or prefix", scale=2, elem_id="tl_undo_lot_id"
            )
            tl_undo_btn = gr.Button(
                "Undo last change", elem_classes="secondary", scale=0, elem_id="tl_undo_btn"
            )
        tl_undo_output = gr.HTML("")
        tl_undo_btn.click(
            undo_last_change,
            tl_undo_lot_id,
            tl_undo_output,
            api_name="undo_last_inventory_change",
            api_description="Undo the most recent change made to an inventory item",
        )
