"""Basket tab — Shopping List sub-tab sub-builder.

The Shopping List sub-tab is the largest sub-tab in the Basket
tab (~230 lines of inline UI). It composes 4 sub-features:

1. **List view** — Cards (rich view), table (raw rows), and a
   goal/title state. The user can build a new list, refresh,
   or finish + add to pantry.
2. **Print shopping list** (poster export) — Generate a
   printable poster image of the active list. Uses the
   ``generate_shopping_poster`` screen which produces a
   ``gr.Image`` preview and a ``gr.File`` download.
3. **Put groceries away** (reconciliation) — A draft table the
   user can edit (mark bought / skipped / substituted, add
   prices) before committing via ``confirm_reconciliation``.
4. **Mark as Bought** (partial completion) — A 2-step
   confirmation that lets the user select a subset of items
   and record purchases via ``mark_items_purchased``.

Extracted from ``shopstack.ui.tabs.basket`` in Pass 8 so each
basket sub-tab lives in its own module (mirrors the
``memory_*`` sub-builder pattern).

**Pattern:** the sub-builder opens its own ``gr.Tab("Shopping
List")`` inside the parent's ``gr.Tabs()`` context, adds the
4 sub-feature UIs, and wires the event handlers. The shared
``State`` components (``sl_list_id``, ``sl_goal``) and
``app.load`` handlers for the initial list view are
established inside the function; no cross-tab references
exist, so the function returns ``None``.
"""
from __future__ import annotations

import gradio as gr

from shopstack.services.empty_states import (
    build_household_context,
    render,
)
from shopstack.ui.components.primitives import (
    confirm_hide_updates,
    confirm_toggle_updates,
    empty_state_enhanced,
    loading_skeleton,
)
from shopstack.ui.screens import (
    build_shopping_list_and_refresh,
    complete_shopping_list,
    confirm_reconciliation,
    generate_shopping_poster,
    get_reconciliation_draft,
    mark_items_purchased,
    shopping_list_item_choices,
    shopping_list_share,
    shopping_list_substitutions_view,
    shopping_list_view_with_cards,
)
from shopstack.ui.tabs.context import TabContext


