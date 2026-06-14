from __future__ import annotations

import os

# HF Spaces: ensure DB_PATH defaults to a writable location before
# shopstack.config instantiates Settings() at module import time.
os.environ.setdefault("SHOPSTACK_DB_PATH", "shopstack.db")

import gradio as gr

from shopstack.ui.header import header_block, pwa_head_html
from shopstack.ui.theme import CSS
from shopstack.ui.tabs.context import TabContext
from shopstack.ui.tabs.today import build_today_tab, TodayTabHandles
from shopstack.ui.tabs.basket import build_basket_tab
from shopstack.ui.tabs.cookbook import build_cookbook_tab
from shopstack.ui.tabs.market import build_market_tab
from shopstack.ui.tabs.reconcile import build_reconcile_tab, ReconcileTabHandles
from shopstack.ui.tabs.memory import build_memory_tab
from shopstack.ui.tabs.timeline import build_timeline_tab
from shopstack.ui.tabs.scanner import build_scanner_tab
from shopstack.ui.tabs.trip_advisor import build_trip_advisor_tab
from shopstack.ui.tabs.market_intel import build_market_intel_tab
from shopstack.ui.tabs.nutrition_coach import build_nutrition_coach_tab
from shopstack.ui.household_settings import build_household_settings
from shopstack.ui.locale_save import build_locale_save
from shopstack.ui.pwa_mount import mount_pwa_static
from shopstack.services.sms_webhook import mount_sms_webhook

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
# Canonical paths — the re-exports in primitives.py emit
# DeprecationWarning on first call (see Pass 5 supersession).
from shopstack.ui.components.js_helpers import (
    autocomplete_injector_js,
    url_state_sync_js,
)


def build_app() -> gr.Blocks:
    """Compose the ShopStack app — pure composition, no business logic.

    Wires up the 6 top-level tabs, the household settings accordion,
    the locale-save API endpoint, and any app-level HTTP / static
    mounts. All business logic lives in the sub-modules; this
    function just glues them together.

    Architecture:
      * gr.Blocks is the root container.
      * mount_pwa_static() mounts shopstack/static/ at /static/*
        so the PWA shell is reachable.
      * mount_sms_webhook() mounts /api/sms/incoming for inbound
        SMS / WhatsApp quick-add.
      * header_block() renders the top header (brand, runtime badge,
        theme toggle, i18n selector, PWA manifest link, JS).
      * build_locale_save() adds the hidden i18n persistence endpoint
        that the header's JS POSTs to.
      * 6 build_<tab>_tab() calls render the daily product flow.
      * build_household_settings() renders the workspace admin panel
        (household switcher + community opt-in + SMS phone registry).
      * The tail block wires cross-tab event handlers (household
        switch → Today refresh, location refresh, JS injection).
    """
    with gr.Blocks(title=APP_NAME) as app:
        # App-level bootstrap: PWA static mount + SMS webhook endpoint
        mount_pwa_static(app)
        mount_sms_webhook(app)

        # Header: brand title, runtime badge, theme toggle, i18n selector
        initial_locale = load_locale_preference(current_user_id() or "default_household")
        gr.HTML(
            header_block(APP_NAME, APP_DESCRIPTION, current_locale=initial_locale),
            padding=True,
        )

        # Hidden i18n persistence endpoint (called by the header's JS)
        build_locale_save()

        # ── 6-tab daily loop: Home → Recipes → Groceries → While Shopping → At Home → Memory ──
        with gr.Tabs(elem_classes="tabs", elem_id="main-content") as tabs:

            # ═══════════════════════════════════════════════════════════════
            # Tab 1: Home — what matters now?
            # ═══════════════════════════════════════════════════════════════
            today_handles: TodayTabHandles = build_today_tab(
                blocks=app, app=app, ctx=TabContext(),
            )
            today_stats = today_handles.today_stats
            today_soon = today_handles.today_soon
            today_list = today_handles.today_list
            today_low = today_handles.today_low
            today_recent = today_handles.today_recent
            today_changed = today_handles.today_changed

            # ═══════════════════════════════════════════════════════════════
            # Tab 2: Recipes — browse the 30-recipe library
            # ═══════════════════════════════════════════════════════════════
            build_cookbook_tab(blocks=app, app=app, ctx=TabContext())

            # ═══════════════════════════════════════════════════════════════
            # Tab 3: Groceries — what should I buy / skip / compare?
            # ═══════════════════════════════════════════════════════════════
            build_basket_tab(blocks=app, app=app, ctx=TabContext())

            # ═══════════════════════════════════════════════════════════════
            # Tab 4: While Shopping — check items before you buy them
            # ═══════════════════════════════════════════════════════════════
            build_market_tab(blocks=app, app=app, ctx=TabContext())

            # ═══════════════════════════════════════════════════════════════
            # Tab 5: At Home — what actually happened?
            # ═══════════════════════════════════════════════════════════════
            reconcile_handles = build_reconcile_tab(blocks=app, app=app, ctx=TabContext())
            p_location = reconcile_handles.p_location
            move_dest = reconcile_handles.move_dest        # ═══════════════════════════════════════════════════════════════
        # Tab 6: Market Intel — cross-source graph
        # ═══════════════════════════════════════════════════════════════
            build_market_intel_tab(blocks=app, app=app, ctx=TabContext())

        # ═══════════════════════════════════════════════════════════════
        # Tab 7: Trip Plans — pre-trip advice
        # ═══════════════════════════════════════════════════════════════
            build_trip_advisor_tab(blocks=app, app=app, ctx=TabContext())

        # ═══════════════════════════════════════════════════════════════
        # Tab 8: Shelf Scan — camera/voice scan
        # ═══════════════════════════════════════════════════════════════
            build_scanner_tab(blocks=app, app=app, ctx=TabContext())

        # ═══════════════════════════════════════════════════════════════
        # Tab 9: Timeline — unified event timeline
        # ═══════════════════════════════════════════════════════════════
            build_timeline_tab(blocks=app, app=app, ctx=TabContext())

        # ═══════════════════════════════════════════════════════════════
        # Tab 10: Memory — what did we learn?
        # ═══════════════════════════════════════════════════════════════
            build_memory_tab(blocks=app, app=app, ctx=TabContext())

        # ═══════════════════════════════════════════════════════════════
        # Tab 11: Nutrition — coaching
        # ═══════════════════════════════════════════════════════════════
            build_nutrition_coach_tab(blocks=app, app=app, ctx=TabContext())

        # Household settings accordion (workspace admin panel)
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
    # ``app.launch(prevent_thread_lock=True)`` returns once ``app.app``
    # (the real FastAPI app, created inside launch()) is ready, but
    # before blocking the main thread. mount_pwa_static() must run
    # AFTER this point — the early call inside build_app() mounts onto
    # a throwaway FastAPI app that launch() discards and recreates.
    app.launch(server_port=args.port, share=args.share, theme=gr.themes.Base(), css=CSS, head=pwa_head_html(), prevent_thread_lock=True)
    mount_pwa_static(app)
    app.block_thread()
