"""Household settings accordion — workspace admin panel (Phase 8 #15 + #24).

This is the "Household settings" ``gr.Accordion`` that lives outside the
main tab strip. It composes three sub-features that are loosely coupled
but share the "household-level / privacy / device pairing" mental bucket:

1. **Household switcher** — switch active household or create a new one.
   State machine is in :mod:`shopstack.ui.state.household` (extracted in
   Pass 3).
2. **Community price map opt-in** — anonymous, city-scoped price sharing.
   Service is in :mod:`shopstack.services.community_price_map`; the
   thin Gradio adapters are in :mod:`shopstack.ui.screens.community`.
3. **SMS / WhatsApp phone registry** — register a phone number so the
   Twilio / WhatsApp Business webhook can route incoming messages to
   the right household. Service is in
   :mod:`shopstack.services.sms_quick_add`.

The builder returns a :class:`HouseholdSettingsHandles` dataclass
exposing the 6 components that ``app.py`` needs to wire cross-tab
references to (the household-switch dropdown, the add button, the
hidden form row, and the form's 3 input/button components). All
other components (community status HTML, phone input, etc.) are
only used inside the accordion and don't need to be exposed.

**Why a separate module and not a tab:**

It's not a top-level tab — it's a collapsed-by-default admin accordion
that lives below the main 6 tabs. The daily product flow (Today →
Recipes → Groceries → While Shopping → At Home → Memory) doesn't go
through this accordion; it's for the user to open when they need
to switch households, opt in to community, or register a phone.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape

import gradio as gr

from shopstack.app_context import current_user_id
from shopstack.ui.header import model_download_status, runtime_label
from shopstack.ui.screens.community import (
    community_pool_stats_screen as _community_stats,
    community_status_screen as _community_status,
    set_opt_in_screen as _set_opt_in,
)
from shopstack.services.sms_quick_add import register_phone as _register_phone


@dataclass
class HouseholdSettingsHandles:
    """Components that ``app.py`` wires cross-tab references to.

    All other components (``community_status_html``, ``phone_input``,
    etc.) are only used inside the accordion — the event handlers
    live here, not in ``app.py``.

    The exposed set is the minimum needed for ``app.py`` to:
    - Wire the dropdown's ``.change`` to the household-switch state
      machine (which refreshes the Today tab's 6 output components).
    - Wire the add / cancel / create buttons to show/hide/create
      the add-household form, and refresh the Today tab on creation.
    """

    household_dropdown: gr.Dropdown
    add_hh_btn: gr.Button
    hh_add_row: gr.Row
    hh_name_input: gr.Textbox
    hh_create_btn: gr.Button
    hh_cancel_btn: gr.Button


def build_household_settings(app: gr.Blocks) -> HouseholdSettingsHandles:
    """Build the Household settings accordion (workspace admin panel).

    Composes three sub-features into one ``gr.Accordion``:

      * **Household switcher** — dropdown + add button + hidden
        add-household form. The state machine that powers the
        switcher lives in :mod:`shopstack.ui.state.household`; this
        function just wires the components to that state.
      * **Community price map** — opt-in / opt-out buttons + status
        HTML. On page load, the status HTML is populated by
        :func:`community_status_screen` and the stats HTML by
        :func:`community_pool_stats_screen`.
      * **SMS / WhatsApp phone registry** — phone input + register
        button + status HTML. The register handler validates the
        phone and stores it locally at
        ``~/.shopstack/inbox/phone_registry.json`` (chmod 0o600).

    Args:
        app: The root ``gr.Blocks`` instance — needed for the
            ``app.load(...)`` handlers that populate the community
            status / stats HTML on first render.

    Returns:
        HouseholdSettingsHandles: the 6 components that ``app.py``
        wires to the household-switch state machine and the Today
        tab's dashboard refresh.
    """
    with gr.Accordion("Household settings", open=False, elem_classes="workspace-admin"):
        gr.HTML(
            f"""
<div style=\"display:flex;flex-direction:column;gap:8px;margin-bottom:10px;\">
  <div style=\"font-size: 0.8125rem;color:var(--text-muted);\">
    Switch households, create a new home, or open advanced runtime details when you need them.
  </div>
  <div style=\"display:flex;gap:8px;flex-wrap:wrap;align-items:center;\">
    <span class=\"badge badge-blue\">{escape(runtime_label())}</span>
    {model_download_status()}
  </div>
</div>"""
        )
        gr.Markdown(
            "Keep this tucked away unless you need household switching or advanced diagnostics. The main tabs above are the day-to-day product flow."
        )
        with gr.Row(variant="compact", elem_classes="household-bar"):
            household_dropdown = gr.Dropdown(
                label="Household",
                # choices populated by app.load in app.py
                choices=[],
                value=current_user_id(),
                interactive=True,
                allow_custom_value=True,
                scale=1,
            )
            add_hh_btn = gr.Button(
                "Add household",
                scale=0,
                min_width=140,
                elem_classes="household-add-btn",
            )
            gr.HTML(
                "<div style='display:flex;align-items:center;gap:8px;font-size: 0.6875rem;color:var(--text-dim);'>"
                "Switch between households or add a new one.</div>",
                scale=3,
            )

        # Hidden add-household form (shown when + is clicked)
        with gr.Row(visible=False, variant="compact", elem_classes="household-add-form") as hh_add_row:
            hh_name_input = gr.Textbox(
                label="New household name",
                placeholder="e.g. My Home, Beach House, Office",
                scale=2,
            )
            hh_create_btn = gr.Button("Create", variant="primary", scale=0)
            hh_cancel_btn = gr.Button("Cancel", scale=0, elem_classes="secondary")

        # ── Phase 8 #15 community price map opt-in + #24 SMS phone registry ─
        gr.Markdown("---")
        gr.Markdown("### 📱 Privacy & sharing")
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("**👥 Community price map**")
                gr.Markdown(
                    "Opt in to share your prices anonymously with the "
                    "community. We never write your name, phone, or "
                    "exact store address — only a daily-rolling anon_id, "
                    "the city, and the city-scoped store tag."
                )
                community_status_html = gr.HTML(
                    value="<div class='home-card'>Loading…</div>"
                )
                community_stats_html = gr.HTML("")
                with gr.Row():
                    community_optin_btn = gr.Button(
                        "✅ Opt in", variant="primary", scale=1
                    )
                    community_optout_btn = gr.Button(
                        "🔒 Opt out", elem_classes="secondary", scale=1
                    )

                def _do_set_opt_in(opt_in: bool) -> str:
                    return _set_opt_in(opt_in)

                community_optin_btn.click(
                    lambda: _do_set_opt_in(True),
                    outputs=[community_status_html],
                    api_name="community_opt_in",
                    api_description="Opt in to community price sharing",
                )
                community_optout_btn.click(
                    lambda: _do_set_opt_in(False),
                    outputs=[community_status_html],
                    api_name="community_opt_out",
                    api_description="Opt out of community price sharing",
                )

            with gr.Column(scale=2):
                gr.Markdown("**📞 SMS / WhatsApp quick-add**")
                gr.Markdown(
                    "Text a registered phone number with 'add 2 kg onion' "
                    "or 'consume bread' and it lands in your inventory. "
                    "Numbers are stored locally with chmod 0o600."
                )
                with gr.Row():
                    phone_input = gr.Textbox(
                        label="Register phone number",
                        placeholder="+91 98765 43210",
                        scale=2,
                    )
                    phone_register_btn = gr.Button(
                        "Register", variant="primary", scale=0
                    )
                phone_status_html = gr.HTML("")

                def _do_register_phone(phone: str) -> str:
                    uid = current_user_id() or ""
                    if not phone:
                        return "<span style='color:var(--red);'>Enter a phone number.</span>"
                    result = _register_phone(phone, uid)
                    if result.get("registered"):
                        return f"<span style='color:var(--green);'>✅ Registered {result['phone']}</span>"
                    return f"<span style='color:var(--red);'>{result.get('reason', 'Failed')}</span>"

                phone_register_btn.click(
                    _do_register_phone,
                    phone_input,
                    phone_status_html,
                    api_name="sms_register_phone",
                    api_description="Register a phone number for SMS/WhatsApp quick-add",
                )

        # Populate community status / stats on first render. The dropdown
        # choices are populated by a separate ``app.load`` in app.py
        # (which needs to know the household_id before refresh).
        app.load(_community_status, outputs=[community_status_html])
        app.load(_community_stats, outputs=[community_stats_html])

    return HouseholdSettingsHandles(
        household_dropdown=household_dropdown,
        add_hh_btn=add_hh_btn,
        hh_add_row=hh_add_row,
        hh_name_input=hh_name_input,
        hh_create_btn=hh_create_btn,
        hh_cancel_btn=hh_cancel_btn,
    )
