"""Memory tab — Patterns (Intelligence) sub-builder.

Extracted from ``build_memory_tab`` so the intelligence dashboard
(waste patterns, inferred preferences, price memory analysis) is
independently testable and reusable.

The sub-builder adds a Markdown header, a refresh button, three
HTML cards (waste, preferences, price), and a "Delete preference by
signal ID" form with the 2-step confirm pattern (per §0.10
observability + §0.14 operator workflow). On page load and on
button click, the screen function ``get_intelligence_dashboard`` is
called to populate the cards.
"""
from __future__ import annotations

import gradio as gr

from shopstack.ui.components.primitives import (
    confirm_dialog,
    confirm_hide_updates,
    confirm_toggle_updates,
    loading_skeleton,
)
from shopstack.ui.screens import get_intelligence_dashboard
from shopstack.ui.screens.intelligence import delete_preference
from shopstack.ui.tabs.context import TabContext


def build_memory_intelligence(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Patterns (Intelligence) sub-tab inside the Memory tab.

    Adds a refresh button + three HTML cards + a 2-step-confirm
    "Delete preference" form. The cards are populated on page load
    and on button click.

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

    # ── Delete preference by signal ID (2-step confirm) ─────────
    gr.Markdown("### Remove a preference")
    gr.Markdown(
        "To remove a learned preference, copy its `signal_id` from "
        "the card above and paste it here. This is destructive — "
        "the preference and its learned signal are deleted. The 2-step "
        "confirm pattern below prevents accidental clicks."
    )
    with gr.Row():
        intel_del_signal_id = gr.Textbox(
            label="Signal ID to delete",
            placeholder="paste signal_id here",
            scale=3,
        )
        intel_del_btn = gr.Button("Remove preference", elem_classes="secondary", scale=0)
    with gr.Group(visible=False) as intel_del_confirm_group:
        gr.HTML(
            confirm_dialog(
                "Remove this preference signal? This is hard to undo.",
                confirm_label="Yes, Remove",
                variant="danger",
            )
        )
        with gr.Row():
            intel_del_yes_btn = gr.Button(
                "Yes, Remove", variant="stop", scale=0
            )
            intel_del_no_btn = gr.Button("Cancel", elem_classes="secondary", scale=0)
    intel_del_result = gr.HTML("")

    # Refresh the preference card after a successful delete so the
    # user sees the change immediately.
    def _delete_and_refresh(signal_id: str):
        result = delete_preference(signal_id)
        refreshed = get_intelligence_dashboard()
        # get_intelligence_dashboard returns (waste, pref, price)
        return result, refreshed[0], refreshed[1], refreshed[2]

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
    # 2-step delete preference: first click shows confirm, second click fires
    intel_del_btn.click(
        confirm_toggle_updates,
        None,
        [intel_del_btn, intel_del_confirm_group],
    )
    intel_del_yes_btn.click(
        _delete_and_refresh,
        intel_del_signal_id,
        [intel_del_result, intel_waste_html, intel_pref_html, intel_price_html],
    ).then(
        confirm_hide_updates,
        None,
        [intel_del_btn, intel_del_confirm_group],
    )
    intel_del_no_btn.click(
        confirm_hide_updates,
        None,
        [intel_del_btn, intel_del_confirm_group],
    )
