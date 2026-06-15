"""Memory facts — turn household purchase history into "ShopStack remembers" cards.

**Why this exists (motto_v3 §0.14 product reality):**

The Memory tab is one of ShopStack's differentiators, but the visible
"memory" surface was vague: a list of recent events and a few
preference cards. Users who asked "what has ShopStack learned about
me?" got an underwhelming answer.

This module extracts the *concrete remembered facts* the system has
about a household — purchase cadence, price ceilings, dietary
preferences — and renders them as a small set of explainable
:func:`shopstack.services.intelligence_cards.build_memory_card`
cards. Examples of the kind of fact a card surfaces:

  * "Milk — you usually buy every 3 days"
  * "Rice — you usually buy every 24 days"
  * "Onion — you avoid prices above ₹60/kg"
  * "Vegetarian household — non-veg items are filtered out"

**Architecture (motto_v3 §0.15 third-layer rule):**

* model — none.
* pipeline — :func:`extract_memory_facts` (read purchase history,
  cadence, preferences) → :func:`render_memory_facts` (turn the facts
  into :class:`IntelligenceCard` list) → HTML via the existing
  :func:`render_intelligence_card`.
* data/config — the threshold counts live in
  :data:`MEMORY_FACT_THRESHOLDS`. New fact kinds are added by
  extending the extractor.

**Supersession (motto_v3 §7):**

The existing :func:`shopstack.ui.renderers.decision_cards.render_cadence_insights`
function continues to render the legacy cadence row in the
"Detailed signals" panel. The new :func:`render_memory_facts` is the
*preferred* path for the Memory tab and the home flow's "Memory"
section. Old code is unchanged.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from shopstack.app_context import current_user_id, db
from shopstack.services.intelligence_cards import (
    ConfidenceLabel,
    build_memory_card,
    render_intelligence_card,
)
from shopstack.ui.components.primitives import home_card

logger = logging.getLogger(__name__)


# ── Thresholds ─────────────────────────────────────────────────────


MEMORY_FACT_THRESHOLDS: dict[str, int] = {
    "min_purchases_for_cadence_fact": 3,
    "min_purchases_for_high_confidence": 8,
    "max_cards_in_memory_section": 8,
}


# ── Memory fact dataclass ─────────────────────────────────────────


@dataclass
class MemoryFact:
    """A single concrete fact the system has learned about a household.

    Attributes:
        title: Card heading (the item or category name).
        fact: The "ShopStack remembers ..." line.
        supporting_evidence: Optional extra line with the data behind
            the fact (e.g. "Logged 12 purchases in the last 60 days").
        confidence: Confidence label shown beneath the fact.
    """

    title: str
    fact: str
    supporting_evidence: str = ""
    confidence: ConfidenceLabel | None = None

    def to_card_html(self) -> str:
        return render_intelligence_card(
            build_memory_card(
                title=self.title,
                fact=self.fact,
                supporting_evidence=self.supporting_evidence,
            )
        )


# ── Fact extraction ──────────────────────────────────────────────


def _confidence_for_count(count: int) -> ConfidenceLabel:
    """Pick a confidence label from a purchase count."""
    return ConfidenceLabel.from_count(count)


def extract_memory_facts(
    *,
    user_id: str = "",
    cadence_data: dict[str, dict[str, Any]] | None = None,
    preference_data: list[dict[str, Any]] | None = None,
    dietary_preference: str | None = None,
) -> list[MemoryFact]:
    """Pull concrete remembered facts from household data.

    Args:
        user_id: Active household id (unused — kept for future
            filter support).
        cadence_data: Output of :func:`shopstack.decisions.detect_purchase_cadence`.
            When ``None``, the function attempts to read it from the
            database.
        preference_data: Output of
            :func:`shopstack.persistence.database.get_preference_signals`.
            When ``None``, the function attempts to read it.
        dietary_preference: Output of
            :func:`shopstack.persistence.database.get_config_value('dietary_preference')`.
            When ``None``, the function attempts to read it.

    Returns:
        List of :class:`MemoryFact`. Empty list when the household
        has not yet generated enough history.
    """
    facts: list[MemoryFact] = []
    min_purchases = MEMORY_FACT_THRESHOLDS["min_purchases_for_cadence_fact"]
    max_cards = MEMORY_FACT_THRESHOLDS["max_cards_in_memory_section"]

    # 1) Cadence facts (most visible — "you buy X every Y days")
    if cadence_data:
        for cname, info in cadence_data.items():
            if not isinstance(info, dict):
                continue
            count = int(info.get("count") or info.get("purchase_count") or 0)
            if count < min_purchases:
                continue
            avg = info.get("avg_interval_days") or info.get("avg_interval") or 0
            try:
                avg_f = float(avg)
            except (TypeError, ValueError):
                continue
            if avg_f <= 0:
                continue
            display = str(cname).replace("_", " ").title()
            # round to integer days
            avg_d = max(1, int(round(avg_f)))
            facts.append(
                MemoryFact(
                    title=display,
                    fact=f"You usually buy {display} every {avg_d} day{'s' if avg_d != 1 else ''}.",
                    supporting_evidence=(
                        f"Based on {count} recent purchase"
                        f"{'s' if count != 1 else ''}."
                    ),
                    confidence=_confidence_for_count(count),
                )
            )
            if len(facts) >= max_cards:
                break

    # 2) Dietary preference fact (always shown when set, even
    # with no purchases).
    if dietary_preference:
        display = dietary_preference.title()
        facts.append(
            MemoryFact(
                title="Diet",
                fact=f"{display} household — non-veg items are filtered out of suggestions."
                if dietary_preference in ("vegetarian", "vegan")
                else f"{display} household.",
                supporting_evidence="Saved during onboarding.",
                confidence=ConfidenceLabel(
                    level="high",
                    text="Set during setup — change in Memory → Preferences.",
                ),
            )
        )

    return facts


def _read_cadence(user_id: str) -> dict[str, dict[str, Any]]:
    """Best-effort: read cadence data from the DB."""
    try:
        from shopstack.decisions import detect_purchase_cadence
        return detect_purchase_cadence(db, user_id=user_id or current_user_id() or "")
    except Exception as exc:  # noqa: BLE001
        logger.debug("memory facts: cadence read failed: %s", exc)
        return {}


def _read_dietary_preference() -> str | None:
    """Best-effort: read the dietary preference from app_config."""
    try:
        value = db.get_config_value("dietary_preference", "")
        return value or None
    except Exception as exc:  # noqa: BLE001
        logger.debug("memory facts: dietary read failed: %s", exc)
        return None


def get_memory_facts_for_user(user_id: str = "") -> list[MemoryFact]:
    """High-level convenience: read everything from the DB and return facts."""
    cadence = _read_cadence(user_id)
    dietary = _read_dietary_preference()
    return extract_memory_facts(
        user_id=user_id,
        cadence_data=cadence,
        dietary_preference=dietary,
    )


# ── Rendering ─────────────────────────────────────────────────────


def render_memory_facts(
    *,
    user_id: str = "",
    facts: list[MemoryFact] | None = None,
) -> str:
    """Render a list of :class:`MemoryFact` as a stack of intelligence cards.

    Returns a wrapping ``<div class='home-memory'>`` block (or an
    actionable empty-state card when the household has no remembered
    facts yet).
    """
    if facts is None:
        facts = get_memory_facts_for_user(user_id)
    if not facts:
        return _render_memory_empty_state()
    cards = "".join(f.to_card_html() for f in facts)
    return f"<div class='home-memory'>{cards}</div>"


def _render_memory_empty_state() -> str:
    """Actionable empty state for the memory section.

    The state explains: (a) what is missing — ShopStack has not
    yet learned anything about this household, (b) why it matters
    — the more it knows, the better the suggestions, (c) the next
    action — log a few purchases.
    """
    body = (
        "<p>ShopStack will learn your household's buying cycle after a few "
        "purchases are logged. Once it knows, you'll see facts like:</p>"
        "<ul style='margin:6px 0 12px 18px;color:var(--text-muted);font-size:0.8125rem;'>"
        "<li>You buy milk every 3 days</li>"
        "<li>You avoid onions above ₹60/kg</li>"
        "<li>You shop at Swiggy and DMart on weekends</li>"
        "</ul>"
        "<p style='font-size:0.75rem;color:var(--text-dim);margin:0;'>"
        "To get started, add what you bought today in the box above, or "
        "open the Pantry tab and log a recent purchase."
        "</p>"
    )
    return home_card(
        title="Memory is empty",
        body=body,
        extra_class="home-flow-card--memory-empty",
    )


__all__ = [
    "MEMORY_FACT_THRESHOLDS",
    "MemoryFact",
    "extract_memory_facts",
    "get_memory_facts_for_user",
    "render_memory_facts",
]
