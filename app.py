from __future__ import annotations

from datetime import date

import gradio as gr

from shopstack.ui.screens import (
    today_dashboard,
    shopping_list_view,
    shopping_list_create,
    shopping_list_view_with_cards,
    build_shopping_list_and_refresh,
    complete_shopping_list,
    shopping_list_item_choices,
    mark_items_purchased,
    get_reconciliation_draft,
    confirm_reconciliation,
    get_intelligence_dashboard,
    run_unified_plan,
    unified_plan_summary,
    consumption_dashboard,
    quick_consume,
    batch_consume_with_context,
    consumption_history,
    consumption_rates,
    market_lens_process,
    market_lens_confirm_buy,
    market_lens_skip,
    market_lens_save_trace,
    market_lens_barcode_add,
    ask_shopstack,
    add_purchase_form,
    inventory_view,
    inventory_cards_view,
    consume_item,
    consume_items_batch,
    add_purchase_batch,
    use_soon_view,
    model_budget_view,
    provider_status_badge,
    runtime_proof_view,
    price_memory_view,
    price_intelligence_view,
    market_intelligence_view,
    household_map_view,
    agent_trace_view,
    agent_trace_detail,
    agent_trace_bootstrap,
    agent_trace_export_file,
    agent_trace_refresh,
    agent_trace_search_filter,
    trace_bundle,
    field_notes_view,
    field_notes_save,
    export_data_json,
    export_data_csv,
    import_data_file,
    generate_shopping_poster,
)
from shopstack.ui.screens.other import move_inventory_to_location
from shopstack.ui.screens.receipt import (
    receipt_scan_ocr,
    receipt_parse_text,
    receipt_confirm,
    _load_ocr_model,
)
from shopstack.ui.screens.nutrition import nutrition_lookup_view, nutrition_kitchen_view
from shopstack.ui.screens.price_compare import (
    multi_source_price_view,
    single_item_compare,
    refresh_source_registry,
)
from shopstack.ui.screens.basket import build_basket_screen
from shopstack.ui.components import WORKFLOW_STEPS, workflow_header, workflow_title_bar
from shopstack.ui.theme import CSS
from shopstack.ui.tabs.context import TabContext
from shopstack.ui.tabs.today import build_today_tab, TodayTabHandles

from pathlib import Path
from shopstack.app_context import APP_DESCRIPTION, APP_NAME, db, providers, tools, planner, model_registry
from shopstack.app_context import current_user_id, list_households, switch_household, add_household
from shopstack.config import settings
from shopstack.module_registry import tab_label as _tab_label


def _model_download_status() -> str:
    """Check whether the configured MLX planner model is cached locally.
    Returns an HTML snippet if a download is pending, or empty string if cached.
    """
    try:
        import os as _os

        mlx_model = settings.local_mlx_model
        if not mlx_model:
            return ""

        # Check HF hub cache
        hf_home = _os.environ.get("HF_HOME", _os.path.expanduser("~/.cache/huggingface"))
        hf_cache = Path(hf_home) / "hub"
        model_dir_name = "models--" + mlx_model.replace("/", "--")
        model_cache_dir = hf_cache / model_dir_name

        if model_cache_dir.is_dir():
            snapshots_dir = model_cache_dir / "snapshots"
            if snapshots_dir.is_dir():
                for snap in snapshots_dir.iterdir():
                    if snap.is_dir() and any(
                        f.suffix in (".safetensors", ".gguf")
                        for f in snap.iterdir()
                    ):
                        return ""
            return ""

        return (
            "<div style='font-size:11px;color:var(--amber);margin-top:4px;'>"
            f"<span>\u23F3 {mlx_model.split('/')[-1]} download pending (first query triggers it)</span>"
            "</div>"
        )
    except Exception:
        return ""


