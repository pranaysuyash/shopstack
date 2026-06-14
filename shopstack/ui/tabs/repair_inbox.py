"""Repair Inbox tab — operator view of open condition/damage issues.

Wraps :mod:`shopstack.ui.screens.repair_inbox` with Gradio components:
inbox view with severity filter, report-damage form, confirm/close/delete
actions.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import empty_state_enhanced, loading_skeleton
from shopstack.ui.screens.repair_inbox import (
    close_condition_event,
    confirm_condition_event,
    delete_condition_event,
    repair_inbox_view,
    report_damage,
)
from shopstack.ui.tabs.context import TabContext


def build_repair_inbox_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Repair Inbox tab."""
    with gr.Tab(_tab_label("repair_inbox"), id="repair_inbox"):
        gr.Markdown("### Repair Inbox")
        ri_severity = gr.Dropdown(
            label="Filter by severity",
            choices=[("All", ""), ("Spoiled", "spoiled"), ("Broken", "broken"),
                     ("Damaged", "damaged"), ("Worn", "worn"), ("Cosmetic", "cosmetic")],
            value="",
        )
        ri_refresh = gr.Button("Refresh", elem_classes="secondary")
        ri_view = gr.HTML(loading_skeleton("card"))

        gr.Markdown("---")
        gr.Markdown("### Report damage")
        with gr.Row():
            ri_lot = gr.Textbox(label="Lot ID", scale=2)
            ri_kind = gr.Dropdown(
                label="Kind",
                choices=["physical_damage", "liquid_leak", "expiry_risk", "wear_tear",
                         "packaging_damage", "visual_change", "other"],
                value="other",
                scale=1,
            )
            ri_sev = gr.Dropdown(
                label="Severity",
                choices=["cosmetic", "worn", "damaged", "broken", "spoiled"],
                value="worn",
                scale=1,
            )
        ri_desc = gr.Textbox(label="Description", lines=2, placeholder="What happened?")
        ri_report = gr.Button("Report")
        ri_result = gr.HTML("")

        with gr.Row():
            ri_confirm = gr.Textbox(label="Event ID to confirm", scale=2)
            ri_confirm_btn = gr.Button("Confirm", scale=0)
            ri_close = gr.Textbox(label="Event ID to close", scale=2)
            ri_close_btn = gr.Button("Close", scale=0)
            ri_delete = gr.Textbox(label="Event ID to delete", scale=2)
            ri_delete_btn = gr.Button("Delete", scale=0)
        ri_action_result = gr.HTML("")

        ri_refresh.click(repair_inbox_view, ri_severity, ri_view,
                         api_name="repair_inbox_refresh")
        ri_report.click(report_damage, [ri_lot, ri_kind, ri_sev, ri_desc], ri_result,
                        api_name="report_damage")
        ri_confirm_btn.click(confirm_condition_event, ri_confirm, ri_action_result,
                             api_name="confirm_condition_event")
        ri_close_btn.click(close_condition_event, ri_close, ri_action_result,
                           api_name="close_condition_event")
        ri_delete_btn.click(delete_condition_event, ri_delete, ri_action_result,
                            api_name="delete_condition_event")
        app.load(repair_inbox_view, inputs=ri_severity, outputs=ri_view)
