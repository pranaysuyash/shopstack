"""Basket tab — shopping planning, lists, price comparison, market intelligence, and receipt scanning.

This is the largest top-level tab (8 sub-tabs, ~400 lines) and the one that
covers everything the user does *before* a shopping trip: planning, list
building, price comparison, and receipt scanning.

Sub-tabs:
1. **Plan** — Unified shopping plan (classify, price, substitute, score deals)
2. **Optimizer** — Basket optimizer screen (delegated to `build_basket_screen()`)
3. **Shopping List** — Create, view, complete, mark purchased, generate poster, reconcile
4. **Price Compare** — Multi-source comparison + item lookup + basket compare
5. **Market Map** — Market intelligence graph (focus + lane filter)
6. **Price Check** — Price history with trend charts + price intelligence
7. **Scan Receipt** — OCR receipt scanning with editable draft

The tab is self-contained: no components are referenced by other parts of the
app. All `app.load` handlers register here.
"""
from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.screens import (
    build_shopping_list_and_refresh,
    complete_shopping_list,
    confirm_reconciliation,
    generate_shopping_poster,
    get_reconciliation_draft,
    market_intelligence_view,
    mark_items_purchased,
    multi_source_price_view,
    price_intelligence_view,
    price_memory_view,
    refresh_source_registry,
    run_unified_plan,
    shopping_list_item_choices,
    shopping_list_view_with_cards,
    shopping_list_substitutions_view,
    single_item_compare,
    unified_plan_summary,
)
from shopstack.ui.screens.basket import build_basket_screen
from shopstack.ui.screens.price_compare import basket_compare_view
from shopstack.ui.screens.receipt import (
    _load_ocr_model,
    receipt_confirm,
    receipt_parse_text,
    receipt_scan_ocr,
)
from shopstack.ui.tabs.context import TabContext


