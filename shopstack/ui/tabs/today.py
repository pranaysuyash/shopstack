"""Today tab — decision-first dashboard with embedded Ask ShopStack.

This is the first thing the user sees when they open ShopStack. It answers
"what should I do right now?" by surfacing:
- Use-soon items (expiring/aging inventory)
- Low-stock alerts
- Recent purchase activity
- "What changed" diff vs last session
- **Restock predictions** with one-click "add to my shopping list" action

The `today_dashboard()` screen function returns a 6-tuple of HTML strings;
we register it as an `app.load` handler so the panel populates on page open.

The Ask ShopStack sub-section is co-located with the dashboard so the user
doesn't need a separate tab for simple questions. The Ask panel is built
by `shopstack.ui.tabs.ask_panel.build_ask_panel` (a sub-builder of this
tab) so the wiring is testable in isolation and reusable.
"""
from __future__ import annotations

from dataclasses import dataclass

import gradio as gr

from shopstack.app_context import current_user_id, db
from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import loading_skeleton, toast
from shopstack.ui.screens import today_dashboard
from shopstack.ui.tabs.ask_panel import build_ask_panel
from shopstack.ui.tabs.context import TabContext


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
        # ── Phase 9 Today Intelligence (unified action surface) ──
        # Sits above the per-signal sections because it answers
        # the user's actual question: "what should I do right now?"
        gr.Markdown("### 🎯 Today intelligence")
        gr.Markdown(
            "The top 5 things worth doing right now — use-soon, "
            "restock-due, price-drops, and overpriced-vs-community "
            "rolled up into one ranked list. Trip advisor call below."
        )
        from shopstack.ui.screens.today_intelligence import today_intelligence_screen
        def _today_intel() -> str:
            try:
                return today_intelligence_screen()
            except Exception as exc:
                return f"<div>Today intelligence unavailable: {exc}</div>"
        today_intel_html = gr.HTML(loading_skeleton("card"))
        today_intel_refresh = gr.Button("🔄 Refresh", elem_classes="secondary", size="sm")
        today_intel_refresh.click(
            _today_intel, outputs=today_intel_html,
            api_name="today_intel_refresh",
            api_description="Refresh the unified Today intelligence block",
        )
        app.load(_today_intel, outputs=today_intel_html)

        # ── Phase 10 Restock next 7 days card ────────────────────
        gr.Markdown("### 📦 Restock next 7 days")
        gr.Markdown(
            "Items you'll likely run out of soon, with a one-tap "
            "**Add to my list** action for each. Sorted soonest first."
        )
        from shopstack.services.restock_card import (
            restock_card_screen as _restock_card,
            add_restock_to_list as _add_restock,
        )
        restock_card_html = gr.HTML(loading_skeleton("card"))
        def _restock_refresh() -> str:
            try:
                return _restock_card()
            except Exception as exc:
                return f"<div>Restock card unavailable: {exc}</div>"
        restock_refresh = gr.Button("🔄 Refresh", elem_classes="secondary", size="sm")
        restock_refresh.click(
            _restock_refresh, outputs=restock_card_html,
            api_name="restock_refresh",
            api_description="Refresh the restock next 7 days card",
        )
        app.load(_restock_refresh, outputs=restock_card_html)
        # Quick-add row: textbox + button for one-tap add
        with gr.Row():
            restock_item_input = gr.Textbox(
                label="Quick add: type an item name to add to your list",
                placeholder="e.g. milk, bread, rice",
                scale=4,
            )
            restock_add_btn = gr.Button("Add to my shopping list", variant="primary", scale=1)
        restock_quick_output = gr.HTML("")
        restock_add_btn.click(
            _add_restock,
            restock_item_input,
            restock_quick_output,
            api_name="restock_quick_add",
            api_description="Add a restock prediction to the active shopping list by name",
        )

        gr.Markdown("---")
        gr.Markdown("### Detailed signals")
        today_stats = gr.HTML(loading_skeleton("card"))
        today_soon = gr.HTML(loading_skeleton("card"))
        today_list = gr.HTML(loading_skeleton("card"))
        today_low = gr.HTML(loading_skeleton("card"))
        today_recent = gr.HTML(loading_skeleton("card"))
        today_changed = gr.HTML(loading_skeleton("card"))
        app.load(today_dashboard, outputs=[today_stats, today_soon, today_list,
                                            today_low, today_recent, today_changed])

        gr.Markdown("---")
        # Item 9: The old duplicate restock dataframe table has been removed.
        # Restock predictions are surfaced via the intelligence block and
        # the restock card above.

        gr.Markdown("### Ask ShopStack")
        build_ask_panel(blocks=app, app=app, ctx=ctx)

    return TodayTabHandles(
        today_stats=today_stats,
        today_soon=today_soon,
        today_list=today_list,
        today_low=today_low,
        today_recent=today_recent,
        today_changed=today_changed,
    )
