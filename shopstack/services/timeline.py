"""Unified Timeline — cross-source event aggregation.

Aggregates *all* household event types into a single chronological feed,
so the user can answer questions like:

- "What happened to my passport last week?"
- "Show me everything that touched the kitchen in May."
- "When did I last pay for milk, and at which store?"

**Inputs (all optional, all narrow):**
- inventory events (added / consumed / moved / adjusted / discarded)
- movement events (where a lot was moved)
- purchase events (buys)
- reconciliation events (plan → actual deltas)
- traces (planner / agent decisions)
- preference signals (staple / disliked / brand_preferred)
- correction events (user feedback)
- price observations (price memory writes)
- negative memory (Task 1 "confirmed NOT at")

The aggregator is pure: it never touches the DB directly. The caller
passes in lists, often via the convenience :class:`TimelineService`
which knows how to fetch from the active database.

**Why a new module (not extending ``activity_log``):**
``services/activity_log.py`` is a *narrow* trace aggregator built for
the Memory tab's "Activity" sub-tab. It deliberately ignores purchase,
movement, and inventory events. The Unified Timeline has a wider
purpose — it's the trust surface for "what really happened to my
stuff" and needs a different filter/shape contract. Per
``motto_v3`` §11 we prefer consolidation, so callers that today use
``activity_log`` directly should continue to do so. The Unified
Timeline is the canonical feed for the "Find" and "Map" surfaces.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from html import escape
from typing import Any, Iterable

from shopstack.persistence.database import Database

logger = logging.getLogger(__name__)


# ─── Event taxonomy ─────────────────────────────────────────────────

#: All event types recognized by the Unified Timeline. Unknown types
#: from the underlying rows still flow through; they just don't get a
#: friendly label or icon.
class TimelineEventType(str, Enum):
    INVENTORY_ADDED = "inventory.added"
    INVENTORY_CONSUMED = "inventory.consumed"
    INVENTORY_MOVED = "inventory.moved"
    INVENTORY_ADJUSTED = "inventory.adjusted"
    INVENTORY_DISCARDED = "inventory.discarded"
    INVENTORY_STATUS = "inventory.status_changed"
    MOVED = "movement.recorded"
    PURCHASED = "purchase.recorded"
    RECONCILED = "reconciliation.recorded"
    PRICE_OBSERVED = "price.observed"
    PREFERENCE_LEARNED = "preference.learned"
    CORRECTION = "correction.recorded"
    NEGATIVE_MEMORY = "negative_memory.recorded"
    TRACE_PLAN = "trace.plan"
    TRACE_FINALIZE = "trace.finalize"


#: Human-friendly label + emoji for each known type. Unknown types
#: fall back to a plain label derived from the type string.
_EVENT_LABELS: dict[str, tuple[str, str]] = {
    TimelineEventType.INVENTORY_ADDED.value:    ("Added to inventory",      "➕"),
    TimelineEventType.INVENTORY_CONSUMED.value: ("Consumed",                "🍽"),
    TimelineEventType.INVENTORY_MOVED.value:    ("Moved",                   "↗"),
    TimelineEventType.INVENTORY_ADJUSTED.value: ("Quantity adjusted",       "✏"),
    TimelineEventType.INVENTORY_DISCARDED.value: ("Discarded",              "🗑"),
    TimelineEventType.INVENTORY_STATUS.value:   ("Status changed",          "🔁"),
    TimelineEventType.MOVED.value:              ("Moved between locations", "↗"),
    TimelineEventType.PURCHASED.value:          ("Purchased",               "🛒"),
    TimelineEventType.RECONCILED.value:         ("Reconciled",              "✅"),
    TimelineEventType.PRICE_OBSERVED.value:     ("Price recorded",          "₹"),
    TimelineEventType.PREFERENCE_LEARNED.value: ("Preference learned",      "★"),
    TimelineEventType.CORRECTION.value:         ("User correction",         "🛠"),
    TimelineEventType.NEGATIVE_MEMORY.value:    ("Confirmed NOT at",        "✗"),
    TimelineEventType.TRACE_PLAN.value:         ("Plan recorded",           "🧠"),
    TimelineEventType.TRACE_FINALIZE.value:     ("Action finalized",        "✓"),
}


# ─── Data shapes ───────────────────────────────────────────────────


@dataclass(frozen=True)
class TimelineEvent:
    """A single normalized event in the Unified Timeline.

    Every event the aggregator produces has the same shape, regardless
    of the underlying source. This is the single contract the UI and
    any future consumers depend on.
    """
    event_id: str
    event_type: str
    timestamp: datetime
    canonical_name: str = ""
    lot_id: str = ""
    location_id: str = ""
    location_name: str = ""
    location_from: str | None = None
    location_to: str | None = None
    quantity_delta: float | None = None
    quantity_after: float | None = None
    unit: str = ""
    source: str = ""
    user_id: str = ""
    notes: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "canonical_name": self.canonical_name,
            "lot_id": self.lot_id,
            "location_id": self.location_id,
            "location_name": self.location_name,
            "location_from": self.location_from,
            "location_to": self.location_to,
            "quantity_delta": self.quantity_delta,
            "quantity_after": self.quantity_after,
            "unit": self.unit,
            "source": self.source,
            "user_id": self.user_id,
            "notes": self.notes,
        }


@dataclass
class TimelineBucket:
    """A day's worth of events, oldest-first within the day."""
    date: str  # YYYY-MM-DD
    events: list[TimelineEvent] = field(default_factory=list)