def build_basket_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Basket tab inside the parent's `gr.Tabs` context.

    Args:
        blocks: Alias for the parent gr.Blocks. Kept for symmetry with other
            tab builders.
        app: The root gr.Blocks instance — needed for `app.load(...)` handlers.
        ctx: Shared dependencies (unused in this tab, but part of the
            uniform builder signature).

    Returns:
        None. The Basket tab is self-contained: no components are referenced
        by other parts of the app, so no TabHandles dataclass is needed.
    """
    with gr.Tab(_tab_label("basket"), id="basket"):
        with gr.Tabs():
            # ── Unified Plan ──
            with gr.Tab("Plan"):
                gr.Markdown("### Unified Shopping Plan")
                gr.Markdown("Enter items to classify, price, find substitutions, and score deals in one pass.")
                with gr.Row():
                    up_goal = gr.Textbox(label="Goal", placeholder="Weekly groceries", scale=1)
                    up_items = gr.Textbox(
                        label="Items (comma or newline separated)",
                        placeholder="milk, bread, tomato, onion, rice, egg",
                        lines=3,
                        scale=2,
                    )
                up_run_btn = gr.Button("Run Plan", variant="primary")
                up_summary = gr.HTML("")
                up_detail = gr.HTML("")
                up_run_btn.click(
                    run_unified_plan,
                    [up_goal, up_items],
                    [up_summary, up_detail],
                    api_name="unified_plan",
                    api_description="Run unified shopping plan: classify, price, substitute, score deals",
                )
                app.load(unified_plan_summary, outputs=up_summary)

            # ── Optimizer ──
            with gr.Tab("Optimizer"):
                build_basket_screen()

            # ── Shopping List ──
            with gr.Tab("Shopping List"):
                sl_cards = gr.HTML("")
                sl_substitutions = gr.HTML("")
                sl_display = gr.HTML("")
                sl_table = gr.DataFrame(label="Items")
                sl_list_id = gr.State("")
                sl_goal = gr.State("")
                with gr.Row():
                    goal_input = gr.Textbox(label="List Goal (e.g. Weekly Groceries)", placeholder="What's this list for?")
                    items_input = gr.Textbox(
                        label="Shopping list",
                        placeholder="milk, bread, tomato, onion",
                        lines=3,
                    )
                sl_share = gr.HTML("")

                # --- Shopping Poster Export ---
                with gr.Accordion("Generate Shopping Poster", open=False):
                    gr.Markdown(
                        "Export your shopping decisions as a printable poster image. "
                        "Each item is rendered as a decision card with its buy/skip/optional status."
                    )
                    with gr.Row():
                        poster_btn = gr.Button("\U0001f5bc Generate Poster", variant="primary", scale=1)
                    poster_status = gr.HTML("")
                    with gr.Row():
                        poster_preview = gr.Image(
                            label="Poster Preview",
                            show_label=True,
                            visible=True,
                            height=400,
                            scale=2,
                        )
                        poster_download = gr.File(
                            label="Download Poster",
                            visible=True,
                            scale=1,
                        )
                    poster_btn.click(
                        generate_shopping_poster,
                        outputs=[poster_preview, poster_status],
                        api_name="generate_poster",
                        api_description="Generate a shopping poster from the active shopping list",
                    ).then(
                        lambda poster_path: gr.update(value=poster_path, visible=bool(poster_path)),
                        poster_preview,
                        poster_download,
                    )

                # --- Reconciliation UI ---
                with gr.Accordion("List Reconciliation (Review & Add to Inventory)", open=False):
                    sl_reconciliation_table = gr.Dataframe(
                        headers=["Item", "Qty", "Unit", "Action (bought/skipped/substituted)", "Price Paid", "Substitution Note"],
                        datatype=["str", "number", "str", "str", "number", "str"],
                        column_count=6,
                        interactive=True,
                        label="Reconciliation Draft (Edit before confirming)"
                    )
                    with gr.Row():
                        sl_reconcile_load_btn = gr.Button("Load Active List", elem_classes="secondary")
                        sl_reconcile_confirm_btn = gr.Button("Confirm & Complete List", variant="primary")
                    sl_reconcile_result = gr.HTML("")

                with gr.Row():
                    sl_item_dropdown = gr.Dropdown(
                        label="Select items to mark as purchased",
                        choices=[],
                        value=[],
                        multiselect=True,
                        interactive=True,
                    )
                    sl_item_refresh = gr.Button("Refresh Items", elem_classes="secondary")
                    sl_mark_purchased_btn = gr.Button("Mark Selected as Purchased", variant="primary")
                sl_mark_result = gr.HTML("")
                sl_item_refresh.click(
                    shopping_list_item_choices,
                    outputs=sl_item_dropdown,
                    api_name="refresh_items",
                    api_description="Refresh shopping list item selector",
                )
                sl_mark_purchased_btn.click(
                    mark_items_purchased,
                    sl_item_dropdown,
                    sl_mark_result,
                    api_name="mark_purchased",
                    api_description="Mark selected shopping list items as purchased",
                ).then(
                    shopping_list_view_with_cards,
                    outputs=[sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share],
                ).then(
                    shopping_list_substitutions_view,
                    outputs=sl_substitutions,
                ).then(
                    shopping_list_item_choices,
                    outputs=sl_item_dropdown
                )
                app.load(shopping_list_item_choices, outputs=sl_item_dropdown)
                app.load(shopping_list_view_with_cards, outputs=[sl_cards, sl_display, sl_table,
                                                                  sl_list_id, sl_goal, sl_share])
                app.load(shopping_list_substitutions_view, outputs=sl_substitutions)

                with gr.Row():
                    create_btn = gr.Button("Build Shopping Plan")
                    refresh_btn = gr.Button("Refresh", elem_classes="secondary")
                    complete_btn = gr.Button("Complete List & Add to Inventory", variant="primary")
                create_output = gr.HTML("")
                create_btn.click(
                    build_shopping_list_and_refresh,
                    [goal_input, items_input],
                    [create_output, sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share],
                    api_name="build_list",
                    api_description="Build a shopping list for current goal and refresh cards/table",
                ).then(
                    shopping_list_substitutions_view,
                    outputs=sl_substitutions,
                ).then(
                    shopping_list_item_choices,
                    outputs=sl_item_dropdown
                )
                refresh_btn.click(
                    shopping_list_view_with_cards,
                    outputs=[sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share],
                    api_name="refresh_shopping_list",
                    api_description="Refresh shopping list cards, table, and state",
                )

                sl_reconcile_load_btn.click(
                    get_reconciliation_draft,
                    None,
                    [sl_reconciliation_table, sl_list_id, sl_reconcile_result],
                )

                sl_reconcile_confirm_btn.click(
                    confirm_reconciliation,
                    [sl_reconciliation_table, sl_list_id],
                    sl_reconcile_result,
                ).then(
                    shopping_list_view_with_cards,
                    outputs=[sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share]
                ).then(
                    shopping_list_substitutions_view,
                    outputs=sl_substitutions,
                ).then(
                    shopping_list_item_choices,
                    outputs=sl_item_dropdown
                )

                complete_btn.click(
                    complete_shopping_list,
                    sl_list_id,
                    sl_reconcile_result,
                    api_name="complete_list",
                    api_description="Complete active shopping list and add purchased items to inventory",
                ).then(
                    shopping_list_view_with_cards,
                    outputs=[sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share]
                ).then(
                    shopping_list_substitutions_view,
                    outputs=sl_substitutions,
                ).then(
                    shopping_list_item_choices,
                    outputs=sl_item_dropdown
                )

            # ── Price Compare (Multi-Source) ──
            with gr.Tab("Price Compare"):
                gr.Markdown("### Compare prices across Swiggy, Blinkit, Zepto, and DMart")
                pc_button = gr.Button("Refresh Comparison", elem_classes="secondary")
                pc_results = gr.HTML("")
                pc_status = gr.HTML("")
                pc_button.click(
                    multi_source_price_view,
                    outputs=pc_results,
                    api_name="price_compare_refresh",
                    api_description="Refresh multi-source price comparison dashboard",
                )
                pc_status_btn = gr.Button("Check Registry Status", elem_classes="secondary")
                pc_status_btn.click(
                    refresh_source_registry,
                    outputs=pc_status,
                    api_name="price_compare_status",
                    api_description="Check which market sources are registered and loaded",
                )
                app.load(multi_source_price_view, outputs=pc_results)

                gr.Markdown("---")
                gr.Markdown("### Item Lookup")
                with gr.Row():
                    pc_item_input = gr.Textbox(label="Item Name", placeholder="e.g. tomato, onion, milk")
                    pc_lookup_btn = gr.Button("Look Up")
                pc_lookup_result = gr.HTML("")
                pc_lookup_btn.click(
                    single_item_compare,
                    pc_item_input,
                    pc_lookup_result,
                    api_name="price_compare_item",
                    api_description="Compare single item prices across all market sources",
                )

                gr.Markdown("---")
                gr.Markdown("### Basket Compare")
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
                    bc_button = gr.Button("Compare Basket", variant="primary")
                    bc_example_btn = gr.Button("Load Example", elem_classes="secondary")
                bc_results = gr.HTML("")
                bc_button.click(
                    basket_compare_view,
                    bc_items_input,
                    bc_results,
                    api_name="price_compare_basket",
                    api_description="Compare a multi-item basket total across all market sources",
                )
                bc_example_btn.click(
                    lambda: "2kg onion\n1.5kg potato\n500g tomato\n1L milk\n12 eggs\ngreen chilli",
                    outputs=bc_items_input,
                    api_name="price_compare_basket_example",
                )

            # ── Market Map ──
            with gr.Tab("Market Map"):
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
                    market_refresh = gr.Button("Refresh", elem_classes="secondary")
                market_graph_html = gr.HTML("")
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
                app.load(market_intelligence_view, inputs=[market_focus, market_lane], outputs=market_graph_html)

            # ── Price Check ──
            with gr.Tab("Price Check"):
                with gr.Row():
                    price_item = gr.Textbox(label="Item Name", placeholder="e.g. basmati rice")
                    price_search = gr.Button("Search")
                price_summary = gr.HTML("")
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
                    api_description="Load price history and trend charts for a product",
                )
                app.load(price_memory_view, inputs=price_item,
                         outputs=[price_summary, price_plot, unit_price_plot, price_table])
                gr.Markdown("### Price Intelligence")
                pi_html = gr.HTML("")
                pi_refresh = gr.Button("Refresh", elem_classes="secondary")
                pi_refresh.click(
                    price_intelligence_view,
                    outputs=pi_html,
                    api_name="price_intelligence_refresh",
                    api_description="Refresh price intelligence dashboard",
                )
                app.load(price_intelligence_view, outputs=pi_html)

            # ── Scan Receipt ──
            with gr.Tab("Scan Receipt"):
                receipt_status = gr.HTML("")
                gr.Markdown("### Scan a Receipt")
                gr.Markdown("Upload a receipt image (OCR) or a text file containing the receipt text.")
                with gr.Row():
                    receipt_file = gr.File(label="Upload Receipt (image or .txt)", file_count="single")
                    receipt_scan_btn = gr.Button("Scan & Parse", variant="primary")
                receipt_raw_text = gr.Textbox(
                    label="Raw OCR Text / Paste Receipt Text",
                    lines=6,
                    placeholder="Paste receipt text here, or upload a file above and click Scan & Parse...",
                )

                receipt_df = gr.Dataframe(
                    headers=["Item", "Quantity", "Unit", "Price"],
                    datatype=["str", "number", "str", "number"],
                    column_count=4,
                    interactive=True,
                    label="Editable Receipt Draft",
                )
                with gr.Row():
                    receipt_merchant = gr.Textbox(label="Store Name", interactive=True)
                    receipt_date = gr.Textbox(label="Purchase Date (YYYY-MM-DD)", interactive=True)

                receipt_confirm_btn = gr.Button("Confirm & Add to Inventory", variant="primary")
                receipt_result = gr.HTML("")
                receipt_scan_btn.click(
                    receipt_scan_ocr,
                    receipt_file,
                    [receipt_df, receipt_merchant, receipt_date, receipt_raw_text, receipt_status],
                    api_name="receipt_scan",
                    api_description="Extract receipt text from uploaded file",
                )
                receipt_raw_text.change(
                    receipt_parse_text,
                    receipt_raw_text,
                    [receipt_df, receipt_merchant, receipt_date],
                    api_name="receipt_parse",
                    api_description="Parse pasted or OCR'd receipt text into item suggestions",
                )
                receipt_confirm_btn.click(
                    receipt_confirm,
                    [receipt_df, receipt_merchant, receipt_date, receipt_raw_text],
                    receipt_result,
                    api_name="receipt_confirm",
                    api_description="Confirm parsed receipt lines and add items to inventory",
                )
                app.load(_load_ocr_model, outputs=receipt_status)
