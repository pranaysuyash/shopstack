"""Decision types — pure data structures for the ShopStack decision engine.

No HTML rendering, no database access, no provider calls.
Every ShopStack decision (buy / skip / use-soon / compare / etc.) uses
DecisionResult as its canonical representation.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from shopstack.schemas.models import (  # noqa: F401 — canonical types
    DecisionEvidence,
    DecisionResult,
    DecisionSet,
    DecisionWarning,
    FreshnessStatus,
    _ACTION_COLORS,
    _ACTION_ICONS,
)

# Keep DECISION_COLORS / DECISION_ICONS as module-level exports for callers.
DECISION_COLORS = _ACTION_COLORS
DECISION_ICONS = _ACTION_ICONS


class Decision(str, Enum):
    BUY = "buy"
    SKIP = "skip"
    USE_SOON = "use_soon"
    OPTIONAL = "optional"
    COMPARE = "compare"
    CONFIRM = "confirm"
    WATCH = "watch"


# ── Legacy aliases for backward compatibility with existing tests ──────────
# These map the old Decision enum values to the new DecisionResult.action values.
# Used by classify_all() and _classify() when building DecisionResult items.
ACTION_MAP: dict[str, str] = {
    "buy": "buy",
    "skip": "skip",
    "use_soon": "use_soon",
    "optional": "optional",
    "compare": "compare",
    "confirm": "wait",        # confirm → wait in new schema
    "watch": "wait",          # watch → wait in new schema
}
