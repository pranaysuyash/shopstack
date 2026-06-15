"""Intelligence cards — the reusable, explainable action surfaces.

**Why this exists (motto_v3 §0.14 product reality):**

The Today dashboard already surfaces a dozen separate "signals"
(restock-due, use-soon, price-drop, community-overpriced, trip
advice, seasonal). Each signal is computed correctly in isolation
but the user sees a wall of numbers with no answer to the actual
question: *what should I do right now, and why?*

This module provides the *card* layer for those signals — one
rendering helper per action type, each producing HTML that shows:

  * the item name
  * the recommendation (one word: "Buy soon", "Use soon", "Skip",
    "Price drop", "Watch")
  * a one-line reason ("You'll run out in 2 days — you usually buy
    every 4 days and last bought 4 days ago")
  * a confidence label ("High confidence — 8 purchases logged")
  * a primary action button (Add to list / Show recipes / Do not
    remind this week)
  * an optional secondary action

**Architecture (motto_v3 §0.15 third-layer rule):**

* model — none. The cards are pure data → HTML. The actual signal
  reasoning lives in :mod:`shopstack.services.decision_engine`,
  :mod:`shopstack.services.restock_card`, :mod:`shopstack.services.price_memory`,
  and the dashboard service. This module is the *renderer* for the
  signals, not the source of truth.
* pipeline — :func:`build_*_card` → HTML → injected into
  :class:`gr.HTML` components.
* data/config — the per-card fields (``reason``, ``confidence``,
  ``typical_qty``, ``days_until``) come from upstream dataclasses.
  New card kinds are added by writing one new ``build_*_card`` function
  and one CSS class.

**Supersession (motto_v3 §7):**

The existing card renderers in
:mod:`shopstack.ui.renderers.decision_cards`,
:mod:`shopstack.services.restock_card`, and
:mod:`shopstack.ui.components.cards` are not deleted. They continue
to render the legacy signal cards. The functions in this module are
the *preferred* path for new code and the ones wired into the
command-driven Today flow.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from typing import Any

logger = logging.getLogger(__name__)


# ── Shared types ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ConfidenceLabel:
    """A visible "how sure are we?" tag shown on intelligence cards.

    Attributes:
        level: One of ``"high"``, ``"medium"``, ``"low"`` (or
            ``"unscored"`` for the "we have no idea yet" case).
        text: The user-facing phrase. E.g. ``"High confidence —
            8 purchases logged"``.
    """

    level: str
    text: str

    @classmethod
    def from_count(cls, purchase_count: int, *, total_observed: int = 0) -> "ConfidenceLabel":
        """Build a confidence label from raw observation counts.

        * 0 observations → "unscored"
        * 1-2 → "low"
        * 3-7 → "medium"
        * 8+ → "high"
        """
        n = purchase_count
        if n <= 0:
            return cls(
                level="unscored",
                text="Low confidence — not enough history yet",
            )
        if n < 3:
            return cls(
                level="low",
                text=f"Low confidence — {n} purchase{'s' if n != 1 else ''} logged",
            )
        if n < 8:
            return cls(
                level="medium",
                text=f"Medium confidence — {n} purchases logged",
            )
        return cls(
            level="high",
            text=f"High confidence — {n} purchases logged",
        )


@dataclass
class IntelligenceCard:
    """Generic card data — the renderer fills in the HTML.

    Attributes:
        kind: One of ``"buy_soon"``, ``"use_soon"``, ``"skip"``,
            ``"price_drop"``, ``"price_overpriced"``, ``"restock"``,
            ``"memory"``, ``"trip"``.
        title: Card heading (typically the item name).
        subtitle: One-line reason.
        secondary: Optional small text (e.g. "2d to expiry", "-12%").
        confidence: Optional :class:`ConfidenceLabel`.
        primary_action: A dict ``{"label": str, "target_id": str,
            "target_tab": str}`` — the CTA at the bottom-right of
            the card. ``target_tab`` is the canonical tab to jump
            to if the click should switch tabs.
        secondary_action: Optional secondary CTA, same shape.
    """

    kind: str
    title: str
    subtitle: str = ""
    secondary: str = ""
    confidence: ConfidenceLabel | None = None
    primary_action: dict[str, str] = field(default_factory=dict)
    secondary_action: dict[str, str] = field(default_factory=dict)
    # Item #41 (motto_v3 §0.10): when this card was rendered
    # (i.e. when the dashboard was last built). The renderer
    # converts this into a "Last updated: just now" relative-
    # time stamp so every card on the home dashboard tells the
    # user how fresh the data is. Optional so existing call
    # sites that don't care can leave it None.
    last_updated: datetime | None = None

    def to_html(self) -> str:
        return render_intelligence_card(self)


# ── Per-kind card builders ─────────────────────────────────────────


def build_buy_soon_card(
    *,
    item: str,
    days_until: int | None = None,
    confidence: ConfidenceLabel | None = None,
    purchase_count: int = 0,
    typical_qty: float | None = None,
    unit: str = "unit",
    last_updated: datetime | None = None,
) -> IntelligenceCard:
    """Card for "buy this soon" recommendations."""
    if days_until is None:
        subtitle = f"You'll likely run out of {item} soon."
    elif days_until <= 0:
        subtitle = f"You may already be out of {item}."
    else:
        subtitle = f"You'll run out of {item} in about {days_until} day{'s' if days_until != 1 else ''}."

    if purchase_count > 0:
        rhythm = "every few days" if purchase_count >= 3 else "occasionally"
        why = f" You usually buy {item} {rhythm} (logged {purchase_count} times)."
        subtitle = subtitle + why

    secondary_parts: list[str] = []
    if typical_qty is not None:
        secondary_parts.append(f"Typical buy: {typical_qty:g} {unit}")
    secondary = " · ".join(secondary_parts)

    return IntelligenceCard(
        kind="buy_soon",
        title=item,
        last_updated=last_updated,
        subtitle=subtitle,
        secondary=secondary,
        confidence=confidence,
        primary_action={
            "label": "Add to shopping list",
            "target_id": "",
            "target_tab": "shopping",
            "intent": "add",
            "item": item,
        },
        secondary_action={
            "label": "Snooze",
            "target_id": "",
            "target_tab": "",
        },
    )


def build_use_soon_card(
    *,
    item: str,
    days_until_expiry: int | None = None,
    confidence: ConfidenceLabel | None = None,
    last_updated: datetime | None = None,
) -> IntelligenceCard:
    """Card for "use this before it spoils" recommendations."""
    if days_until_expiry is None:
        subtitle = f"Use {item} soon — it may be aging."
    elif days_until_expiry <= 0:
        subtitle = f"{item} is past its prime — use or compost today."
    else:
        subtitle = f"{item} will spoil in about {days_until_expiry} day{'s' if days_until_expiry != 1 else ''}."

    return IntelligenceCard(
        kind="use_soon",
        title=item,
        subtitle=subtitle,
        secondary=(
            f"{days_until_expiry}d to expiry"
            if days_until_expiry is not None
            else ""
        ),
        confidence=confidence,
        last_updated=last_updated,
        primary_action={
            "label": "Show recipes",
            "target_id": "",
            "target_tab": "recipes",
        },
        secondary_action={
            "label": "Mark used",
            "target_id": "",
            "target_tab": "",
        },
    )


def build_skip_card(
    *,
    item: str,
    reason: str,
    confidence: ConfidenceLabel | None = None,
) -> IntelligenceCard:
    """Card for "you have enough of this — skip" recommendations."""
    return IntelligenceCard(
        kind="skip",
        title=item,
        subtitle=reason,
        confidence=confidence,
        primary_action={
            "label": "Don't remind this week",
            "target_id": "",
            "target_tab": "",
        },
    )


def build_price_drop_card(
    *,
    item: str,
    drop_pct: float,
    current_price: float | None = None,
    typical_price: float | None = None,
    unit: str = "unit",
    confidence: ConfidenceLabel | None = None,
) -> IntelligenceCard:
    """Card for "this item is at a recent low" price signals."""
    price_line = ""
    if current_price is not None and typical_price is not None:
        price_line = f" Now ₹{current_price:.0f} per {unit} (typical ₹{typical_price:.0f})."
    elif current_price is not None:
        price_line = f" Now ₹{current_price:.0f} per {unit}."

    return IntelligenceCard(
        kind="price_drop",
        title=item,
        subtitle=(
            f"{item} is at a recent low (-{abs(drop_pct):.0f}%).{price_line}"
        ),
        secondary=f"-{abs(drop_pct):.0f}%",
        confidence=confidence,
        primary_action={
            "label": "Add to shopping list",
            "target_id": "",
            "target_tab": "shopping",
            "intent": "add",
            "item": item,
        },
    )


def build_price_overpriced_card(
    *,
    item: str,
    observed_price: float,
    community_median: float,
    unit: str = "unit",
) -> IntelligenceCard:
    """Card for "community median is lower than what you paid" signals."""
    diff = observed_price - community_median
    pct = (diff / community_median * 100) if community_median > 0 else 0.0
    return IntelligenceCard(
        kind="price_overpriced",
        title=item,
        subtitle=(
            f"{item} — you paid ₹{observed_price:.0f} per {unit}; community median is "
            f"₹{community_median:.0f} ({pct:+.0f}%)."
        ),
        secondary="verify on next receipt",
        confidence=ConfidenceLabel(
            level="low",
            text="Community signal — verify with your own receipt",
        ),
        primary_action={
            "label": "Open price history",
            "target_id": "",
            "target_tab": "memory",
        },
    )


def build_restock_card(
    *,
    item: str,
    days_until: int | None = None,
    urgency: str = "due_soon",
    typical_qty: float | None = None,
    unit: str = "unit",
    confidence: ConfidenceLabel | None = None,
    last_updated: datetime | None = None,
) -> IntelligenceCard:
    """Card for "you'll run out soon" restock predictions."""
    if days_until is None:
        subtitle = f"{item} restock is expected soon."
    elif days_until <= 0:
        subtitle = f"{item} is overdue — restock today."
    else:
        subtitle = (
            f"{item} restock predicted in {days_until} day"
            f"{'s' if days_until != 1 else ''}."
        )

    secondary_parts: list[str] = []
    if typical_qty is not None:
        secondary_parts.append(f"Typical: {typical_qty:g} {unit}")
    secondary_parts.append(f"Urgency: {urgency.replace('_', ' ')}")
    secondary = " · ".join(secondary_parts)

    return IntelligenceCard(
        kind="restock",
        title=item,
        subtitle=subtitle,
        secondary=secondary,
        confidence=confidence,
        last_updated=last_updated,
        primary_action={
            "label": "Add to shopping list",
            "target_id": "",
            "target_tab": "shopping",
            "intent": "add",
            "item": item,
        },
    )


def build_memory_card(
    *,
    title: str,
    fact: str,
    supporting_evidence: str = "",
) -> IntelligenceCard:
    """Card for "here's what ShopStack has learned about your household".

    E.g. ``build_memory_card(title='Milk', fact='You buy it every 3 days',
    supporting_evidence='Logged 12 purchases in the last 60 days.')``.
    """
    subtitle = fact
    if supporting_evidence:
        subtitle = f"{fact} {supporting_evidence}"
    return IntelligenceCard(
        kind="memory",
        title=title,
        subtitle=subtitle,
        primary_action={
            "label": "Open memory",
            "target_id": "",
            "target_tab": "memory",
        },
    )


def build_trip_card(
    *,
    label: str,
    reason: str,
    secondary: str = "",
) -> IntelligenceCard:
    """Card for the trip advisor's go/delay/stay recommendation."""
    return IntelligenceCard(
        kind="trip",
        title=label,
        subtitle=reason,
        secondary=secondary,
        primary_action={
            "label": "Open trip advisor",
            "target_id": "",
            "target_tab": "trips",
        },
    )


