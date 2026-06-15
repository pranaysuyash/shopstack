"""Household activity log — Phase 6 #26 (Tier 4 #26).

Aggregates the existing trace stream into a household-level activity
view:

- **Timeline** — the last N traces, oldest first, grouped by day.
- **Top actions** — counts of each action type over the last 30 days.
- **Top items** — which canonical items were touched most often
  (additions, consumptions, recipes, etc.).
- **Member breakdown** — when traces carry a ``user_id`` (multi-user
  households), counts per user.

**Inputs:** a :class:`shopstack.schemas.models.Trace` (or a duck-typed
object with the same fields). The aggregator never touches the DB
directly — callers pass in the result of
``db.get_traces(limit=N, user_id=...)``.

**Outputs:** a :class:`ActivitySummary` dataclass + a small HTML
block for the Memory tab.

**Privacy / scope:** household-scoped only. The user_id filter in
``db.get_traces`` keeps cross-household data out.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Iterable

from shopstack.ui.components.primitives import home_card

logger = logging.getLogger(__name__)


# ─── Summary dataclasses ──────────────────────────────────────────


@dataclass
class DayBucket:
    """A day's worth of traces, oldest-first within the day."""

    date: str  # YYYY-MM-DD
    traces: list[Any] = field(default_factory=list)


@dataclass
class ActivitySummary:
    """Aggregated activity for a household over a date range."""

    days: list[DayBucket] = field(default_factory=list)
    action_counts: dict[str, int] = field(default_factory=dict)
    item_counts: dict[str, int] = field(default_factory=dict)
    member_counts: dict[str, int] = field(default_factory=dict)
    total_traces: int = 0
    window_days: int = 30
    most_active_day: str = ""
    most_active_member: str = ""
    top_item: str = ""
    top_action: str = ""


# ─── Aggregation ─────────────────────────────────────────────────


# Recognized trace action types. Unknown types still get counted.
KNOWN_ACTIONS = {
    "add_purchase", "consume", "shopping_list_add",
    "shopping_list_check", "reconcile", "recipe_add",
    "price_observation", "backup_create", "backup_restore",
    "household_create", "household_switch",
}


def _trace_field(trace: Any, key: str, default: Any = None) -> Any:
    """Best-effort field accessor (works for both dataclass and dict)."""
    if isinstance(trace, dict):
        return trace.get(key, default)
    return getattr(trace, key, default)


def _trace_user_id(trace: Any) -> str:
    """Extract user/actor id from a trace (default: "you")."""
    uid = _trace_field(trace, "user_id") or _trace_field(trace, "actor_id") or "you"
    if not isinstance(uid, str):
        return str(uid)
    return uid


def _trace_canonical(trace: Any) -> str:
    """Extract the canonical_name from a trace payload, if any."""
    payload = _trace_field(trace, "payload", {}) or {}
    if isinstance(payload, dict):
        cn = payload.get("canonical_name")
        if cn:
            return str(cn)
        # Fall back to the input if it carries one
        inp = payload.get("input")
        if isinstance(inp, dict):
            cn = inp.get("canonical_name")
            if cn:
                return str(cn)
    return ""


def _trace_day_key(trace: Any) -> str:
    """Extract a YYYY-MM-DD key from a trace timestamp."""
    ts = _trace_field(trace, "created_at") or _trace_field(trace, "timestamp")
    if isinstance(ts, datetime):
        return ts.strftime("%Y-%m-%d")
    if isinstance(ts, str):
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
        except ValueError:
            return ts[:10] if len(ts) >= 10 else "unknown"
    return "unknown"


