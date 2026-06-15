"""Smart planner — Phase 9 (community-pool-aware basket planning).

The current basket planner (Phase 0 #3 multi-store comparison)
picks the cheapest store per item. That's correct but
leaves money on the table: a community price map can flag
items that are *temporarily* overpriced relative to recent
history and recommend waiting.

**1st-principles design:**

A "smart" planner should answer three questions per item:

1. **Where** is it cheapest right now? (per-store compare)
2. **When** should I buy it? (now vs. wait — based on
   community median, price-memory trend, and the
   household's use-soon timeline)
3. **How much** should I buy? (use-soon-aware quantity
   recommendation)

**Inputs:**

- A list of requested items (canonical_name, quantity, unit).
- The community pool (for the "is this overpriced?" check).
- The household's use-soon / cadence data (for "do I
  need it now?").
- A :class:`BasketComparison` from the basket-compare
  service (for the "where" question).

**Outputs:**

A :class:`SmartBasket` with:
- For each item: store recommendation, "buy now" / "wait"
  verdict, recommended quantity.
- A summary header: "buy now: ₹X, wait: ₹Y saved, total
  basket: ₹Z".
- A community-aware insight per item (e.g. "milk is 20%
  above community median — consider waiting 3 days").

**Why a separate module:**

The basket-compare service answers the "where" question.
The community-price-map answers the "what's the market
saying" question. Combining them is the smart-planner
service — additive on top, no breaking changes to either.

**Failure modes:**

- No community data for an item: fall back to "buy now at
  the cheapest store" (the legacy behavior).
- No basket-compare data: fall back to "buy now" with no
  store recommendation.
- Stale use-soon data: surface as a warn, don't fail.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from typing import Any, Iterable

from shopstack.services._utils import safe_get

logger = logging.getLogger(__name__)


# ─── Verdict constants ───────────────────────────────────────────


BUY_NOW = "buy_now"
WAIT = "wait"
SKIP = "skip"  # not used in v1; reserved for future "don't buy at all"


# ─── Dataclasses ─────────────────────────────────────────────────


@dataclass
class SmartLine:
    """One item's smart-planner recommendation."""

    canonical_name: str
    display_name: str
    requested_qty: float
    requested_unit: str
    verdict: str  # BUY_NOW | WAIT
    recommended_store: str = ""
    cheapest_price: float | None = None
    community_median: float | None = None
    pct_above_median: float | None = None  # positive = overpriced
    recommended_qty: float | None = None
    reason: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SmartBasket:
    """The full smart-planner output for a basket."""

    lines: list[SmartLine] = field(default_factory=list)
    total_buy_now: float = 0.0
    total_wait: float = 0.0
    total_savings_if_wait: float = 0.0
    n_buy_now: int = 0
    n_wait: int = 0
    n_unknown: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    generated_at: str = ""


# ─── Build a smart basket ────────────────────────────────────────


