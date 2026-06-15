"""Unified Timeline UI screen.

Renders the household's cross-source event timeline for the Find and
Map surfaces. Filters at the screen level are intentionally narrow
(``canonical_name`` and ``lot_id``); broader date-range filters live
in the service.

Related screen (kept separate for backward compatibility):
:func:`shopstack.ui.screens.activity_log.activity_log_screen` —
narrow trace aggregator for the Memory tab.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any

from shopstack.app_context import current_user_id, db
from shopstack.services.timeline import (
    TimelineQuery,
    TimelineService,
    render_timeline_html,
)
from shopstack.ui.components.decorators import aria_live_screen
from shopstack.ui.components.primitives import home_card
from shopstack.ui.screens._utils import safe_render

logger = logging.getLogger(__name__)


@safe_render
def timeline_view(
    canonical_name: str = "",
    lot_id: str = "",
    days: int = 30,
) -> str:
    """Render the Unified Timeline for the active household.

    Args:
        canonical_name: Optional filter — only events for this item.
        lot_id: Optional filter — only events for this lot.
        days: Window size in days. Defaults to 30.
    """
    days = max(1, int(days or 30))
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    user_id = current_user_id() or ""
    query = TimelineQuery(
        canonical_name=(canonical_name or "").strip(),
        lot_id=(lot_id or "").strip(),
        since=since,
        limit=200,
    )
    try:
        result = TimelineService(db).query(query, user_id=user_id)
    except Exception as exc:
        logger.warning("timeline_view failed: %s", exc)
        return home_card(
            style="text-align:center;padding:16px;",
            body=(
                "<div style='color:var(--amber);font-weight:600;'>Could not load timeline</div>"
                f"<div style='font-size: 0.75rem;color:var(--text-dim);margin-top:4px;'>{escape(str(exc)[:120])}</div>"
            ),
        )
    return render_timeline_html(result)


@safe_render
def timeline_for_canonical(canonical_name: str) -> str:
    """Convenience: short (90-day) timeline focused on a single item."""
    return timeline_view(canonical_name=canonical_name, days=90)


@safe_render
def timeline_for_lot(lot_id: str) -> str:
    """Convenience: full history for a single lot."""
    return timeline_view(lot_id=lot_id, days=365)


@aria_live_screen()
def set_timeline_window(window_days: int) -> str:
    """No-op: the screen reads ``days`` per call, this confirms the window."""
    return f"<div style='color:var(--green);'>Showing last {int(window_days)} day(s).</div>"


__all__ = [
    "timeline_view",
    "timeline_for_canonical",
    "timeline_for_lot",
    "set_timeline_window",
]
