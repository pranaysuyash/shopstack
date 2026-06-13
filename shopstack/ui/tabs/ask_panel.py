"""Ask ShopStack panel — natural-language queries across the full app.

This is a sub-builder of the Today tab: a textbox + button that fires the
AI planner (via `shopstack.ui.screens.ask_shopstack`) and renders the
structured response in a `gr.JSON` panel. The submit button and Enter-key
both fire the handler.

Extracted from `build_today_tab()` so that:
- The Ask feature is independently testable in isolation.
- The Today tab builder is shorter and more focused on the dashboard.
- The same panel can be reused in other tabs (e.g. a future Help tab)
  without duplicating the wiring.

The panel returns an `AskPanelHandles` dataclass exposing the
`ask_input` and `ask_output` components. Currently nothing else in the
app references them, but the handles are exposed for symmetry with the
tab-builder pattern and to enable future cross-tab interactions (e.g.
clearing the input on tab switch).
"""
from __future__ import annotations

from dataclasses import dataclass

import gradio as gr

from shopstack.ui.screens import ask_shopstack
from shopstack.ui.tabs.context import TabContext


@dataclass
class AskPanelHandles:
    """Components that other parts of the app may reference after the Ask panel builds.

    Currently no cross-tab references exist, but the handles are
    exposed for future use (e.g. clearing `ask_input` on household
    switch, or populating `ask_input` from a quick-action elsewhere).
    """
    ask_input: gr.Textbox
    ask_output: gr.JSON


def build_ask_panel(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> AskPanelHandles:
    """Build the Ask ShopStack panel inside the parent's `gr.Tabs` context.

    Adds a `gr.Markdown` separator, a `gr.Markdown` heading, a text input,
    a submit button, and a `gr.JSON` output. Wires:
    - The button's `click` event to `ask_shopstack`.
    - The textbox's `submit` event (Enter key) to `ask_shopstack`.

    Args:
        blocks: Alias for the parent gr.Blocks. Kept for symmetry with
            the other tab builders.
        app: The root gr.Blocks instance — needed for `app.load(...)`
            handlers (not used in this panel, but part of the uniform
            builder signature).
        ctx: Shared dependencies (unused in this panel, but part of the
            uniform builder signature).

    Returns:
        AskPanelHandles: the input and output components, in case future
        cross-tab interactions need them.
    """
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

    return AskPanelHandles(ask_input=ask_input, ask_output=ask_output)
