"""Per-member activity attribution — Phase 11.

Once every write path checks permissions, the natural
follow-on is to record *which member* of the household
actually made each change. The trace stream is the
canonical audit log — extending it to carry an
``actor_id`` field is purely additive (the supersession
rule applies: the old behavior is preserved, we just
record more).

**1st-principles design:**

- ``household_id`` in a trace identifies *which household*
  the change belongs to.
- ``actor_id`` identifies *which member* of that household
  triggered it.
- The two are independent: a household can have one
  active user but multiple members, and a single action
  is performed by one of them.
- Analytics (per-member spend, per-member activity) reads
  on ``actor_id`` to surface "alice added 12 items this
  month, bob consumed 8".

**Public API:**

- :func:`record_actor` — decorator / helper to add the
  actor_id to a trace before saving.
- :func:`aggregate_by_actor` — count traces + action types
  per actor in a household.
- :func:`render_per_member_html` — XSS-safe HTML for the
  Memory tab "Per-member" sub-section.

**Why a separate module:**

The trace model has an ``actor_id`` field now, but the
*analytics* that read it live here, not in
``shopstack.services.activity_log``. Keeping them
separate means the per-member view can grow independently
(spend per member, items per member, etc.) without
cluttering the general activity log.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import escape
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ─── Result dataclass ────────────────────────────────────────────


@dataclass
class MemberActivity:
    """One member's activity summary."""

    actor_id: str
    total_traces: int = 0
    by_action: dict[str, int] = field(default_factory=dict)
    by_item: dict[str, int] = field(default_factory=dict)
    last_active: str = ""
    first_active: str = ""


@dataclass
class PerMemberActivity:
    """Per-member activity for one household over a date range."""

    members: list[MemberActivity] = field(default_factory=list)
    total_traces: int = 0
    window_days: int = 30
    unknown_actor_traces: int = 0


# ─── record_actor helper ────────────────────────────────────────


def with_actor(trace: Any, actor_id: str) -> Any:
    """Return the trace with ``actor_id`` set.

    Pure helper — doesn't mutate the input trace. Pydantic
    v2 models are immutable by default, so this returns a
    new instance. For dataclass / dict inputs, sets the
    field in place.

    Args:
        trace: A :class:`Trace` (Pydantic), a dict, or any
            object with an ``actor_id`` attribute.
        actor_id: The member id of the actor.

    Returns:
        The trace with ``actor_id`` set. If the trace doesn't
        have an ``actor_id`` field, returns the original
        unchanged (backward compat for legacy call sites).
    """
    if trace is None:
        return trace
    aid = (actor_id or "").strip()
    if isinstance(trace, dict):
        if "actor_id" in trace:
            new_d = dict(trace)
            new_d["actor_id"] = aid
            return new_d
        return trace
    if hasattr(trace, "model_copy"):
        # Pydantic v2
        try:
            return trace.model_copy(update={"actor_id": aid})
        except Exception:
            return trace
    if hasattr(trace, "copy"):
        try:
            new = trace.copy()
            setattr(new, "actor_id", aid)
            return new
        except Exception:
            return trace
    if hasattr(trace, "actor_id"):
        try:
            setattr(trace, "actor_id", aid)
            return trace
        except Exception:
            return trace
    return trace


# ─── aggregate_by_actor ────────────────────────────────────────


def _trace_field(trace: Any, key: str, default: Any = None) -> Any:
    if isinstance(trace, dict):
        return trace.get(key, default)
    return getattr(trace, key, default)


def _trace_dt(trace: Any) -> datetime | None:
    ts = _trace_field(trace, "timestamp") or _trace_field(trace, "created_at")
    if isinstance(ts, datetime):
        return ts.replace(tzinfo=None) if ts.tzinfo else ts
    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _trace_action(trace: Any) -> str:
    """Extract a human-readable action label from the trace."""
    decision = _trace_field(trace, "decision", {}) or {}
    if isinstance(decision, dict):
        # decision can have a top-level "action" or a "decisions" list
        action = decision.get("action")
        if action:
            return str(action)
        decisions_list = decision.get("decisions") or []
        if decisions_list and isinstance(decisions_list[0], dict):
            return str(decisions_list[0].get("action") or "decision")
    proposed = _trace_field(trace, "proposed_tool_calls", []) or []
    if proposed and isinstance(proposed, list) and isinstance(proposed[0], dict):
        return str(proposed[0].get("tool_name") or proposed[0].get("name") or "tool_call")
    input_type = _trace_field(trace, "input_type") or "trace"
    return str(input_type)


