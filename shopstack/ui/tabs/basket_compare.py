"""Basket tab — Compare sub-tab sub-builder.

The Compare sub-tab is a 3-way sub-tabbed view for price
intelligence:

1. **Stores** — Multi-source price comparison dashboard
   (``multi_source_price_view``), source registry status
   (``refresh_source_registry``), single-item lookup
   (``single_item_compare``), and basket compare
   (``basket_compare_view`` — multi-item, multi-source total).
2. **Market Graph** — Interactive market intelligence graph
   (``market_intelligence_view``) with a focus-item textbox
   and a lane filter (Buy / Use Soon / Compare / Substitute /
   Wait / Skip).
3. **Price History** — Per-item price trend charts
   (``price_memory_view`` — summary + price LinePlot + unit
   price LinePlot + DataFrame) and a price intelligence
   dashboard (``price_intelligence_view``).

Extracted from ``shopstack.ui.tabs.basket`` in Pass 8 so each
basket sub-tab lives in its own module (mirrors the
``memory_*`` sub-builder pattern).

**Pattern:** the sub-builder opens its own
``gr.Tab("Compare")`` inside the parent's ``gr.Tabs()`` context
and a nested ``gr.Tabs()`` for the 3 inner sub-tabs. Adds the
UI and wires the event handlers. The function returns ``None``
(no cross-tab references exist).
"""
from __future__ import annotations

import gradio as gr

from shopstack.ui.components.primitives import (
    empty_state_enhanced,
    loading_skeleton,
    with_loading_state,
)
from shopstack.ui.components.js_helpers import busy_js
from shopstack.ui.screens import (
    market_intelligence_view,
    multi_source_price_view,
    price_intelligence_view,
    price_memory_view,
    refresh_source_registry,
    single_item_compare,
)
from shopstack.ui.screens.price_compare import basket_compare_view
from shopstack.ui.tabs.context import TabContext


