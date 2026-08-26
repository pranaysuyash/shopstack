"""Repair / Damage Inbox — operator view of open condition issues.

Renders the household's open condition issues sorted by severity and
recency, with actions to confirm, close, or delete each event.

This is the long-term home for "your detergent is leaking" alerts.
The user reviews the inbox, confirms or dismisses each issue, and
the system records the action.
"""
from __future__ import annotations

import logging
from html import escape

from shopstack.app_context import db
from shopstack.schemas.condition import (
    ConditionAction,
    ConditionSeverity,
)
from shopstack.services.condition import (
    get_repair_inbox,
    record_condition_event,
)
from shopstack.ui.components.decorators import aria_live_screen
from shopstack.ui.components.primitives import home_card, stat_card

logger = logging.getLogger(__name__)


# Color palette per severity
_SEVERITY_COLORS: dict[str, str] = {
    ConditionSeverity.SPOILED.value: "var(--red)",
    ConditionSeverity.BROKEN.value: "var(--red)",
    ConditionSeverity.DAMAGED.value: "var(--amber)",
    ConditionSeverity.WORN.value: "var(--blue)",
    ConditionSeverity.COSMETIC.value: "var(--text-dim)",
}


# Human label per action
_ACTION_LABELS: dict[str, str] = {
    ConditionAction.REPLACE.value: "Replace",
    ConditionAction.REPAIR.value: "Repair",
    ConditionAction.DISCARD.value: "Discard",
    ConditionAction.USE_SOON.value: "Use soon",
    ConditionAction.MONITOR.value: "Monitor",
    ConditionAction.NONE.value: "—",
}



def repair_inbox_view(severity: str = "") -> str:
    """Render the repair inbox."""
    from shopstack.ui.errors import safe_render_html
    sev = severity
    return safe_render_html(
        lambda: _repair_inbox_view_inner(sev),
        user_message="Could not load repair inbox",
        help_tab="household",
        icon="🔧",
    )


def _repair_inbox_view_inner(severity: str) -> str:
    """Inner render for the repair inbox."""
    sev = None
    if severity:
        try:
            sev = ConditionSeverity(severity)
        except ValueError:
            sev = None
    try:
        items = get_repair_inbox(db, severity=sev, limit=50)
    except Exception as exc:
        logger.exception("repair_inbox_view failed")
        return home_card(
            style="text-align:center;padding:16px;",
            body=(
                "<div style='color:var(--red);font-weight:600;'>Could not load inbox</div>"
                f"<div style='font-size: 0.75rem;color:var(--text-dim);margin-top:4px;'>{escape(str(exc)[:120])}</div>"
            ),
        )
    if not items:
        return home_card(
            style="text-align:center;padding:24px;",
            body=(
                "<div style='font-size:1.5rem;margin-bottom:8px;'>✓</div>"
                "<div style='font-weight:600;'>All clear</div>"
                "<div style='font-size:0.75rem;color:var(--text-dim);margin-top:4px;'>"
                "No open condition issues. Items in good shape."
                "</div>"
            ),
        )

    parts: list[str] = []
    parts.append("<h3>Repair Inbox</h3>")
    parts.append(
        f"<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>{len(items)} open issue(s), sorted by severity and recency."
        f"</div>"
    )
    for item in items:
        sev_color = _SEVERITY_COLORS.get(item.severity.value, "var(--text-dim)")
        action_label = _ACTION_LABELS.get(item.recommended_action.value, "—")
        last_seen = item.last_seen_at.strftime("%b %d") if item.last_seen_at else "?"
        first_seen = item.first_seen_at.strftime("%b %d") if item.first_seen_at else "?"
        occ = item.occurrences
        # Confirm-status badge
        confirm_badge = (
            "<span style='font-size:0.625rem;background:var(--green);color:#fff;padding:2px 6px;border-radius:8px;margin-left:6px;'>confirmed</span>"
            if item.user_confirmed
            else f"<span style='font-size:0.625rem;background:var(--amber);color:#fff;"
            f"padding:2px 6px;border-radius:8px;margin-left:6px;'>{item.pending_user_confirmation} pending</span>"
        )
        parts.append(stat_card(
            style="text-align:left;margin-bottom:8px;",
            body_html=(
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<div style='font-weight:600;color:var(--text);'>{escape(item.canonical_name)}{confirm_badge}</div><span style='background:{sev_color};color:#fff;padding:2px 8px;"
                f"border-radius:10px;font-size:0.625rem;font-weight:600;'>{escape(item.severity.value.upper())}</span>"
                f"</div><div style='font-size:0.75rem;color:var(--text-dim);margin-top:4px;'>"
                f"{escape(item.dominant_kind.value)} · {occ}x · last {escape(last_seen)} · first {escape(first_seen)}</div>"
                f"<div style='font-size:0.75rem;margin-top:4px;'>📍 {escape(item.location_name or 'unknown')} · "
                f"<strong>Action:</strong> {escape(action_label)}</div>"
                f"{('<div style=\"font-size:0.6875rem;color:var(--text-dim);margin-top:4px;font-style:italic;\">'
                  '\"' + escape(item.latest_description) + '\"</div>') if item.latest_description else ''}"
            ),
        ))
    return "".join(parts)