def _trace_canonical(trace: Any) -> str:
    decision = _trace_field(trace, "decision", {}) or {}
    if isinstance(decision, dict):
        cn = decision.get("canonical_name")
        if cn:
            return str(cn)
        decisions_list = decision.get("decisions") or []
        if decisions_list and isinstance(decisions_list[0], dict):
            cn = decisions_list[0].get("canonical_name")
            if cn:
                return str(cn)
    return ""


def aggregate_by_actor(
    traces: Iterable[Any],
    *,
    window_days: int = 30,
    today: datetime | None = None,
) -> PerMemberActivity:
    """Aggregate the household's trace stream by actor.

    Args:
        traces: Iterable of trace objects (dataclass, Pydantic, or dict).
        window_days: How many days back to consider.
        today: Override "now" for deterministic tests.

    Returns:
        A :class:`PerMemberActivity` with per-member counts.
    """
    if today is None:
        today = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = today - timedelta(window_days)

    per_actor: dict[str, MemberActivity] = {}
    total = 0
    unknown = 0

    for tr in traces:
        total += 1
        dt = _trace_dt(tr)
        if dt is None or dt < cutoff:
            continue
        actor = str(_trace_field(tr, "actor_id", "") or "").strip()
        if not actor:
            unknown += 1
            actor = "(unknown)"
        if actor not in per_actor:
            per_actor[actor] = MemberActivity(actor_id=actor)
        m = per_actor[actor]
        m.total_traces += 1
        action = _trace_action(tr)
        m.by_action[action] = m.by_action.get(action, 0) + 1
        cn = _trace_canonical(tr)
        if cn:
            m.by_item[cn] = m.by_item.get(cn, 0) + 1
        iso = dt.isoformat() if isinstance(dt, datetime) else str(dt)
        if not m.first_active or iso < m.first_active:
            m.first_active = iso
        if not m.last_active or iso > m.last_active:
            m.last_active = iso

    # Sort members by total_traces desc, with "(unknown)" last
    members = sorted(
        per_actor.values(),
        key=lambda m: (m.actor_id == "(unknown)", -m.total_traces, m.actor_id),
    )

    return PerMemberActivity(
        members=members,
        total_traces=total,
        window_days=window_days,
        unknown_actor_traces=unknown,
    )


# ─── HTML rendering ────────────────────────────────────────────


def render_per_member_html(activity: PerMemberActivity) -> str:
    """Render the per-member activity as XSS-safe HTML.

    Sections:
    1. Headline (total traces + member count).
    2. Per-member rows (ranked by trace count, with top action
       and last-active).
    """
    if activity.total_traces == 0:
        return (
            "<div class='pm-block'>"
            "<div class='pm-empty'>📊 No member activity yet. Add a few items to see who-did-what.</div>"
            "</div>"
        )
    parts: list[str] = [
        "<div class='pm-block'>",
        f"<div class='pm-headline'>"
        f"<strong>{activity.total_traces}</strong> traces in the last "
        f"{activity.window_days} days"
        + (f" · <strong>{activity.unknown_actor_traces}</strong> pre-attribution" if activity.unknown_actor_traces else "")
        + "</div>",
    ]
    if activity.members:
        parts.append("<div class='pm-members'>")
        for m in activity.members:
            top_action = max(m.by_action.items(), key=lambda kv: kv[1], default=("", 0))
            top_action_str = top_action[0] if top_action[0] else "—"
            top_count = top_action[1] if top_action[0] else 0
            last = (m.last_active or "")[:10]  # YYYY-MM-DD
            parts.append(
                "<div class='pm-member-row'>"
                f"<span class='pm-actor'>{escape(m.actor_id)}</span>"
                f"<span class='pm-count'>{m.total_traces}</span>"
                f"<span class='pm-top-action'>"
                f"top: {escape(top_action_str)} ({top_count})"
                f"</span>"
                f"<span class='pm-last'>last: {escape(last) or '—'}</span>"
                "</div>"
            )
        parts.append("</div>")
    parts.append("</div>")
    return "".join(parts)


__all__ = [
    "MemberActivity",
    "PerMemberActivity",
    "aggregate_by_actor",
    "render_per_member_html",
    "with_actor",
]