@dataclass
class TimelineQuery:
    """A filter shape for :meth:`TimelineService.query`.

    Every field is optional. Combine freely. ``since`` / ``until`` are
    ISO datetimes (timezone-naive or aware — both work).
    """
    canonical_name: str = ""
    lot_id: str = ""
    location_id: str = ""
    event_types: list[str] = field(default_factory=list)
    since: datetime | None = None
    until: datetime | None = None
    limit: int = 200
    order: str = "desc"  # "desc" (newest first) or "asc" (oldest first)


@dataclass
class TimelineResult:
    """Result of a Unified Timeline query."""
    events: list[TimelineEvent] = field(default_factory=list)
    buckets: list[TimelineBucket] = field(default_factory=list)
    by_type: dict[str, int] = field(default_factory=dict)
    by_location: dict[str, int] = field(default_factory=dict)
    by_canonical: dict[str, int] = field(default_factory=dict)
    total_in_window: int = 0
    window_start: str = ""
    window_end: str = ""
    query: TimelineQuery = field(default_factory=TimelineQuery)


# ─── Source-row → TimelineEvent mappers ────────────────────────────


def _coerce_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            return None
    return None


def _as_dict(row: Any) -> dict[str, Any]:
    """Convert a row-like object to a dict.

    Supports:
    - ``dict`` (returned as-is)
    - ``sqlite3.Row`` (uses ``row[k]`` indexing)
    - Pydantic v2 BaseModel (uses ``model_dump()``)
    - arbitrary objects with ``__dict__`` (last resort)
    """
    if isinstance(row, dict):
        return row
    if hasattr(row, "keys"):
        try:
            return {k: row[k] for k in row.keys()}
        except (KeyError, TypeError):
            pass
    # Pydantic v2 models
    if hasattr(row, "model_dump"):
        return row.model_dump()
    # Generic object with __dict__
    if hasattr(row, "__dict__"):
        return dict(row.__dict__)
    return {}


def _location_name(db: Database, location_id: str | None) -> str:
    if not location_id:
        return ""
    try:
        loc = db.get_location(location_id)
    except Exception:
        return ""
    return loc.name if loc else location_id


def _from_inventory_event(row: Any, db: Database) -> TimelineEvent:
    d = _as_dict(row)
    action = (d.get("action") or "").lower()
    type_map = {
        "added": TimelineEventType.INVENTORY_ADDED.value,
        "consumed": TimelineEventType.INVENTORY_CONSUMED.value,
        "moved": TimelineEventType.INVENTORY_MOVED.value,
        "adjusted": TimelineEventType.INVENTORY_ADJUSTED.value,
        "discarded": TimelineEventType.INVENTORY_DISCARDED.value,
        "status_changed": TimelineEventType.INVENTORY_STATUS.value,
    }
    location_to = d.get("location_to") or ""
    return TimelineEvent(
        event_id=str(d.get("event_id", "")),
        event_type=type_map.get(action, f"inventory.{action or 'event'}"),
        timestamp=_coerce_dt(d.get("timestamp")) or datetime.now(),
        canonical_name=d.get("canonical_name", "") or "",
        lot_id=d.get("lot_id", "") or "",
        location_id=location_to,
        location_name=_location_name(db, location_to),
        location_from=d.get("location_from"),
        location_to=location_to,
        quantity_delta=d.get("quantity_delta"),
        quantity_after=d.get("quantity_after"),
        unit=d.get("unit", "") or "",
        source=d.get("source", "") or "manual",
        user_id=d.get("user_id", "") or "",
        notes=d.get("notes", "") or "",
        raw=d,
    )


