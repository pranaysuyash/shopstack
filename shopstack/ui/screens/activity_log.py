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
    from shopstack.ui.errors import safe_render_html
    return safe_render_html(
        lambda: _activity_log_inner(window_days),
        user_message="Could not load activity log",
        help_tab="memory",
    )


def _activity_log_inner(window_days: int) -> str:
    user_id = current_user_id() or ""
    try:
        traces = db.get_traces(limit=200, user_id=user_id) or []
    except Exception:
        traces = []
    summary = aggregate_activity(traces, window_days=window_days)
    return render_activity_log_html(summary)


__all__ = ["activity_log_screen"]
