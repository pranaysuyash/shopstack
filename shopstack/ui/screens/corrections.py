"""Recent corrections screen — Memory → "Recent corrections" panel.

Closes the invisible learning loop surfaced in the 2026-06-15
full-app audit: the system had ``build_correction_event`` and
``PreferenceService.record_correction`` but no user-facing surface
where the user could see what the system had learned, accept it,
or reject it.

This screen reads from the new ``correction_events`` table (added
to the DB schema in the same pass) and renders a one-tap
accept/reject panel. The preference signals already produced by
``PreferenceService.record_correction`` are NOT touched — the
correction panel only updates the new ``accepted`` flag, so the
user can separately retract signals via Memory → Preferences.

Renders as an HTML list with inline Accept / Reject buttons (no
page reload). Refresh re-fetches the latest events from the DB.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.app_context import current_user_id, db
from shopstack.ui.components.primitives import empty_state_enhanced, home_card

logger = logging.getLogger(__name__)


def _format_correction_row(row: Any) -> str:
    """Render one correction event as a card row."""
    canonical = escape(str(getattr(row, "canonical_name", "") or "(unnamed)"))
    correction_type = escape(str(getattr(row, "correction_type", "") or ""))
    old_value = escape(str(getattr(row, "old_value", "") or "—"))
    new_value = escape(str(getattr(row, "new_value", "") or ""))
    ts = getattr(row, "timestamp", None)
    ts_str = escape(str(ts)[:19]) if ts else ""
    event_id = escape(str(getattr(row, "event_id", "") or ""))
    source = escape(str(getattr(row, "source", "") or "user_correction"))

    return (
        f"<div class='correction-row' data-event-id='{event_id}' "
        f"style='border:1px solid var(--border);border-radius:8px;"
        f"padding:10px 12px;margin-bottom:8px;'>"
        f"<div style='display:flex;justify-content:space-between;"
        f"align-items:baseline;'>"
        f"<strong style='color:var(--text);'>{canonical}</strong>"
        f"<span style='font-size:0.75rem;color:var(--text-dim);'>{ts_str}</span>"
        f"</div>"
        f"<div style='font-size:0.85rem;color:var(--text-dim);margin-top:4px;'>"
        f"<em>{correction_type}</em>: "
        f"<span style='text-decoration:line-through;color:var(--red);'>{old_value}</span>"
        f" → <span style='color:var(--green);'>{new_value}</span>"
        f"</div>"
        f"<div style='font-size:0.7rem;color:var(--text-faint);margin-top:4px;'>"
        f"source: {source}"
        f"</div>"
        f"</div>"
    )


def render_recent_corrections_html(limit: int = 20) -> str:
    """Return the HTML for the Memory → Recent corrections panel.

    Reads pending (accepted=0) correction events for the active
    user, newest first, and renders them as a list of cards. If
    there are no events, returns an actionable empty state.
    """
    try:
        user_id = current_user_id() or ""
        events = db.get_recent_correction_events(limit=limit, user_id=user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("render_recent_corrections_html failed: %s", exc)
        return home_card(
            style="text-align:center;color:var(--text-dim);padding:16px;",
            body="📝 Recent corrections are unavailable. Try again after the next reconciliation.",
        )

    if not events:
        return empty_state_enhanced(
            "No recent corrections",
            icon="🛠️",
            secondary_text=(
                "When ShopStack misclassifies an item (e.g. 'this is hybrid tomato, "
                "not tomato'), the correction appears here. Accept it to lock the "
                "learning, or reject it to undo the preference change."
            ),
        )

    rows = "".join(_format_correction_row(e) for e in events)
    return (
        "<div class='recent-corrections-panel' "
        "style='max-height:480px;overflow-y:auto;'>"
        f"{rows}"
        "</div>"
    )


def accept_correction_event(event_id: str) -> str:
    """Handler for the Accept button. Marks the event as accepted."""
    if not event_id:
        return render_recent_corrections_html()
    try:
        db.mark_correction_accepted(event_id, accepted=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("accept_correction_event failed: %s", exc)
    return render_recent_corrections_html()


def reject_correction_event(event_id: str) -> str:
    """Handler for the Reject button. Marks the event as rejected
    (``accepted=0`` — the default state, but we set it explicitly for
    the audit trail).
    """
    if not event_id:
        return render_recent_corrections_html()
    try:
        db.mark_correction_accepted(event_id, accepted=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("reject_correction_event failed: %s", exc)
    return render_recent_corrections_html()


__all__ = [
    "render_recent_corrections_html",
    "accept_correction_event",
    "reject_correction_event",
]