def _from_movement_event(row: Any, db: Database) -> TimelineEvent:
    d = _as_dict(row)
    to_id = d.get("to_location_id") or ""
    return TimelineEvent(
        event_id=f"mv_{d.get('movement_id', '')}",
        event_type=TimelineEventType.MOVED.value,
        timestamp=_coerce_dt(d.get("timestamp")) or datetime.now(),
        lot_id=d.get("lot_id", "") or "",
        location_id=to_id,
        location_name=_location_name(db, to_id),
        location_from=d.get("from_location_id"),
        location_to=to_id,
        source=d.get("source", "") or "manual",
        notes=f"Confidence {d.get('confidence', 1.0):.2f}" if d.get("confidence") not in (None, 1.0) else "",
        raw=d,
    )


def _from_purchase_event(row: Any, db: Database) -> TimelineEvent:
    d = _as_dict(row)
    store = d.get("store_name") or ""
    total = d.get("total_price") or 0.0
    currency = d.get("currency") or "INR"
    notes = f"Paid {currency} {total:.0f}"
    if store:
        notes += f" at {store}"
    return TimelineEvent(
        event_id=str(d.get("event_id", "")),
        event_type=TimelineEventType.PURCHASED.value,
        timestamp=_coerce_dt(d.get("timestamp")) or datetime.now(),
        canonical_name=d.get("canonical_name", "") or "",
        quantity_delta=d.get("quantity"),
        quantity_after=d.get("quantity"),
        unit=d.get("unit", "") or "",
        source=d.get("source_type", "") or "manual",
        notes=notes,
        raw=d,
    )


def _from_reconciliation_event(row: Any, db: Database) -> TimelineEvent:
    d = _as_dict(row)
    notes_parts = [f"Planned: {d.get('planned_action', '?')}", f"Actual: {d.get('actual_action', '?')}"]
    if d.get("substituted_with"):
        notes_parts.append(f"Substituted with {d.get('substituted_with')}")
    if d.get("price_paid") is not None:
        notes_parts.append(f"Paid {d.get('price_paid'):.0f}")
    return TimelineEvent(
        event_id=str(d.get("event_id", "")),
        event_type=TimelineEventType.RECONCILED.value,
        timestamp=_coerce_dt(d.get("timestamp")) or datetime.now(),
        canonical_name=d.get("canonical_name", "") or "",
        quantity_delta=d.get("quantity"),
        unit=d.get("unit", "") or "",
        source=d.get("source", "") or "manual",
        notes="; ".join(notes_parts),
        raw=d,
    )


def _from_trace(row: Any, db: Database) -> list[TimelineEvent]:
    """A trace can produce up to two events: the plan and the finalization."""
    d = _as_dict(row)
    ts = _coerce_dt(d.get("timestamp")) or datetime.now()
    user_goal = d.get("user_goal") or "agent_run"
    redacted = d.get("redacted_user_request") or ""
    human = d.get("human_confirmation") or ""
    canonical = ""
    if isinstance(d.get("proposed_tool_calls"), list) and d["proposed_tool_calls"]:
        first_call = d["proposed_tool_calls"][0] or {}
        if isinstance(first_call, dict):
            args = first_call.get("args") or {}
            if isinstance(args, dict):
                canonical = args.get("canonical_name", "") or ""
    events: list[TimelineEvent] = []
    events.append(TimelineEvent(
        event_id=f"plan_{d.get('trace_id', '')}",
        event_type=TimelineEventType.TRACE_PLAN.value,
        timestamp=ts,
        canonical_name=canonical,
        source="agent",
        notes=f"Plan: {user_goal}" + (f" — {redacted[:80]}" if redacted else ""),
        user_id=d.get("actor_id", "") or d.get("user_id", "") or "",
        raw=d,
    ))
    if human or d.get("final_response"):
        events.append(TimelineEvent(
            event_id=f"fin_{d.get('trace_id', '')}",
            event_type=TimelineEventType.TRACE_FINALIZE.value,
            timestamp=ts,
            canonical_name=canonical,
            source="agent",
            notes=human or (d.get("final_response", "")[:80] or ""),
            user_id=d.get("actor_id", "") or d.get("user_id", "") or "",
            raw=d,
        ))
    return events


