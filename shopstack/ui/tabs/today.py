"""Today tab — decision-first dashboard with embedded Ask ShopStack.

This is the first thing the user sees when they open ShopStack. It answers
"what should I do right now?" by surfacing:
- Use-soon items (expiring/aging inventory)
- Low-stock alerts
- Recent purchase activity
- "What changed" diff vs last session
- Embedded Ask ShopStack textbox (natural language queries)
- **Restock predictions** with one-click "add to my shopping list" action

The `today_dashboard()` screen function returns a 6-tuple of HTML strings;
we register it as an `app.load` handler so the panel populates on page open.

The Ask ShopStack sub-section is co-located with the dashboard so the user
doesn't need a separate tab for simple questions. The submit button and
Enter-key both fire `ask_shopstack` (returns a structured dict rendered via
gr.JSON).
"""
from __future__ import annotations

from dataclasses import dataclass

import gradio as gr

from shopstack.app_context import current_user_id, db
from shopstack.module_registry import tab_label as _tab_label
from shopstack.services.dashboard import build_dashboard_state
from shopstack.services.restock_action import add_prediction_to_list
from shopstack.ui.components.primitives import toast
from shopstack.ui.screens import ask_shopstack, today_dashboard
from shopstack.ui.tabs.context import TabContext


def _restock_table_rows() -> list[list[str]]:
    """Return a list-of-lists suitable for ``gr.Dataframe`` from the dashboard state.

    Columns: [canonical, display, urgency, typical_qty, days_until]. Empty
    list when no predictions.
    """
    try:
        state = build_dashboard_state(db, [], user_id=current_user_id() or "")
    except Exception:
        return []
    rows: list[list[str]] = []
    for p in (state.restock_predictions or [])[:6]:
        rows.append([
            p.get("canonical_name", ""),
            p.get("canonical_name", "").replace("_", " ").title(),
            p.get("urgency", "due_soon"),
            f"{float(p.get('typical_qty') or 1.0):.0f} {p.get('typical_unit') or 'unit'}",
            f"{p.get('days_until_restock', 0)}d",
        ])
    return rows


def _add_selected_to_list(selected_row: list[str] | None) -> str:
    """Gradio click handler: add the selected prediction to the active list."""
    if not selected_row or len(selected_row) < 1:
        return toast("Select a row first.", kind="warning")
    cname = (selected_row[0] or "").strip()
    if not cname:
        return toast("No item selected.", kind="warning")
    try:
        state = build_dashboard_state(db, [], user_id=current_user_id() or "")
        match = next(
            (p for p in (state.restock_predictions or [])
             if p.get("canonical_name") == cname),
            None,
        )
        if not match:
            return toast(f"Could not find prediction for {cname}.", kind="error")
        result = add_prediction_to_list(db, match)
        if not result.get("added"):
            return toast(result.get("reason", "Failed to add to list."), kind="error")
        return toast(result.get("reason", "Added to shopping list."), kind="success")
    except Exception as exc:
        return toast(f"Failed: {exc}", kind="error")


@dataclass
class TodayTabHandles:
    """Components that other parts of the app reference after the Today tab builds.

    The household-switch wiring in `app.py` reads back these components to
    refresh the dashboard when the active household changes.
    """
    today_stats: gr.HTML
    today_soon: gr.HTML
    today_list: gr.HTML
    today_low: gr.HTML
    today_recent: gr.HTML
    today_changed: gr.HTML


def build_today_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> TodayTabHandles:
    """Build the Today tab inside the parent's `gr.Tabs` context.

    Args:
        blocks: Alias for the parent gr.Blocks. Kept for symmetry with other
            tab builders and to make the call-site read consistently.
        app: The root ``gr.Blocks`` instance — needed for ``app.load(...)`` to
            register handlers that fire on page open.
        ctx: Shared dependencies (unused in this tab, but part of the
            uniform builder signature).

    Returns:
        TodayTabHandles: the six output components the household-switch
        wiring in `app.py` needs to reference.
    """
    with gr.Tab(_tab_label("today"), id="today"):
        today_stats = gr.HTML("")
        today_soon = gr.HTML("")
        today_list = gr.HTML("")
        today_low = gr.HTML("")
        today_recent = gr.HTML("")
        today_changed = gr.HTML("")
        app.load(today_dashboard, outputs=[today_stats, today_soon, today_list,
                                            today_low, today_recent, today_changed])

        gr.Markdown("---")
        gr.Markdown("### Restock Predictions")
        gr.Markdown(
            "Items you'll likely run out of soon. Click a row and press "
            "**Add to my list** to put it on the shopping list."
        )
        restock_df = gr.Dataframe(
            headers=["canonical", "Item", "Urgency", "Qty", "Days"],
            datatype=["str", "str", "str", "str", "str"],
            interactive=False,
            label="Predicted restocks",
            show_label=False,
        )
        restock_add_btn = gr.Button("Add selected to my shopping list", variant="primary")
        restock_add_output = gr.HTML("")
        app.load(_restock_table_rows, outputs=restock_df)
        restock_add_btn.click(
            _add_selected_to_list,
            restock_df,
            restock_add_output,
            api_name="restock_add_to_list",
            api_description="Add the selected restock prediction to the active shopping list",
        )

        gr.Markdown("---")
        gr.Markdown("### Ask a question")
        ask_input = gr.Textbox(
            label="Ask anything across your inventory, lists, and prices",
            placeholder="Do we have milk?  |  What should I buy today?  |  Where is toothpaste?",
            lines=2,
        )
        ask_btn = gr.Button("Ask")
        ask_output = gr.JSON(label="Answer")
        ask_btn.click(
            ask_shopstack,
            ask_input,
            ask_output,
            api_name="ask",
            api_description="Ask the ShopStack agent a natural language question about inventory, shopping, or prices",
        )
        ask_input.submit(
            ask_shopstack,
            ask_input,
            ask_output,
            api_name="ask_submit",
            api_description="Submit question via Enter key",
        )

    return TodayTabHandles(
        today_stats=today_stats,
        today_soon=today_soon,
        today_list=today_list,
        today_low=today_low,
        today_recent=today_recent,
        today_changed=today_changed,
    )
