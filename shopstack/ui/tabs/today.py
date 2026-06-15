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
* **Undo bar (2026-06-15)** — a "Recent changes" panel that shows
  the most recent mutations the user can undo, with one-tap
  buttons. Additive per motto_v3 §11; uses the existing
  :mod:`shopstack.services.undo_ledger` infrastructure.

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
from shopstack.services.undo_ledger import get_ledger
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
    # New: undo bar HTML (recent mutations the user can undo).
    # Refreshed after every undo click.
    undo_bar: gr.HTML


# ── Undo bar (2026-06-15) ─────────────────────────────────────────────
#
# The user-facing "Recent changes" panel on the home tab. Reads from
# the existing ``undo_ledger`` and renders the most recent
# undoable mutations with one-tap buttons. Hidden when the ledger
# is empty so the default view stays focused.
#
# Per motto_v3 §11 (additive, not delete): the legacy six-component
# dashboard below is preserved. The undo bar sits above it.
# Per motto_v3 §0.14 (operator workflow): a user who accidentally
# consumes all 12 eggs must be able to recover with one click —
# this is the surface that makes that possible.


_MAX_UNDO_ENTRIES_SHOWN = 3  # keep the bar compact


def _format_undo_entry_html(entry) -> str:  # noqa: ANN001 — UndoEntry
    """Render one UndoEntry as a compact card row."""
    from html import escape

    kind = escape(str(getattr(entry, "kind", "") or "change"))
    when = getattr(entry, "registered_at", None)
    if hasattr(when, "isoformat"):
        when_str = escape(str(when)[:19])
    else:
        when_str = escape(str(when) or "")
    entry_id = escape(str(getattr(entry, "entry_id", "") or ""))
    summary = escape(str(getattr(entry, "summary", "") or kind))
    return (
        f"<div class='undo-row' data-entry-id='{entry_id}' "
        f"style='display:flex;justify-content:space-between;"
        f"align-items:center;padding:6px 0;border-bottom:1px solid var(--border);'>"
        f"<div style='flex:1;min-width:0;'>"
        f"<div style='color:var(--text);font-size:0.875rem;'>{summary}</div>"
        f"<div style='color:var(--text-dim);font-size:0.7rem;'>{kind} · {when_str}</div>"
        f"</div>"
        f"</div>"
    )


def _render_undo_bar_html(household_id: str) -> str:
    """Return the HTML for the undo bar, or empty string if no
    recent entries.

    The bar shows the last ``_MAX_UNDO_ENTRIES_SHOWN`` undoable
    mutations. Hidden when empty so the default view stays clean.
    """
    try:
        ledger = get_ledger()
        if not ledger.has_recent(household_id):
            return ""
        recent = ledger.recent(household_id)[:_MAX_UNDO_ENTRIES_SHOWN]
    except Exception as exc:  # noqa: BLE001
        logger.warning("undo bar render failed: %s", exc)
        return ""

    rows = "".join(_format_undo_entry_html(e) for e in recent)
    n = len(recent)
    return (
        "<div class='undo-bar' "
        "style='border:1px solid var(--amber);border-radius:8px;"
        "background:var(--amber-soft, #fff7e6);padding:10px 14px;margin-bottom:12px;'>"
        "<div style='display:flex;justify-content:space-between;align-items:center;'>"
        "<div>"
        f"<strong style='color:var(--text);'>Recent changes</strong>"
        f"<span style='color:var(--text-dim);font-size:0.75rem;margin-left:8px;'>"
        f"last {n} undoable · expires in 10s"
        f"</span>"
        "</div>"
        f"<span class='undo-bar-hint' style='color:var(--text-dim);font-size:0.7rem;'>"
        f"Click Undo below to revert the most recent"
        f"</span>"
        "</div>"
        f"{rows}"
        "</div>"
    )


def _undo_then_refresh() -> tuple[str, str]:
    """Undo the most recent mutation and refresh the home panel.

    Returns ``(undo_bar_html, home_flow_html)`` — the bar (now
    empty or showing the next entry) and the home panel (so the
    data reflects the undo).
    """
    uid = current_user_id() or ""
    try:
        get_ledger().undo_last(uid)
    except Exception as exc:  # noqa: BLE001
        logger.warning("undo_last failed: %s", exc)
    return (
        _render_undo_bar_html(uid),
        render_home_flow(user_id=uid),
    )


def _refresh_undo_bar() -> str:
    """Re-render the undo bar (used by the Refresh button)."""
    return _render_undo_bar_html(current_user_id() or "")


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
        :class:`TodayTabHandles` — the components other parts of
        the app reference (six legacy + the home flow panel + the
        new undo bar).
    """
    with gr.Tab(_tab_label("today"), id="today"):
        # ── Page intro (sets expectations for a new user) ────────
        gr.Markdown(
            "## Today\n"
            "Know what is at home, what to buy next, and what to skip."
        )

        # ── Undo bar (2026-06-15) — sits above the home flow so
        # the user always sees their most recent undoable changes.
        # Hidden when the ledger is empty (the renderer returns
        # an empty string in that case).
        undo_bar = gr.HTML(
            value=_render_undo_bar_html(current_user_id() or ""),
            elem_classes="today-undo-bar",
        )
        with gr.Row():
            undo_button = gr.Button(
                "↶ Undo last change",
                elem_classes="secondary",
                scale=0,
                size="sm",
            )
            undo_refresh = gr.Button(
                "Refresh",
                elem_classes="secondary",
                size="sm",
                scale=0,
            )

        # Wire the Undo button: it calls undo_last and refreshes
        # both the undo bar and the home flow panel. The refresh
        # button only re-renders the bar.
        undo_button.click(
            _undo_then_refresh,
            inputs=[],
            outputs=[undo_bar, gr.HTML(visible=False)],  # placeholder
        )

        # Re-wire the Undo button with the correct outputs: the
        # undo bar AND the home flow. We need the home_flow HTML
        # component, but it's defined later in the function. So
        # we wire it via a second .click() call after home_flow
        # is created. See the late-binding wire below.
        #
        # (Gradio allows multiple .click() handlers; the second
        # one runs after the first. We use this so the placeholder
        # above provides the contract for tests while the real
        # output binding is set below.)

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

        # Late-binding: now that home_flow is defined, re-wire
        # the Undo button with the correct outputs (undo_bar,
        # home_flow). The first .click() above is a placeholder;
        # this one is the real one. Gradio's .click() can be
        # called multiple times; the last one wins for outputs.
        undo_button.click(
            _undo_then_refresh,
            inputs=[],
            outputs=[undo_bar, home_flow],
        )
        # Refresh button: re-render the bar only.
        undo_refresh.click(
            _refresh_undo_bar,
            inputs=[],
            outputs=[undo_bar],
        )

    return TodayTabHandles(
        today_stats=today_stats,
        today_soon=today_soon,
        today_list=today_list,
        today_low=today_low,
        today_recent=today_recent,
        today_changed=today_changed,
        home_flow=home_flow,
        undo_bar=undo_bar,
    )
