"""Memory tab — System + Backup sub-builders.

Extracted from ``build_memory_tab`` so:
- The developer-only "Advanced" sub-tab (model stack, provider status)
  is independently testable.
- The "Backup" sub-tab (export/import portability) with its two nested
  sub-tabs (Export, Import) is independently testable.

The Advanced sub-tab is gated by ``settings.ui_mode == "developer"`` and
renders nothing for non-developer modes. The Backup sub-tab is always
visible.

The "Recent corrections" panel (added 2026-06-15) closes the invisible
learning loop: the user can see, accept, or reject the corrections
that ShopStack has learned from their reconciliation feedback.
"""
from __future__ import annotations

import gradio as gr

from shopstack.app_context import current_user_id, db
from shopstack.config import settings
from shopstack.ui.components.primitives import (
    empty_state_enhanced,
    loading_skeleton,
)
from shopstack.ui.screens import (
    accept_correction_event,
    export_data_csv,
    export_data_json,
    import_data_file,
    model_budget_view,
    model_eval_view,
    reject_correction_event,
    render_recent_corrections_html,
)
# 2026-06-15 (Pass 20): import the "Record a correction" handler
# so the Memory → Recent corrections sub-tab can offer a
# user-facing creation flow (the "Mark as wrong" button
# equivalent at the form level). This closes the full
# learning loop: the user records a correction, the engine
# picks it up on the next decision.
from shopstack.ui.screens.corrections import record_correction_handler
from shopstack.services.memory_facts import render_memory_facts
from shopstack.ui.tabs.context import TabContext


