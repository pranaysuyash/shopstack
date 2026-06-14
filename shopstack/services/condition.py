"""Condition / damage detection service.

Records and aggregates observations of damaged, worn, or
otherwise-noteworthy items. The service does NOT depend on a vision
model — it can ingest user-reported issues directly, and it can
also be called from :mod:`shopstack.services.shelf_intelligence`
to add model-derived condition events.

The detection layer is intentionally a *heuristic scaffold*:

- The heavy lifting ("is this bottle actually leaking?") is left
  to the upstream vision model — the service just records what
  the model reports.
- For user reports (the common case), the user describes the
  issue and the service records it.
- The aggregation layer (per-lot rollup, repair inbox) is the
  product surface; the detection layer is plumbing.

First principles:
- Severity drives the inbox; kind is metadata.
- Repetition matters: a bottle that leaks 3 times in a week is a
  different problem from one that has leaked once.
- The user is the trust gate: ``user_confirmed`` is what makes an
  event "real" for any automatic action.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Iterable

from shopstack.persistence.database import Database
from shopstack.schemas.condition import (
    ConditionAction,
    ConditionAggregate,
    ConditionEvent,
    ConditionKind,
    ConditionSeverity,
    RepairInboxItem,
)
from shopstack.schemas.models import InventoryLot, HouseholdLocation

logger = logging.getLogger(__name__)


# Severity ladder — higher index = more severe
SEVERITY_ORDER: list[ConditionSeverity] = [
    ConditionSeverity.COSMETIC,
    ConditionSeverity.WORN,
    ConditionSeverity.DAMAGED,
    ConditionSeverity.BROKEN,
    ConditionSeverity.SPOILED,
]


# Recommended action per severity. Cosmetic → monitor; worn →
# log/replace; damaged → repair; broken → replace; spoiled → discard.
SEVERITY_TO_ACTION: dict[ConditionSeverity, ConditionAction] = {
    ConditionSeverity.COSMETIC: ConditionAction.MONITOR,
    ConditionSeverity.WORN: ConditionAction.MONITOR,
    ConditionSeverity.DAMAGED: ConditionAction.REPAIR,
    ConditionSeverity.BROKEN: ConditionAction.REPLACE,
    ConditionSeverity.SPOILED: ConditionAction.DISCARD,
}


# ─── Detection scaffold ──────────────────────────────────────────


def _image_heuristic_score(image_path: str | None) -> dict[str, Any]:
    """A pluggable heuristic for image-based detection.

    In a real deployment this would call the vision provider with a
    prompt like "Describe the condition of each item in this image.
    Note any damage, leaks, mold, or wear." For now we return a
    neutral no-op so the pipeline integration is testable.

    Returns:
        A dict with keys ``kind``, ``severity``, ``confidence``,
        ``description``. The caller (an upstream vision step)
        fills in the actual values.
    """
    if not image_path:
        return {"kind": ConditionKind.OTHER.value, "severity": ConditionSeverity.WORN.value,
                "confidence": 0.0, "description": ""}
    # No real detection here — upstream caller passes the result in.
    return {"kind": ConditionKind.OTHER.value, "severity": ConditionSeverity.WORN.value,
            "confidence": 0.0, "description": ""}


def analyze_image_for_damage(
    image_path: str | None,
    lot: InventoryLot | None = None,
    user_id: str = "",
) -> ConditionEvent | None:
    """Record a vision-derived condition event for a lot.

    Args:
        image_path: Optional path to an image of the lot.
        lot: Optional InventoryLot. When provided, ``canonical_name``
            is taken from the lot; otherwise the caller must pass it
            via the returned event.
        user_id: Household scope.

    Returns:
        A :class:`ConditionEvent` with the model's best guess, or
        None if the image is missing or the model had no signal.
    """
    if not image_path:
        return None
    score = _image_heuristic_score(image_path)
    if score.get("confidence", 0.0) <= 0.0:
        return None
    return ConditionEvent(
        lot_id=lot.lot_id if lot else "",
        canonical_name=lot.canonical_name if lot else "",
        kind=ConditionKind(score.get("kind", "other")),
        severity=ConditionSeverity(score.get("severity", "worn")),
        confidence=score.get("confidence", 0.0),
        description=score.get("description", ""),
        source="vision_model",
        image_path=image_path,
        user_confirmed=False,
        user_id=user_id,
    )


# ─── Recording ────────────────────────────────────────────────────


def record_condition_event(
    db: Database,
    lot_id: str,
    kind: str | ConditionKind,
    severity: str | ConditionSeverity,
    description: str = "",
    confidence: float = 0.7,
    source: str = "user_report",
    image_path: str | None = None,
    canonical_name: str = "",
    user_confirmed: bool = True,  # user reports are confirmed by default
    user_id: str = "",
) -> str:
    """Persist a single condition event to the DB.

    Returns:
        The generated event_id.

    Raises:
        ValueError: if ``kind`` or ``severity`` is not a valid enum value.
    """
    if isinstance(kind, str):
        kind = _coerce_kind(kind)
    if isinstance(severity, str):
        severity = _coerce_severity(severity)
    return db.add_condition_event(
        lot_id=lot_id,
        kind=kind.value,
        severity=severity.value,
        canonical_name=canonical_name,
        confidence=confidence,
        description=description,
        source=source,
        image_path=image_path,
        user_confirmed=user_confirmed,
        user_id=user_id,
    )


def _coerce_kind(value: str) -> ConditionKind:
    """Parse a string into a ConditionKind enum, case-insensitive."""
    v = (value or "").strip().lower().replace(" ", "_")
    for kind in ConditionKind:
        if kind.value == v:
            return kind
    raise ValueError(f"Unknown condition kind: {value!r}")


def _coerce_severity(value: str) -> ConditionSeverity:
    """Parse a string into a ConditionSeverity enum, case-insensitive."""
    v = (value or "").strip().lower()
    for sev in ConditionSeverity:
        if sev.value == v:
            return sev
    raise ValueError(f"Unknown condition severity: {value!r}")


# ─── Aggregation ─────────────────────────────────────────────────


def _row_to_event(row: dict) -> ConditionEvent:
    """Convert a DB row to a ConditionEvent."""
    return ConditionEvent(
        event_id=row["event_id"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
        lot_id=row["lot_id"],
        canonical_name=row.get("canonical_name", "") or "",
        kind=ConditionKind(row.get("kind", "other") or "other"),
        severity=ConditionSeverity(row.get("severity", "worn") or "worn"),
        confidence=float(row.get("confidence", 0.5) or 0.5),
        description=row.get("description", "") or "",
        source=row.get("source", "user_report") or "user_report",
        image_path=row.get("image_path"),
        user_confirmed=bool(row.get("user_confirmed", 0)),
        user_id=row.get("user_id", "") or "",
    )


def get_lot_condition(
    db: Database,
    lot_id: str,
    include_closed: bool = True,
) -> ConditionAggregate:
    """Aggregate all condition events for a single lot."""
    rows = db.get_condition_events_for_lot(lot_id, include_closed=include_closed)
    events = [_row_to_event(r) for r in rows]
    open_events: list[ConditionEvent] = []
    closed_events: list[ConditionEvent] = []
    for r, ev in zip(rows, events):
        if r.get("closed_at"):
            closed_events.append(ev)
        else:
            open_events.append(ev)
    if not events:
        return ConditionAggregate(
            lot_id=lot_id,
            canonical_name="",
        )
    # Sort newest first
    events_sorted = sorted(events, key=lambda e: e.timestamp, reverse=True)
    severities = [e.severity for e in events]
    kinds = [e.kind for e in events]
    highest = max(severities, key=lambda s: SEVERITY_ORDER.index(s))
    dominant_kind_counts = Counter(kinds)
    dominant_kind = dominant_kind_counts.most_common(1)[0][0]
    return ConditionAggregate(
        lot_id=lot_id,
        canonical_name=events_sorted[0].canonical_name,
        open_events=open_events,
        closed_events=closed_events,
        last_seen_at=events_sorted[0].timestamp,
        first_seen_at=events_sorted[-1].timestamp,
        occurrences=len(events),
        highest_severity=highest,
        dominant_kind=dominant_kind,
        recommended_action=SEVERITY_TO_ACTION[highest],
        user_confirmed=any(e.user_confirmed for e in events),
    )


def _is_closed_row(row: dict) -> bool:
    return bool(row.get("closed_at"))


# ─── Repair inbox ────────────────────────────────────────────────


def get_repair_inbox(
    db: Database,
    severity: ConditionSeverity | None = None,
    limit: int = 50,
) -> list[RepairInboxItem]:
    """Return open condition issues, sorted by severity then recency.

    The inbox is the operator's view: which lots need attention,
    ranked so critical items surface first.
    """
    severity_value = severity.value if severity else None
    rows = db.get_open_condition_events(severity=severity_value, limit=limit * 4)

    # Group by lot
    by_lot: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_lot[row["lot_id"]].append(row)

    locations: dict[str, HouseholdLocation] = {loc.location_id: loc for loc in db.get_locations()}
    lots: dict[str, InventoryLot] = {lot.lot_id: lot for lot in db.get_inventory()}

    items: list[RepairInboxItem] = []
    for lot_id, lot_rows in by_lot.items():
        events = [_row_to_event(r) for r in lot_rows]
        events.sort(key=lambda e: e.timestamp, reverse=True)
        severities = [e.severity for e in events]
        kinds = [e.kind for e in events]
        highest = max(severities, key=lambda s: SEVERITY_ORDER.index(s))
        dominant_kind_counts = Counter(kinds)
        dominant_kind = dominant_kind_counts.most_common(1)[0][0]
        lot = lots.get(lot_id)
        loc = locations.get(lot.storage_location_id) if lot else None
        items.append(RepairInboxItem(
            lot_id=lot_id,
            canonical_name=events[0].canonical_name or (lot.canonical_name if lot else ""),
            display_name=lot.display_name if lot else "",
            location_id=lot.storage_location_id if lot else "",
            location_name=loc.name if loc else "",
            severity=highest,
            dominant_kind=dominant_kind,
            occurrences=len(events),
            last_seen_at=events[0].timestamp,
            first_seen_at=events[-1].timestamp,
            recommended_action=SEVERITY_TO_ACTION[highest],
            latest_description=events[0].description,
            user_confirmed=any(e.user_confirmed for e in events),
            pending_user_confirmation=sum(1 for e in events if not e.user_confirmed),
        ))

    # Sort by severity (most severe first), then most-recent
    items.sort(key=lambda it: (
        -SEVERITY_ORDER.index(it.severity),
        -(it.last_seen_at.timestamp() if it.last_seen_at else 0),
    ))
    return items[:limit]


__all__ = [
    "ConditionEvent",
    "ConditionKind",
    "ConditionSeverity",
    "ConditionAction",
    "ConditionAggregate",
    "RepairInboxItem",
    "SEVERITY_ORDER",
    "SEVERITY_TO_ACTION",
    "analyze_image_for_damage",
    "record_condition_event",
    "get_lot_condition",
    "get_repair_inbox",
    "_coerce_kind",
    "_coerce_severity",
]
