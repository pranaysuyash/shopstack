"""Community tab — community price map opt-in and pool stats.

Wraps :mod:`shopstack.ui.screens.community` with Gradio components:
opt-in toggle, pool stats, and community price indicator.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import empty_state_enhanced
from shopstack.ui.screens.community import (
    community_pool_stats_screen,
    community_status_screen,
    set_opt_in_screen,
)
from shopstack.ui.tabs.context import TabContext


def build_community_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Community tab."""
    with gr.Tab(_tab_label("community"), id="community"):
        gr.Markdown("### Community Price Map")
        gr.HTML(
            "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
            "Share and compare prices anonymously with your local community. "
            "Opt in to contribute and see community medians."
            "</div>"
        )
        cm_status = gr.HTML(loading_skeleton())
        cm_pool = gr.HTML(loading_skeleton())
        with gr.Row():
            cm_opt_in = gr.Button("Opt in", variant="primary", scale=1)
            cm_opt_out = gr.Button("Opt out", scale=1)
            cm_refresh = gr.Button("Refresh", elem_classes="secondary", scale=0)
        cm_result = gr.HTML("")

        cm_refresh.click(lambda: (community_status_screen(), community_pool_stats_screen()),
                         outputs=[cm_status, cm_pool],
                         api_name="community_refresh")
        cm_opt_in.click(lambda: set_opt_in_screen(True), outputs=[cm_status, cm_result],
                        api_name="community_opt_in")
        cm_opt_out.click(lambda: set_opt_in_screen(False), outputs=[cm_status, cm_result],
                         api_name="community_opt_out")
        app.load(lambda: (community_status_screen(), community_pool_stats_screen()),
                 outputs=[cm_status, cm_pool])


def loading_skeleton() -> str:
    """Minimal loading placeholder."""
    return "<div style='padding:8px;color:var(--text-dim);font-size:0.75rem;'>Loading...</div>"
