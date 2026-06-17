from __future__ import annotations

import gradio as gr

from shopstack.app_context import (
    APP_NAME,
    current_user_id,
    db,
)
from shopstack.services.health_mount import mount_health_endpoint as _mount_health_endpoint
from shopstack.services.i18n import load_locale_preference
from shopstack.ui.header import header_block
from shopstack.ui.household_settings import build_household_settings
from shopstack.ui.locale_save import build_locale_save
from shopstack.ui.pwa_mount import mount_pwa_static as _mount_pwa_static
from shopstack.ui.runtime_status import build_runtime_status
from shopstack.ui.security_middleware import (
    install_permissions_policy_middleware as _install_permissions_policy_middleware,
)
from shopstack.ui.tabs.context import TabContext
from shopstack.ui.tabs.onboarding import build_onboarding_wizard
from shopstack.ui.tabs.registry import build_all_tabs

from shopstack.api.wire_all_mounts import (
    install_post_launch_hooks as _install_post_launch_hooks,
)


def build_app(
    *,
    include_v1_surface: bool = True,
    install_permissions_policy: bool = True,
    install_post_launch_hooks: bool = True,
    mount_pwa_static=_mount_pwa_static,
    mount_health_endpoint=_mount_health_endpoint,
    install_permissions_policy_middleware=_install_permissions_policy_middleware,
    install_post_launch_hooks_fn=_install_post_launch_hooks,
) -> gr.Blocks:
    """Compose the ShopStack Gradio UI.

    This stays as the compatibility UI layer while the FastAPI host
    becomes the primary backend entrypoint.
    """
    with gr.Blocks(title=APP_NAME) as app:
        if include_v1_surface:
            from shopstack.api.wire_in_context import wire_in_context_routes
            wire_in_context_routes(app, db)

        initial_locale = load_locale_preference(current_user_id() or "default_household")
        gr.HTML(
            header_block(
                APP_NAME,
                "Know what is at home, what to buy next, and what to skip.",
                current_locale=initial_locale,
            ),
            padding=True,
        )

        build_locale_save()
        build_runtime_status()

        onboarding_wizard = build_onboarding_wizard(app)

        def _show_onboarding_if_first_run() -> gr.update:
            from shopstack.services.onboarding import should_show_onboarding
            return gr.update(visible=should_show_onboarding(db))

        app.load(
            _show_onboarding_if_first_run,
            outputs=[onboarding_wizard],
        )

        hh = build_household_settings(app)
        household_dropdown = hh.household_dropdown
        add_hh_btn = hh.add_hh_btn
        hh_add_row = hh.hh_add_row
        hh_name_input = hh.hh_name_input
        hh_create_btn = hh.hh_create_btn
        hh_cancel_btn = hh.hh_cancel_btn

        with gr.Tabs(elem_classes="tabs primary-nav", elem_id="main-content"):
            handles = build_all_tabs(
                blocks=app, app=app, ctx=TabContext(),
                use_primary_nav=True,
            )

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

        from shopstack.ui.state.household_wiring import wire_household_handlers

        wire_household_handlers(
            app,
            household_dropdown=household_dropdown,
            add_hh_btn=add_hh_btn,
            hh_add_row=hh_add_row,
            hh_name_input=hh_name_input,
            hh_create_btn=hh_create_btn,
            hh_cancel_btn=hh_cancel_btn,
            today_handles=today_handles,
            reconcile_handles=reconcile_handles,
        )

    mount_pwa_static(app)
    mount_health_endpoint(app, db)
    if install_permissions_policy:
        install_permissions_policy_middleware(app)
    if install_post_launch_hooks:
        install_post_launch_hooks_fn(app, db)

    return app


__all__ = ["build_app"]
