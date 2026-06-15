"""Activity log UI screen — Phase 8 #26 wiring.

Thin server-rendered panel that pulls the household's trace
stream, aggregates it, and returns the activity log HTML.
Wired into the Memory tab as a new "Activity" sub-tab.
"""
from __future__ import annotations

import logging
from html import escape

from shopstack.app_context import current_user_id, db
from shopstack.services.activity_log import (
    aggregate_activity,
    render_activity_log_html,
)
from shopstack.ui.components.primitives import home_card

logger = logging.getLogger(__name__)


def activity_log_screen(window_days: int = 30) -> str:
    """Render the activity log panel for the active household.

    Returns XSS-safe HTML for direct insertion into a Gradio
    component. Empty-state when no traces are available.
    """
    try:
        user_id = current_user_id() or ""
        try:
            traces = db.get_traces(limit=200, user_id=user_id) or []
        except Exception:
            traces = []
        summary = aggregate_activity(traces, window_days=window_days)
        return render_activity_log_html(summary)
    except Exception as exc:
        logger.warning("activity_log_screen failed: %s", exc)
        return home_card(
            style="text-align:center;padding:16px;",
            body=(
                "<div style='color:var(--amber);font-weight:600;'>Could not load activity log</div>"
                f"<div style='font-size: 0.75rem;color:var(--text-dim);margin-top:4px;'>{escape(str(exc)[:120])}</div>"
                "<div style='font-size: 0.6875rem;color:var(--text-dim);margin-top:8px;'>"
                "Try refreshing, or add a purchase, log a recipe, or use the app to see activity here."
                "</div>"
            ),
        )


__all__ = ["activity_log_screen"]
