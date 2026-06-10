"""Data freshness service — classifies freshness of market data and inventory.

The review (§5.8) identifies this as a dedicated service needed for trust:
every recommendation should honestly communicate data age.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# ── Thresholds ──────────────────────────────────────────────────────────────
LIVE_MAX_DAYS = 0       # captured today
RECENT_MAX_DAYS = 1     # within 24h
STALE_THRESHOLD = 2     # older than 24h


@dataclass
class FreshnessReport:
    """Structured freshness assessment for any data source."""
    status: str          # FreshnessStatus value: live / recent / stale / unknown
    age_days: int | None  # None if unknown
    label: str           # human-readable: "Snapshot from 6 Jun 2026"
    captured_at: str     # ISO date string
    is_stale: bool       # convenience boolean
    warning: str         # UI copy if stale, empty otherwise

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "age_days": self.age_days,
            "label": self.label,
            "captured_at": self.captured_at,
            "is_stale": self.is_stale,
            "warning": self.warning,
        }


def _parse_date(value: str) -> date | None:
    """Parse an ISO date string, returning None on failure."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def classify_freshness(captured_at: str, today: date | None = None) -> FreshnessReport:
    """Classify data freshness from a captured_at ISO date string.

    This is the canonical freshness classifier for market snapshots,
    price observations, and any time-stamped data.

    Args:
        captured_at: ISO date string (e.g. "2026-06-06" or "2026-06-06T14:30:00").
        today: Override for testing; defaults to date.today().

    Returns:
        FreshnessReport with status, age, label, and UI-ready warning copy.
    """
    current = today or date.today()
    captured = _parse_date(captured_at)

    if captured is None:
        return FreshnessReport(
            status="unknown",
            age_days=None,
            label=f"Data date unclear: {captured_at or 'unknown'}",
            captured_at=captured_at,
            is_stale=True,
            warning="Data freshness unknown — prices and availability may have changed.",
        )

    age_days = (current - captured).days

    if age_days < 0:
        # Future date — likely clock skew
        return FreshnessReport(
            status="unknown",
            age_days=age_days,
            label=f"Data from future ({captured_at})",
            captured_at=captured_at,
            is_stale=True,
            warning="Data timestamp appears incorrect.",
        )

    if age_days <= LIVE_MAX_DAYS:
        status = "live"
        label = f"Today's data ({captured_at})"
        warning = ""
    elif age_days <= RECENT_MAX_DAYS:
        status = "recent"
        label = f"Captured yesterday ({captured_at})"
        warning = ""
    elif age_days <= STALE_THRESHOLD:
        status = "stale"
        label = f"Captured {age_days} days ago ({captured_at})"
        warning = (
            f"Prices and availability from {age_days} days ago — "
            "verify before checkout."
        )
    else:
        status = "stale"
        label = f"Captured {age_days} days ago ({captured_at})"
        warning = (
            f"Market data is {age_days} days old. "
            "Prices and availability may have changed significantly."
        )

    return FreshnessReport(
        status=status,
        age_days=age_days,
        label=label,
        captured_at=captured_at,
        is_stale=status == "stale",
        warning=warning,
    )


def classify_snapshot_freshness(snapshot, today: date | None = None) -> FreshnessReport:
    """Classify freshness for a MarketSnapshot object.

    Convenience wrapper that reads captured_at from the snapshot.
    """
    captured = getattr(snapshot, "captured_at", "")
    return classify_freshness(captured, today)


