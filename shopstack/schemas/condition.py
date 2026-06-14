"""Condition / damage detection schema.

First principles:

1. **The user has finite attention.** They do not need to know about
   a crushed box of cereal, but they DO need to know about a leaking
   detergent bottle. Severity is the gate, not the kind of damage.

2. **Some damage is "fix it now"** (leak, broken glass, spoiled
   food, expiring medicine) vs **"log for later"** (worn clothes,
   faded labels). The schema encodes this with a
   :class:`ConditionSeverity` ladder and a
   :class:`ConditionAction` recommendation per severity.

3. **Condition events are rare per item.** A simple append-only log
   is sufficient — no state machine, no transitions, no
   reconciliation. The aggregate is a derived view.

4. **Detection is best-effort.** Vision models mis-classify. The
   schema records *what was seen* and lets the user confirm or
   correct via the repair inbox. The "user_confirmed" flag is the
   trust gate for any automatic action.

5. **Repetition matters.** A bottle that's been "leaking" 3 times
   in a week is a different problem from one that's been leaking
   for a year and we still haven't thrown it out. ``occurrences``
   and ``last_seen_at`` capture this without modelling state.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────────


class ConditionKind(str, Enum):
    """What kind of condition issue was observed."""
    PHYSICAL_DAMAGE = "physical_damage"   # dented, cracked, torn
    LIQUID_LEAK = "liquid_leak"           # leaking, oozing, wet
    EXPIRY_RISK = "expiry_risk"           # past or near expiry
    WEAR_TEAR = "wear_tear"               # worn, faded, frayed
    PACKAGING_DAMAGE = "packaging_damage" # box crushed, seal broken
    VISUAL_CHANGE = "visual_change"       # mold, discoloration, color shift
    OTHER = "other"


class ConditionSeverity(str, Enum):
    """How urgent is the issue.

    The ladder matters for the repair inbox: critical → use-soon,
    moderate → log for next shopping trip, cosmetic → ignore unless
    the user wants to track.
    """
    COSMETIC = "cosmetic"  # looks rough, no impact on use
    WORN = "worn"          # usable but visibly degraded
    DAMAGED = "damaged"    # partially unusable or risky
    BROKEN = "broken"      # fully unusable
    SPOILED = "spoiled"    # health/safety risk (food, medicine)


class ConditionAction(str, Enum):
    """What the system recommends the user do."""
    REPLACE = "replace"           # buy a new one
    REPAIR = "repair"             # fix it (Task 4's repair inbox)
    DISCARD = "discard"           # throw it out
    USE_SOON = "use_soon"         # consume before it gets worse
    MONITOR = "monitor"           # watch; log if it recurs
    NONE = "none"                 # no action recommended


# ─── Per-event record ────────────────────────────────────────────


class ConditionEvent(BaseModel):
    """A single observation of a condition issue.

    Each row is one observation. The lot-level "what's the current
    condition" view is derived from these via aggregation.
    """
    event_id: str = Field(default_factory=lambda: f"cond_{datetime.now().timestamp():.0f}_{id(object()):x}")
    timestamp: datetime = Field(default_factory=datetime.now)
    lot_id: str
    canonical_name: str = ""
    kind: ConditionKind = ConditionKind.OTHER
    severity: ConditionSeverity = ConditionSeverity.WORN
    confidence: float = 0.5
    description: str = ""
    source: str = "user_report"  # user_report | vision_model | shelf_scan | other
    image_path: str | None = None
    user_confirmed: bool = False  # user has seen and accepted this
    user_id: str = ""


# ─── Per-lot aggregate ───────────────────────────────────────────


class ConditionAggregate(BaseModel):
    """The current condition state of a single lot, derived from events.

    ``last_seen_at`` is the most recent observation. ``occurrences``
    is the total count in the active window. The recommended action
    is the highest-severity action across all open events.
    """
    lot_id: str
    canonical_name: str
    open_events: list[ConditionEvent] = Field(default_factory=list)
    closed_events: list[ConditionEvent] = Field(default_factory=list)
    last_seen_at: datetime | None = None
    first_seen_at: datetime | None = None
    occurrences: int = 0
    highest_severity: ConditionSeverity = ConditionSeverity.COSMETIC
    dominant_kind: ConditionKind = ConditionKind.OTHER
    recommended_action: ConditionAction = ConditionAction.NONE
    user_confirmed: bool = False  # any event user has accepted

    @property
    def has_open_issue(self) -> bool:
        return bool(self.open_events)


# ─── Repair inbox item ───────────────────────────────────────────


class RepairInboxItem(BaseModel):
    """A single item in the repair inbox.

    The inbox is the *operator's* view: which lots need attention,
    sorted by severity and recency.
    """
    lot_id: str
    canonical_name: str
    display_name: str = ""
    location_id: str = ""
    location_name: str = ""
    severity: ConditionSeverity
    dominant_kind: ConditionKind
    occurrences: int
    last_seen_at: datetime
    first_seen_at: datetime
    recommended_action: ConditionAction
    latest_description: str = ""
    user_confirmed: bool
    pending_user_confirmation: int = 0  # how many events await user action


__all__ = [
    "ConditionKind",
    "ConditionSeverity",
    "ConditionAction",
    "ConditionEvent",
    "ConditionAggregate",
    "RepairInboxItem",
]
