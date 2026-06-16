"""Recurring shopping plan — "what should I buy based on my rhythm?".

**Why this exists (motto_v3 §0 first-principles + §0.14 product reality):**

Every household has a shopping rhythm. Milk every 3 days, rice
every 14, oil every 30. ShopStack already detects this rhythm
via ``shopstack.decisions.detect_purchase_cadence``. The
data exists. The product gap is that it's NOT surfaced
anywhere — neither the dashboard nor the Trips tab shows the
user "based on your rhythm, you should buy X today."

This module is the smallest first-principles fix:

  1. ``build_recurring_shopping_plan(db, user_id, window_days=3)``
     takes the existing cadence dict + the most recent
     purchase event per item, and returns a list of
     ``DecisionResult`` objects (action=buy) for items that
     are due within ``window_days``.

  2. Each ``DecisionResult`` has the structured
     ``reasons: list[str]`` + ``evidence: list[DecisionEvidence]``
     + the right ``confidence`` — so the existing
     explainability service (Pass 18) and the Why? toggle
     (Pass 19) automatically work.

  3. The output is mode-portable: the CLI prints it, the HTTP
     endpoint returns it, the dashboard renders it as
     decision cards (with Why? toggles).

**Why ``DecisionResult`` (not a new type)?**

The "this item is due in your rhythm" signal is a
*decision*: the system is telling the user to buy X. The
existing ``DecisionResult`` schema already models this
(``action=buy``, ``confidence``, ``reasons``, ``evidence``).
Reusing it means:

  - The Why? toggle works out of the box.
  - The CLI ``explain`` subcommand works on the result.
  - The dashboard's "Today" panel already renders these.

No new type, no new renderer — just a new pure function that
produces a list of the existing type.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from shopstack.schemas.models import DecisionEvidence, DecisionResult
from shopstack.decisions import detect_purchase_cadence

logger = logging.getLogger(__name__)


# ── Defaults ────────────────────────────────────────────────────────


# Items with avg_interval_days shorter than this are considered
# "active rhythm" (the user is buying consistently). Items
# with longer intervals are excluded — they're not really
# "recurring shopping" in the user-perceivable sense.
MIN_INTERVAL_DAYS = 1.0
MAX_INTERVAL_DAYS = 60.0

# Items with at least this many purchase events are considered
# a reliable rhythm (not a one-off purchase that happened to
# repeat).
MIN_PURCHASE_COUNT = 2

# Default "due soon" window. Items with next_expected within
# this many days of today are flagged for the plan.
DEFAULT_WINDOW_DAYS = 3


# ── Public API ──────────────────────────────────────────────────────


def build_recurring_shopping_plan(
    db: Any,
    user_id: str = "",
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    today: date | None = None,
) -> list[DecisionResult]:
    """Build a list of ``DecisionResult`` (action=buy) for items
    that are due in the user's shopping rhythm.

    Args:
        db: The ``Database`` instance.
        user_id: The active household. Empty string means
            "use the default household" (per the convention
            used elsewhere in the codebase).
        window_days: Items with ``next_expected - today <= window_days``
            are included in the plan. Default 3.
        today: Override the "today" date (for testing).
            Default ``date.today()``.

    Returns:
        A list of ``DecisionResult`` objects, ordered by
        ``days_until_next`` ascending (most-imminent first).
        Each ``DecisionResult`` has:

          - ``action="buy"`` (the system is telling the user
            to buy)
          - ``reasons=["you buy <X> every <N> days", ...]``
          - ``evidence=[DecisionEvidence(...)]`` with the
            cadence data
          - ``confidence`` based on the purchase count and
            interval consistency
          - ``priority`` based on how soon the item is due
    """
    today = today or date.today()
    cadence = detect_purchase_cadence(db, user_id=user_id or "")
    if not cadence:
        return []

    # Fetch the latest purchase event per item so we can
    # surface "last bought on X" in the explanation.
    recent_purchases = db.get_purchase_events(limit=200, user_id=user_id or "")
    last_event_by_item: dict[str, Any] = {}
    for p in recent_purchases:
        if p.canonical_name not in last_event_by_item:
            last_event_by_item[p.canonical_name] = p

    plan: list[DecisionResult] = []
    for canonical_name, info in cadence.items():
        result = _try_build_decision(
            canonical_name=canonical_name,
            info=info,
            last_event=last_event_by_item.get(canonical_name),
            window_days=window_days,
            today=today,
        )
        if result is not None:
            plan.append(result)

    # Most-imminent first.
    plan.sort(key=lambda d: -d.priority)
    return plan


# ── Pure helpers ───────────────────────────────────────────────────


def _try_build_decision(
    *,
    canonical_name: str,
    info: dict[str, Any],
    last_event: Any,
    window_days: int,
    today: date,
) -> DecisionResult | None:
    """Build a single ``DecisionResult`` for an item, or ``None``
    if the item doesn't qualify (interval out of range, not
    due within the window, etc.).
    """
    avg_interval = float(info.get("avg_interval_days", 0))
    purchase_count = int(info.get("purchase_count", 0))
    next_expected = info.get("next_expected")
    typical_qty = info.get("typical_qty", 1)
    typical_unit = info.get("typical_unit", "unit")

    # Filter: must be a reliable, short-interval rhythm.
    if purchase_count < MIN_PURCHASE_COUNT:
        return None
    if not (MIN_INTERVAL_DAYS <= avg_interval <= MAX_INTERVAL_DAYS):
        return None

    # Compute days_until_next from the cadence's next_expected.
    if next_expected is None:
        return None
    if isinstance(next_expected, datetime):
        next_expected_date = next_expected.date()
    elif isinstance(next_expected, date):
        next_expected_date = next_expected
    else:
        # Some other type — skip defensively.
        return None

    days_until_next = (next_expected_date - today).days
    if days_until_next > window_days:
        return None  # Not due within the planning window.

    # Confidence: based on purchase count and recency.
    # - 5+ purchases: high confidence (0.85)
    # - 3-4 purchases: medium (0.7)
    # - exactly MIN_PURCHASE_COUNT: low (0.55)
    if purchase_count >= 5:
        confidence = 0.85
    elif purchase_count >= 3:
        confidence = 0.7
    else:
        confidence = 0.55

    # Priority: more-imminent items get higher priority.
    # Today: priority=10. Tomorrow: 8. 2 days: 6. 3 days: 4.
    # Negative days (overdue): priority=20.
    if days_until_next < 0:
        priority = 20
    elif days_until_next == 0:
        priority = 10
    else:
        priority = max(1, 10 - days_until_next * 2)

    # Reasons — human-readable strings the explainability
    # service composes into a sentence.
    display_name = canonical_name.replace("_", " ").title()
    if days_until_next < 0:
        when_phrase = f"was due {-days_until_next} day{'s' if days_until_next != -1 else ''} ago"
    elif days_until_next == 0:
        when_phrase = "is due today"
    elif days_until_next == 1:
        when_phrase = "is due tomorrow"
    else:
        when_phrase = f"is due in {days_until_next} days"
    reasons = [
        f"you buy {display_name} every {avg_interval:.0f} days",
        when_phrase,
    ]

    # Evidence — structured for the explainability service.
    evidence = [
        DecisionEvidence(
            source="purchase_cadence",
            value=f"every {avg_interval:.0f} days ({purchase_count} purchases)",
            confidence=confidence,
            captured_at=(
                last_event.timestamp.date().isoformat()
                if last_event and hasattr(last_event, "timestamp")
                and hasattr(last_event.timestamp, "date")
                else None
            ),
        ),
        DecisionEvidence(
            source="typical_quantity",
            value=f"{typical_qty} {typical_unit}",
            confidence=0.9,
        ),
    ]

    return DecisionResult(
        canonical_name=canonical_name,
        display_name=display_name,
        action="buy",
        confidence=confidence,
        priority=priority,
        reasons=reasons,
        evidence=evidence,
        alternatives=[],
        data_freshness="recurring_rhythm",
        data_freshness_label=f"Last bought {info.get('last_bought', '?')}",
        quantity_at_home=0.0,  # Recurring items are not necessarily at home.
    )


# ── Convenience: summary for the dashboard ─────────────────────────


def summarize_plan(plan: list[DecisionResult]) -> str:
    """One-line summary: "3 items due in your usual rhythm."

    Used by the dashboard's recurring card. The summary
    adapts to the count: "1 item due" / "2 items due" / "3
    items due" / "no items due" / etc.
    """
    count = len(plan)
    if count == 0:
        return "No items due in your usual rhythm right now."
    if count == 1:
        return "1 item due in your usual rhythm."
    return f"{count} items due in your usual rhythm."
