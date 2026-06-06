from __future__ import annotations

from datetime import date

import gradio as gr

from shopstack.ui.screens import (
    today_dashboard,
    shopping_list_view_with_cards,
    build_shopping_list_and_refresh,
    complete_shopping_list,
    shopping_list_item_choices,
    mark_items_purchased,
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
    price_memory_view,
    price_intelligence_view,
    household_map_view,
    agent_trace_view,
    agent_trace_bootstrap,
    agent_trace_export_file,
    trace_bundle,
    field_notes_view,
    field_notes_save,
    export_data_json,
    export_data_csv,
    import_data_file,
)
from shopstack.ui.screens.other import move_inventory_to_location
from shopstack.ui.screens._utils import WORKFLOW_STEPS, workflow_header, workflow_title_bar
from shopstack.ui.theme import CSS

# Backward compatibility wrappers for tests
from shopstack.ui.screens.shopping import (
    shopping_list_view,
    shopping_list_create,
    _shopping_list_view_with_cards,
    _build_shopping_list_and_refresh,
)
from shopstack.ui.screens.traces import _trace_bundle, agent_trace_detail
from shopstack.app_context import db, providers, tools, planner, model_registry

_workflow_header = workflow_header


def _runtime_label() -> str:
    try:
        runtime = providers.runtime_report()
        loaded_real = [r for r in runtime if getattr(r, "loaded", False) and getattr(r, "backend", "") != "mock"]
        return "Local runtime" if loaded_real else "Local mock mode"
    except Exception:
        return "Local runtime"