def _build_smart_line(
    canonical_name: str,
    requested_qty: float,
    requested_unit: str,
    *,
    basket_comparison: Any | None,
    community_median_value: float | None,
    use_soon_for_item: dict | None,
) -> SmartLine:
    """Build one :class:`SmartLine` for a single item."""
    display = canonical_name.replace("_", " ").title()
    # Per-item price from basket comparison
    cheapest_price: float | None = None
    recommended_store: str = ""
    if basket_comparison is not None:
        # BasketComparison is a dataclass; lines is a list of BasketLine
        line = _find_line_for(basket_comparison, canonical_name)
        if line is not None:
            cheapest_price = _line_total(line)
            recommended_store = _line_store(line)
    # Community median
    pct_above: float | None = None
    if community_median_value and community_median_value > 0 and cheapest_price:
        pct_above = (cheapest_price - community_median_value) / community_median_value * 100
    # Decide verdict. The use-soon check comes first because an
    # item about to spoil is a harder constraint than "this
    # is overpriced right now" — the user can buy less of it
    # and consume it faster; they can't un-spoil a tomato.
    if cheapest_price is None and community_median_value is None:
        verdict = BUY_NOW
        reason = "No price data — buy at your usual store."
    elif use_soon_for_item and _is_use_soon_critical(use_soon_for_item):
        verdict = BUY_NOW
        reason = f"Use-soon: {display} will spoil soon. Buy now."
    elif pct_above is not None and pct_above > 15:
        # Significantly above community median — recommend waiting
        verdict = WAIT
        reason = (
            f"{display} is {pct_above:.0f}% above the community median (₹{community_median_value:.0f}). Consider waiting."
        )
    else:
        verdict = BUY_NOW
        reason = f"Cheapest at {recommended_store or 'your store'}: ₹{cheapest_price:.0f}." if cheapest_price else "Buy at your usual store."
    # Recommended quantity: round up requested to a sensible size
    rec_qty = requested_qty
    return SmartLine(
        canonical_name=canonical_name,
        display_name=display,
        requested_qty=requested_qty,
        requested_unit=requested_unit,
        verdict=verdict,
        recommended_store=recommended_store,
        cheapest_price=cheapest_price,
        community_median=community_median_value,
        pct_above_median=pct_above,
        recommended_qty=rec_qty,
        reason=reason,
    )


def _find_line_for(basket_comparison: Any, canonical_name: str) -> Any | None:
    """Return the BasketLine matching ``canonical_name``, if any."""
    lines = safe_get(basket_comparison, "lines", default=[]) or []
    for line in lines:
        cname = safe_get(line, "canonical_name", default="") or ""
        if cname.lower() == canonical_name.lower():
            return line
    return None


def _line_total(line: Any) -> float | None:
    """Return the cheapest total for a single line."""
    t = safe_get(line, "cheapest_total", default=None)
    if t is None:
        # Alternative field name
        t = safe_get(line, "total", default=None)
    if t is None:
        return None
    try:
        return float(t)
    except (TypeError, ValueError):
        return None


def _line_store(line: Any) -> str:
    """Return the source label for a line's cheapest price."""
    return str(safe_get(line, "best_source", "cheapest_source", default="") or "")


def _is_use_soon_critical(use_soon: dict) -> bool:
    """True if the item is about to expire (within 2 days)."""
    days = use_soon.get("days_until_expiry")
    if isinstance(days, (int, float)):
        return days <= 2
    return False