@aria_live_screen()
def report_damage(
    lot_id: str,
    kind: str,
    severity: str,
    description: str = "",
) -> str:
    """Record a user-reported condition issue.

    Args:
        lot_id: The item lot to attach the issue to.
        kind: Type of issue (physical_damage, liquid_leak, etc.).
        severity: Severity (cosmetic, worn, damaged, broken, spoiled).
        description: Optional free-text note.
    """
    if not (lot_id or "").strip():
        return "<div style='color:var(--red);'>Item reference required.</div>"
    if not (kind or "").strip():
        return "<div style='color:var(--red);'>Issue type required.</div>"
    if not (severity or "").strip():
        return "<div style='color:var(--red);'>Severity required.</div>"
    # Validate the lot exists
    lot = db.get_inventory_lot(lot_id.strip())
    if not lot:
        return f"<div style='color:var(--red);'>Unknown lot: {escape(lot_id[:12])}</div>"
    try:
        record_condition_event(
            db,
            lot_id=lot_id.strip(),
            kind=kind.strip(),
            severity=severity.strip(),
            description=description.strip(),
            canonical_name=lot.canonical_name,
        )
    except ValueError as exc:
        return f"<div style='color:var(--red);'>{escape(str(exc))}</div>"
    return (
        f"<div style='color:var(--green);'>Recorded {escape(severity)} {escape(kind)} issue for {escape(lot.canonical_name)}."
        f"</div>"
    )


@aria_live_screen()
def confirm_condition_event(event_id: str) -> str:
    """Mark a condition event as user-confirmed."""
    if not (event_id or "").strip():
        return "<div style='color:var(--red);'>Event reference required.</div>"
    ok = db.confirm_condition_event(event_id.strip())
    if not ok:
        return f"<div style='color:var(--red);'>Failed to confirm event {escape(event_id[:12])}.</div>"
    return "<div style='color:var(--green);'>Confirmed issue.</div>"


@aria_live_screen()
def close_condition_event(event_id: str) -> str:
    """Close (resolve/dismiss) a condition event."""
    if not (event_id or "").strip():
        return "<div style='color:var(--red);'>Event reference required.</div>"
    ok = db.close_condition_event(event_id.strip())
    if not ok:
        return f"<div style='color:var(--red);'>Failed to close event {escape(event_id[:12])}.</div>"
    return "<div style='color:var(--green);'>Issue resolved and closed.</div>"


@aria_live_screen()
def delete_condition_event(event_id: str) -> str:
    """Permanently delete a condition event."""
    if not (event_id or "").strip():
        return "<div style='color:var(--red);'>Event reference required.</div>"
    ok = db.delete_condition_event(event_id.strip())
    if not ok:
        return f"<div style='color:var(--red);'>Failed to delete event {escape(event_id[:12])}.</div>"
    return "<div style='color:var(--green);'>Issue removed.</div>"


__all__ = [
    "close_condition_event",
    "confirm_condition_event",
    "delete_condition_event",
    "repair_inbox_view",
    "report_damage",
]