# ── Renderer ────────────────────────────────────────────────────────


_KIND_META: dict[str, dict[str, str]] = {
    "buy_soon": {
        "badge": "Buy soon",
        "badge_class": "badge badge-amber",
        "icon": "🛒",
    },
    "use_soon": {
        "badge": "Use soon",
        "badge_class": "badge badge-amber",
        "icon": "🥬",
    },
    "skip": {
        "badge": "Skip",
        "badge_class": "badge badge-gray",
        "icon": "⏸",
    },
    "price_drop": {
        "badge": "Price drop",
        "badge_class": "badge badge-green",
        "icon": "💰",
    },
    "price_overpriced": {
        "badge": "Above median",
        "badge_class": "badge badge-gray",
        "icon": "👥",
    },
    "restock": {
        "badge": "Restock",
        "badge_class": "badge badge-amber",
        "icon": "📦",
    },
    "memory": {
        "badge": "Memory",
        "badge_class": "badge badge-blue",
        "icon": "🧠",
    },
    "trip": {
        "badge": "Trip",
        "badge_class": "badge badge-blue",
        "icon": "🧭",
    },
}


def render_intelligence_card(card: IntelligenceCard) -> str:
    """Render an :class:`IntelligenceCard` as XSS-safe HTML."""
    meta = _KIND_META.get(card.kind, {"badge": "", "badge_class": "", "icon": ""})
    confidence_html = (
        f"<div class='ic-confidence ic-confidence--{escape(card.confidence.level)}'>"
        f"{escape(card.confidence.text)}</div>"
        if card.confidence is not None
        else ""
    )
    actions_html = _render_actions(card)
    badge = escape(meta["badge"])
    badge_class = escape(meta["badge_class"])
    icon = escape(meta["icon"])
    title = escape(card.title)
    subtitle = escape(card.subtitle)
    secondary = escape(card.secondary) if card.secondary else ""
    badge_html = (
        f'<span class="{badge_class}">{badge}</span>' if meta["badge"] else ""
    )
    secondary_html = (
        f"<div class='ic-secondary'>{secondary}</div>" if card.secondary else ""
    )
    from shopstack.ui.components.primitives import last_updated_stamp
    last_updated_html = last_updated_stamp(
        card.last_updated, label="Last updated"
    ) if card.last_updated else ""
    return (
        f"<div class='intelligence-card intelligence-card--{escape(card.kind)}'>"
        f"{last_updated_html}"
        f"<div class='ic-head'>"
        f"<span class='ic-icon' aria-hidden='true'>{icon}</span>"
        f"<div class='ic-title-block'>"
        f"<div class='ic-title'>{title}</div>"
        f"{badge_html}"
        f"</div>"
        f"</div>"
        f"<div class='ic-subtitle'>{subtitle}</div>"
        f"{secondary_html}"
        f"{confidence_html}"
        f"{actions_html}"
        f"</div>"
    )


