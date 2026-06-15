"""Store Mode tab — large-touch-target shopping list for in-store use.

Wraps :mod:`shopstack.ui.screens.store_mode` with Gradio components:
store mode view with big touch-friendly checkboxes.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import empty_state_enhanced
from shopstack.ui.screens.store_mode import store_mode_view
from shopstack.ui.tabs.context import TabContext


def build_store_mode_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Store Mode tab."""
    with gr.Tab(_tab_label("store_mode"), id="store_mode"):
        gr.Markdown("### Store Mode")
        gr.HTML(
            "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
            "Large touch-friendly shopping list for in-store use. "
            "Tap items to mark as checked."
            "</div>"
        )
        sm_output = gr.HTML(empty_state_enhanced(
            "Loading your shopping list...", icon="\U0001f6d2"
        ))
        sm_refresh = gr.Button("Refresh", elem_classes="secondary")
        sm_refresh.click(store_mode_view, outputs=sm_output,
                         api_name="store_mode_refresh",
                         api_description="Refresh the large-touch shopping list for in-store use")
        app.load(store_mode_view, outputs=sm_output)
