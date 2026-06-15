"""Parser Test tab — fine-tuned parser preview panel.

Wraps :mod:`shopstack.ui.screens.parser_preview` with Gradio components:
utterance input, parse button, and intent classification HTML.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.services.empty_states import (
    build_household_context,
    render,
)
from shopstack.ui.components.primitives import empty_state_enhanced
from shopstack.ui.screens.parser_preview import parser_preview_screen
from shopstack.ui.tabs.context import TabContext


def build_parser_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Parser Test tab."""
    # Pass 17 §2.5: rich empty-state for the "Type a command to see
    # the parser in action" placeholder. The previous generic
    # one-liner (line 30 before Pass 17) was a static "no input yet"
    # state. The rich service + i18n keys turn it into a 3-line
    # card with an icon and an example command.
    household_ctx = build_household_context(ctx.db)
    parser_empty_state = render(
        "parser.no_input", household=household_ctx
    )
    with gr.Tab(_tab_label("parser"), id="parser"):
        gr.Markdown("### Parser Test")
        gr.HTML(
            "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
            "Test the fine-tuned intent parser. Type a command and see "
            "what the system understood."
            "</div>"
        )
        pr_input = gr.Textbox(label="Natural language command", lines=3,
                              placeholder="e.g. add doodh and 2 kg atta to my shopping list")
        pr_parse = gr.Button("Parse", variant="primary")
        pr_output = gr.HTML(parser_empty_state)

        pr_parse.click(
            parser_preview_screen,
            inputs=[pr_input],
            outputs=[pr_output],
            api_name="parser_preview",
            api_description="Parse a natural-language command and display intent classification results",
        )
