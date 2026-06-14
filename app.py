from __future__ import annotations

import os

# HF Spaces: ensure DB_PATH defaults to a writable location before
# shopstack.config instantiates Settings() at module import time.
os.environ.setdefault("SHOPSTACK_DB_PATH", "shopstack.db")

import gradio as gr

from shopstack.ui.header import header_block, pwa_head_html
from shopstack.ui.theme import CSS
from shopstack.ui.tabs.context import TabContext
from shopstack.ui.tabs.registry import build_all_tabs
from shopstack.ui.household_settings import build_household_settings
from shopstack.ui.locale_save import build_locale_save
from shopstack.ui.pwa_mount import mount_pwa_static
from shopstack.services.sms_webhook import mount_sms_webhook
from shopstack.services.health_mount import mount_health_endpoint

from shopstack.app_context import (
    APP_DESCRIPTION,
    APP_NAME,
    current_user_id,
    db,
    tools,
    providers,
    planner,
)
from shopstack.services.i18n import load_locale_preference
from shopstack.ui.state.household import (
    household_choices,
    switch_household_state,
    show_add_form,
    hide_add_form,
    create_household_state,
)
from shopstack.ui.components.js_helpers import (
    autocomplete_injector_js,
    script_bootstrap_js,
    url_state_sync_js,
)


def build_app() -> gr.Blocks:
    """Compose the ShopStack app — pure composition, no business logic.

    All tab builders are dispatched via ``shopstack.ui.tabs.registry``,
    which iterates ``module_registry.TAB_ORDER`` to determine what tabs
    exist and what order they appear in. This makes the module registry
    the single source of truth for tab wiring.

    Architecture:
      * ``gr.Blocks`` is the root container.
      * ``mount_pwa_static()`` mounts shopstack/static/ at /static/*.
      * ``mount_sms_webhook()`` mounts /api/sms/incoming.
      * ``header_block()`` renders the top header.
      * ``build_all_tabs()`` iterates TAB_ORDER and calls each builder.
      * ``build_household_settings()`` renders the workspace admin panel.
      * The tail block wires cross-tab event handlers.

    Adding a new tab does NOT require editing this file — register it
    in ``module_registry.TAB_ORDER`` and ``shopstack.ui.tabs.registry``.
    """
    with gr.Blocks(title=APP_NAME) as app:
        mount_pwa_static(app)
        mount_sms_webhook(app)
        # /health/ui — operator liveness probe (motto_v3 §0.10 Observability
        # Is Delivery). Reports database + gradio_blocks + pwa_assets status.
        mount_health_endpoint(app, db)

        initial_locale = load_locale_preference(current_user_id() or "default_household")
        gr.HTML(
            header_block(APP_NAME, APP_DESCRIPTION, current_locale=initial_locale),
            padding=True,
        )

        build_locale_save()

        # ── Tab bar — driven by module_registry.TAB_ORDER via the builder registry ──
        with gr.Tabs(elem_classes="tabs", elem_id="main-content"):
            handles = build_all_tabs(blocks=app, app=app, ctx=TabContext())

        # Extract handles from tabs that expose them for cross-tab wiring
        today_handles = handles.get("today")
        reconcile_handles = handles.get("reconcile")
        today_stats = today_handles.today_stats
        today_soon = today_handles.today_soon
        today_list = today_handles.today_list
        today_low = today_handles.today_low
        today_recent = today_handles.today_recent
        today_changed = today_handles.today_changed
        p_location = reconcile_handles.p_location
        move_dest = reconcile_handles.move_dest

        # ── Household settings accordion (workspace admin panel) ──
        hh = build_household_settings(app)
        household_dropdown = hh.household_dropdown
        add_hh_btn = hh.add_hh_btn
        hh_add_row = hh.hh_add_row
        hh_name_input = hh.hh_name_input
        hh_create_btn = hh.hh_create_btn
        hh_cancel_btn = hh.hh_cancel_btn

        # Refresh dropdown choices on initial load
        app.load(
            lambda: gr.update(choices=household_choices(), value=current_user_id()),
            outputs=household_dropdown,
        )

        # Wire household dropdown change after all output components are defined
        household_dropdown.change(
            switch_household_state,
            household_dropdown,
            [household_dropdown, today_stats, today_soon, today_list, today_low, today_recent, today_changed],
            api_name="switch_household",
            api_description="Switch active household and refresh dashboard",
        )

        # Per-render refresh of location-dependent dropdowns.
        def _refresh_location_choices() -> gr.update:
            return gr.update(choices=[(l.name, l.location_id) for l in db.get_locations()])

        app.load(_refresh_location_choices, outputs=p_location)
        app.load(_refresh_location_choices, outputs=move_dest)

        # Post-render JS: inject `autocomplete="off"` into every Gradio
        # text/number input. Vercel WIG requires this on every form input.
        app.load(None, js=autocomplete_injector_js())
        # URL state sync: clicking a tab updates the URL hash, and
        # opening the app with `#basket` deep-links to the Shopping tab.
        app.load(None, js=url_state_sync_js())
        # Bootstrap re-execution: re-run inline <script data-ss-exec> tags
        # that Gradio's head=/gr.HTML injection left inert (item #99).
        app.load(None, js=script_bootstrap_js())

        # Wire add-household button and form
        add_hh_btn.click(
            show_add_form,
            outputs=hh_add_row,
            api_name="show_add_household",
            api_description="Show the add-household form",
        )
        hh_cancel_btn.click(
            hide_add_form,
            outputs=hh_add_row,
            api_name="cancel_add_household",
            api_description="Hide the add-household form without creating",
        )
        hh_create_btn.click(
            create_household_state,
            hh_name_input,
            [household_dropdown, hh_add_row, today_stats, today_soon, today_list, today_low, today_recent, today_changed],
            api_name="create_household",
            api_description="Create a new household, switch to it, and refresh the dashboard",
        )

    return app



if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    app = build_app()
    app.launch(server_port=args.port, share=args.share, theme=gr.themes.Base(), css=CSS, head=pwa_head_html(), prevent_thread_lock=True)
    mount_pwa_static(app)
    app.block_thread()
