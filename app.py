from __future__ import annotations

from html import escape

import gradio as gr

from shopstack.ui.header import (
    header_block,
    model_download_status,
    runtime_label,
)
from shopstack.ui.theme import CSS
from shopstack.ui.tabs.context import TabContext
from shopstack.ui.tabs.today import build_today_tab, TodayTabHandles
from shopstack.ui.tabs.basket import build_basket_tab
from shopstack.ui.tabs.cookbook import build_cookbook_tab
from shopstack.ui.tabs.market import build_market_tab
from shopstack.ui.tabs.reconcile import build_reconcile_tab, ReconcileTabHandles
from shopstack.ui.tabs.memory import build_memory_tab

from shopstack.ui.state.household import (
    create_household_state,
    hide_add_form,
    household_choices,
    show_add_form,
    switch_household_state,
)
from shopstack.app_context import APP_DESCRIPTION, APP_NAME, current_user_id, db, providers, tools, planner, model_registry
from shopstack.config import settings
from shopstack.module_registry import tab_label as _tab_label


def build_app() -> gr.Blocks:
    with gr.Blocks(title=APP_NAME) as app:
        current_runtime_label = runtime_label()
        # ── Phase 4 #5 PWA: serve manifest + service worker at /static/* ──
        # Gradio doesn't auto-serve a /static/ directory, so we mount
        # Starlette's StaticFiles against the underlying FastAPI app.
        # This makes the PWA shell (manifest, sw.js, icons) reachable
        # at predictable URLs that the service worker can register.
        from pathlib import Path as _Path
        from starlette.staticfiles import StaticFiles as _StaticFiles

        _STATIC_DIR = _Path(__file__).resolve().parent / "static"
        if _STATIC_DIR.is_dir():
            try:
                app.app.mount(
                    "/static",
                    _StaticFiles(directory=str(_STATIC_DIR), html=False),
                    name="shopstack_static",
                )
            except Exception as exc:  # noqa: BLE001 — best-effort PWA bootstrap
                import logging
                logging.getLogger(__name__).warning(
                    "PWA static mount failed: %s", exc
                )

        gr.HTML(header_block(APP_NAME, APP_DESCRIPTION), padding=True)

        # ── 6-tab daily loop: Home → Recipes → Groceries → While Shopping → At Home → Memory ──
        with gr.Tabs(elem_classes="tabs") as tabs:

            # ═══════════════════════════════════════════════════════════════
            # Tab 1: Home — what matters now?
            # Built in shopstack/ui/tabs/today.py
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
            # Built in shopstack/ui/tabs/cookbook.py
            # ═══════════════════════════════════════════════════════════════
            build_cookbook_tab(blocks=app, app=app, ctx=TabContext())

            # ═══════════════════════════════════════════════════════════════
            # Tab 3: Groceries — what should I buy / skip / compare?
            # Built in shopstack/ui/tabs/basket.py
            # ═══════════════════════════════════════════════════════════════
            build_basket_tab(blocks=app, app=app, ctx=TabContext())

            # ═══════════════════════════════════════════════════════════════
            # Tab 4: While Shopping — check items before you buy them
            # Built in shopstack/ui/tabs/market.py
            # ═══════════════════════════════════════════════════════════════
            build_market_tab(blocks=app, app=app, ctx=TabContext())

            # ═══════════════════════════════════════════════════════════════
            # Tab 5: At Home — what actually happened?
            # Built in shopstack/ui/tabs/reconcile.py
            # ═══════════════════════════════════════════════════════════════
            reconcile_handles = build_reconcile_tab(blocks=app, app=app, ctx=TabContext())
            p_location = reconcile_handles.p_location
            move_dest = reconcile_handles.move_dest

            # ═══════════════════════════════════════════════════════════════
            # Tab 6: Memory — what did we learn?
            # Built in shopstack/ui/tabs/memory.py
            # ═══════════════════════════════════════════════════════════════
            build_memory_tab(blocks=app, app=app, ctx=TabContext())

        with gr.Accordion("Household settings", open=False, elem_classes="workspace-admin"):
            gr.HTML(
                f"""
<div style=\"display:flex;flex-direction:column;gap:8px;margin-bottom:10px;\">
  <div style=\"font-size:13px;color:var(--text-muted);\">
    Switch households, create a new home, or open advanced runtime details when you need them.
  </div>
  <div style=\"display:flex;gap:8px;flex-wrap:wrap;align-items:center;\">
    <span class=\"badge badge-blue\">{escape(current_runtime_label)}</span>
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
                    choices=household_choices(),
                    value=current_user_id(),
                    interactive=True,
                    allow_custom_value=True,
                    scale=1,
                )
                add_hh_btn = gr.Button(
                    "+",
                    scale=0,
                    min_width=40,
                    elem_classes="household-add-btn",
                )
                gr.HTML(
                    "<div style='display:flex;align-items:center;gap:8px;font-size:11px;color:var(--text-dim);'>"
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
        # The dropdowns are constructed with choices at build_app() time. This
        # `app.load` handler re-fetches them on first page render, so locations
        # added mid-session (e.g. via household switching) appear without an
        # app restart. The default value stays the same; "pantry" is always
        # present in the seeded locations.
        def _refresh_location_choices() -> gr.update:
            return gr.update(choices=[(l.name, l.location_id) for l in db.get_locations()])

        app.load(_refresh_location_choices, outputs=p_location)
        app.load(_refresh_location_choices, outputs=move_dest)

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
    app.launch(server_port=args.port, share=args.share, theme=gr.themes.Base(), css=CSS)