def aggregate_activity(
    traces: Iterable[Any],
    *,
    window_days: int = 30,
    today: datetime | None = None,
) -> ActivitySummary:
    """Aggregate a list of traces into an :class:`ActivitySummary`.

    Args:
        traces: An iterable of trace objects (dataclass or dict).
        window_days: How many days back to consider. Traces older
            than ``today - window_days`` are excluded from the
            timeline but still counted in the lifetime totals.
        today: Override "now" for deterministic tests.
    """
    if today is None:
        today = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = today - timedelta(days=window_days)

    def _as_naive(ts: Any) -> datetime | None:
        """Strip tzinfo so naive/aware datetimes can be compared uniformly."""
        if isinstance(ts, datetime):
            return ts.replace(tzinfo=None) if ts.tzinfo else ts
        return None

    days_map: dict[str, list[Any]] = defaultdict(list)
    action_counts: Counter[str] = Counter()
    item_counts: Counter[str] = Counter()
    member_counts: Counter[str] = Counter()
    total = 0
    in_window = 0

    for tr in traces:
        total += 1
        action = str(_trace_field(tr, "action_type") or _trace_field(tr, "action") or "unknown")
        action_counts[action] += 1
        cn = _trace_canonical(tr)
        if cn:
            item_counts[cn] += 1
        member_counts[_trace_user_id(tr)] += 1

        # Day bucketing — only for traces in the window
        ts = _trace_field(tr, "created_at") or _trace_field(tr, "timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                ts = None
        ts_naive = _as_naive(ts) if isinstance(ts, datetime) else None
        if ts_naive is not None and ts_naive < cutoff:
            continue
        if ts_naive is None:
            continue  # skip unparseable from the timeline
        in_window += 1
        day_key = ts_naive.strftime("%Y-%m-%d")
        days_map[day_key].append(tr)

    # Sort days oldest-first
    days: list[DayBucket] = [
        DayBucket(date=k, traces=sorted(v, key=_trace_field_or_dt))
        for k, v in sorted(days_map.items())
    ]

    most_active_day = ""
    if days:
        most_active_day = max(days, key=lambda d: len(d.traces)).date
    most_active_member = member_counts.most_common(1)[0][0] if member_counts else ""
    top_item = item_counts.most_common(1)[0][0] if item_counts else ""
    top_action = action_counts.most_common(1)[0][0] if action_counts else ""

    return ActivitySummary(
        days=days,
        action_counts=dict(action_counts.most_common()),
        item_counts=dict(item_counts.most_common(20)),  # top 20 only
        member_counts=dict(member_counts.most_common()),
        total_traces=total,
        window_days=window_days,
        most_active_day=most_active_day,
        most_active_member=most_active_member,
        top_item=top_item,
        top_action=top_action,
    )


def _trace_field_or_dt(tr: Any):
    ts = _trace_field(tr, "created_at") or _trace_field(tr, "timestamp")
    if isinstance(ts, datetime):
        return ts
    return datetime.min


# ─── HTML rendering ──────────────────────────────────────────────


def render_activity_log_html(summary: ActivitySummary, *, max_days: int = 14) -> str:
    """Render the activity log as a small HTML block.

    Sections:
    1. Headline stats (total traces, top action, top item, active members).
    2. Top actions (horizontal bars).
    3. Top items (small chips).
    4. Recent timeline (the most-recent ``max_days`` days).
    """
    if summary.total_traces == 0:
        return home_card(
            style="text-align:center;padding:16px;color:var(--text-dim);",
            body="No activity yet. Add a purchase, log a recipe, or use the app to see it here.",
        )

    parts: list[str] = []
    parts.append("<div class='al-block'>")
    parts.append(
        "<div class='al-headline'>"
        f"<strong>{summary.total_traces}</strong> actions in the last {summary.window_days} days"
    )
    if summary.top_action:
        parts.append(
            f" · top: <strong>{escape(summary.top_action.replace('_', ' '))}</strong>"
        )
    if summary.top_item:
        parts.append(
            f" · top item: <strong>{escape(summary.top_item.replace('_', ' ').title())}</strong>"
        )
    if summary.most_active_member:
        parts.append(
            f" · most active: <strong>{escape(summary.most_active_member)}</strong>"
        )
    parts.append("</div>")

    # Top actions as bars
    if summary.action_counts:
        parts.append("<div class='al-section-h'>Top actions</div>")
        max_count = max(summary.action_counts.values()) or 1
        for action, count in list(summary.action_counts.items())[:6]:
            pct = round(count / max_count * 100, 1)
            parts.append(
                "<div class='al-bar-row'>"
                f"<div class='al-bar-label'>{escape(action.replace('_', ' '))}</div><div class='al-bar-track'>"
                f"<div class='al-bar-fill' style='width:{pct:.0f}%;'></div></div>"
                f"<div class='al-bar-pct'>{count}</div></div>"
            )

    # Top items as chips
    if summary.item_counts:
        parts.append("<div class='al-section-h'>Top items</div>")
        chips = "".join(
            f"<span class='al-chip'>{escape(name.replace('_', ' ').title())} <span class='al-chip-n'>{count}</span></span>"
            for name, count in list(summary.item_counts.items())[:12]
        )
        parts.append(f"<div class='al-chips'>{chips}</div>")

    # Timeline (most recent max_days days)
    if summary.days:
        parts.append("<div class='al-section-h'>Recent activity</div>")
        parts.append("<ul class='al-timeline'>")
        for day in summary.days[-max_days:]:
            parts.append(
                f"<li class='al-tl-day'><span class='al-tl-date'>{escape(day.date)}</span>"
                f"<span class='al-tl-count'>{len(day.traces)} event(s)</span></li>"
            )
        parts.append("</ul>")

    parts.append("</div>")
    return "".join(parts)


__all__ = [
    "ActivitySummary",
    "DayBucket",
    "KNOWN_ACTIONS",
    "aggregate_activity",
    "render_activity_log_html",
]