def build_memory_corrections(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Recent corrections sub-tab inside the Memory tab.

    The panel shows the user's most recent pending correction events
    (one row per event) with inline Accept / Reject buttons. The
    handlers are wired to update the ``accepted`` flag on the
    ``correction_events`` table; the underlying preference signals
    (already produced by ``PreferenceService.record_correction``)
    are not modified here.

    Pass 20 also adds a "Record a new correction" form at the
    top of the sub-tab. This closes the full learning loop:
    the user can record a correction (e.g. "I marked BUY
    wrong — it should be SKIP because I have plenty"), and
    the engine adjusts future decisions on the same item.
    """
    with gr.Tab("Recent corrections"):
        gr.Markdown(
            "ShopStack records every correction from reconciliation. "
            "Accept a correction to lock the learning, or reject it to "
            "mark the event as untrusted. The underlying preference signal "
            "stays in place — you can retract it from **Preferences** if "
            "you want to undo the system-wide effect."
        )
        # 2026-06-15 (Pass 20): "Record a new correction" form.
        # This is the creation flow for the learning loop. The
        # user enters the item name, the action the system
        # recommended, the action they think should have been
        # recommended, and an optional reason. On submit, the
        # correction is recorded and the panel refreshes.
        with gr.Group():
            gr.Markdown("### Record a new correction")
            with gr.Row():
                correction_canonical = gr.Textbox(
                    label="Item name (e.g. 'milk', 'rice')",
                    placeholder="milk",
                )
                correction_was = gr.Dropdown(
                    label="System said",
                    choices=[
                        "buy", "skip", "use_soon", "compare", "wait",
                        "substitute", "watch", "confirm", "optional",
                    ],
                    value="buy",
                )
                correction_should_be = gr.Dropdown(
                    label="Should have said",
                    choices=[
                        "buy", "skip", "use_soon", "compare", "wait",
                        "substitute", "watch", "confirm", "optional",
                    ],
                    value="skip",
                )
            correction_reason = gr.Textbox(
                label="Reason (optional)",
                placeholder="I have plenty at home",
                lines=2,
            )
            record_btn = gr.Button(
                "Record correction",
                variant="primary",
                elem_classes="corrections-record-btn",
            )
        corrections_html = gr.HTML(loading_skeleton("card"))
        corrections_event_id = gr.Textbox(
            visible=False,
            label="Selected correction event id",
        )
        with gr.Row():
            accept_btn = gr.Button("Accept", variant="primary", elem_classes="corrections-accept-btn", scale=1)
            reject_btn = gr.Button("Reject", elem_classes="corrections-reject-btn secondary", scale=1)
            refresh_btn = gr.Button("Refresh", scale=1)

        # The inline Accept/Reject buttons need the event id of the
        # row they belong to. To keep the UI simple and the panel
        # server-rendered, we expose a textbox that the user can
        # paste the event id from. This is the same pattern the
        # Memory tab uses for trace search. The hidden textbox is
        # populated by a JS hook (added in a follow-up) or by the
        # user copy-pasting the id from a row.
        accept_btn.click(
            accept_correction_event,
            inputs=[corrections_event_id],
            outputs=[corrections_html],
            api_name="memory_corrections_accept",
            api_description="Accept a pending correction event",
        )
        reject_btn.click(
            reject_correction_event,
            inputs=[corrections_event_id],
            outputs=[corrections_html],
            api_name="memory_corrections_reject",
            api_description="Reject a pending correction event",
        )
        refresh_btn.click(
            render_recent_corrections_html,
            inputs=[],
            outputs=[corrections_html],
            api_name="memory_corrections_refresh",
            api_description="Refresh the recent-corrections panel",
        )
        # Pass 20: wire the "Record a correction" form to the
        # handler. On submit, the correction is persisted and
        # the panel refreshes to show the new event.
        record_btn.click(
            record_correction_handler,
            inputs=[
                correction_canonical,
                correction_was,
                correction_should_be,
                correction_reason,
            ],
            outputs=[corrections_html],
            api_name="memory_corrections_record",
            api_description="Record a new user correction",
        )
        app.load(render_recent_corrections_html, outputs=corrections_html)


def build_memory_facts(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Insights sub-tab inside the Memory tab.

    The Insights sub-tab shows the user what ShopStack has learned
    about their household (e.g. "Your household usually buys: Milk
    every 3 days"). The data layer
    (:mod:`shopstack.services.memory_facts`) and the renderer
    (:func:`render_memory_facts`) are already implemented; this
    sub-builder wires them into a Gradio sub-tab.

    Per motto_v3 §7 supersession: the sub-builder does NOT introduce
    a new renderer or a new data source. It only wires the canonical
    :func:`render_memory_facts` into a Gradio sub-tab with the
    standard ``(app, ctx)`` signature used by sibling sub-builders.

    Args:
        app: The root gr.Blocks instance — needed for ``app.load(...)``.
        ctx: Shared dependencies (currently unused here, kept for
            uniform signature with sibling builders).

    Returns:
        None. No cross-sub-tab references.
    """
    insights_html = gr.HTML(loading_skeleton("card"))
    # Populate on initial page load (Tier 2 evidence: the renderer
    # is the same function the data layer exports — no fork).
    app.load(render_memory_facts, outputs=insights_html)
    # Expose a manual refresh button so the user can re-render after
    # adding purchases elsewhere (per the home screen review P2).
    refresh_btn = gr.Button("Refresh insights", scale=1)
    refresh_btn.click(
        render_memory_facts,
        outputs=insights_html,
        api_name="memory_insights_refresh",
        api_description="Re-render the household memory insights cards",
    )


def build_memory_advanced(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Advanced sub-tab (developer mode only) inside the Memory tab.

    Renders the model stack / budget view and the o/p eval panel. Only
    adds the sub-tab if ``settings.ui_mode == "developer"`` is True; for
    non-developer modes this function is a no-op.

    Args:
        app: The root gr.Blocks instance — needed for ``app.load(...)``.
        ctx: Shared dependencies (unused in this sub-tab, kept for
            uniform signature).

    Returns:
        None. No cross-sub-tab references.
    """
    if settings.ui_mode != "developer":
        return
    with gr.Tab("Model Stack"):
        model_stack_html = gr.HTML(loading_skeleton("card"))
        app.load(model_budget_view, outputs=model_stack_html)
    with gr.Tab("Model Output Eval"):
        model_eval_html = gr.HTML(loading_skeleton("card"))
        app.load(model_eval_view, outputs=model_eval_html)
        refresh_btn = gr.Button("Refresh eval", scale=1)
        refresh_btn.click(
            model_eval_view,
            outputs=model_eval_html,
            api_name="model_eval_refresh",
            api_description="Re-render per-route o/p eval stats and recent records",
        )


def build_memory_backup(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Backup sub-tab inside the Memory tab.

    Two nested sub-tabs:
    - **Export** — back up pantry as JSON or CSV, with download.
    - **Import** — restore from a backup file.

    Args:
        app: The root gr.Blocks instance — needed for ``app.load(...)``.
        ctx: Shared dependencies (unused in this sub-tab, kept for
            uniform signature).

    Returns:
        None. No cross-sub-tab references.
    """
    with gr.Tab("Export"):
        export_json_btn = gr.Button("Back up pantry (JSON)")
        export_csv_btn = gr.Button("Back up pantry (CSV)")
        export_file = gr.File(label="Download", visible=False)
        export_json_btn.click(
            export_data_json,
            outputs=export_file,
            api_name="export_json",
            api_description="Export inventory state to JSON",
        ).then(
            lambda f: gr.update(value=f, visible=True) if f else gr.update(visible=False),
            export_file,
            export_file,
        )
        export_csv_btn.click(
            export_data_csv,
            outputs=export_file,
            api_name="export_csv",
            api_description="Export inventory state to CSV",
        ).then(
            lambda f: gr.update(value=f, visible=True) if f else gr.update(visible=False),
            export_file,
            export_file,
        )
    with gr.Tab("Import"):
        import_file = gr.File(
            label="Choose a backup file (JSON or CSV)",
            file_count="single",
        )
        import_btn = gr.Button("Restore from backup")
        import_result = gr.HTML(
            empty_state_enhanced(
                "Choose a backup file above and click Restore to "
                "add items back into your pantry.",
                icon="📥",
            )
        )
        import_btn.click(
            import_data_file,
            import_file,
            import_result,
            api_name="import_data",
            api_description="Import inventory from JSON or CSV file",
        )