def build_app() -> gr.Blocks:
    runtime_label = _runtime_label()
    with gr.Blocks(title="ShopStack") as app:
        gr.HTML(f"""
<div class="app-header">
  <div>
    <h1 class="brand-title">ShopStack</h1>
    <div class="brand-subtitle">Your home's shopping memory.</div>
  </div>
  <div>
    <div class="env-badge">{runtime_label}</div>
  </div>
</div>""", padding=True)

        with gr.Tabs(elem_classes="tabs") as tabs:
            with gr.Tab("Today", id="today"):
                gr.HTML(workflow_header(WORKFLOW_STEPS))
                today_stats = gr.HTML("")
                today_soon = gr.HTML("")
                today_list = gr.HTML("")
                today_low = gr.HTML("")
                today_recent = gr.HTML("")
                app.load(today_dashboard, outputs=[today_stats, today_soon, today_list, today_low, today_recent])

            with gr.Tab("Ask ShopStack", id="ask"):
                gr.HTML(workflow_header(WORKFLOW_STEPS))
                ask_input = gr.Textbox(
                    label="Ask ShopStack",
                    placeholder="Do we have milk?  |  What should I buy today?  |  Where is toothpaste?",
                    lines=2,
                )
                ask_btn = gr.Button("Ask")
                ask_output = gr.HTML("")
                ask_btn.click(ask_shopstack, ask_input, ask_output)
                ask_input.submit(ask_shopstack, ask_input, ask_output)

            with gr.Tab("Shopping List", id="shopping"):
                gr.HTML(workflow_header(WORKFLOW_STEPS, current_step=3))
                sl_cards = gr.HTML("")
                sl_display = gr.HTML("")
                sl_table = gr.DataFrame(label="Items")
                sl_list_id = gr.State("")
                sl_goal = gr.State("")
                with gr.Row():
                    goal_input = gr.Textbox(label="List Goal (e.g. Weekly Groceries)", placeholder="What's this list for?")
                    items_input = gr.Textbox(
                        label="Shopping list",
                        placeholder="milk, bread, tomato, onion  (or JSON for power users)",
                        lines=3,
                    )
                sl_share = gr.HTML("")
                sl_complete_result = gr.HTML("")
                with gr.Row():
                    sl_item_dropdown = gr.Dropdown(
                        label="Select items to mark as purchased",
                        choices=[],
                        multiselect=True,
                        interactive=True,
                    )
                    sl_item_refresh = gr.Button("Refresh Items", elem_classes="secondary")
                    sl_mark_purchased_btn = gr.Button("Mark Selected as Purchased", variant="primary")

                with gr.Row():
                    create_btn = gr.Button("Build Shopping Plan")
                    refresh_btn = gr.Button("Refresh", elem_classes="secondary")
                    complete_btn = gr.Button("Complete List & Add to Inventory", variant="primary")
                create_output = gr.HTML("")
                create_btn.click(
                    build_shopping_list_and_refresh,
                    [goal_input, items_input],
                    [create_output, sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share],
                ).then(
                    shopping_list_item_choices,
                    outputs=sl_item_dropdown
                )
                refresh_btn.click(shopping_list_view_with_cards, outputs=[sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share])
                complete_btn.click(complete_shopping_list, sl_list_id, sl_complete_result).then(
                    shopping_list_view_with_cards,
                    outputs=[sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share]
                ).then(
                    shopping_list_item_choices,
                    outputs=sl_item_dropdown
                )

                with gr.Row():
                    sl_item_dropdown = gr.Dropdown(
                        label="Select items to mark as purchased",
                        choices=[],
                        multiselect=True,
                        interactive=True,
                    )
                    sl_item_refresh = gr.Button("Refresh Items", elem_classes="secondary")
                    sl_mark_purchased_btn = gr.Button("Mark Selected as Purchased", variant="primary")
                sl_mark_result = gr.HTML("")
                sl_item_refresh.click(shopping_list_item_choices, outputs=sl_item_dropdown)
                sl_mark_purchased_btn.click(mark_items_purchased, sl_item_dropdown, sl_mark_result).then(
                    shopping_list_view_with_cards,
                    outputs=[sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share]
                ).then(
                    shopping_list_item_choices,
                    outputs=sl_item_dropdown
                )
                app.load(shopping_list_item_choices, outputs=sl_item_dropdown)
                app.load(shopping_list_view_with_cards, outputs=[sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share])

            with gr.Tab("Market Lens", id="market"):
                gr.HTML(workflow_header(WORKFLOW_STEPS, current_step=2))
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
                scan_btn.click(market_lens_process, [image_input, audio_input], [ml_results, ml_items, ml_analysis, ml_last_trace_id, ml_barcode_state])
                with gr.Row():
                    ml_confirm_btn = gr.Button("Confirm BUY \u2192 Add to List", variant="primary")
                    ml_skip_btn = gr.Button("Skip Selected")
                    ml_save_btn = gr.Button("Save Trace")
                    ml_barcode_add_btn = gr.Button("Add Barcode to Inventory")
                ml_confirm_btn.click(market_lens_confirm_buy, [ml_analysis, ml_last_trace_id], ml_action_result)
                ml_skip_btn.click(market_lens_skip, [ml_analysis, ml_last_trace_id], ml_action_result)
                ml_save_btn.click(market_lens_save_trace, [ml_analysis, ml_last_trace_id], ml_action_result)
                ml_barcode_add_btn.click(market_lens_barcode_add, ml_barcode_state, ml_action_result)

            with gr.Tab("Add Purchase", id="purchase"):
                gr.HTML(workflow_header(WORKFLOW_STEPS, current_step=5))
                gr.Markdown("### Record a Purchase")
                location_choices = [(l.name, l.location_id) for l in db.get_locations()]
                default_location = (
                    "pantry"
                    if any(value == "pantry" for _label, value in location_choices)
                    else (location_choices[0][1] if location_choices else None)
                )
                with gr.Row():
                    p_name = gr.Textbox(label="Item Name", placeholder="e.g. Milk, Atta, Rice")
                    p_qty = gr.Number(label="Quantity", value=1.0)
                    p_unit = gr.Textbox(label="Unit", value="unit", placeholder="kg, L, pieces")
                with gr.Row():
                    p_price = gr.Number(label="Price (\u20b9)", value=0.0)
                    p_store = gr.Textbox(label="Store", placeholder="e.g. Big Bazaar, Local Kirana")
                    p_location = gr.Dropdown(label="Storage Location", choices=location_choices, value=default_location)
                with gr.Row():
                    p_date = gr.Textbox(label="Purchase Date (YYYY-MM-DD)", placeholder=date.today().isoformat())
                    p_category = gr.Textbox(label="Category", placeholder="e.g. Dairy, Grains, Vegetables")
                p_submit = gr.Button("Add to Inventory")
                p_result = gr.HTML("")
                p_submit.click(add_purchase_form, [p_name, p_qty, p_unit, p_price, p_store, p_location, p_date, p_category], p_result)
                gr.Markdown("### Batch Add Purchases")
                gr.Markdown("One item per line: `name, qty, unit, price, store, location, category`  \nOr paste JSON array.")
                p_batch_input = gr.Textbox(label="Batch Purchases", lines=5, placeholder="milk, 2, L, 64, Sharma Kirana, fridge, dairy\nrice, 5, kg, 680, DMart, pantry_mid, grains")
                p_batch_btn = gr.Button("Add Batch")
                p_batch_result = gr.HTML("")
                p_batch_btn.click(add_purchase_batch, p_batch_input, p_batch_result)

            with gr.Tab("Find Item at Home", id="inventory"):
                gr.HTML(workflow_header(WORKFLOW_STEPS))
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
                inv_search.change(inventory_view, inv_search, inv_table)
                inv_search.change(inventory_cards_view, inv_search, inv_cards)
                inv_refresh.click(inventory_view, outputs=inv_table)
                inv_refresh.click(inventory_cards_view, outputs=inv_cards)
                cons_btn.click(consume_item, [cons_lot, cons_qty], cons_result)
                gr.Markdown("**Batch Consume** (one per line: `lot_id: qty`, or just `lot_id` for qty 1)")
                batch_consume_input = gr.Textbox(label="Batch Consume", lines=4, placeholder="abc123: 0.5\ndef456: 1\nghi789")
                batch_consume_btn = gr.Button("Consume Batch")
                batch_consume_result = gr.HTML("")
                batch_consume_btn.click(consume_items_batch, batch_consume_input, batch_consume_result)
                app.load(inventory_view, outputs=inv_table)
                app.load(inventory_cards_view, outputs=inv_cards)

            with gr.Tab("Use Soon", id="usesoon"):
                gr.HTML(workflow_header(WORKFLOW_STEPS, current_step=4))
                with gr.Row():
                    use_days = gr.Slider(1, 30, value=3, step=1, label="Days threshold")
                    use_refresh = gr.Button("Refresh", elem_classes="secondary")
                use_table = gr.DataFrame(label="Items to Use Soon")
                use_refresh.click(use_soon_view, use_days, use_table)
                app.load(use_soon_view, inputs=use_days, outputs=use_table)

            with gr.Tab("Price Memory Check", id="prices"):
                gr.HTML(workflow_header(WORKFLOW_STEPS))
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
                price_search.click(price_memory_view, price_item, [price_summary, price_plot, unit_price_plot, price_table])
                app.load(price_memory_view, inputs=price_item, outputs=[price_summary, price_plot, unit_price_plot, price_table])
                gr.Markdown("### Price Intelligence")
                pi_html = gr.HTML("")
                pi_refresh = gr.Button("Refresh", elem_classes="secondary")
                pi_refresh.click(price_intelligence_view, outputs=pi_html)
                app.load(price_intelligence_view, outputs=pi_html)

            with gr.Tab("Map", id="map"):
                gr.HTML(workflow_header(WORKFLOW_STEPS))
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
                move_btn.click(move_inventory_to_location, [move_lot_input, move_dest], move_result)
                app.load(household_map_view, outputs=map_html)

            with gr.Tab("Model Stack", id="modelstack"):
                model_stack_html = gr.HTML("")
                app.load(model_budget_view, outputs=model_stack_html)

            with gr.Tab("Traces", id="trace"):
                gr.HTML(workflow_title_bar(
                    "Export Redacted Trace",
                    "Pick a workflow run, inspect the timeline, then download a redacted trace artifact.",
                ))
                gr.HTML(workflow_header(WORKFLOW_STEPS, current_step=6))
                with gr.Row():
                    trace_search = gr.Textbox(
                        label="Search",
                        placeholder="Search by goal, type, or trace ID",
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
                trace_table = gr.DataFrame(label="Recent Traces")
                with gr.Row():
                    trace_selector = gr.Dropdown(label="Select a trace", choices=[], allow_custom_value=False)
                trace_timeline = gr.HTML("")
                trace_raw = gr.HTML("")
                with gr.Row():
                    trace_export = gr.Button("Export trace JSONL")
                    trace_file = gr.File(file_count="single", visible=True, label="Download redacted JSONL")
                trace_bootstrap_state = gr.State("")

                def _trace_selector_change(trace_id):
                    timeline, raw = trace_bundle(trace_id)
                    return timeline, raw

                def _trace_refresh_click():
                    result = agent_trace_bootstrap()
                    if isinstance(result[0], dict):
                        return (gr.update(**result[0]), *result[1:])
                    return result

                def _trace_search_change(search, type_filter):
                    from shopstack.ui.screens.traces import agent_trace_view, agent_trace_bootstrap as atb
                    tbl, _ = agent_trace_view(search, type_filter)
                    boot = atb(search, type_filter)
                    if isinstance(boot[0], dict):
                        return (gr.update(**boot[0]), boot[2], boot[3])
                    return (gr.update(choices=boot[0]), boot[2], boot[3])

                trace_search.change(
                    _trace_search_change,
                    [trace_search, trace_type_filter],
                    [trace_selector, trace_timeline, trace_raw],
                )
                trace_type_filter.change(
                    _trace_search_change,
                    [trace_search, trace_type_filter],
                    [trace_selector, trace_timeline, trace_raw],
                )
                trace_selector.change(_trace_selector_change, trace_selector, [trace_timeline, trace_raw])
                trace_refresh.click(
                    _trace_refresh_click,
                    outputs=[trace_selector, trace_timeline, trace_raw, trace_bootstrap_state, trace_table],
                )
                trace_export.click(agent_trace_export_file, trace_selector, trace_file)
                app.load(lambda: agent_trace_view()[0], outputs=trace_table)
                app.load(
                    lambda: agent_trace_bootstrap(),
                    outputs=[trace_selector, trace_timeline, trace_raw, trace_bootstrap_state],
                )

            with gr.Tab("Data", id="portability"):
                gr.HTML(workflow_header(WORKFLOW_STEPS))
                with gr.Tab("Export"):
                    export_json_btn = gr.Button("Export Inventory as JSON")
                    export_csv_btn = gr.Button("Export Inventory as CSV")
                    export_file = gr.File(label="Download", visible=False)
                    export_json_btn.click(
                        export_data_json, 
                        outputs=export_file,
                    ).then(
                        lambda f: gr.update(value=f, visible=True) if f else gr.update(visible=False),
                        export_file,
                        export_file
                    )
                    export_csv_btn.click(
                        export_data_csv, 
                        outputs=export_file,
                    ).then(
                        lambda f: gr.update(value=f, visible=True) if f else gr.update(visible=False),
                        export_file,
                        export_file
                    )
                with gr.Tab("Import"):
                    import_file = gr.File(label="Upload JSON or CSV", file_count="single")
                    import_btn = gr.Button("Import Data")
                    import_result = gr.HTML("")
                    import_btn.click(import_data_file, import_file, import_result)

            with gr.Tab("Field Notes", id="notes"):
                gr.HTML(workflow_header(WORKFLOW_STEPS))
                gr.Markdown("### Field Notes")
                gr.Markdown("Use this area to capture household notes, shopping decisions, price changes, and things to remember next time.")
                notes_editor = gr.Textbox(label="Editable Draft", lines=16, placeholder="# Household Notes\n\nWrite what we learned...")
                notes_preview = gr.Markdown()
                notes_status = gr.HTML("")
                with gr.Row():
                    notes_reload = gr.Button("Reload Draft", elem_classes="secondary")
                    notes_save = gr.Button("Save Notes")
                notes_reload.click(field_notes_view, outputs=[notes_editor, notes_preview, notes_status])
                notes_save.click(field_notes_save, notes_editor, outputs=[notes_editor, notes_preview, notes_status])
                notes_editor.change(lambda text: text, notes_editor, notes_preview)
                app.load(field_notes_view, outputs=[notes_editor, notes_preview, notes_status])

    return app


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    app = build_app()
    app.launch(server_port=args.port, share=args.share, theme=gr.themes.Base(), css=CSS)
