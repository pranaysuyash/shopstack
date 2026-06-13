"""Basket tab — shopping planning, lists, price comparison, and receipt scanning.

This is the largest top-level tab (~400 lines) and covers everything the
user does *before* a shopping trip: planning, list building, price
comparison, and receipt/recipe input.

Sub-tabs (5):
1. **Plan** — Unified shopping plan (classify, price, substitute, score deals)
2. **Best Basket** — Basket optimizer screen (delegated to ``build_basket_screen()``)
3. **Shopping List** — Create, view, complete, mark purchased, generate poster, reconcile
4. **Compare** — Multi-source comparison, market intelligence graph, price history & intelligence
5. **Add Items** — Receipt OCR scanning and recipe-to-shopping-list conversion

The tab is self-contained: no components are referenced by other parts of the
app. All ``app.load`` handlers register here.
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
    shopping_list_substitutions_view,
    shopping_list_view_with_cards,
    recipe_text_to_shopping_list,
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
from shopstack.ui.components.primitives import (
    busy_js,
    confirm_hide_updates,
    confirm_toggle_updates,
    empty_state_enhanced,
    loading_skeleton,
    with_loading_state,
)
from shopstack.ui.tabs.context import TabContext


def build_basket_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Basket tab inside the parent's ``gr.Tabs`` context.

    Args:
        blocks: Alias for the parent gr.Blocks. Kept for symmetry with other
            tab builders.
        app: The root gr.Blocks instance — needed for ``app.load(...)`` handlers.
        ctx: Shared dependencies (unused in this tab, but part of the
            uniform builder signature).

    Returns:
        None. The Basket tab is self-contained: no components are referenced
        by other parts of the app, so no TabHandles dataclass is needed.
    """
    with gr.Tab(_tab_label("basket"), id="basket"):
        # ── Phase 8 #25 Trip Advisor banner (sits above sub-tabs) ──
        from shopstack.ui.screens.trip_advisor import trip_advisor_screen
        def _trip_advisor() -> str:
            try:
                return trip_advisor_screen()
            except Exception as exc:
                return f"<div>Trip advisor unavailable: {exc}</div>"
        trip_advisor_html = gr.HTML(_trip_advisor())
        trip_advisor_refresh = gr.Button(
            "🔄 Refresh trip advisor", elem_classes="secondary", size="sm"
        )
        trip_advisor_refresh.click(_trip_advisor, outputs=trip_advisor_html,
                                   api_name="trip_advisor_refresh",
                                   api_description="Refresh trip advisor banner")
        app.load(_trip_advisor, outputs=trip_advisor_html)

        with gr.Tabs():
            # ── Unified Plan ──
            with gr.Tab("Plan"):
                gr.Markdown("### Plan groceries")
                gr.Markdown("Turn a rough idea into a list, then see what to buy, skip, or compare.")
                with gr.Row():
                    up_goal = gr.Textbox(label="Goal", placeholder="Weekly groceries", scale=1)
                    up_items = gr.Textbox(
                        label="Items (comma or newline separated)",
                        placeholder="milk, bread, tomato, onion, rice, egg",
                        lines=3,
                        scale=2,
                    )
                up_run_btn = gr.Button("Run Plan", variant="primary", elem_id="run-plan-btn")
                up_summary = gr.HTML(loading_skeleton("card"))
                up_detail = gr.HTML(
                    empty_state_enhanced(
                        "Detailed plan results will appear here after you run a plan.",
                        icon="📑",
                    )
                )
                up_run_btn.click(
                    run_unified_plan,
                    [up_goal, up_items],
                    [up_summary, up_detail],
                    js=busy_js("run-plan-btn", original_label="Run Plan"),
                    api_name="unified_plan",
                    api_description="Run unified shopping plan: classify, price, substitute, score deals",
                ).then(
                    with_loading_state(up_run_btn, [])[1],
                    outputs=[up_run_btn],
                )
                app.load(unified_plan_summary, outputs=up_summary)

                # ── Phase 9 Smart basket (community-pool-aware) ──
                gr.Markdown("---")
                gr.Markdown("### 🧠 Smart basket")
                gr.Markdown(
                    "Community-pool-aware: items significantly above the "
                    "community median get a **wait** verdict; use-soon "
                    "items get a **buy now** verdict even when overpriced."
                )
                from shopstack.ui.screens.smart_basket import smart_basket_screen
                def _smart_basket_for_input(items_text: str) -> str:
                    if not items_text or not items_text.strip():
                        return smart_basket_screen()
                    # Parse the items: assume the same format as
                    # the unified plan — comma- or newline-separated
                    # canonical_name list.
                    raw_items: list[dict[str, Any]] = []
                    for token in items_text.replace("\n", ",").split(","):
                        t = token.strip().lower().replace(" ", "_")
                        if not t:
                            continue
                        raw_items.append({
                            "canonical_name": t,
                            "quantity": 1.0,
                            "unit": "unit",
                        })
                    return smart_basket_screen(items=raw_items)
                smart_basket_items = gr.Textbox(
                    label="Items to evaluate",
                    placeholder="milk, bread, rice, onion…",
                    value="milk, bread, rice, onion",
                    lines=2,
                )
                smart_basket_btn = gr.Button(
                    "Run smart basket", variant="primary",
                )
                smart_basket_html = gr.HTML(loading_skeleton("card"))
                smart_basket_btn.click(
                    _smart_basket_for_input,
                    smart_basket_items,
                    smart_basket_html,
                    api_name="smart_basket_run",
                    api_description="Evaluate the basket against the community pool + use-soon data",
                )
                app.load(
                    _smart_basket_for_input,
                    smart_basket_items,
                    smart_basket_html,
                )

            # ── Optimizer ──
            with gr.Tab("Best Basket"):
                build_basket_screen()

            # ── Shopping List ──
            with gr.Tab("Shopping List"):
                sl_cards = gr.HTML(loading_skeleton("card"))
                sl_substitutions = gr.HTML(loading_skeleton("text"))
                sl_display = gr.HTML(loading_skeleton("card"))
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
                sl_share = gr.HTML(loading_skeleton("text"))

                # --- Shopping Poster Export ---
                with gr.Accordion("Print shopping list", open=False):
                    gr.Markdown(
                        "Export the list as a printable poster image. Each item is rendered as a simple buy / skip / optional card."
                    )
                    with gr.Row():
                        poster_btn = gr.Button("\U0001f5bc Generate Poster", variant="primary", scale=1)
                    poster_status = gr.HTML(
                    empty_state_enhanced(
                        "Poster generation status will appear here.",
                        icon="🖼️",
                    )
                )
                    with gr.Row():
                        poster_preview = gr.Image(
                            label="Poster Preview",
                            show_label=True,
                            visible=True,
                            height=400,
                            scale=2,
                            value=None,
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
                    js="() => showToast('Generating poster...', 'info')",
                ).then(
                        lambda poster_path: gr.update(value=poster_path, visible=bool(poster_path)),
                        poster_preview,
                        poster_download,
                    )

                # --- Reconciliation UI ---
                with gr.Accordion("Put groceries away", open=False):
                    sl_reconciliation_table = gr.Dataframe(
                        headers=["Item", "Qty", "Unit", "Action (bought/skipped/substituted)", "Price Paid", "Substitution Note"],
                        datatype=["str", "number", "str", "str", "number", "str"],
                        column_count=6,
                        interactive=True,
                        label="Put-away draft (edit before confirming)"
                    )
                    with gr.Row():
                        sl_reconcile_load_btn = gr.Button("Load Active List", elem_classes="secondary")
                        sl_reconcile_confirm_btn = gr.Button("Confirm & Finish", variant="primary")
                    sl_reconcile_result = gr.HTML(
                    empty_state_enhanced(
                        "Put-away results will appear here.",
                        icon="📋",
                    )
                )

                with gr.Row():
                    sl_item_dropdown = gr.Dropdown(
                        label="Items already bought",
                        choices=[],
                        value=[],
                        multiselect=True,
                        interactive=True,
                    )
                    sl_item_refresh = gr.Button("Refresh Items", elem_classes="secondary")
                    sl_mark_purchased_btn = gr.Button("Mark as Bought", variant="stop")
                sl_mark_confirm = gr.Group(visible=False)
                with sl_mark_confirm:
                    gr.Markdown("⚠ **Mark the selected items as bought?**")
                    with gr.Row():
                        sl_mark_yes = gr.Button("Yes, mark bought", variant="stop")
                        sl_mark_no = gr.Button("Cancel", elem_classes="secondary")
                sl_mark_result = gr.HTML(
                    empty_state_enhanced(
                        "Select items above and click Mark as Bought to record the purchase.",
                        icon="✓",
                    )
                )
                sl_item_refresh.click(
                    shopping_list_item_choices,
                    outputs=sl_item_dropdown,
                    api_name="refresh_items",
                    api_description="Refresh shopping list item selector",
                )
                # 2-step confirmation: first click reveals the confirm group;
                # the yes button fires mark_items_purchased and restores state on completion.
                sl_mark_purchased_btn.click(
                    confirm_toggle_updates,
                    outputs=[sl_mark_purchased_btn, sl_mark_confirm],
                )
                sl_mark_yes.click(
                    mark_items_purchased,
                    sl_item_dropdown,
                    sl_mark_result,
                    api_name="mark_purchased",
                    api_description="Mark selected shopping list items as purchased",
                    js="() => showToast('Marking items as bought...', 'info')",
                ).then(
                    confirm_hide_updates,
                    outputs=[sl_mark_purchased_btn, sl_mark_confirm],
                ).then(
                    shopping_list_view_with_cards,
                    outputs=[sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share],
                ).then(
                    shopping_list_substitutions_view,
                    outputs=sl_substitutions,
                ).then(
                    shopping_list_item_choices,
                    outputs=sl_item_dropdown,
                )
                sl_mark_no.click(
                    confirm_hide_updates,
                    outputs=[sl_mark_purchased_btn, sl_mark_confirm],
                )
                app.load(shopping_list_item_choices, outputs=sl_item_dropdown)
                app.load(shopping_list_view_with_cards, outputs=[sl_cards, sl_display, sl_table,
                                                                  sl_list_id, sl_goal, sl_share])
                app.load(shopping_list_substitutions_view, outputs=sl_substitutions)

                with gr.Row():
                    create_btn = gr.Button("Build Shopping List")
                    refresh_btn = gr.Button("Refresh", elem_classes="secondary")
                    complete_btn = gr.Button("Finish List & Add to Pantry", variant="stop")
                complete_confirm = gr.Group(visible=False)
                with complete_confirm:
                    gr.Markdown(
                        "⚠ **Finish the list and move all bought items to the pantry?** "
                        "This commits the entire list and is hard to undo."
                    )
                    with gr.Row():
                        complete_yes = gr.Button("Yes, finish the list", variant="stop")
                        complete_no = gr.Button("Cancel", elem_classes="secondary")
                create_output = gr.HTML(
                    empty_state_enhanced(
                        "Build results will appear here.",
                        icon="🛒",
                    )
                )
                create_btn.click(
                    build_shopping_list_and_refresh,
                    [goal_input, items_input],
                    [create_output, sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share],
                    api_name="build_list",
                    api_description="Build a shopping list for current goal and refresh cards/table",
                    js="() => showToast('Building shopping list...', 'info')",
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
                    js="() => showToast('Confirming put-away...', 'info')",
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

                # 2-step confirmation: first click reveals the confirm group;
                # the yes button fires complete_shopping_list and restores state on completion.
                complete_btn.click(
                    confirm_toggle_updates,
                    outputs=[complete_btn, complete_confirm],
                )
                complete_yes.click(
                    complete_shopping_list,
                    sl_list_id,
                    sl_reconcile_result,
                    api_name="complete_list",
                    api_description="Complete active shopping list and add purchased items to inventory",
                    js="() => showToast('Finishing list and adding to pantry...', 'info')",
                ).then(
                    confirm_hide_updates,
                    outputs=[complete_btn, complete_confirm],
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
                complete_no.click(
                    confirm_hide_updates,
                    outputs=[complete_btn, complete_confirm],
                )

            # ── Compare (merged: stores + market graph + price history) ──
            with gr.Tab("Compare"):
                with gr.Tabs():
                    # ── Multi-source price comparison ──
                    with gr.Tab("Stores"):
                        gr.Markdown("### Compare stores")
                        gr.Markdown("Compare prices across the market sources we have loaded.")
                        pc_button = gr.Button("Refresh Comparison", elem_classes="secondary")
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
                        pc_status_btn = gr.Button("Check Registry Status", elem_classes="secondary")
                        pc_status_btn.click(
                            refresh_source_registry,
                            outputs=pc_status,
                            api_name="price_compare_status",
                            api_description="Check which market sources are registered and loaded",
                        )
                        app.load(multi_source_price_view, outputs=pc_results)

                        gr.Markdown("---")
                        gr.Markdown("### Item lookup")
                        with gr.Row():
                            pc_item_input = gr.Textbox(label="Item Name", placeholder="e.g. tomato, onion, milk")
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
                            api_description="Compare single item prices across all market sources",
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
                            bc_button = gr.Button("Compare Basket", variant="primary", elem_id="compare-basket-btn")
                            bc_example_btn = gr.Button("Load Example", elem_classes="secondary")
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
                            api_description="Compare a multi-item basket total across all market sources",
                        ).then(
                            with_loading_state(bc_button, [])[1],
                            outputs=[bc_button],
                        )
                        bc_example_btn.click(
                            lambda: "2kg onion\n1.5kg potato\n500g tomato\n1L milk\n12 eggs\ngreen chilli",
                            outputs=bc_items_input,
                            api_name="price_compare_basket_example",
                            api_description="Populate the basket price-compare input with a sample 6-item Indian household shopping list (onion, potato, tomato, milk, eggs, green chilli) for quick demo of the multi-store price comparison flow.",
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
                            market_refresh = gr.Button("Refresh", elem_classes="secondary")
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
                        app.load(market_intelligence_view, inputs=[market_focus, market_lane], outputs=market_graph_html)

                    # ── Price history & intelligence ──
                    with gr.Tab("Price History"):
                        with gr.Row():
                            price_item = gr.Textbox(label="Item Name", placeholder="e.g. basmati rice")
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
                            api_description="Load price history and trend charts for a product",
                        )
                        app.load(price_memory_view, inputs=price_item,
                                 outputs=[price_summary, price_plot, unit_price_plot, price_table])
                        gr.Markdown("### Price intelligence")
                        pi_html = gr.HTML(loading_skeleton("card"))
                        pi_refresh = gr.Button("Refresh", elem_classes="secondary")
                        pi_refresh.click(
                            price_intelligence_view,
                            outputs=pi_html,
                            api_name="price_intelligence_refresh",
                            api_description="Refresh price intelligence dashboard",
                        )
                        app.load(price_intelligence_view, outputs=pi_html)

            # ── Add Items (merged: receipt + recipe) ──
            with gr.Tab("Add Items"):
                with gr.Tabs():
                    # ── Receipt scanning ──
                    with gr.Tab("Receipt"):
                        receipt_status = gr.HTML(loading_skeleton("text"))
                        gr.Markdown("### Scan a receipt")
                        gr.Markdown("Upload a receipt image (OCR) or a text file containing the receipt text.")
                        with gr.Row():
                            receipt_file = gr.File(label="Upload Receipt (image or .txt)", file_count="single")
                            receipt_scan_btn = gr.Button("Scan & Parse", variant="primary", elem_id="receipt-scan-btn")
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
                        receipt_result = gr.HTML(
                    empty_state_enhanced(
                        "Receipt confirmation will appear here.",
                        icon="✅",
                    )
                )
                        receipt_scan_btn.click(
                            receipt_scan_ocr,
                            receipt_file,
                            [receipt_df, receipt_merchant, receipt_date, receipt_raw_text, receipt_status],
                            js=busy_js("receipt-scan-btn", original_label="Scan & Parse"),
                            api_name="receipt_scan",
                            api_description="Extract receipt text from uploaded file",
                        ).then(
                            with_loading_state(receipt_scan_btn, [])[1],
                            outputs=[receipt_scan_btn],
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
                            js="() => showToast('Adding receipt items to inventory...', 'info')",
                        )
                        app.load(_load_ocr_model, outputs=receipt_status)

                    # ── Recipe to shopping list ──
                    with gr.Tab("From Recipe"):
                        gr.Markdown("### Recipe to shopping list")
                        gr.Markdown(
                            "Paste a recipe's ingredients section. The system parses "
                            "the text, diffs against your inventory, and shows what's "
                            "missing — paste the missing list into the **Shopping List** "
                            "tab to add it. (Text-only for now; OCR image upload is "
                            "future work.)"
                        )
                        recipe_input = gr.Textbox(
                            label="Recipe ingredients",
                            placeholder=(
                                "- 2 cups rice\n"
                                "- 1 cup chickpea\n"
                                "- 1 tsp turmeric\n"
                                "- 1 onion, chopped\n"
                                "- 2 tomatoes, pureed\n"
                                "- Salt to taste"
                            ),
                            lines=10,
                        )
                        recipe_btn = gr.Button("Parse & Diff", variant="primary", elem_id="recipe-parse-btn")
                        recipe_result = gr.HTML(
                    empty_state_enhanced(
                        "Recipe diff will appear here.",
                        icon="🍳",
                    )
                )
                        recipe_btn.click(
                            recipe_text_to_shopping_list,
                            recipe_input,
                            recipe_result,
                            js=busy_js("recipe-parse-btn", original_label="Parse & Diff"),
                            api_name="recipe_to_list",
                            api_description="Parse pasted recipe text and diff against inventory",
                        ).then(
                            with_loading_state(recipe_btn, [])[1],
                            outputs=[recipe_btn],
                        )
