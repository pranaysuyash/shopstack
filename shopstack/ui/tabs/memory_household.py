"""Memory tab — Household management sub-builder.

Wires the archived ``_legacy/households`` screens into a visible
Gradio sub-tab inside the Memory tab. This is Phase 10 #1 wiring:

  - ``households_panel_screen`` — shows current members + roles
  - ``add_member_screen`` — form to invite a new member
  - ``remove_member_screen`` — remove an existing member
  - ``change_role_screen`` — change a member's role

The underlying service layer (``shopstack.services.permissions``)
has full CRUD for household members. This sub-builder is the
final UI wire-up that makes the archived code visible again.
"""

from __future__ import annotations

import gradio as gr

from shopstack.ui.components.primitives import loading_skeleton
from shopstack.ui.screens._legacy.households import (
    add_member_screen,
    households_panel_screen,
    remove_member_screen,
    change_role_screen,
    list_user_households_screen,
)
from shopstack.ui.tabs.context import TabContext


def build_memory_household(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Household sub-tab inside the Memory tab.

    Shows current members, a summary of the user's households,
    and forms to add/remove/change roles.

    Args:
        app: The root gr.Blocks instance — needed for ``app.load(...)``.
        ctx: Shared dependencies (unused in this sub-builder, kept for
            uniform signature).

    Returns:
        None. No cross-sub-tab references.
    """
    members_html = gr.HTML(loading_skeleton("card"))
    toast_output = gr.HTML(visible=False)

    # Member list — loaded on page load
    app.load(households_panel_screen, outputs=members_html)

    gr.Markdown("### Your Households")
    your_hhs = gr.HTML()
    app.load(list_user_households_screen, outputs=your_hhs)

    with gr.Group():
        gr.Markdown("### Add Member")
        with gr.Row():
            add_user_id = gr.Textbox(label="User ID", placeholder="e.g. family_member_1")
            add_role = gr.Dropdown(
                label="Role",
                choices=["member", "guest"],
                value="member",
            )
        add_btn = gr.Button("Add Member", variant="primary", scale=1)

    with gr.Group():
        gr.Markdown("### Remove Member")
        remove_user_id = gr.Textbox(label="User ID to remove", placeholder="e.g. family_member_1")
        remove_btn = gr.Button("Remove", variant="secondary", scale=1)

    with gr.Group():
        gr.Markdown("### Change Role")
        with gr.Row():
            change_user_id = gr.Textbox(label="User ID", placeholder="e.g. family_member_1")
            change_role_dd = gr.Dropdown(
                label="New role",
                choices=["owner", "member", "guest"],
                value="member",
            )
        change_btn = gr.Button("Change Role", variant="secondary", scale=1)

    # Wire add member
    def _add_member_wrapper(user_id: str, role: str) -> tuple[str, str]:
        from shopstack.app_context import current_user_id as _cuid
        actor = _cuid() or ""
        if not actor:
            return "<div class='perm-empty'>No active household user.</div>", ""
        return add_member_screen(actor, user_id, role, actor)

    add_btn.click(
        _add_member_wrapper,
        inputs=[add_user_id, add_role],
        outputs=[members_html, toast_output],
        api_name="household_add_member",
        api_description="Add a new member to the active household",
    )

    # Wire remove member
    def _remove_member_wrapper(user_id: str) -> tuple[str, str]:
        from shopstack.app_context import current_user_id as _cuid
        actor = _cuid() or ""
        if not actor:
            return "<div class='perm-empty'>No active household user.</div>", ""
        return remove_member_screen(actor, user_id, actor)

    remove_btn.click(
        _remove_member_wrapper,
        inputs=[remove_user_id],
        outputs=[members_html, toast_output],
        api_name="household_remove_member",
        api_description="Remove a member from the active household",
    )

    # Wire change role
    def _change_role_wrapper(user_id: str, new_role: str) -> tuple[str, str]:
        from shopstack.app_context import current_user_id as _cuid
        actor = _cuid() or ""
        if not actor:
            return "<div class='perm-empty'>No active household user.</div>", ""
        return change_role_screen(actor, user_id, new_role, actor)

    change_btn.click(
        _change_role_wrapper,
        inputs=[change_user_id, change_role_dd],
        outputs=[members_html, toast_output],
        api_name="household_change_role",
        api_description="Change a member's role in the active household",
    )

    # Manual refresh button
    refresh_btn = gr.Button("Refresh members", scale=1)
    refresh_btn.click(
        households_panel_screen,
        outputs=members_html,
        api_name="household_refresh",
        api_description="Refresh the household members panel",
    )

    # Toast display — show the toast message from the last action
    toast_display = gr.HTML(visible=True)
    toast_output.change(
        lambda msg: f"<div style='padding:8px;border-radius:6px;background:var(--bg-card);'>{msg}</div>",
        inputs=[toast_output],
        outputs=[toast_display],
    )
