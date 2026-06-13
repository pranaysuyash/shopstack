"""Memory tab — reflection surfaces: intelligence, field notes, history, nutrition, model stack, data portability.

This is the "what did we learn?" tab. It surfaces everything the user
wants to inspect, not act on quickly:
- Intelligence (waste patterns, preferences, price memory)
- Field Notes (free-form household notes)
- History (browse, filter, export activity records)
- Nutrition (lookup + kitchen aggregate)
- System (developer mode only — model stack, provider status)
- Data (export/import portability)

All sub-tabs are self-contained. No cross-tab references.

Note: The `if settings.ui_mode == "developer"` guard for the System sub-tab
is preserved verbatim. The `settings` object is accessed via the module
registry pattern (not through TabContext) because `ui_mode` is a
configuration flag, not a runtime singleton.
"""
from __future__ import annotations

import gradio as gr

from shopstack.config import settings
from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import empty_state_enhanced, loading_skeleton, toast
from shopstack.ui.screens import (
    agent_trace_bootstrap,
    agent_trace_export_file,
    agent_trace_refresh,
    agent_trace_search_filter,
    agent_trace_view,
    export_data_csv,
    export_data_json,
    field_notes_save,
    field_notes_view,
    get_intelligence_dashboard,
    import_data_file,
    model_budget_view,
    trace_bundle,
)
from shopstack.ui.screens.nutrition import (
    nutrition_kitchen_view,
    nutrition_lookup_view,
)
from shopstack.ui.tabs.context import TabContext


def build_memory_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Memory tab inside the parent's `gr.Tabs` context.

    Args:
        blocks: Alias for the parent gr.Blocks. Kept for symmetry with other
            tab builders.
        app: The root gr.Blocks instance — needed for `app.load(...)` handlers.
        ctx: Shared dependencies (unused in this tab, but part of the
            uniform builder signature).

    Returns:
        None. The Memory tab is self-contained: no components are referenced
        by other parts of the app, so no TabHandles dataclass is needed.
    """
    with gr.Tab(_tab_label("memory"), id="memory"):
        with gr.Tabs():
            # ── Patterns (consumer label; internal: intelligence) ──
            with gr.Tab("Patterns"):
                gr.Markdown("### What we have learned")
                gr.Markdown("Waste patterns, inferred preferences, and price memory analysis.")
                with gr.Row():
                    intel_refresh_btn = gr.Button("Refresh patterns", elem_classes="secondary")
                intel_waste_html = gr.HTML(loading_skeleton(variant="card"))
                intel_pref_html = gr.HTML(loading_skeleton(variant="card"))
                intel_price_html = gr.HTML(loading_skeleton(variant="card"))

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

            # ── Remember (consumer label; internal: field notes) ──
            with gr.Tab("Remember"):
                gr.Markdown("### Household notes")
                gr.Markdown(
                    "Capture household notes, shopping decisions, price changes, and things to remember next time.")
                notes_editor = gr.Textbox(
                    label="Editable Draft", lines=16,
                    placeholder="# Household Notes\n\nWrite what we learned...",
                )
                notes_preview = gr.Markdown()
                notes_status = gr.HTML(loading_skeleton("text"))
                with gr.Row():
                    notes_reload = gr.Button("Reload draft", elem_classes="secondary")
                    notes_save = gr.Button("Save notes")
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

            # ── What Happened (consumer label; internal: trace history) ──
            with gr.Tab("What Happened"):
                gr.Markdown(
                    "### Household history\n\n"
                    "Browse household activity, inspect details, and export records when you need them."
                )
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
                        choices=[("No activity yet", "")],
                        value="",
                        allow_custom_value=False,
                    )
                trace_timeline = gr.HTML(
                    empty_state_enhanced(
                        "Select a record above to see the timeline and details.",
                        icon="📜",
                    )
                )
                trace_raw = gr.HTML("")
                with gr.Row():
                    trace_export = gr.Button("Download activity record")
                    trace_file = gr.File(
                        file_count="single",
                        visible=True,
                        label="Download record (private info removed)",
                    )
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
                gr.Markdown("### Nutrition lookup")
                nutrition_search = gr.Textbox(
                    label="Search Item",
                    placeholder="e.g. milk, atta, rice, chicken, doodh, dal…",
                )
                nutrition_search_btn = gr.Button("Look up")
                nutrition_result = gr.HTML(
                    empty_state_enhanced(
                        "Type an item and click Look up to see nutrition facts.",
                        icon="🥗",
                    )
                )
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
                gr.Markdown("### My kitchen nutrition")
                kitchen_nutrition = gr.HTML(loading_skeleton("card"))
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
                with gr.Tab("Advanced"):
                    model_stack_html = gr.HTML(loading_skeleton("card"))
                    app.load(model_budget_view, outputs=model_stack_html)

            # ── Backup ──
            with gr.Tab("Backup"):
                with gr.Tab("Export"):
                    export_json_btn = gr.Button("Back up pantry (JSON)")
                    export_csv_btn = gr.Button("Back up pantry (CSV)")
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
                    import_file = gr.File(
                        label="Choose a backup file (JSON or CSV)",
                        file_count="single",
                    )
                    import_btn = gr.Button("Restore from backup")
                    import_result = gr.HTML(
                        empty_state_enhanced(
                            "Choose a backup file above and click Restore to add items back into your pantry.",
                            icon="📥",
                        )
                    )
                    import_btn.click(
                        import_data_file,
                        import_file,
                        import_result,
                        api_name="import_data",
                        api_description="Import inventory from JSON or CSV file",
                    )
