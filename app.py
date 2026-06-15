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
from shopstack.ui.tabs.onboarding import build_onboarding_wizard
from shopstack.ui.locale_save import build_locale_save
from shopstack.ui.pwa_mount import mount_pwa_static
from shopstack.ui.runtime_status import build_runtime_status
from shopstack.services.sms_webhook import mount_sms_webhook
from shopstack.services.health_mount import mount_health_endpoint
from shopstack.services.global_search_mount import mount_global_search
from shopstack.services.privacy_mount import mount_privacy_endpoints
from shopstack.services.undo_mount import mount_undo_endpoint
from shopstack.services.data_retention import (
    render_privacy_panel_html,
    render_privacy_panel_script,
)

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


def _install_post_launch_hooks(app: gr.Blocks) -> None:
    """Ensure root routes are restored after Gradio recreates the FastAPI app.

    Gradio's ``launch()`` rebuilds ``app.app``. That means any routes
    mounted during ``build_app()`` are lost unless we mount them again
    after launch. HF Spaces follows the same launch path, so this wrapper
    keeps ``/sw.js``, ``/manifest.json``, and ``/health/ui`` reachable
    both locally and on Spaces.
    """
    original_launch = app.launch

    def _launch_with_post_hooks(*args, **kwargs):
        result = original_launch(*args, **kwargs)
        mount_pwa_static(app)
        mount_health_endpoint(app, db)
        return result

    app.launch = _launch_with_post_hooks


