"""Parser Test tab — fine-tuned parser preview panel.

Wraps :mod:`shopstack.ui.screens.parser_preview` with Gradio components:
utterance input, parse button, and intent classification HTML.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import empty_state_enhanced
from shopstack.ui.screens.parser_preview import parser_preview_screen
from shopstack.ui.tabs.context import TabContext


def build_parser_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Parser Test tab."""
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
        pr_output = gr.HTML(empty_state_enhanced(
            "Type a command and click Parse.", icon="\U0001f9e0"
        ))

        pr_parse.click(parser_preview_screen, pr_input, pr_output,
                       api_name="parser_preview",
                       api_description="Parse a natural-language command and display intent classification results")