def inventory_freshness_label(
    purchase_date: date | None,
    shelf_life_days: int = 0,
    today: date | None = None,
) -> FreshnessReport:
    """Assess inventory item freshness from purchase date and shelf life.

    Returns a FreshnessReport describing whether the item is still fresh,
    approaching expiry, or past expected use-by date.
    """
    current = today or date.today()

    if purchase_date is None:
        return FreshnessReport(
            status="unknown",
            age_days=None,
            label="Purchase date unknown",
            captured_at="",
            is_stale=False,
            warning="Item freshness uncertain — no purchase date recorded.",
        )

    age_days = (current - purchase_date).days

    if shelf_life_days <= 0:
        return FreshnessReport(
            status="recent" if age_days <= 1 else "stale",
            age_days=age_days,
            label=f"Bought {age_days} days ago",
            captured_at=purchase_date.isoformat(),
            is_stale=age_days > 1,
            warning="",
        )

    remaining = shelf_life_days - age_days
    if remaining > 2:
        status = "live"
        warning = ""
    elif remaining > 0:
        status = "recent"
        warning = f"Use within {remaining} days for best freshness."
    elif remaining == 0:
        status = "stale"
        warning = "Use today — at end of expected shelf life."
    else:
        status = "stale"
        warning = f"Past expected shelf life by {abs(remaining)} days."

    label = f"Bought {age_days} days ago ({remaining} days remaining)" if remaining >= 0 else f"Bought {age_days} days ago (past shelf life)"

    return FreshnessReport(
        status=status,
        age_days=age_days,
        label=label,
        captured_at=purchase_date.isoformat(),
        is_stale=status == "stale",
        warning=warning,
    )


def inventory_confidence(
    purchase_date: date | None,
    shelf_life_days: int = 0,
    last_confirmed: date | None = None,
    today: date | None = None,
) -> float:
    """Compute inventory confidence score based on age and freshness.

    The review (§4.1) identifies confidence as essential for reliable inventory:

      | Source                       | Confidence    |
      | ---------------------------- | ------------- |
      | Manual user entry            | high          |
      | Receipt extraction           | high/medium   |
      | Image/fridge scan            | medium/low    |
      | Old inferred inventory       | low           |
      | Planned but unconfirmed cart | not inventory |

    This function computes a confidence decay curve based on how long ago the
    item was purchased or last confirmed, relative to its shelf life.

    Returns 0.0–1.0 where:
      - 1.0 = just purchased / manually confirmed
      - 0.8+ = within shelf life, recently confirmed
      - 0.5–0.8 = approaching expiry, needs confirmation
      - 0.2–0.5 = past expected shelf life, likely spoiled
      - <0.2 = very old, should prompt confirmation
    """
    current = today or date.today()

    if purchase_date is None and last_confirmed is None:
        return 0.3  # low confidence — entirely unknown provenance

    # Use most recent of purchase_date and last_confirmed
    ref_date = purchase_date or last_confirmed or current
    if last_confirmed and purchase_date:
        ref_date = max(last_confirmed, purchase_date)
    elif last_confirmed:
        ref_date = last_confirmed

    age_days = (current - ref_date).days

    if age_days < 0:
        return 1.0  # future date? trust

    if shelf_life_days <= 0:
        # No shelf life info — use generic decay curve
        if age_days <= 1:
            return 0.95
        if age_days <= 3:
            return 0.85
        if age_days <= 7:
            return 0.7
        if age_days <= 14:
            return 0.5
        if age_days <= 30:
            return 0.3
        return 0.15

    # Shelf-life-based decay
    fraction_consumed = age_days / shelf_life_days if shelf_life_days > 0 else 99

    if fraction_consumed <= 0.2:
        return 0.95
    if fraction_consumed <= 0.5:
        return 0.85
    if fraction_consumed <= 0.8:
        return 0.65
    if fraction_consumed <= 1.0:
        return 0.45
    # Past shelf life
    over_by = age_days - shelf_life_days
    if over_by <= 3:
        return 0.3
    if over_by <= 7:
        return 0.2
    return 0.1


def needs_confirmation(confidence: float, threshold: float = 0.4) -> bool:
    """Returns True if an inventory item's confidence is below threshold and needs user confirmation.

    The review: "You bought coriander 7 days ago. It may be gone or spoiled. Confirm?"
    """
    return confidence < threshold


def confirmation_prompt(
    canonical_name: str,
    display_name: str,
    confidence: float,
    purchase_date: date | None = None,
    quantity: float = 0.0,
    unit: str = "unit",
) -> str:
    """Generate a human-readable confirmation prompt for low-confidence inventory."""
    if confidence >= 0.4:
        return ""

    if purchase_date is None:
        return f"Do you still have {display_name}? No purchase date recorded."

    age_days = (date.today() - purchase_date).days
    if age_days <= 1:
        return ""  # too recent to need confirmation

    if confidence < 0.2:
        return f"Has {display_name} been used or discarded? It was purchased {age_days} days ago."
    return f"Do you still have {display_name} ({quantity} {unit})? It was purchased {age_days} days ago."
