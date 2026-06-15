"""Reconcile tab — post-shopping reconciliation: add purchase, inventory, use soon, consumption, locations.

This is the "what actually happened?" tab. After a shopping trip, the user
comes here to:
- Log a purchase (manual form or batch paste)
- View and search inventory
- Mark items as consumed
- See use-soon items (expiring/aging)
- Track consumption (waste, meals, rates)
- Move items between storage locations

Sub-tabs:
1. **Add Purchase** — Manual form + batch paste
2. **Inventory** — Table view + search + card view + consume
3. **Use Soon** — Expiring/aging items
4. **Consume** — Consumption tracker + quick consume + batch with context
5. **Locations** — Storage map + move item

Cross-tab references: The `p_location` (Add Purchase) and `move_dest` (Locations)
dropdowns are referenced by the per-render `_refresh_location_choices` handler
in `app.py` (so newly-added locations appear without an app restart). These
components are returned via `ReconcileTabHandles`.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import gradio as gr

from shopstack.app_context import db
from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import (
    confirm_dialog,
    confirm_hide_updates,
    confirm_toggle_updates,
    empty_state_enhanced,
    help_text,
    loading_skeleton,
    tooltip_icon,
)
from shopstack.ui.screens import (
    add_purchase_batch,
    add_purchase_form,
    batch_consume_with_context,
    consume_item,
    consume_items_batch,
    consumption_dashboard,
    household_map_view,
    inventory_cards_view,
    inventory_view,
    quick_consume,
    use_first_view,
)
from shopstack.ui.screens.other import move_inventory_to_location
from shopstack.ui.tabs.context import TabContext


@dataclass
class ReconcileTabHandles:
    """Components that other parts of the app reference after the Reconcile tab builds.

    The `_refresh_location_choices` handler in `app.py` (registered as an
    `app.load` handler) reads back these dropdowns to refresh their choices
    on first render so newly-added locations appear without an app restart.
    """
    p_location: gr.Dropdown
    move_dest: gr.Dropdown


def build_reconcile_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> ReconcileTabHandles:
    """Build the Reconcile tab inside the parent's `gr.Tabs` context.

    Args:
        blocks: Alias for the parent gr.Blocks. Kept for symmetry with other
            tab builders.
        app: The root gr.Blocks instance — needed for `app.load(...)` handlers.
        ctx: Shared dependencies (unused in this tab, but part of the
            uniform builder signature).

    Returns:
        ReconcileTabHandles: the two location dropdowns that the per-render
        location-choices refresh handler in `app.py` needs to reference.
    """
    with gr.Tab(_tab_label("reconcile"), id="reconcile"):
        with gr.Tabs():
            # ── Add Purchase ──
            with gr.Tab("Add Purchase"):
                with gr.Row():
                    p_name = gr.Textbox(label="Item Name", placeholder="e.g. Milk, Atta, Rice")
                    p_qty = gr.Number(label="Quantity", value=1.0)
                    p_unit = gr.Textbox(
                        label="Unit", value="unit", placeholder="kg, L, pieces"
                    )
                with gr.Row():
                    p_price = gr.Number(label="Price (\u20b9)", value=0.0)
                    p_store = gr.Textbox(label="Store", placeholder="e.g. Big Bazaar, Local Kirana")
                    # Location choices are bound at construction; the
                    # `app.load` handler in app.py refreshes them on first
                    # render so newly-added locations (e.g. via household
                    # switching) appear without an app restart.
                    p_location = gr.Dropdown(
                        label="Storage Location",
                        choices=[(l.name, l.location_id) for l in db.get_locations()],
                        value="pantry",
                    )
                with gr.Row():
                    p_date = gr.Textbox(
                        label="Purchase Date (YYYY-MM-DD)",
                        placeholder=date.today().isoformat(),
                    )
                    p_category = gr.Textbox(
                        label="Category",
                        placeholder="e.g. Dairy, Grains, Vegetables",
                    )
                p_submit = gr.Button("Add to Pantry")
                p_result = gr.HTML(
                    empty_state_enhanced(
                        "Items you add will appear here with what was saved.",
                        icon="\U0001f6d2",
                    )
                )
                p_submit.click(
                    add_purchase_form,
                    [p_name, p_qty, p_unit, p_price, p_store, p_location, p_date, p_category],
                    p_result,
                    api_name="add_purchase",
                    api_description="Record a new purchase with lot details",
                    js="() => showToast('Adding to pantry...', 'info')",
                )
                gr.Markdown("### Quick add groceries")
                gr.HTML(help_text(
                    "Format: one item per line as `name, qty, unit, price, store, "
                    "location, category`. Items are added in order; you can leave "
                    "later fields blank by ending the line early. Example: "
                    "`milk, 2, L, 64, Sharma Kirana, fridge, dairy`.",
                    label_for="p_batch_input",
                ))
                gr.Markdown(
                    "One item per line: `name, qty, unit, price, store, location, category`")
                p_batch_input = gr.Textbox(
                    label="Batch Purchases",
                    lines=5,
                    placeholder="milk, 2, L, 64, Sharma Kirana, fridge, dairy\nrice, 5, kg, 680, DMart, pantry_mid, grains",
                    elem_id="p_batch_input",
                )
                p_batch_btn = gr.Button("Add batch")
                p_batch_result = gr.HTML(
                    empty_state_enhanced(
                        "Batch results will appear here after you click Add batch.",
                        icon="📦",
                    )
                )
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
                    inv_search = gr.Textbox(
                        label="Search pantry",
                        placeholder="Type to filter…",
                    )
                    inv_refresh = gr.Button("Refresh", elem_classes="secondary")
                inv_table = gr.DataFrame(label="All Inventory Items")
                with gr.Row():
                    cons_lot = gr.Textbox(
                        label="Batch (full or prefix)",
                        placeholder="abcdef123456",
                    )
                    cons_qty = gr.Number(label="Quantity to Consume", value=1.0)
                    cons_btn = gr.Button("Mark used")
                cons_result = gr.HTML(
                    empty_state_enhanced(
                        "Mark an item as used by entering its lot ID and quantity above.",
                        icon="✓",
                    )
                )
                inv_cards = gr.HTML(loading_skeleton("card"))
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
                    js="() => showToast('Marking as used...', 'info')",
                )
                gr.HTML(
                    "**Quick use** (one per line: `batch: qty`, or just `batch` for qty 1)")
                gr.HTML(help_text(
                    "Format: one item per line. Each line is either a batch reference by itself "
                    "(uses quantity 1) or `batch: qty` to use a specific amount. "
                    "Example: `abc123: 0.5` or just `abc123`.",
                    label_for="batch_consume_input",
                ))
                batch_consume_input = gr.Textbox(
                    label="Quick Consume", lines=4,
                    placeholder="abc123: 0.5\ndef456: 1\nghi789",
                    elem_id="batch_consume_input",
                )
                batch_consume_btn = gr.Button("Mark batch used")
                batch_consume_result = gr.HTML(
                    empty_state_enhanced(
                        "Batch consumption results will appear here.",
                        icon="✓",
                    )
                )
                batch_consume_btn.click(
                    consume_items_batch,
                    batch_consume_input,
                    batch_consume_result,
                    api_name="consume_batch",
                    api_description="Consume multiple lot quantities from batch input",
                    js="() => showToast('Marking batch as used...', 'info')",
                )
                app.load(inventory_view, outputs=inv_table)
                app.load(inventory_cards_view, outputs=inv_cards)

            # ── Use First (consumer label; internal: "use_first") ──
            with gr.Tab("Use First"):
                with gr.Row():
                    use_days = gr.Slider(
                        1, 30, value=3, step=1,
                        label="Show items expiring within ___ days",
                    )
                    use_refresh = gr.Button("Refresh", elem_classes="secondary")
                use_table = gr.DataFrame(label="Items to Use First")
                use_refresh.click(
                    use_first_view,
                    use_days,
                    use_table,
                    api_name="use_first_refresh",
                    api_description="Refresh use-first inventory recommendations",
                )
                app.load(use_first_view, inputs=use_days, outputs=use_table)

            # ── What Got Used (consumer label; internal: consumption) ──
            with gr.Tab("What Got Used"):
                gr.Markdown("### What got used")
                gr.Markdown("Log what you use. Track waste, meals, and consumption rates.")
                cons_grid = gr.HTML(loading_skeleton("card"))
                cons_history = gr.HTML(loading_skeleton("text"))
                cons_rates = gr.HTML(loading_skeleton("text"))
                cons_refresh = gr.Button("Refresh", elem_classes="secondary")
                cons_refresh.click(
                    consumption_dashboard,
                    outputs=[cons_grid, cons_history, cons_rates],
                    api_name="consumption_refresh",
                    api_description="Refresh consumption dashboard",
                )
                app.load(consumption_dashboard, outputs=[cons_grid, cons_history, cons_rates])

                gr.Markdown("---")
                gr.Markdown("### Quick use")
                with gr.Row():
                    cons_lot_input = gr.Textbox(
                        label=f"Batch {tooltip_icon('lot_id')}",
                        placeholder="e.g. abc123",
                        scale=2,
                    )
                    cons_qty_input = gr.Number(label="Quantity", value=1.0, scale=1)
                    cons_btn_quick = gr.Button("Mark used", variant="stop", scale=0)
                cons_quick_confirm = gr.Group(visible=False)
                with cons_quick_confirm:
                    gr.Markdown("⚠ **Mark this item as used?**")
                    with gr.Row():
                        cons_quick_yes = gr.Button("Yes, mark used", variant="stop")
                        cons_quick_no = gr.Button("Cancel", elem_classes="secondary")
                cons_result = gr.HTML(
                    empty_state_enhanced(
                        "Use an item by entering its lot ID and quantity above.",
                        icon="✓",
                    )
                )
                cons_btn_quick.click(
                    confirm_toggle_updates,
                    outputs=[cons_btn_quick, cons_quick_confirm],
                )
                cons_quick_yes.click(
                    quick_consume,
                    [cons_lot_input, cons_qty_input],
                    cons_result,
                    api_name="quick_consume",
                    api_description="Quick consume quantity from a lot",
                    js="() => showToast('Marking as used...', 'info')",
                ).then(
                    confirm_hide_updates,
                    outputs=[cons_btn_quick, cons_quick_confirm],
                )
                cons_quick_no.click(
                    confirm_hide_updates,
                    outputs=[cons_btn_quick, cons_quick_confirm],
                )

                gr.Markdown("---")
                gr.Markdown("### Batch use with context")
                gr.HTML(help_text(
                    "Format: one item per line as `batch:qty` (e.g. `abc123: 0.5`). "
                    "Add a meal context and mark as Wasted only if the food was thrown "
                    "out without being eaten.",
                    label_for="cons_batch_input",
                ))
                cons_batch_input = gr.Textbox(
                    label="Items (one per line: batch:qty)",
                    lines=4,
                    placeholder="abc123: 0.5\ndef456: 1",
                    elem_id="cons_batch_input",
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
                cons_batch_btn = gr.Button("Log batch")
                cons_batch_result = gr.HTML(
                    empty_state_enhanced(
                        "Batch results will appear here.",
                        icon="📋",
                    )
                )
                cons_batch_btn.click(
                    batch_consume_with_context,
                    [cons_batch_input, cons_meal, cons_waste],
                    cons_batch_result,
                    api_name="batch_consume_context",
                    api_description="Batch consume with meal context and waste tracking",
                    js="() => showToast('Logging batch use...', 'info')",
                )

            # ── Where It Lives (consumer label; internal: locations) ──
            with gr.Tab("Where It Lives"):
                map_html = gr.HTML(loading_skeleton("card"))
                gr.Markdown("### Move item between locations")
                with gr.Row():
                    move_lot_input = gr.Textbox(
                        label="Batch (or prefix)",
                        placeholder="e.g. abc123",
                    )
                    move_dest = gr.Dropdown(
                        label="Destination",
                        choices=[(l.name, l.location_id) for l in db.get_locations()],
                    )
                    move_btn = gr.Button("Move", variant="stop")
                move_confirm = gr.Group(visible=False)
                with move_confirm:
                    gr.Markdown(
                        "⚠ **Move this item to the chosen location?** "
                        "Inventory location affects what counts as 'at home'."
                    )
                    with gr.Row():
                        move_yes = gr.Button("Yes, move it", variant="stop")
                        move_no = gr.Button("Cancel", elem_classes="secondary")
                move_result = gr.HTML(
                    empty_state_enhanced(
                        "Move results will appear here.",
                        icon="📍",
                    )
                )
                move_btn.click(
                    confirm_toggle_updates,
                    outputs=[move_btn, move_confirm],
                )
                move_yes.click(
                    move_inventory_to_location,
                    [move_lot_input, move_dest],
                    move_result,
                    api_name="move_inventory",
                    api_description="Move one lot to a different storage location",
                    js="() => showToast('Moving item...', 'info')",
                ).then(
                    confirm_hide_updates,
                    outputs=[move_btn, move_confirm],
                )
                move_no.click(
                    confirm_hide_updates,
                    outputs=[move_btn, move_confirm],
                )
                app.load(household_map_view, outputs=map_html)

    return ReconcileTabHandles(
        p_location=p_location,
        move_dest=move_dest,
    )
