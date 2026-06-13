"""Memory tab — Patterns (Intelligence) sub-builder.

Extracted from ``build_memory_tab`` so the intelligence dashboard
(waste patterns, inferred preferences, price memory analysis) is
independently testable and reusable.

The sub-builder adds a Markdown header, a refresh button, and three
HTML cards (waste, preferences, price). On page load and on button
click, the screen function ``get_intelligence_dashboard`` is called
to populate the cards.
"""
from __future__ import annotations

import gradio as gr

from shopstack.ui.components.primitives import loading_skeleton
from shopstack.ui.screens import get_intelligence_dashboard
from shopstack.ui.tabs.context import TabContext


def build_memory_intelligence(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Patterns (Intelligence) sub-tab inside the Memory tab.

    Adds a refresh button + three HTML cards. The cards are populated
    on page load and on button click.

    Args:
        app: The root gr.Blocks instance — needed for ``app.load(...)``
            handlers.
        ctx: Shared dependencies (unused in this sub-tab, but part of
            the uniform builder signature for symmetry with other
            sub-builders).

    Returns:
        None. No components need to be referenced by other sub-tabs
        within the Memory tab, so no Handles dataclass is needed.
    """
    gr.Markdown("### What we have learned")
    gr.Markdown(
        "Waste patterns, inferred preferences, and price memory analysis."
    )
    with gr.Row():
        intel_refresh_btn = gr.Button("Refresh patterns", elem_classes="secondary")
    intel_waste_html = gr.HTML(loading_skeleton(variant="card"))
    intel_pref_html = gr.HTML(loading_skeleton(variant="card"))
    intel_price_html = gr.HTML(loading_skeleton(variant="card"))

    intel_refresh_btn.click(
        get_intelligence_dashboard,
        None,
        [intel_waste_html, intel_pref_html, intel_price_html],
    )
    app.load(
        get_intelligence_dashboard,
        None,
        [intel_waste_html, intel_pref_html, intel_price_html],
    )
