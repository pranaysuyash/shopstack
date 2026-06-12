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
    shelf_scan_process,
    shelf_scan_confirm,
    shelf_scan_skip,
    shelf_scan_save_trace,
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
    basket_compare_view,
)
from shopstack.ui.screens.basket import build_basket_screen
from shopstack.ui.components import WORKFLOW_STEPS, workflow_header, workflow_title_bar
from shopstack.ui.theme import CSS
from shopstack.ui.tabs.context import TabContext
from shopstack.ui.tabs.today import build_today_tab, TodayTabHandles
from shopstack.ui.tabs.basket import build_basket_tab
from shopstack.ui.tabs.market import build_market_tab
from shopstack.ui.tabs.reconcile import build_reconcile_tab, ReconcileTabHandles

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
            # Built in shopstack/ui/tabs/basket.py
            # ═══════════════════════════════════════════════════════════════
            build_basket_tab(blocks=app, app=app, ctx=TabContext())

            # ═══════════════════════════════════════════════════════════════
            # Tab 3: ShopLens — check while shopping
            # Built in shopstack/ui/tabs/market.py
            # ═══════════════════════════════════════════════════════════════
            build_market_tab(blocks=app, app=app, ctx=TabContext())

            # ═══════════════════════════════════════════════════════════════
            # Tab 4: Reconcile — what actually happened?
            # Built in shopstack/ui/tabs/reconcile.py
            # ═══════════════════════════════════════════════════════════════
            reconcile_handles = build_reconcile_tab(blocks=app, app=app, ctx=TabContext())
            p_location = reconcile_handles.p_location
            move_dest = reconcile_handles.move_dest

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