def _from_preference_signal(row: Any, db: Database) -> TimelineEvent:
    d = _as_dict(row)
    return TimelineEvent(
        event_id=f"pref_{d.get('signal_id', '')}",
        event_type=TimelineEventType.PREFERENCE_LEARNED.value,
        timestamp=_coerce_dt(d.get("updated_at")) or _coerce_dt(d.get("created_at")) or datetime.now(),
        canonical_name=d.get("canonical_name", "") or "",
        source=d.get("source", "") or "observed",
        notes=f"{d.get('signal_type', '')}: {d.get('value', '')}",
        raw=d,
    )


def _from_correction_event(row: Any, db: Database) -> TimelineEvent:
    d = _as_dict(row)
    return TimelineEvent(
        event_id=f"corr_{d.get('event_id', '')}",
        event_type=TimelineEventType.CORRECTION.value,
        timestamp=_coerce_dt(d.get("timestamp")) or datetime.now(),
        canonical_name=d.get("canonical_name", "") or "",
        source=d.get("source", "") or "user_correction",
        notes=f"{d.get('correction_type', '')}: {d.get('old_value', '?')} → {d.get('new_value', '?')}",
        raw=d,
    )


def _from_price_observation(row: Any, db: Database) -> TimelineEvent:
    d = _as_dict(row)
    notes = f"₹{d.get('price', 0):.0f} / {d.get('quantity', 1)} {d.get('unit', 'unit')}"
    if d.get("store_name"):
        notes += f" @ {d.get('store_name')}"
    return TimelineEvent(
        event_id=f"price_{d.get('price_id', '')}",
        event_type=TimelineEventType.PRICE_OBSERVED.value,
        timestamp=_coerce_dt(d.get("observation_date")) or datetime.now(),
        canonical_name=d.get("canonical_name", "") or "",
        unit=d.get("unit", "") or "",
        source="price_memory",
        notes=notes,
        raw=d,
    )


def _from_negative_memory(row: dict, db: Database) -> TimelineEvent:
    return TimelineEvent(
        event_id=f"negmem_{row.get('memory_id', '')}",
        event_type=TimelineEventType.NEGATIVE_MEMORY.value,
        timestamp=_coerce_dt(row.get("confirmed_at")) or datetime.now(),
        lot_id=row.get("lot_id", "") or "",
        location_id=row.get("location_id", "") or "",
        location_name=row.get("location_name", "") or _location_name(db, row.get("location_id")),
        source=row.get("source", "") or "user_feedback",
        notes=f"Confirmed not at {row.get('location_name') or row.get('location_id')}",
        raw=dict(row),
    )


# ─── Pure aggregator ───────────────────────────────────────────────


def merge_events(
    *,
    inventory_events: Iterable[Any] = (),
    movement_events: Iterable[Any] = (),
    purchase_events: Iterable[Any] = (),
    reconciliation_events: Iterable[Any] = (),
    traces: Iterable[Any] = (),
    preference_signals: Iterable[Any] = (),
    correction_events: Iterable[Any] = (),
    price_observations: Iterable[Any] = (),
    negative_memory: Iterable[dict] = (),
    db: Database | None = None,
) -> list[TimelineEvent]:
    """Normalize all event sources into a single list of TimelineEvent.

    ``db`` is only used to resolve location_id → location_name. Pass
    None if you have already-resolved names in the rows.
    """
    db = db or _NullDB()
    out: list[TimelineEvent] = []
    for row in inventory_events:
        out.append(_from_inventory_event(row, db))
    for row in movement_events:
        out.append(_from_movement_event(row, db))
    for row in purchase_events:
        out.append(_from_purchase_event(row, db))
    for row in reconciliation_events:
        out.append(_from_reconciliation_event(row, db))
    for row in traces:
        out.extend(_from_trace(row, db))
    for row in preference_signals:
        out.append(_from_preference_signal(row, db))
    for row in correction_events:
        out.append(_from_correction_event(row, db))
    for row in price_observations:
        out.append(_from_price_observation(row, db))
    for row in negative_memory:
        out.append(_from_negative_memory(row, db))
    return out


