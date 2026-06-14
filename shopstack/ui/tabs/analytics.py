"""Analytics tab — household usage analytics from trace stream.

Wraps :mod:`shopstack.ui.screens.analytics` with Gradio components:
window-days slider, refresh button, and analytics HTML panel.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import loading_skeleton
from shopstack.ui.screens.analytics import analytics_screen
from shopstack.ui.tabs.context import TabContext


def build_analytics_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Analytics tab."""
    with gr.Tab(_tab_label("analytics"), id="analytics"):
        gr.Markdown("### Household Analytics")
        gr.HTML(
            "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
            "Usage patterns, timing, and trends based on your trace history."
            "</div>"
        )
        with gr.Row():
            an_days = gr.Slider(minimum=7, maximum=365, value=180, step=1,
                                label="Window (days)", scale=3)
            an_refresh = gr.Button("Refresh", elem_classes="secondary", scale=0)
        an_output = gr.HTML(loading_skeleton("card"))

        an_refresh.click(analytics_screen, an_days, an_output,
                         api_name="analytics_refresh")
        app.load(analytics_screen, inputs=an_days, outputs=an_output)
