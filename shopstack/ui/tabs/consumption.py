"""Consumption tab — quick-consume, consumption history, and rates.

Wraps :mod:`shopstack.ui.screens.consumption` with Gradio components:
smart consumption dashboard with quick tap buttons, batch logging, and
consumption rate stats.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import loading_skeleton
from shopstack.ui.screens.consumption import (
    batch_consume_with_context,
    consumption_dashboard,
    consumption_history,
    consumption_rates,
    quick_consume,
)
from shopstack.ui.tabs.context import TabContext


def build_consumption_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Consumption tab."""
    with gr.Tab(_tab_label("consumption"), id="consumption"):
        gr.Markdown("### Consumption Dashboard")
        cn_grid = gr.HTML(loading_skeleton("card"))
        cn_history = gr.HTML(loading_skeleton("text"))
        cn_rates = gr.HTML(loading_skeleton("text"))
        cn_refresh = gr.Button("Refresh", elem_classes="secondary")

        gr.Markdown("---")
        gr.Markdown("### Quick consume")
        with gr.Row():
            cn_lot = gr.Textbox(label="Lot ID", scale=2)
            cn_qty = gr.Number(label="Quantity", value=1.0, scale=1)
            cn_go = gr.Button("Consume", scale=0)
        cn_result = gr.HTML("")

        gr.Markdown("---")
        gr.Markdown("### Batch consume with context")
        cn_batch = gr.Textbox(label="Items (one per line: lot_id:qty)", lines=4,
                              placeholder="abc123: 0.5\ndef456: 1")
        with gr.Row():
            cn_meal = gr.Dropdown(label="Meal", choices=["breakfast", "lunch", "dinner", "snack", "other"],
                                  value="other", scale=1)
            cn_waste = gr.Dropdown(label="Waste?", choices=[("Normal", ""), ("Wasted", "waste")],
                                   value="", scale=1)
            cn_batch_go = gr.Button("Log batch", scale=0)
        cn_batch_result = gr.HTML("")

        cn_refresh.click(consumption_dashboard, outputs=[cn_grid, cn_history, cn_rates],
                         api_name="consumption_dashboard_refresh")
        cn_go.click(quick_consume, [cn_lot, cn_qty], cn_result,
                    api_name="consumption_tab_quick_consume")
        cn_batch_go.click(batch_consume_with_context, [cn_batch, cn_meal, cn_waste],
                          cn_batch_result, api_name="consumption_tab_batch_consume_context")
        app.load(consumption_dashboard, outputs=[cn_grid, cn_history, cn_rates])