def build_basket_shopping_list(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Shopping List sub-tab inside the parent's ``gr.Tabs()`` context.

    Opens a ``gr.Tab("Shopping List")``, adds the 4 sub-feature
    UIs, and wires the event handlers. The shared ``State``
    components (``sl_list_id``, ``sl_goal``) are used across
    sub-features (e.g. the reconciliation UI needs
    ``sl_list_id`` to know which list to load the draft for).

    Args:
        app: The root ``gr.Blocks`` instance — needed for
            ``app.load(...)`` handlers (initial list view,
            initial substitutions view, initial item choices).
        ctx: Shared dependencies (unused in this sub-tab, kept
            for the uniform builder signature).

    Returns:
        None. The Shopping List sub-tab is self-contained: no
        components are referenced by other parts of the app, so
        no Handles dataclass is needed (matches the existing
        pattern for self-contained sub-tabs).
    """
    # Pass 16 §2.5: rich empty-state for the "No list built yet"
    # placeholder. Uses the same smart household context as the
    # find_trail tab (Pass 15). The legacy ``empty_state_enhanced``
    # one-liner stays as the fallback for the other 3 sites in
    # this tab (poster, reconcile, mark-bought) — they're
    # addressed in future passes per the §0.13 scope discipline.
    household_ctx = build_household_context(ctx.db)
    create_list_empty_state = render(
        "basket.create_list.no_action", household=household_ctx
    )
    with gr.Tab("Shopping List"):
        sl_cards = gr.HTML(loading_skeleton("card"))
        sl_substitutions = gr.HTML(loading_skeleton("text"))
        sl_display = gr.HTML(loading_skeleton("card"))
        sl_table = gr.DataFrame(label="Items")
        sl_list_id = gr.State("")
        sl_goal = gr.State("")
        with gr.Row():
            goal_input = gr.Textbox(
                label="List Goal (e.g. Weekly Groceries)",
                placeholder="What's this list for?",
            )
            items_input = gr.Textbox(
                label="Shopping list",
                placeholder="milk, bread, tomato, onion",
                lines=3,
            )
        with gr.Row():
            share_btn = gr.Button(
                "📤 Share list",
                variant="primary",
                scale=1,
                elem_id="sl-share-btn",
            )
            share_status = gr.HTML("")
        sl_share = gr.HTML(loading_skeleton("text"))

        # --- Shopping Poster Export ---
        with gr.Accordion("Print shopping list", open=False):
            gr.Markdown(
                "Export the list as a printable poster image. Each item is rendered as a simple buy / skip / optional card."
            )
            with gr.Row():
                poster_btn = gr.Button(
                    "\U0001f5bc Generate Poster", variant="primary", scale=1
                )
            poster_status = gr.HTML(
                empty_state_enhanced(
                    "No poster generated yet.",
                    icon="🖼️",
                    secondary_text="Click Generate Poster to create a printable version of your shopping list.",
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
            lambda poster_path: gr.update(
                value=poster_path, visible=bool(poster_path)
            ),
            poster_preview,
            poster_download,
        )

        # --- Reconciliation UI ---
        with gr.Accordion("Put groceries away", open=False):
            sl_reconciliation_table = gr.Dataframe(
                headers=[
                    "Item", "Qty", "Unit",
                    "Action (bought/skipped/substituted)",
                    "Price Paid", "Substitution Note",
                ],
                datatype=["str", "number", "str", "str", "number", "str"],
                column_count=6,
                interactive=True,
                label="Put-away draft (edit before confirming)",
            )
            with gr.Row():
                sl_reconcile_load_btn = gr.Button(
                    "Load Active List", elem_classes="secondary"
                )
                sl_reconcile_confirm_btn = gr.Button(
                    "Confirm & Finish", variant="primary"
                )
            sl_reconcile_result = gr.HTML(
                empty_state_enhanced(
                    "No put-away results yet.",
                    icon="📋",
                    secondary_text="Click Load Active List to review items before confirming.",
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
            sl_item_refresh = gr.Button(
                "Refresh Items", elem_classes="secondary"
            )
            sl_mark_purchased_btn = gr.Button(
                "Mark as Bought", variant="stop"
            )
        sl_mark_confirm = gr.Group(visible=False)
        with sl_mark_confirm:
            gr.Markdown("⚠ **Mark the selected items as bought?**")
            with gr.Row():
                sl_mark_yes = gr.Button(
                    "Yes, mark bought", variant="stop"
                )
                sl_mark_no = gr.Button(
                    "Cancel", elem_classes="secondary"
                )
        sl_mark_result = gr.HTML(
            empty_state_enhanced(
                "No purchases recorded yet.",
                icon="✓",
                secondary_text="Select items above and click Mark as Bought.",
            )
        )
        sl_item_refresh.click(
            shopping_list_item_choices,
            outputs=sl_item_dropdown,
            api_name="refresh_items",
            api_description="Refresh shopping list item selector",
        )
        # 2-step confirmation: first click reveals the confirm
        # group; the yes button fires mark_items_purchased and
        # restores state on completion.
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
        app.load(
            shopping_list_view_with_cards,
            outputs=[sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share],
        )
        app.load(shopping_list_substitutions_view, outputs=sl_substitutions)

        with gr.Row():
            create_btn = gr.Button("Build Shopping List")
            refresh_btn = gr.Button("Refresh", elem_classes="secondary")
            complete_btn = gr.Button(
                "Finish List & Add to Pantry", variant="stop"
            )
        complete_confirm = gr.Group(visible=False)
        with complete_confirm:
            gr.Markdown(
                "⚠ **Finish the list and move all bought items to the pantry?** "
                "This commits the entire list and is hard to undo."
            )
            with gr.Row():
                complete_yes = gr.Button(
                    "Yes, finish the list", variant="stop"
                )
                complete_no = gr.Button(
                    "Cancel", elem_classes="secondary"
                )
        create_output = gr.HTML(create_list_empty_state)
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
            outputs=sl_item_dropdown,
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
        # Share button: renders the shareable list HTML (textarea +
        # Copy button + WhatsApp link). Public Gradio adapter
        # `shopping_list_share` (added 2026-06-13) wraps the
        # internal share_text + share_html helpers.
        share_btn.click(
            shopping_list_share,
            None,
            sl_share,
            api_name="shopping_list_share",
            api_description=(
                "Render the active shopping list as a shareable "
                "HTML snippet (textarea + Copy button + WhatsApp link) "
                "so the user can share it with their household."
            ),
        )
        sl_reconcile_confirm_btn.click(
            confirm_reconciliation,
            [sl_reconciliation_table, sl_list_id],
            sl_reconcile_result,
            js="() => showToast('Confirming put-away...', 'info')",
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

        # 2-step confirmation for finishing the list
        complete_btn.click(
            confirm_toggle_updates,
            outputs=[complete_btn, complete_confirm],
        )
        complete_yes.click(
            complete_shopping_list,
            sl_list_id,
            sl_reconcile_result,
            api_name="complete_list",
            api_description=(
                "Complete active shopping list and add purchased items to inventory"
            ),
            js="() => showToast('Finishing list and adding to pantry...', 'info')",
        ).then(
            confirm_hide_updates,
            outputs=[complete_btn, complete_confirm],
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
        complete_no.click(
            confirm_hide_updates,
            outputs=[complete_btn, complete_confirm],
        )