def filter_events(
    events: list[TimelineEvent],
    q: TimelineQuery,
) -> list[TimelineEvent]:
    """Apply a TimelineQuery to a list of events."""
    since = q.since.replace(tzinfo=None) if q.since and q.since.tzinfo else q.since
    until = q.until.replace(tzinfo=None) if q.until and q.until.tzinfo else q.until
    out: list[TimelineEvent] = []
    for ev in events:
        if q.canonical_name and ev.canonical_name.lower() != q.canonical_name.lower():
            continue
        if q.lot_id and ev.lot_id != q.lot_id:
            continue
        # Location filter: match against any of the event's location fields.
        if q.location_id and not any(
            x == q.location_id
            for x in (ev.location_id, ev.location_from, ev.location_to)
        ):
            continue
        if q.event_types and ev.event_type not in q.event_types:
            continue
        if since and ev.timestamp < since:
            continue
        if until and ev.timestamp >= until:
            continue
        out.append(ev)
    out.sort(key=lambda e: e.timestamp, reverse=(q.order != "asc"))
    return out[: q.limit]


def bucket_by_day(events: list[TimelineEvent]) -> list[TimelineBucket]:
    """Group events into YYYY-MM-DD buckets, preserving event order."""
    grouped: dict[str, list[TimelineEvent]] = defaultdict(list)
    for ev in events:
        grouped[ev.timestamp.strftime("%Y-%m-%d")].append(ev)
    return [
        TimelineBucket(date=k, events=v)
        for k, v in sorted(grouped.items(), reverse=True)
    ]


def summarize(events: list[TimelineEvent], q: TimelineQuery) -> TimelineResult:
    by_type: Counter[str] = Counter()
    by_location: Counter[str] = Counter()
    by_canonical: Counter[str] = Counter()
    for ev in events:
        by_type[ev.event_type] += 1
        if ev.location_id:
            by_location[ev.location_id] += 1
        if ev.canonical_name:
            by_canonical[ev.canonical_name] += 1
    window_start = events[0].timestamp.isoformat() if events else ""
    window_end = events[-1].timestamp.isoformat() if events else ""
    return TimelineResult(
        events=events,
        buckets=bucket_by_day(events),
        by_type=dict(by_type.most_common()),
        by_location=dict(by_location.most_common()),
        by_canonical=dict(by_canonical.most_common(20)),
        total_in_window=len(events),
        window_start=window_start,
        window_end=window_end,
        query=q,
    )


# ─── NullDB: lets merge_events work without a real DB ──────────────


class _NullDB:
    """Stand-in for Database when callers only pass fully-resolved rows."""
    def get_location(self, location_id: str):
        return None


# ─── Service facade ────────────────────────────────────────────────


class TimelineService:
    """Convenience facade that fetches and aggregates events.

    The underlying :func:`merge_events` and :func:`filter_events` are
    pure and can be tested without a database. This class adds the
    "fetch from the active database" glue so screens can call
    ``TimelineService(db).query(TimelineQuery(canonical_name=...))``
    in one line.
    """

    def __init__(self, db: Database):
        self.db = db

    def query(self, q: TimelineQuery | None = None, user_id: str = "") -> TimelineResult:
        q = q or TimelineQuery()
        since_iso = q.since.isoformat() if q.since else None
        until_iso = q.until.isoformat() if q.until else None
        # Fetch ceiling = max(limit * 4, 200) so filtering has headroom.
        fetch_limit = max(q.limit * 4, 200)

        # Inventory events
        inv_events = self.db.get_inventory_events(
            canonical_name=q.canonical_name,
            lot_id=q.lot_id,
            limit=fetch_limit,
            user_id=user_id,
            since=since_iso,
            until=until_iso,
        )
        # Movement events
        if q.lot_id:
            mv_events = self.db.get_movements_for_lot(q.lot_id)
        else:
            mv_events = self.db.get_movements_in_window(
                user_id=user_id,
                since=since_iso,
                until=until_iso,
                limit=fetch_limit,
            )
        # Purchase events
        purchase_events = self.db.get_purchase_events(limit=fetch_limit, user_id=user_id)
        # Reconciliation events
        recon_events = self.db.get_reconciliation_events(
            canonical_name=q.canonical_name or None,
            limit=fetch_limit,
            user_id=user_id,
        )
        # Traces
        traces = self.db.get_traces(limit=fetch_limit, user_id=user_id)
        # Preference signals
        pref_events = self.db.get_preference_signals(
            canonical_name=q.canonical_name or None,
            user_id=user_id,
        )
        # Price observations
        if q.canonical_name:
            price_events = self.db.get_price_history(q.canonical_name, user_id=user_id)
        else:
            price_events = self.db.get_price_history("", user_id=user_id)[:fetch_limit]

        merged = merge_events(
            inventory_events=inv_events,
            movement_events=mv_events,
            purchase_events=purchase_events,
            reconciliation_events=recon_events,
            traces=traces,
            preference_signals=pref_events,
            price_observations=price_events,
            db=self.db,
        )
        filtered = filter_events(merged, q)
        return summarize(filtered, q)