def _runtime_label() -> str:
    try:
        runtime = providers.get_runtime_diagnostics()
        loaded_real = [
            r for r in runtime.providers
            if getattr(r, "loaded", False) and getattr(r, "backend", "") != "mock"
        ]
        blocked = [r for r in runtime.providers if getattr(r, "blocked_by_off_grid", False)]
        if loaded_real and any(getattr(r, "backend", "") in {"openai", "huggingface", "whisper"} for r in loaded_real):
            return "Cloud runtime"
        if loaded_real:
            return "Local runtime"
        if blocked:
            return "Off-grid mock mode"
        return "Local mock mode"
    except Exception:
        return "Local runtime"


def build_app() -> gr.Blocks:
    runtime_label = _runtime_label()
    with gr.Blocks(title=APP_NAME) as app:
        header_html = f"""
<div class=\"app-header\">
  <div>
    <h1 class=\"brand-title\">{APP_NAME}</h1>
    <div class=\"brand-subtitle\">{APP_DESCRIPTION}</div>
  </div>
  <div>
    <div class=\"env-badge\">{runtime_label}</div>
    {_model_download_status()}
    <button onclick=\"toggleTheme()\" aria-label=\"Toggle light/dark theme\" title=\"Toggle theme\" style=\"margin-top:4px;background:none;border:1px solid var(--border);border-radius:var(--radius-sm);padding:4px 10px;cursor:pointer;font-size:11px;color:var(--text-muted);\">🌓</button>
  </div>
</div>"""
        header_script = """
<script>
(function() {
  var t = localStorage.getItem('shopstack-theme');
  if (t) {
    document.documentElement.setAttribute('data-theme', t);
  }
})();
function toggleTheme() {
  var e = document.documentElement;
  var t = e.getAttribute('data-theme');
  var n = (t === 'dark' ? 'light' : 'dark');
  e.setAttribute('data-theme', n);
  localStorage.setItem('shopstack-theme', n);
}
document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  var tabs = Array.from(document.querySelectorAll('[data-testid^=tab-], .tabs > button[role=tab]'));
  var idx = tabs.findIndex(t => t.getAttribute('aria-selected') === 'true');
  if (e.key === 'j' || e.key === 'ArrowRight') {
    e.preventDefault();
    var next = (idx + 1) % tabs.length;
    tabs[next] && tabs[next].click();
  } else if (e.key === 'k' || e.key === 'ArrowLeft') {
    e.preventDefault();
    var prev = (idx - 1 + tabs.length) % tabs.length;
    tabs[prev] && tabs[prev].click();
  }
});
</script>"""
        gr.HTML(header_html + header_script, padding=True)

        # ── Household switcher (inline row below header) ──
        def _household_choices() -> list[tuple[str, str]]:
            households = list_households()
            choices = [(h["name"], h["household_id"]) for h in households]
            return choices

        def _switch_and_refresh(household_id: str) -> tuple:
            """Switch household, return updated dropdown value + refresh dashboard."""
            if not household_id:
                return gr.update(), *today_dashboard()
            switch_household(household_id)
            return gr.update(value=household_id), *today_dashboard()

        def _show_add_form() -> gr.update:
            return gr.update(visible=True)

        def _hide_add_form() -> gr.update:
            return gr.update(visible=False)

        def _create_household(name: str) -> tuple:
            """Create a new household, switch to it, and refresh the dashboard."""
            name = (name or "").strip()
            if not name:
                return gr.update(), gr.update(visible=False), *today_dashboard()

            # Slugify the name for a household ID
            household_id = name.lower().replace(" ", "_")
            import re
            household_id = re.sub(r"[^a-z0-9_]", "", household_id)
            if not household_id:
                household_id = f"household_{abs(hash(name)) % 10000}"

            created = add_household(household_id, name)
            if not created:
                # Household ID collision; append a suffix
                import random
                household_id = f"{household_id}_{random.randint(100,999)}"
                add_household(household_id, name)

            switch_household(household_id)
            choices = [(h["name"], h["household_id"]) for h in list_households()]
            return (
                gr.update(choices=choices, value=household_id),
                gr.update(visible=False),
                *today_dashboard(),
            )

        with gr.Row(variant="compact", elem_classes="household-bar"):
            household_dropdown = gr.Dropdown(
                label="Household",
                choices=_household_choices(),
                value=current_user_id(),
                interactive=True,
                allow_custom_value=True,
                scale=1,
            )
            add_hh_btn = gr.Button(
                "+",
                scale=0,
                min_width=40,
                elem_classes="household-add-btn",
            )
            gr.HTML(
                "<div style='display:flex;align-items:center;gap:8px;font-size:11px;color:var(--text-dim);'>"
                "Switch between households or add a new one.</div>",
                scale=3,
            )

        # Hidden add-household form (shown when + is clicked)
        with gr.Row(visible=False, variant="compact", elem_classes="household-add-form") as hh_add_row:
            hh_name_input = gr.Textbox(
                label="New household name",
                placeholder="e.g. My Home, Beach House, Office",
                scale=2,
            )
            hh_create_btn = gr.Button("Create", variant="primary", scale=0)
            hh_cancel_btn = gr.Button("Cancel", scale=0, elem_classes="secondary")


        # Refresh dropdown choices on initial load
        app.load(
            lambda: gr.update(choices=_household_choices(), value=current_user_id()),
            outputs=household_dropdown,
        )

        # ── 5-tab daily loop: Today → Shopping → Scan & Compare → Pantry → Insights ──
        with gr.Tabs(elem_classes="tabs") as tabs:

            # ═══════════════════════════════════════════════════════════════
            # Tab 1: Today — what matters now?
            # Built in shopstack/ui/tabs/today.py
            # ═══════════════════════════════════════════════════════════════
            today_handles: TodayTabHandles = build_today_tab(
                blocks=app, app=app, ctx=TabContext(),
            )
            today_stats = today_handles.today_stats
            today_soon = today_handles.today_soon
            today_list = today_handles.today_list
            today_low = today_handles.today_low
            today_recent = today_handles.today_recent
            today_changed = today_handles.today_changed

            # ═══════════════════════════════════════════════════════════════
            # Tab 2: Basket — what should I buy / skip / compare?
            # ═══════════════════════════════════════════════════════════════
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
                            
                        # Keep complete_btn for fast one-click without edit, or remove it.
                        # The task said "Upgrade Shopping List Completion v2: Do not blindly add items." 
                        # So we might want to just keep the old one but encourage the new one.
                        
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
                            shopping_list_item_choices,
                            outputs=sl_item_dropdown
                        )
                        app.load(shopping_list_item_choices, outputs=sl_item_dropdown)
                        app.load(shopping_list_view_with_cards, outputs=[sl_cards, sl_display, sl_table,
                                                                          sl_list_id, sl_goal, sl_share])

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

            # ═══════════════════════════════════════════════════════════════
            # Tab 3: ShopLens — check while shopping
            # ═══════════════════════════════════════════════════════════════
            with gr.Tab(_tab_label("market"), id="market"):
                gr.Markdown("### Point your camera or upload a photo \u2014 or speak what you see")
                with gr.Row():
                    image_input = gr.Image(type="filepath", label="Camera / Photo")
                    audio_input = gr.Audio(type="filepath", label="Voice Note")
                with gr.Row():
                    scan_btn = gr.Button("Scan & Compare to Inventory", variant="primary")
                ml_results = gr.HTML("")
                ml_items = gr.Textbox(label="Detected Items", visible=False)
                ml_analysis = gr.Textbox(visible=False)
                ml_last_trace_id = gr.State("")
                ml_barcode_state = gr.State("[]")
                ml_action_result = gr.HTML("")
                scan_btn.click(
                    market_lens_process,
                    [image_input, audio_input],
                    [ml_results, ml_items, ml_analysis, ml_last_trace_id, ml_barcode_state],
                    api_name="market_scan",
                    api_description="Scan image or voice input to classify and compare products",
                )
                with gr.Row():
                    ml_confirm_btn = gr.Button("Confirm BUY \u2192 Add to List", variant="primary")
                    ml_skip_btn = gr.Button("Skip Selected")
                    ml_save_btn = gr.Button("Save Trace")
                    ml_barcode_add_btn = gr.Button("Add Barcode to Inventory")
                ml_confirm_btn.click(
                    market_lens_confirm_buy,
                    [ml_analysis, ml_last_trace_id],
                    ml_action_result,
                    api_name="market_confirm_buy",
                    api_description="Add confirmed BUY items from Market Lens to current shopping list",
                )
                ml_skip_btn.click(
                    market_lens_skip,
                    [ml_analysis, ml_last_trace_id],
                    ml_action_result,
                    api_name="market_skip",
                    api_description="Record skip decision for Market Lens workflow",
                )
                ml_save_btn.click(
                    market_lens_save_trace,
                    [ml_analysis, ml_last_trace_id],
                    ml_action_result,
                    api_name="market_save_trace",
                    api_description="Save Market Lens trace output",
                )
                ml_barcode_add_btn.click(
                    market_lens_barcode_add,
                    ml_barcode_state,
                    ml_action_result,
                    api_name="market_add_barcode",
                    api_description="Add detected barcode items to inventory",
                )

            # ═══════════════════════════════════════════════════════════════
            # Tab 4: Pantry — what actually happened?
            # ═══════════════════════════════════════════════════════════════
            with gr.Tab(_tab_label("reconcile"), id="reconcile"):
                with gr.Tabs():
                    # ── Add Purchase ──
                    with gr.Tab("Add Purchase"):
                        with gr.Row():
                            p_name = gr.Textbox(label="Item Name", placeholder="e.g. Milk, Atta, Rice")
                            p_qty = gr.Number(label="Quantity", value=1.0)
                            p_unit = gr.Textbox(label="Unit", value="unit", placeholder="kg, L, pieces")
                        with gr.Row():
                            p_price = gr.Number(label="Price (\u20b9)", value=0.0)
                            p_store = gr.Textbox(label="Store", placeholder="e.g. Big Bazaar, Local Kirana")
                            # Location choices are bound at construction; the
                            # `app.load` handler below refreshes them on first
                            # render so newly-added locations (e.g. via household
                            # switching) appear without an app restart.
                            p_location = gr.Dropdown(
                                label="Storage Location",
                                choices=[(l.name, l.location_id) for l in db.get_locations()],
                                value="pantry",
                            )
                        with gr.Row():
                            p_date = gr.Textbox(label="Purchase Date (YYYY-MM-DD)",
                                                placeholder=date.today().isoformat())
                            p_category = gr.Textbox(label="Category", placeholder="e.g. Dairy, Grains, Vegetables")
                        p_submit = gr.Button("Add to Inventory")
                        p_result = gr.HTML("")
                        p_submit.click(
                            add_purchase_form,
                            [p_name, p_qty, p_unit, p_price, p_store, p_location, p_date, p_category],
                            p_result,
                            api_name="add_purchase",
                            api_description="Record a new purchase with lot details",
                        )
                        gr.Markdown("### Quick Add Purchases")
                        gr.Markdown(
                            "One item per line: `name, qty, unit, price, store, location, category`")
                        p_batch_input = gr.Textbox(
                            label="Batch Purchases",
                            lines=5,
                            placeholder="milk, 2, L, 64, Sharma Kirana, fridge, dairy\nrice, 5, kg, 680, DMart, pantry_mid, grains",
                        )
                        p_batch_btn = gr.Button("Add Batch")
                        p_batch_result = gr.HTML("")
                        p_batch_btn.click(
                            add_purchase_batch,
                            p_batch_input,
                            p_batch_result,
                            api_name="add_purchase_batch",
                            api_description="Add multiple purchases from pasted or JSON-like input",
                        )

                    # ── Inventory ──
                    with gr.Tab("Inventory"):
                        with gr.Row():
                            inv_search = gr.Textbox(label="Search Inventory", placeholder="Type to filter...")
                            inv_refresh = gr.Button("Refresh", elem_classes="secondary")
                        inv_table = gr.DataFrame(label="All Inventory Items")
                        with gr.Row():
                            cons_lot = gr.Textbox(label="Lot ID (full or prefix)", placeholder="abcdef123456")
                            cons_qty = gr.Number(label="Quantity to Consume", value=1.0)
                            cons_btn = gr.Button("Consume")
                        cons_result = gr.HTML("")
                        inv_cards = gr.HTML("")
                        inv_search.change(
                            inventory_view,
                            inv_search,
                            inv_table,
                            api_name="inventory_search",
                            api_description="Search and filter inventory table by query",
                        )
                        inv_search.change(
                            inventory_cards_view,
                            inv_search,
                            inv_cards,
                            api_name="inventory_cards_search",
                            api_description="Search and filter inventory card view",
                        )
                        inv_refresh.click(
                            inventory_view,
                            outputs=inv_table,
                            api_name="inventory_refresh",
                            api_description="Refresh inventory table state",
                        )
                        inv_refresh.click(
                            inventory_cards_view,
                            outputs=inv_cards,
                            api_name="inventory_cards_refresh",
                            api_description="Refresh inventory card tiles",
                        )
                        cons_btn.click(
                            consume_item,
                            [cons_lot, cons_qty],
                            cons_result,
                            api_name="consume_item",
                            api_description="Consume quantity from a lot",
                        )
                        gr.Markdown(
                            "**Quick Consume** (one per line: `lot_id: qty`, or just `lot_id` for qty 1)")
                        batch_consume_input = gr.Textbox(
                            label="Quick Consume", lines=4,
                            placeholder="abc123: 0.5\ndef456: 1\nghi789")
                        batch_consume_btn = gr.Button("Consume Batch")
                        batch_consume_result = gr.HTML("")
                        batch_consume_btn.click(
                            consume_items_batch,
                            batch_consume_input,
                            batch_consume_result,
                            api_name="consume_batch",
                            api_description="Consume multiple lot quantities from batch input",
                        )
                        app.load(inventory_view, outputs=inv_table)
                        app.load(inventory_cards_view, outputs=inv_cards)

                    # ── Use Soon ──
                    with gr.Tab("Use Soon"):
                        with gr.Row():
                            use_days = gr.Slider(1, 30, value=3, step=1, label="Days threshold")
                            use_refresh = gr.Button("Refresh", elem_classes="secondary")
                        use_table = gr.DataFrame(label="Items to Use Soon")
                        use_refresh.click(
                            use_soon_view,
                            use_days,
                            use_table,
                            api_name="use_soon_refresh",
                            api_description="Refresh use-soon inventory recommendations",
                        )
                        app.load(use_soon_view, inputs=use_days, outputs=use_table)

                    # ── Consumption ──
                    with gr.Tab("Consume"):
                        gr.Markdown("### Consumption Tracker")
                        gr.Markdown("Log what you use. Track waste, meals, and consumption rates.")
                        cons_grid = gr.HTML("")
                        cons_history = gr.HTML("")
                        cons_rates = gr.HTML("")
                        cons_refresh = gr.Button("Refresh", elem_classes="secondary")
                        cons_refresh.click(
                            consumption_dashboard,
                            outputs=[cons_grid, cons_history, cons_rates],
                            api_name="consumption_refresh",
                            api_description="Refresh consumption dashboard",
                        )
                        app.load(consumption_dashboard, outputs=[cons_grid, cons_history, cons_rates])

                        gr.Markdown("---")
                        gr.Markdown("### Quick Consume")
                        with gr.Row():
                            cons_lot_input = gr.Textbox(label="Lot ID", placeholder="e.g. abc123", scale=2)
                            cons_qty_input = gr.Number(label="Quantity", value=1.0, scale=1)
                            cons_btn = gr.Button("Consume", variant="primary", scale=0)
                        cons_result = gr.HTML("")
                        cons_btn.click(
                            quick_consume,
                            [cons_lot_input, cons_qty_input],
                            cons_result,
                            api_name="quick_consume",
                            api_description="Quick consume quantity from a lot",
                        )

                        gr.Markdown("---")
                        gr.Markdown("### Batch Consume with Context")
                        cons_batch_input = gr.Textbox(
                            label="Items (one per line: lot_id:qty)",
                            lines=4,
                            placeholder="abc123: 0.5\ndef456: 1",
                        )
                        with gr.Row():
                            cons_meal = gr.Dropdown(
                                label="Meal context",
                                choices=["breakfast", "lunch", "dinner", "snack", "other"],
                                value="other",
                                scale=1,
                            )
                            cons_waste = gr.Dropdown(
                                label="Waste?",
                                choices=[("Normal use", ""), ("Wasted", "waste")],
                                value="",
                                scale=1,
                            )
                        cons_batch_btn = gr.Button("Log Batch")
                        cons_batch_result = gr.HTML("")
                        cons_batch_btn.click(
                            batch_consume_with_context,
                            [cons_batch_input, cons_meal, cons_waste],
                            cons_batch_result,
                            api_name="batch_consume_context",
                            api_description="Batch consume with meal context and waste tracking",
                        )

                    # ── Locations ──
                    with gr.Tab("Locations"):
                        map_html = gr.HTML("")
                        gr.Markdown("### Move Item Between Locations")
                        with gr.Row():
                            move_lot_input = gr.Textbox(label="Lot ID (or prefix)", placeholder="e.g. abc123")
                            move_dest = gr.Dropdown(
                                label="Destination",
                                choices=[(l.name, l.location_id) for l in db.get_locations()],
                            )
                            move_btn = gr.Button("Move")
                        move_result = gr.HTML("")
                        move_btn.click(
                            move_inventory_to_location,
                            [move_lot_input, move_dest],
                            move_result,
                            api_name="move_inventory",
                            api_description="Move one lot to a different storage location",
                        )
                        app.load(household_map_view, outputs=map_html)

            # ═══════════════════════════════════════════════════════════════
            # Tab 5: Insights — what did we learn?
            # ═══════════════════════════════════════════════════════════════
            with gr.Tab(_tab_label("memory"), id="memory"):
                with gr.Tabs():
                    # ── Intelligence & Insights ──
                    with gr.Tab("Intelligence"):
                        gr.Markdown("### Price & Preference Intelligence")
                        gr.Markdown("Waste patterns, inferred preferences, and price memory analysis.")
                        with gr.Row():
                            intel_refresh_btn = gr.Button("Refresh Intelligence", elem_classes="secondary")
                        intel_waste_html = gr.HTML("<div class='home-card'>Loading waste insights...</div>")
                        intel_pref_html = gr.HTML("<div class='home-card'>Loading preference signals...</div>")
                        intel_price_html = gr.HTML("<div class='home-card'>Loading price intelligence...</div>")
                        
                        intel_refresh_btn.click(
                            get_intelligence_dashboard,
                            None,
                            [intel_waste_html, intel_pref_html, intel_price_html]
                        )
                        app.load(
                            get_intelligence_dashboard,
                            None,
                            [intel_waste_html, intel_pref_html, intel_price_html]
                        )

                    # ── Field Notes ──
                    with gr.Tab("Field Notes"):
                        gr.Markdown("### Field Notes")
                        gr.Markdown(
                            "Capture household notes, shopping decisions, price changes, and things to remember next time.")
                        notes_editor = gr.Textbox(
                            label="Editable Draft", lines=16,
                            placeholder="# Household Notes\n\nWrite what we learned...")
                        notes_preview = gr.Markdown()
                        notes_status = gr.HTML("")
                        with gr.Row():
                            notes_reload = gr.Button("Reload Draft", elem_classes="secondary")
                            notes_save = gr.Button("Save Notes")
                        notes_reload.click(
                            field_notes_view,
                            outputs=[notes_editor, notes_preview, notes_status],
                            api_name="notes_reload",
                            api_description="Reload persisted field notes and preview",
                        )
                        notes_save.click(
                            field_notes_save,
                            notes_editor,
                            outputs=[notes_editor, notes_preview, notes_status],
                            api_name="notes_save",
                            api_description="Save field notes draft",
                        )
                        notes_editor.change(
                            lambda text: text,
                            notes_editor,
                            notes_preview,
                            api_name="notes_live_preview",
                            api_description="Update markdown preview while typing notes",
                        )
                        app.load(field_notes_view, outputs=[notes_editor, notes_preview, notes_status])

                    # ── History ──
                    with gr.Tab("History"):
                        gr.HTML(workflow_title_bar(
                            "Household History",
                            "Browse household activity, inspect details, and export records when you need them.",
                        ))
                        with gr.Row():
                            trace_search = gr.Textbox(
                                label="Search",
                                placeholder="Search by goal, type, or record ID",
                                scale=2,
                            )
                            trace_type_filter = gr.Dropdown(
                                label="Input type",
                                choices=[("All", ""), ("Text", "text"), ("Voice", "voice"), ("Image", "image")],
                                value="",
                                allow_custom_value=False,
                                scale=1,
                            )
                            trace_refresh = gr.Button("Refresh", elem_classes="secondary", scale=1)
                        trace_table = gr.DataFrame(label="Recent Activity")
                        with gr.Row():
                            trace_selector = gr.Dropdown(
                                label="Select a record",
                                choices=[("No traces yet", "")],
                                value="",
                                allow_custom_value=False,
                            )
                        trace_timeline = gr.HTML("")
                        trace_raw = gr.HTML("")
                        with gr.Row():
                            trace_export = gr.Button("Export trace JSONL")
                            trace_file = gr.File(file_count="single", visible=True,
                                                 label="Download redacted JSONL")
                        trace_bootstrap_state = gr.State("")

                        trace_search.change(
                            agent_trace_search_filter,
                            [trace_search, trace_type_filter],
                            [trace_selector, trace_timeline, trace_raw],
                            api_name="trace_search",
                            api_description="Search and filter traces",
                        )
                        trace_type_filter.change(
                            agent_trace_search_filter,
                            [trace_search, trace_type_filter],
                            [trace_selector, trace_timeline, trace_raw],
                            api_name="trace_filter",
                            api_description="Filter traces by input type",
                        )
                        trace_selector.change(
                            trace_bundle,
                            trace_selector,
                            [trace_timeline, trace_raw],
                            api_name="trace_select",
                            api_description="Load timeline and redacted payload for selected trace",
                        )
                        trace_refresh.click(
                            agent_trace_refresh,
                            outputs=[trace_selector, trace_timeline, trace_raw, trace_bootstrap_state,
                                     trace_table],
                            api_name="trace_refresh",
                            api_description="Refresh trace list and selected timeline",
                        )
                        trace_export.click(
                            agent_trace_export_file,
                            trace_selector,
                            trace_file,
                            api_name="trace_export",
                            api_description="Export selected record as redacted JSONL",
                        )
                        app.load(lambda: agent_trace_view()[0], outputs=trace_table)
                        app.load(
                            lambda: agent_trace_bootstrap(),
                            outputs=[trace_selector, trace_timeline, trace_raw, trace_bootstrap_state],
                        )

                    # ── Nutrition ──
                    with gr.Tab("Nutrition"):
                        gr.Markdown("### Nutrition Lookup")
                        nutrition_search = gr.Textbox(
                            label="Search Item",
                            placeholder="e.g. milk, atta, rice, chicken, doodh, dal...",
                        )
                        nutrition_search_btn = gr.Button("Look Up")
                        nutrition_result = gr.HTML("")
                        nutrition_search_btn.click(
                            nutrition_lookup_view,
                            nutrition_search,
                            nutrition_result,
                            api_name="nutrition_lookup",
                            api_description="Lookup nutrition for searched item",
                        )
                        nutrition_search.submit(
                            nutrition_lookup_view,
                            nutrition_search,
                            nutrition_result,
                            api_name="nutrition_lookup_submit",
                            api_description="Lookup nutrition for submitted text",
                        )
                        gr.Markdown("### My Kitchen Nutrition")
                        kitchen_nutrition = gr.HTML("")
                        kitchen_refresh = gr.Button("Refresh Kitchen Nutrition", elem_classes="secondary")
                        kitchen_refresh.click(
                            nutrition_kitchen_view,
                            outputs=kitchen_nutrition,
                            api_name="nutrition_kitchen_refresh",
                            api_description="Refresh kitchen nutrition aggregate view",
                        )
                        app.load(nutrition_kitchen_view, outputs=kitchen_nutrition)

                    # ── System (developer mode only) ──
                    if settings.ui_mode == "developer":
                        with gr.Tab("System"):
                            model_stack_html = gr.HTML("")
                            app.load(model_budget_view, outputs=model_stack_html)

                    # ── Data ──
                    with gr.Tab("Data"):
                        with gr.Tab("Export"):
                            export_json_btn = gr.Button("Export Inventory as JSON")
                            export_csv_btn = gr.Button("Export Inventory as CSV")
                            export_file = gr.File(label="Download", visible=False)
                            export_json_btn.click(
                                export_data_json,
                                outputs=export_file,
                                api_name="export_json",
                                api_description="Export inventory state to JSON",
                            ).then(
                                lambda f: gr.update(value=f, visible=True) if f else gr.update(visible=False),
                                export_file,
                                export_file
                            )
                            export_csv_btn.click(
                                export_data_csv,
                                outputs=export_file,
                                api_name="export_csv",
                                api_description="Export inventory state to CSV",
                            ).then(
                                lambda f: gr.update(value=f, visible=True) if f else gr.update(visible=False),
                                export_file,
                                export_file
                            )
                        with gr.Tab("Import"):
                            import_file = gr.File(label="Upload JSON or CSV", file_count="single")
                            import_btn = gr.Button("Import Data")
                            import_result = gr.HTML("")
                            import_btn.click(
                                import_data_file,
                                import_file,
                                import_result,
                                api_name="import_data",
                                api_description="Import inventory from JSON or CSV file",
                            )

        # Wire household dropdown change after all output components are defined
        household_dropdown.change(
            _switch_and_refresh,
            household_dropdown,
            [household_dropdown, today_stats, today_soon, today_list, today_low, today_recent, today_changed],
            api_name="switch_household",
            api_description="Switch active household and refresh dashboard",
        )

        # Per-render refresh of location-dependent dropdowns.
        # The dropdowns are constructed with choices at build_app() time. This
        # `app.load` handler re-fetches them on first page render, so locations
        # added mid-session (e.g. via household switching) appear without an
        # app restart. The default value stays the same; "pantry" is always
        # present in the seeded locations.
        def _refresh_location_choices() -> gr.update:
            return gr.update(choices=[(l.name, l.location_id) for l in db.get_locations()])

        app.load(_refresh_location_choices, outputs=p_location)
        app.load(_refresh_location_choices, outputs=move_dest)

        # Wire add-household button and form
        add_hh_btn.click(
            _show_add_form,
            outputs=hh_add_row,
            api_name="show_add_household",
            api_description="Show the add-household form",
        )
        hh_cancel_btn.click(
            _hide_add_form,
            outputs=hh_add_row,
            api_name="cancel_add_household",
            api_description="Hide the add-household form without creating",
        )
        hh_create_btn.click(
            _create_household,
            hh_name_input,
            [household_dropdown, hh_add_row, today_stats, today_soon, today_list, today_low, today_recent, today_changed],
            api_name="create_household",
            api_description="Create a new household, switch to it, and refresh the dashboard",
        )

    return app



if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    app = build_app()
    app.launch(server_port=args.port, share=args.share, theme=gr.themes.Base(), css=CSS)