def _household_switch_reload_js() -> str:
    """Return JS that reloads the page after a household switch.

    Per audit 2026-06-14 finding #7: the household dropdown switch
    only refreshed the Today tab's 6 HTML outputs. The other 20+ tabs
    (Basket, Memory, Timeline, Find, etc.) continued showing stale
    data from the previous household until the user manually refreshed
    each tab — a broken user workflow per motto_v3 §0.14 (Product
    Reality and Operator Workflow Rule).

    The robust fix is a full page reload. This guarantees every tab
    re-fetches its data through the active household, the user sees
    a clean view of the new household, and no tab silently displays
    the wrong household's data.

    We use ``setTimeout(50)`` to give the Today tab refresh time to
    commit to the DOM before the reload tears it down, so the user
    doesn't see a flash of the old household on Today.
    """
    return (
        "() => {"
        "setTimeout(function(){"
        # Preserve the URL hash so the user lands on the same tab.
        "var hash = window.location.hash || '';"
        "window.location.href = window.location.pathname + hash;"
        "}, 50);"
        "}"
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
        mount_sms_webhook(app)
        mount_global_search(app)
        mount_privacy_endpoints(app)
        mount_undo_endpoint(app)

        initial_locale = load_locale_preference(current_user_id() or "default_household")
        # 2026-06-15 (Home screen review): the brand subtitle now
        # answers the user's actual job instead of the abstract
        # "platform" copy. The legacy APP_DESCRIPTION is still
        # passed as a tooltip / fallback via header attributes.
        gr.HTML(
            header_block(
                APP_NAME,
                "Know what is at home, what to buy next, and what to skip.",
                current_locale=initial_locale,
            ),
            padding=True,
        )

        build_locale_save()

        # Hidden runtime_status API endpoint (external consumers can
        # query whether the app is in mock or real mode)
        build_runtime_status()

        # ── Onboarding wizard (first-run household setup) ──
        # Rendered above the tab bar so first-time users see setup
        # immediately, instead of after scrolling past every tab's
        # content. Hidden by default; auto-shown on first load if the
        # active household hasn't completed onboarding yet. See
        # Docs/HANDOFF_ONBOARDING_WIRING_2026-06-13.md.
        onboarding_wizard = build_onboarding_wizard(app)

        def _show_onboarding_if_first_run() -> gr.update:
            from shopstack.services.onboarding import should_show_onboarding
            return gr.update(visible=should_show_onboarding(db))

        app.load(
            _show_onboarding_if_first_run,
            outputs=[onboarding_wizard],
        )

        # ── Household settings accordion (workspace admin panel) ──
        # Rendered above the tab bar — a workspace switcher belongs at
        # the top of the page, accessible from any tab, not buried
        # below the last tab's content.
        hh = build_household_settings(app)
        household_dropdown = hh.household_dropdown
        add_hh_btn = hh.add_hh_btn
        hh_add_row = hh.hh_add_row
        hh_name_input = hh.hh_name_input
        hh_create_btn = hh.hh_create_btn
        hh_cancel_btn = hh.hh_cancel_btn

        # ── Tab bar — driven by module_registry.TAB_ORDER via the builder registry ──
        # 2026-06-15: switched to the 6-item user-facing primary nav
        # (Home / Pantry / Shopping / Recipes / Trips / Memory). The
        # old 5-group nested layout is still available via
        # ``build_all_tabs(use_primary_nav=False)`` for back-compat.
        with gr.Tabs(elem_classes="tabs primary-nav", elem_id="main-content"):
            handles = build_all_tabs(
                blocks=app, app=app, ctx=TabContext(),
                use_primary_nav=True,
            )

        # Extract handles from tabs that expose them for cross-tab wiring.
        # These are P0 guards: if a builder silently returns None or is
        # skipped, we fail fast with a clear error rather than crashing
        # with AttributeError deep inside the event wiring below.
        today_handles = handles.get("today")
        reconcile_handles = handles.get("reconcile")
        if today_handles is None:
            raise RuntimeError(
                "Today tab builder did not return required handles. "
                "Check that build_today_tab() returns a TodayTabHandles "
                "dataclass and that the builder is registered in "
                "shopstack/ui/tabs/registry.py."
            )
        if reconcile_handles is None:
            raise RuntimeError(
                "Reconcile tab builder did not return required handles. "
                "Check that build_reconcile_tab() returns a "
                "ReconcileTabHandles dataclass and that the builder is "
                "registered in shopstack/ui/tabs/registry.py."
            )
        today_stats = today_handles.today_stats
        today_soon = today_handles.today_soon
        today_list = today_handles.today_list
        today_low = today_handles.today_low
        today_recent = today_handles.today_recent
        today_changed = today_handles.today_changed
        home_flow = today_handles.home_flow
        p_location = reconcile_handles.p_location
        move_dest = reconcile_handles.move_dest

        # Refresh dropdown choices on initial load
        app.load(
            lambda: gr.update(choices=household_choices(), value=current_user_id()),
            outputs=household_dropdown,
        )

        # Wire household dropdown change after all output components are defined.
        # Also refresh the new home_flow panel so the state-aware hero
        # re-evaluates with the new household's data.
        household_dropdown.change(
            switch_household_state,
            household_dropdown,
            [household_dropdown, today_stats, today_soon, today_list, today_low, today_recent, today_changed, home_flow],
            api_name="switch_household",
            api_description="Switch active household and refresh dashboard",
        ).then(
            None,
            js=_household_switch_reload_js(),
            api_name="after_switch_household",
            api_description="Reload the page after household switch so all tabs show fresh data",
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
            [household_dropdown, hh_add_row, today_stats, today_soon, today_list, today_low, today_recent, today_changed, home_flow],
            api_name="create_household",
            api_description="Create a new household, switch to it, and refresh the dashboard",
        )

    # PWA shell (manifest/sw.js/icons) and the /health/ui liveness probe
    # (motto_v3 §0.10 Observability Is Delivery) must both be mounted AFTER
    # the ``with gr.Blocks()`` block exits: exiting the context recreates
    # ``app.app`` (a fresh FastAPI instance), discarding any routes added
    # while inside the context.
    mount_pwa_static(app)
    mount_health_endpoint(app, db)
    _install_post_launch_hooks(app)

    return app



if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    app = build_app()
    app.launch(server_port=args.port, share=args.share, theme=gr.themes.Base(), head=pwa_head_html(), css=CSS, prevent_thread_lock=True)
    app.block_thread()