# ─── HTML rendering ────────────────────────────────────────────────


def event_label(event_type: str) -> tuple[str, str]:
    """Return (label, emoji) for an event type, with safe fallback."""
    if event_type in _EVENT_LABELS:
        return _EVENT_LABELS[event_type]
    fallback = event_type.replace(".", " ").replace("_", " ").title()
    return (fallback, "•")


def render_timeline_html(result: TimelineResult, *, max_buckets: int = 14) -> str:
    """Render a TimelineResult as a small HTML block.

    Sections:
    1. Headline counts (total, by type, by location).
    2. Day-bucketed event list.
    """
    if not result.events:
        return (
            "<div class='home-card' style='text-align:center;padding:16px;color:var(--text-dim);'>"
            "No events in the selected window."
            "</div>"
        )

    parts: list[str] = []
    parts.append("<div class='al-block'>")
    parts.append(
        f"<div class='al-headline'><strong>{result.total_in_window}</strong> events"
        + (f" between <strong>{escape(result.window_start[:10])}</strong> and <strong>{escape(result.window_end[:10])}</strong>" if result.window_start else "")
        + "</div>"
    )

    # By-type chips
    if result.by_type:
        parts.append("<div class='al-section-h'>By type</div>")
        chips = []
        for t, count in list(result.by_type.items())[:10]:
            label, emoji = event_label(t)
            chips.append(
                f"<span class='al-chip'>{emoji} {escape(label)} <span class='al-chip-n'>{count}</span></span>"
            )
        parts.append(f"<div class='al-chips'>{''.join(chips)}</div>")

    # By-location chips
    if result.by_location:
        parts.append("<div class='al-section-h'>By location</div>")
        chips = []
        # Resolve location names (best effort, fall back to id)
        for lid, count in list(result.by_location.items())[:8]:
            name = lid
            try:
                loc = result.query and None
            except Exception:
                loc = None
            chips.append(
                f"<span class='al-chip'>{escape(name)} <span class='al-chip-n'>{count}</span></span>"
            )
        parts.append(f"<div class='al-chips'>{''.join(chips)}</div>")

    # Day-bucketed timeline
    if result.buckets:
        parts.append("<div class='al-section-h'>Recent activity</div>")
        parts.append("<ul class='al-timeline'>")
        for bucket in result.buckets[:max_buckets]:
            parts.append(
                f"<li class='al-tl-day'><span class='al-tl-date'>{escape(bucket.date)}</span>"
                f"<span class='al-tl-count'>{len(bucket.events)} event(s)</span></li>"
            )
            for ev in bucket.events:
                label, emoji = event_label(ev.event_type)
                title_bits = [f"{emoji} {escape(label)}"]
                if ev.canonical_name:
                    title_bits.append(f"<strong>{escape(ev.canonical_name)}</strong>")
                if ev.location_name:
                    title_bits.append(f"@ {escape(ev.location_name)}")
                if ev.notes:
                    title_bits.append(f"— {escape(ev.notes)}")
                ts_str = ev.timestamp.strftime("%H:%M") if ev.timestamp else ""
                parts.append(
                    f"<li class='al-tl-event'><span class='al-tl-time'>{escape(ts_str)}</span>"
                    f"<span class='al-tl-body'>{' '.join(title_bits)}</span></li>"
                )
        parts.append("</ul>")

    parts.append("</div>")
    return "".join(parts)


__all__ = [
    "TimelineEvent",
    "TimelineEventType",
    "TimelineBucket",
    "TimelineQuery",
    "TimelineResult",
    "TimelineService",
    "merge_events",
    "filter_events",
    "bucket_by_day",
    "summarize",
    "event_label",
    "render_timeline_html",
]
