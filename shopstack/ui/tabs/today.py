"""Today tab — decision-first dashboard with embedded Ask ShopStack.

This is the first thing the user sees when they open ShopStack. It answers
"what should I do right now?" by surfacing:
- Use-soon items (expiring/aging inventory)
- Low-stock alerts
- Recent purchase activity
- "What changed" diff vs last session
- Embedded Ask ShopStack textbox (natural language queries)

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

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.screens import ask_shopstack, today_dashboard
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
        blocks: Alias for the parent `gr.Blocks`. Kept for symmetry with other
            tab builders and to make the call-site read consistently.
        app: The root `gr.Blocks` instance — needed for `app.load(...)` to
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
        gr.Markdown("### Ask ShopStack")
        ask_input = gr.Textbox(
            label="Ask anything across your inventory, lists, and prices",
            placeholder="Do we have milk?  |  What should I buy today?  |  Where is toothpaste?",
            lines=2,
        )
        ask_btn = gr.Button("Ask")
        ask_output = gr.JSON(label="Structured Response")
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
