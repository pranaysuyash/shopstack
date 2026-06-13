from __future__ import annotations

from datetime import date
from html import escape

import gradio as gr

from shopstack.ui.screens import today_dashboard
from shopstack.ui.components import workflow_header
from shopstack.ui.theme import CSS
from shopstack.ui.tabs.context import TabContext
from shopstack.ui.tabs.today import build_today_tab, TodayTabHandles
from shopstack.ui.tabs.basket import build_basket_tab
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
from pathlib import Path
from shopstack.app_context import APP_DESCRIPTION, APP_NAME, current_user_id, db, providers, tools, planner, model_registry
from shopstack.config import settings
from shopstack.module_registry import tab_label as _tab_label


def _model_download_status() -> str:
    """Check whether the configured MLX planner model is cached locally.
    Returns an HTML snippet if a download is pending, or empty string if cached.
    """
    try:
        import os as _os

        mlx_model = settings.local_mlx_model
        if not mlx_model:
            return ""

        # Check HF hub cache
        hf_home = _os.environ.get("HF_HOME", _os.path.expanduser("~/.cache/huggingface"))
        hf_cache = Path(hf_home) / "hub"
        model_dir_name = "models--" + mlx_model.replace("/", "--")
        model_cache_dir = hf_cache / model_dir_name

        if model_cache_dir.is_dir():
            snapshots_dir = model_cache_dir / "snapshots"
            if snapshots_dir.is_dir():
                for snap in snapshots_dir.iterdir():
                    if snap.is_dir() and any(
                        f.suffix in (".safetensors", ".gguf")
                        for f in snap.iterdir()
                    ):
                        return ""
            return ""

        return (
            "<div style='font-size:11px;color:var(--amber);margin-top:4px;'>"
            f"<span>\u23F3 {mlx_model.split('/')[-1]} download pending (first query triggers it)</span>"
            "</div>"
        )
    except Exception:
        return ""


def _runtime_label() -> str:
    try:
        runtime = providers.get_runtime_diagnostics()
        loaded_real = [
            r for r in runtime.providers
            if getattr(r, "loaded", False) and getattr(r, "backend", "") != "mock"
        ]
        blocked = [r for r in runtime.providers if getattr(r, "blocked_by_off_grid", False)]
        if loaded_real and any(getattr(r, "backend", "") in {"openai", "huggingface", "whisper"} for r in loaded_real):
            return "Cloud runtime"
        if loaded_real:
            return "Local runtime"
        if blocked:
            return "Off-grid mock mode"
        return "Local mock mode"
    except Exception:
        return "Local runtime"


def build_app() -> gr.Blocks:
    runtime_label = _runtime_label()
    with gr.Blocks(title=APP_NAME) as app:
        header_html = f"""
<div class=\"app-header\">
  <div>
    <h1 class=\"brand-title\">{APP_NAME}</h1>
    <div class=\"brand-subtitle\">{APP_DESCRIPTION}</div>
  </div>
  <button onclick=\"toggleTheme()\" aria-label=\"Toggle light/dark theme\" title=\"Toggle theme\" style=\"background:none;border:1px solid var(--border);border-radius:var(--radius-sm);padding:4px 10px;cursor:pointer;font-size:11px;color:var(--text-muted);\">🌓</button>
</div>"""
        header_script = """
<script>
(function() {
  var t = localStorage.getItem('shopstack-theme');
  if (t) {
    document.documentElement.setAttribute('data-theme', t);
  }
})();
function toggleTheme() {
  var e = document.documentElement;
  var t = e.getAttribute('data-theme');
  var n = (t === 'dark' ? 'light' : 'dark');
  e.setAttribute('data-theme', n);
  localStorage.setItem('shopstack-theme', n);
}
document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  var tabs = Array.from(document.querySelectorAll('[data-testid^=tab-], .tabs > button[role=tab]'));
  var idx = tabs.findIndex(t => t.getAttribute('aria-selected') === 'true');
  if (e.key === 'j' || e.key === 'ArrowRight') {
    e.preventDefault();
    var next = (idx + 1) % tabs.length;
    tabs[next] && tabs[next].click();
  } else if (e.key === 'k' || e.key === 'ArrowLeft') {
    e.preventDefault();
    var prev = (idx - 1 + tabs.length) % tabs.length;
    tabs[prev] && tabs[prev].click();
  }
});
</script>"""
        gr.HTML(header_html + header_script, padding=True)

        with gr.Accordion("Workspace", open=False, elem_classes="workspace-admin"):
            gr.HTML(
                f"""
<div style=\"display:flex;flex-direction:column;gap:8px;margin-bottom:10px;\">
  <div style=\"font-size:13px;color:var(--text-muted);\">
    Switch households, create a new workspace, or inspect runtime details when you need the plumbing.
  </div>
  <div style=\"display:flex;gap:8px;flex-wrap:wrap;align-items:center;\">
    <span class=\"badge badge-blue\">{escape(runtime_label)}</span>
    {_model_download_status()}
  </div>
</div>"""
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

        # ── 5-tab daily loop: Today → Shopping → Scan & Compare → Pantry → Insights ──
        with gr.Tabs(elem_classes="tabs") as tabs:

            # ═══════════════════════════════════════════════════════════════
            # Tab 1: Today — what matters now?
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
            # Tab 2: Basket — what should I buy / skip / compare?
            # Built in shopstack/ui/tabs/basket.py
            # ═══════════════════════════════════════════════════════════════
            build_basket_tab(blocks=app, app=app, ctx=TabContext())

            # ═══════════════════════════════════════════════════════════════
            # Tab 3: ShopLens — check while shopping
            # Built in shopstack/ui/tabs/market.py
            # ═══════════════════════════════════════════════════════════════
            build_market_tab(blocks=app, app=app, ctx=TabContext())

            # ═══════════════════════════════════════════════════════════════
            # Tab 4: Reconcile — what actually happened?
            # Built in shopstack/ui/tabs/reconcile.py
            # ═══════════════════════════════════════════════════════════════
            reconcile_handles = build_reconcile_tab(blocks=app, app=app, ctx=TabContext())
            p_location = reconcile_handles.p_location
            move_dest = reconcile_handles.move_dest

            # ═══════════════════════════════════════════════════════════════
            # Tab 5: Memory — what did we learn?
            # Built in shopstack/ui/tabs/memory.py
            # ═══════════════════════════════════════════════════════════════
            build_memory_tab(blocks=app, app=app, ctx=TabContext())

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
