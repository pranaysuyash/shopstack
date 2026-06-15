"""Smart Basket tab — optimized basket with community median comparison.

Wraps :mod:`shopstack.ui.screens.smart_basket` with Gradio components:
items text input, city input, build button, and results HTML.
"""

from __future__ import annotations

import json
import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import empty_state_enhanced
from shopstack.ui.screens.smart_basket import smart_basket_screen
from shopstack.ui.tabs.context import TabContext


def build_smart_basket_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Smart Basket tab."""
    with gr.Tab(_tab_label("smart_basket"), id="smart_basket"):
        gr.Markdown("### Smart Basket")
        gr.HTML(
            "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
            "Enter items you want to buy. The system compares prices across "
            "sources, checks community medians, and builds an optimized basket."
            "</div>"
        )
        sb_input = gr.Textbox(
            label="Items (JSON array)",
            lines=4,
            placeholder='[{"canonical_name": "tomato", "quantity": 1, "unit": "kg"}, '
                        '{"canonical_name": "onion", "quantity": 2, "unit": "kg"}]',
        )
        with gr.Row():
            sb_city = gr.Textbox(label="City", value="mumbai", scale=2)
            sb_build = gr.Button("Build basket", variant="primary", scale=0)
        sb_result = gr.HTML(empty_state_enhanced(
            "Enter items above and click Build basket.", icon="\U0001f6d2"
        ))

        def _build_from_text(items_text: str, city: str) -> str:
            if not items_text or not items_text.strip():
                return empty_state_enhanced("Enter items first.", icon="\U0001f6d2")
            try:
                items = json.loads(items_text)
            except json.JSONDecodeError:
                return empty_state_enhanced("Invalid JSON. Use [{\"canonical_name\": \"...\", ...}]",
                                            icon="\u26a0")
            return smart_basket_screen(items=items, city=city)

        sb_build.click(_build_from_text, [sb_input, sb_city], sb_result,
                       api_name="smart_basket_build",
                       api_description="Build an optimized shopping basket from a JSON item list, comparing prices across sources")