def build_smart_basket(
    items: list[dict[str, Any]],
    *,
    basket_comparison: Any | None = None,
    community_medians: dict[str, float] | None = None,
    use_soon_items: list[dict[str, Any]] | None = None,
) -> SmartBasket:
    """Build the smart basket for a list of requested items.

    Args:
        items: List of ``{"canonical_name": ..., "quantity": ...,
            "unit": ...}`` dicts.
        basket_comparison: Optional :class:`BasketComparison`
            from the basket-compare service.
        community_medians: Optional dict of
            ``{canonical_name: median_price}`` from the
            community pool.
        use_soon_items: Optional list of use-soon dicts
            (for the "buy now vs. wait" verdict).
    """
    use_soon_by_cname: dict[str, dict] = {}
    for it in (use_soon_items or []):
        cn = str(it.get("canonical_name") or "")
        if cn:
            use_soon_by_cname[cn.lower()] = it
    medians = community_medians or {}
    lines: list[SmartLine] = []
    total_buy_now = 0.0
    total_wait = 0.0
    n_buy_now = 0
    n_wait = 0
    n_unknown = 0
    for raw in items:
        cname = str(raw.get("canonical_name") or "").strip().lower()
        if not cname:
            continue
        qty = float(raw.get("quantity") or 1.0)
        unit = str(raw.get("unit") or "unit")
        median = medians.get(cname)
        use_soon = use_soon_by_cname.get(cname)
        line = _build_smart_line(
            cname,
            qty,
            unit,
            basket_comparison=basket_comparison,
            community_median_value=median,
            use_soon_for_item=use_soon,
        )
        lines.append(line)
        if line.verdict == BUY_NOW and line.cheapest_price:
            total_buy_now += line.cheapest_price * qty
            n_buy_now += 1
        elif line.verdict == WAIT and line.cheapest_price and line.community_median:
            # If they wait, they save the difference per unit
            saved = (line.cheapest_price - line.community_median) * qty
            total_wait += max(0.0, saved)
            n_wait += 1
        else:
            n_unknown += 1
    by_source: dict[str, int] = {}
    for line in lines:
        if line.recommended_store:
            by_source[line.recommended_store] = by_source.get(line.recommended_store, 0) + 1
    return SmartBasket(
        lines=lines,
        total_buy_now=round(total_buy_now, 2),
        total_wait=round(total_wait, 2),
        total_savings_if_wait=round(total_wait, 2),
        n_buy_now=n_buy_now,
        n_wait=n_wait,
        n_unknown=n_unknown,
        by_source=by_source,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ─── HTML rendering ────────────────────────────────────────────


def _line_html(line: SmartLine) -> str:
    color = {
        BUY_NOW: "var(--green, #176B49)",
        WAIT:    "var(--amber, #A76012)",
    }.get(line.verdict, "var(--text-muted, #5F5144)")
    icon = {
        BUY_NOW: "🛒",
        WAIT:    "⏳",
    }.get(line.verdict, "•")
    price_html = ""
    if line.cheapest_price is not None:
        price_html = f"<span class='sp-price'>₹{line.cheapest_price:.0f}</span>"
    community_html = ""
    if line.community_median is not None:
        delta = (
            f" <span class='sp-delta sp-delta-up'>+{line.pct_above_median:.0f}%</span>"
            if line.pct_above_median and line.pct_above_median > 0
            else (
                f" <span class='sp-delta sp-delta-down'>{line.pct_above_median:.0f}%</span>"
                if line.pct_above_median and line.pct_above_median < 0
                else " <span class='sp-delta'>±0%</span>"
            )
        )
        community_html = (
            f"<span class='sp-community'>👥 ₹{line.community_median:.0f}{delta}</span>"
        )
    return (
        f"<div class='sp-line' style='border-left:3px solid {color};'><span class='sp-icon'>{icon}</span>"
        f"<span class='sp-body'><span class='sp-name'>{escape(line.display_name)}</span>"
        f"<span class='sp-store'>{escape(line.recommended_store) or 'any store'}</span><span class='sp-reason'>{escape(line.reason)}</span>"
        f"</span><span class='sp-prices'>{price_html} {community_html}</span>"
        f"</div>"
    )


def render_smart_basket_html(basket: SmartBasket) -> str:
    """Render the smart basket as XSS-safe HTML.

    Sections:
    1. Headline summary: buy_now / wait / unknown counts.
    2. Per-line verdict rows (color-coded by verdict).
    """
    if not basket.lines:
        return (
            "<div class='sp-block'>"
            "<div class='sp-headline'>📋 Add items to your basket to see smart recommendations.</div>"
            "</div>"
        )
    parts: list[str] = ["<div class='sp-block'>"]
    parts.append(
        "<div class='sp-headline'>"
        f"🛒 <strong>{basket.n_buy_now}</strong> buy now · ⏳ <strong>{basket.n_wait}</strong> wait · "
        f"₹<strong>{basket.total_buy_now:,.0f}</strong> total"
        + (
            f" · save ₹<strong>{basket.total_savings_if_wait:,.0f}</strong> if you wait"
            if basket.total_savings_if_wait > 0
            else ""
        )
        + "</div>"
    )
    if basket.by_source:
        chips = "".join(
            f"<span class='sp-chip'>{escape(s)} · {n}</span>"
            for s, n in basket.by_source.items()
        )
        parts.append(f"<div class='sp-sources'>{chips}</div>")
    parts.append("<div class='sp-lines'>")
    for line in basket.lines:
        parts.append(_line_html(line))
    parts.append("</div></div>")
    return "".join(parts)


__all__ = [
    "BUY_NOW",
    "SKIP",
    "SmartBasket",
    "SmartLine",
    "WAIT",
    "build_smart_basket",
    "render_smart_basket_html",
]