def build_basket_compare(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Compare sub-tab inside the parent's ``gr.Tabs()`` context.

    Opens a ``gr.Tab("Compare")`` with a nested ``gr.Tabs()``
    containing the 3 inner sub-tabs (Stores, Market Graph,
    Price History). Adds the UI and wires the event handlers.

    Args:
        app: The root ``gr.Blocks`` instance — needed for
            ``app.load(...)`` handlers (initial multi-source view,
            initial market intelligence view, initial price memory
            view, initial price intelligence view).
        ctx: Shared dependencies (unused in this sub-tab, kept
            for the uniform builder signature).

    Returns:
        None. The Compare sub-tab is self-contained: no
        components are referenced by other parts of the app.
    """
    with gr.Tab("Compare"):
        with gr.Tabs():
            # ── Multi-source price comparison ──
            with gr.Tab("Stores"):
                gr.Markdown("### Compare stores")
                gr.Markdown(
                    "Compare prices across the market sources we have loaded."
                )
                pc_button = gr.Button(
                    "Refresh Comparison", elem_classes="secondary"
                )
                pc_results = gr.HTML(loading_skeleton("card"))
                pc_status = gr.HTML(
                    empty_state_enhanced(
                        "Source registry status will appear here.",
                        icon="📡",
                    )
                )
                pc_button.click(
                    multi_source_price_view,
                    outputs=pc_results,
                    api_name="price_compare_refresh",
                    api_description="Refresh multi-source price comparison dashboard",
                )
                pc_status_btn = gr.Button(
                    "Check Status", elem_classes="secondary"
                )
                pc_status_btn.click(
                    refresh_source_registry,
                    outputs=pc_status,
                    api_name="price_compare_status",
                    api_description=(
                        "Check which market sources are registered and loaded"
                    ),
                )
                app.load(multi_source_price_view, outputs=pc_results)

                gr.Markdown("---")
                gr.Markdown("### Item lookup")
                with gr.Row():
                    pc_item_input = gr.Textbox(
                        label="Item Name",
                        placeholder="e.g. tomato, onion, milk",
                    )
                    pc_lookup_btn = gr.Button("Look Up")
                pc_lookup_result = gr.HTML(
                    empty_state_enhanced(
                        "Item comparison will appear here.",
                        icon="🔍",
                    )
                )
                pc_lookup_btn.click(
                    single_item_compare,
                    pc_item_input,
                    pc_lookup_result,
                    api_name="price_compare_item",
                    api_description=(
                        "Compare single item prices across all market sources"
                    ),
                )

                gr.Markdown("---")
                gr.Markdown("### Basket compare")
                gr.Markdown(
                    "Enter your shopping list — one item per line, with quantity and unit. "
                    "Get per-source totals and see where you'd save the most."
                )
                bc_items_input = gr.Textbox(
                    label="Items",
                    placeholder=(
                        "2kg onions\n"
                        "1L milk\n"
                        "500g tomatoes\n"
                        "12 eggs"
                    ),
                    lines=6,
                )
                with gr.Row():
                    bc_button = gr.Button(
                        "Compare Basket",
                        variant="primary",
                        elem_id="compare-basket-btn",
                    )
                    bc_example_btn = gr.Button(
                        "Load Example", elem_classes="secondary"
                    )
                bc_results = gr.HTML(
                    empty_state_enhanced(
                        "Enter your basket above and click Compare Basket to see store totals.",
                        icon="🧮",
                    )
                )
                bc_button.click(
                    basket_compare_view,
                    bc_items_input,
                    bc_results,
                    js=busy_js("compare-basket-btn", original_label="Compare Basket"),
                    api_name="price_compare_basket",
                    api_description=(
                        "Compare a multi-item basket total across all market sources"
                    ),
                ).then(
                    with_loading_state(bc_button, [])[1],
                    outputs=[bc_button],
                )
                bc_example_btn.click(
                    lambda: (
                        "2kg onion\n1.5kg potato\n500g tomato\n"
                        "1L milk\n12 eggs\ngreen chilli"
                    ),
                    outputs=bc_items_input,
                    api_name="price_compare_basket_example",
                    api_description=(
                        "Populate the basket price-compare input with a sample 6-item "
                        "Indian household shopping list (onion, potato, tomato, milk, "
                        "eggs, green chilli) for quick demo of the multi-store price "
                        "comparison flow."
                    ),
                )

            # ── Market intelligence graph ──
            with gr.Tab("Market Graph"):
                with gr.Row():
                    market_focus = gr.Textbox(
                        label="Focus item",
                        placeholder="tomato, onion, milk, coriander...",
                    )
                    market_lane = gr.Dropdown(
                        label="Lane",
                        choices=[
                            ("All", ""),
                            ("Buy", "buy"),
                            ("Use Soon", "use_soon"),
                            ("Compare", "compare"),
                            ("Substitute", "substitute"),
                            ("Wait", "wait"),
                            ("Skip", "skip"),
                        ],
                        value="",
                        allow_custom_value=False,
                    )
                    market_refresh = gr.Button(
                        "Refresh", elem_classes="secondary"
                    )
                market_graph_html = gr.HTML(loading_skeleton("card"))
                market_focus.change(
                    market_intelligence_view,
                    [market_focus, market_lane],
                    market_graph_html,
                    api_name="market_intelligence_search",
                    api_description="Search the market intelligence graph",
                )
                market_lane.change(
                    market_intelligence_view,
                    [market_focus, market_lane],
                    market_graph_html,
                    api_name="market_intelligence_lane",
                    api_description="Filter the market intelligence graph by lane",
                )
                market_refresh.click(
                    market_intelligence_view,
                    [market_focus, market_lane],
                    market_graph_html,
                    api_name="market_intelligence_refresh",
                    api_description="Refresh the market intelligence graph",
                )
                app.load(
                    market_intelligence_view,
                    inputs=[market_focus, market_lane],
                    outputs=market_graph_html,
                )

            # ── Price history & intelligence ──
            with gr.Tab("Price History"):
                with gr.Row():
                    price_item = gr.Textbox(
                        label="Item Name",
                        placeholder="e.g. basmati rice",
                    )
                    price_search = gr.Button("Search")
                price_summary = gr.HTML(loading_skeleton("card"))
                with gr.Row():
                    price_plot = gr.LinePlot(
                        label="Price Trend",
                        x="date",
                        y="price",
                        title="Price over time",
                        x_title="Date",
                        y_title="Price (\u20b9)",
                        height=300,
                    )
                    unit_price_plot = gr.LinePlot(
                        label="Unit Price Trend",
                        x="date",
                        y="unit_price",
                        title="Unit price over time",
                        x_title="Date",
                        y_title="Unit Price (\u20b9)",
                        height=300,
                    )
                price_table = gr.DataFrame(label="Price History")
                price_search.click(
                    price_memory_view,
                    price_item,
                    [price_summary, price_plot, unit_price_plot, price_table],
                    api_name="price_search",
                    api_description=(
                        "Load price history and trend charts for a product"
                    ),
                )
                app.load(
                    price_memory_view,
                    inputs=price_item,
                    outputs=[price_summary, price_plot, unit_price_plot, price_table],
                )
                gr.Markdown("### Price intelligence")
                pi_html = gr.HTML(loading_skeleton("card"))
                pi_refresh = gr.Button(
                    "Refresh", elem_classes="secondary"
                )
                pi_refresh.click(
                    price_intelligence_view,
                    outputs=pi_html,
                    api_name="price_intelligence_refresh",
                    api_description="Refresh price intelligence dashboard",
                )
                app.load(price_intelligence_view, outputs=pi_html)