def _render_actions(card: IntelligenceCard) -> str:
    if not card.primary_action and not card.secondary_action:
        return ""
    parts: list[str] = ["<div class='ic-actions'>"]
    if card.secondary_action and card.secondary_action.get("label"):
        parts.append(_render_action_button(card.secondary_action, kind="secondary"))
    if card.primary_action and card.primary_action.get("label"):
        parts.append(_render_action_button(card.primary_action, kind="primary"))
    parts.append("</div>")
    return "".join(parts)


def _render_action_button(action: dict[str, str], *, kind: str) -> str:
    """Render one action button. Encodes intent data as data-* attrs
    so the JS handler can dispatch (fill input, switch tab, fire API).
    """
    data_attrs: list[str] = []
    for key in ("intent", "item", "target_id", "target_tab"):
        if action.get(key):
            data_attrs.append(f"data-{key.replace('_', '-')}='{escape(action[key])}'")
    cls = (
        "ic-action ic-action--primary"
        if kind == "primary"
        else "ic-action ic-action--secondary"
    )
    return (
        f"<button type='button' class='{cls}' "
        f"{' '.join(data_attrs)} "
        f"onclick=\"ssIntelligenceAction(this)\">"
        f"{escape(action.get('label', 'Action'))}</button>"
    )


# ── JS shim (registered by the tab builder via gr.HTML) ────────────


