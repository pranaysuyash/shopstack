"""Market Intelligence tab — cross-source intelligence graph.

Thin tab builder wrapping :mod:`shopstack.ui.screens.market_intelligence` with
Gradio components: search filter, lane filter, refresh button, and the
full market intelligence graph HTML.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import loading_skeleton
from shopstack.ui.screens.market_intelligence import market_intelligence_view
from shopstack.ui.tabs.context import TabContext


def build_market_intel_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Market Intelligence tab.

    Args:
        blocks: Alias for the parent gr.Blocks.
        app: The root gr.Blocks instance for ``app.load(...)`` handlers.
        ctx: Shared dependencies (unused, part of uniform builder signature).
    """
    with gr.Tab(_tab_label("market_intel"), id="market_intel"):
        gr.Markdown("### Market Intelligence Graph")
        gr.HTML(
            "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
            "Cross-source price comparison, buy/skip/signal lanes, "
            "substitution suggestions, and reliability scoring."
            "</div>"
        )
        with gr.Row():
            mi_search = gr.Textbox(
                label="Search items",
                placeholder="e.g. tomato, onion, milk",
                scale=2,
            )
            mi_lane = gr.Dropdown(
                label="Lane filter",
                choices=[
                    ("All lanes", ""),
                    ("Buy Now", "buy"),
                    ("Use Soon First", "use_soon"),
                    ("Compare", "compare"),
                    ("Substitute", "substitute"),
                    ("Wait", "wait"),
                    ("Skip", "skip"),
                ],
                value="",
                scale=1,
            )
            mi_refresh = gr.Button("Refresh", elem_classes="secondary", scale=0)
        mi_output = gr.HTML(loading_skeleton("card"))

        mi_refresh.click(
            market_intelligence_view,
            [mi_search, mi_lane],
            mi_output,
            api_name="market_intel_refresh",
            api_description="Refresh market intelligence graph",
        )
        app.load(market_intelligence_view, inputs=[mi_search, mi_lane], outputs=mi_output)
