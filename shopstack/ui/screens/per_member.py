"""Per-member activity attribution UI screen — Phase 11 wiring.

Thin server-rendered panel that pulls the household's trace
stream, aggregates by actor_id, and returns XSS-safe HTML.
Wired into the Memory tab → "Per-member" sub-tab.
"""
from __future__ import annotations

import logging
from html import escape

from shopstack.app_context import current_user_id, db
from shopstack.services.per_member_activity import (
    aggregate_by_actor,
    render_per_member_html,
)
from shopstack.ui.components.primitives import home_card

logger = logging.getLogger(__name__)


def per_member_screen(window_days: int = 30) -> str:
    """Render the per-member activity panel for the active household."""
    from shopstack.ui.errors import safe_render_html
    wd = window_days
    return safe_render_html(
        lambda: _per_member_screen_inner(wd),
        user_message="Could not load per-member activity",
        help_tab="memory",
        icon="👥",
    )


def _per_member_screen_inner(window_days: int) -> str:
    """Inner: render the per-member activity panel."""
    user_id = current_user_id() or ""
    try:
        traces = db.get_traces(limit=500, user_id=user_id) or []
    except Exception:
        traces = []
    from shopstack.services.per_member_activity import with_actor
    traces = [with_actor(t, user_id) for t in traces]
    activity = aggregate_by_actor(traces, window_days=window_days)
    return render_per_member_html(activity)


__all__ = ["per_member_screen"]