INTELLIGENCE_CARD_SCRIPT_HTML: str = """
<script data-ss-exec="true">
// ── Intelligence card: action dispatch helper ────────────────────
// Wires the data-* attributes of an .ic-action button to the
// appropriate behaviour: switch tab, fill command surface, etc.
function ssIntelligenceAction(btn) {
  try {
    var tab = btn.getAttribute('data-target-tab');
    if (tab) {
      var tabBtn = document.querySelector('[data-testid="tab-' + tab + '"]');
      if (tabBtn) tabBtn.click();
    }
    var intent = btn.getAttribute('data-intent');
    var item = btn.getAttribute('data-item');
    if (intent === 'add' && item) {
      // Defer so the tab-switch animation completes first.
      setTimeout(function() {
        var input = document.getElementById('command-surface-input');
        if (input) {
          var ta = input.querySelector('textarea') || input;
          if (ta && 'value' in ta) {
            ta.value = 'add ' + item.replace(/_/g, ' ');
            ta.dispatchEvent(new Event('input', { bubbles: true }));
            ta.focus();
          }
        }
      }, tab ? 80 : 0);
    }
  } catch (e) {
    console.warn('ssIntelligenceAction failed', e);
  }
}
</script>
"""


__all__ = [
    "ConfidenceLabel",
    "IntelligenceCard",
    "INTELLIGENCE_CARD_SCRIPT_HTML",
    "build_buy_soon_card",
    "build_memory_card",
    "build_price_drop_card",
    "build_price_overpriced_card",
    "build_restock_card",
    "build_skip_card",
    "build_trip_card",
    "build_use_soon_card",
    "render_intelligence_card",
]
