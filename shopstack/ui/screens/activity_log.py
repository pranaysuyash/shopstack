"""Activity log UI screen — Phase 8 #26 wiring.

Thin server-rendered panel that pulls the household's trace
stream, aggregates it, and returns the activity log HTML.
Wired into the Memory tab as a new "Activity" sub-tab.
"""
from __future__ import annotations

import logging

from shopstack.app_context import current_user_id, db
from shopstack.services.activity_log import (
    aggregate_activity,
    render_activity_log_html,
)


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
        logger.debug("activity_log_screen failed: %s", exc)
        return (
            "<div class='home-card' style='text-align:center;color:var(--text-dim);padding:16px;'>"
            "📊 No activity yet. Add a purchase, log a recipe, or use the app to see it here."
            "</div>"
        )


__all__ = ["activity_log_screen"]
