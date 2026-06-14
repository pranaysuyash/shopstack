"""Analytics dashboard UI screen — Phase 8 (new product surface).

Thin server-rendered panel that pulls the household's trace
stream, runs the analytics aggregator, and returns HTML.
Wired into the Memory tab as a new "Analytics" sub-tab.
"""
from __future__ import annotations

import logging

from shopstack.app_context import current_user_id, db
from shopstack.services.analytics import aggregate_analytics, render_analytics_html


def analytics_screen(window_days: int = 180) -> str:
    """Render the household analytics dashboard."""
    try:
        user_id = current_user_id() or ""
        try:
            traces = db.get_traces(limit=500, user_id=user_id) or []
        except Exception:
            traces = []
        analytics = aggregate_analytics(traces, window_days=window_days)
        return render_analytics_html(analytics)
    except Exception as exc:
        logger.warning("analytics_screen failed: %s", exc)
        return (
            "<div class='home-card' style='text-align:center;color:var(--text-dim);padding:16px;'>"
            "📊 No analytics yet. Add some receipts to see insights."
            "</div>"
        )


__all__ = ["analytics_screen"]
