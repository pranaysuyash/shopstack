"""Per-member activity attribution UI screen — Phase 11 wiring.

Thin server-rendered panel that pulls the household's trace
stream, aggregates by actor_id, and returns XSS-safe HTML.
Wired into the Memory tab → "Per-member" sub-tab.
"""
from __future__ import annotations

import logging

from shopstack.app_context import current_user_id, db
from shopstack.services.per_member_activity import (
    aggregate_by_actor,
    render_per_member_html,
)


def per_member_screen(window_days: int = 30) -> str:
    """Render the per-member activity panel for the active household."""
    try:
        user_id = current_user_id() or ""
        try:
            traces = db.get_traces(limit=500, user_id=user_id) or []
        except Exception:
            traces = []
        # Annotate every trace with the active user as the actor
        # (the default user is the default actor for now; once
        # the household UI surfaces "switch actor", this becomes
        # the user_id at the time of action).
        from shopstack.services.per_member_activity import with_actor
        traces = [with_actor(t, user_id) for t in traces]
        activity = aggregate_by_actor(traces, window_days=window_days)
        return render_per_member_html(activity)
    except Exception as exc:
        logger.debug("per_member_screen failed: %s", exc)
        return ""


__all__ = ["per_member_screen"]
