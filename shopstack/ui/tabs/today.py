"""Today tab — decision-first dashboard with embedded command surface.

This is the first thing the user sees when they open ShopStack. It
answers the actual user question — "what should I do right now?" — by
surfacing:

* **Home flow state** (first-run / starting-out / quiet / active)
  — see :mod:`shopstack.services.home_flow`. The state is a single
  enum that the renderer reads to pick which sections to show.
* **Command surface** — the unified input that merges the old
  "Quick add" textbox and the "Ask ShopStack" textbox. See
  :mod:`shopstack.ui.tabs.command_surface`. Handles four action kinds
  (add to list, log purchase, add stock, mark consumed) plus Ask
  fall-through.
* **Today intelligence** — a ranked list of use-soon / restock-due /
  price-drop / community-overpriced actions, rendered as
  :class:`IntelligenceCard` with reasons and confidence.
* **Detailed signals** — the legacy six-component dashboard, kept
  for back-compat (Phase 9 backward-compat shim).

The first-run state replaces the old "Welcome to ShopStack" gate.
A new household is shown the setup wizard first and an actionable
empty state, not a debug dashboard full of zeros.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import gradio as gr

from shopstack.app_context import current_user_id, db
from shopstack.module_registry import tab_label as _tab_label
from shopstack.services.home_flow import (
    HomeState,
    detect_home_state,
    detect_home_state_from_db,
)
from shopstack.ui.components.primitives import (
    home_card,
    loading_skeleton,
    last_updated_stamp,
    toast,
)
from shopstack.ui.screens import today_dashboard
from shopstack.ui.screens.home_flow_render import render_home_flow
from shopstack.ui.tabs.ask_panel import build_ask_panel
from shopstack.ui.tabs.command_surface import build_command_surface
from shopstack.ui.tabs.context import TabContext

logger = logging.getLogger(__name__)


@dataclass
class TodayTabHandles:
    """Components other parts of the app reference after the Today tab builds.

    The household-switch wiring in ``app.py`` reads back these
    components to refresh the dashboard when the active household
    changes.
    """

    today_stats: gr.HTML
    today_soon: gr.HTML
    today_list: gr.HTML
    today_low: gr.HTML
    today_recent: gr.HTML
    today_changed: gr.HTML
    # New: home flow HTML (hero + intelligence + setup gate, all
    # rendered as one panel). The household switch refreshes this
    # rather than the legacy six.
    home_flow: gr.HTML


def _render_home_flow() -> str:
    """Render the unified home-flow panel (state-aware)."""
    try:
        uid = current_user_id() or ""
        return render_home_flow(user_id=uid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("home flow render failed: %s", exc)
        return toast(f"Home panel unavailable: {exc}", kind="error")


def _render_home_flow_with_state(state: HomeState | None) -> str:
    """Render the home flow panel with a pre-computed state (used by
    the Ask-via-state call site in ``app.py``)."""
    try:
        uid = current_user_id() or ""
        return render_home_flow(user_id=uid, force_state=state)
    except Exception as exc:  # noqa: BLE001
        logger.warning("home flow render failed: %s", exc)
        return toast(f"Home panel unavailable: {exc}", kind="error")


def build_today_tab(
    blocks: gr.Blocks,
    app: gr.Blocks,
    ctx: TabContext,
) -> TodayTabHandles:
    """Build the Today tab inside the parent's ``gr.Tabs`` context.

    Args:
        blocks: Alias for the parent gr.Blocks. Kept for symmetry
            with other tab builders.
        app: The root :class:`gr.Blocks` instance — needed for
            ``app.load(...)`` to register handlers that fire on
            page open.
        ctx: Shared dependencies (unused in this tab, but part of
            the uniform builder signature).

    Returns:
        :class:`TodayTabHandles` — the seven HTML components the
        household-switch wiring in ``app.py`` needs to reference
        (six legacy + the new home flow panel).
    """
    with gr.Tab(_tab_label("today"), id="today"):
        # ── Page intro (sets expectations for a new user) ────────
        gr.Markdown(
            "## Today\n"
            "Know what is at home, what to buy next, and what to skip."
        )

        # ── Two-column desktop layout ──────────────────────────
        # Left: intelligence + commands (primary actions)
        # Right: signals + restock (supplementary detail)
        with gr.Row(elem_classes="today-two-col"):
            with gr.Column(elem_classes="today-col-main"):
                # ── Home flow panel (state-aware hero + intelligence) ──
                home_flow = gr.HTML(loading_skeleton("card"), elem_classes="today-home-flow")
                home_flow_refresh = gr.Button(
                    "Refresh",
                    elem_classes="inline-refresh",
                    size="sm",
                )
                home_flow_refresh.click(
                    _render_home_flow,
                    outputs=home_flow,
                    api_name="today_home_flow_refresh",
                    api_description="Refresh the state-aware home flow panel (hero + intelligence + setup gate)",
                )
                app.load(_render_home_flow, outputs=home_flow)

                # ── Command surface (the unified input) ────────────────
                gr.Markdown("### Quick action")
                cmd_handles = build_command_surface(blocks=app, app=app, ctx=ctx)

                # ── Voice memo (secondary input, below command) ──────
                from shopstack.ui.tabs.voice_memo import build_voice_memo_section
                build_voice_memo_section(app=app)

            with gr.Column(elem_classes="today-col-side"):
                # ── Detailed signals (legacy 6-component dashboard) ───
                # Kept for back-compat — many tests reference these handles.
                # New code should read from ``home_flow`` instead.
                gr.Markdown("### Signals")
                today_stats = gr.HTML(loading_skeleton("card"))
                today_soon = gr.HTML(loading_skeleton("card"))
                today_list = gr.HTML(loading_skeleton("card"))
                today_low = gr.HTML(loading_skeleton("card"))
                today_recent = gr.HTML(loading_skeleton("card"))
                today_changed = gr.HTML(loading_skeleton("card"))
                app.load(
                    today_dashboard,
                    outputs=[
                        today_stats, today_soon, today_list,
                        today_low, today_recent, today_changed,
                    ],
                )

                # ── Ask ShopStack (full panel — voice memo below) ──────
                gr.Markdown("### Ask ShopStack")
                build_ask_panel(blocks=app, app=app, ctx=ctx)

    return TodayTabHandles(
        today_stats=today_stats,
        today_soon=today_soon,
        today_list=today_list,
        today_low=today_low,
        today_recent=today_recent,
        today_changed=today_changed,
        home_flow=home_flow,
    )
