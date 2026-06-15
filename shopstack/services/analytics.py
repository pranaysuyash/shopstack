"""Household analytics dashboard — Phase 8 (new product surface).

Aggregates traces + price memory + inventory movements into
a household-level "what's happened" view:

- **Spend this month / this year** — total ₹ spent, broken
  down by store and by category.
- **Top items by spend** — the 10 items the household spends
  the most on.
- **Spend trend** — last 6 months, monthly totals.
- **Waste rate** — items consumed vs items thrown out
  (use-soon count).
- **Top merchants by frequency** — where the household
  actually shops.

**Inputs:**

- A :class:`Trace` or dict stream (we read through the
  database).
- A :class:`PriceObservation` stream.
- The active household id.

**Outputs:**

A :class:`HouseholdAnalytics` dataclass + a renderable HTML
block. Cheap, synchronous, no LLM call.

**Why a separate module:**

The other surfaces (cook tonight, basket compare, etc.) are
all *action* surfaces — they tell the user what to do *now*.
Analytics is a *reflection* surface — it answers "what did we
do this month?" Both are valid; they belong in different
modules.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from html import escape
from typing import Any, Iterable

from shopstack.ui.components.primitives import home_card

logger = logging.getLogger(__name__)


# ─── Result dataclass ────────────────────────────────────────────


@dataclass
class HouseholdAnalytics:
    """Aggregated household analytics over a date range."""

    spend_this_month: float = 0.0
    spend_this_year: float = 0.0
    spend_by_store: dict[str, float] = field(default_factory=dict)
    spend_by_category: dict[str, float] = field(default_factory=dict)
    top_items: list[tuple[str, float]] = field(default_factory=list)
    spend_trend: list[tuple[str, float]] = field(default_factory=list)  # (YYYY-MM, total)
    use_soon_count: int = 0
    consume_count: int = 0
    purchase_count: int = 0
    window_days: int = 180
    new_items_added: int = 0
    top_merchants: list[tuple[str, int]] = field(default_factory=list)

    @property
    def waste_rate_pct(self) -> float:
        """% of consumptions that were use-soon (proxy for waste)."""
        if not self.consume_count:
            return 0.0
        return round(self.use_soon_count / self.consume_count * 100, 1)


# ─── Aggregation ──────────────────────────────────────────────


def _trace_field(trace: Any, key: str, default: Any = None) -> Any:
    if isinstance(trace, dict):
        return trace.get(key, default)
    return getattr(trace, key, default)


def _as_naive_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.replace(tzinfo=None)
        except ValueError:
            return None
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return None


def _trace_dt(trace: Any) -> datetime | None:
    ts = _trace_field(trace, "created_at") or _trace_field(trace, "timestamp")
    return _as_naive_dt(ts)


def _trace_amount(trace: Any) -> float:
    """Best-effort extract of a price/amount from a trace payload."""
    payload = _trace_field(trace, "payload", {}) or {}
    if isinstance(payload, dict):
        for key in ("total", "amount", "price", "price_total"):
            v = payload.get(key)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        # Sometimes nested under items
        items = payload.get("items")
        if isinstance(items, list):
            total = 0.0
            any_found = False
            for it in items:
                if isinstance(it, dict):
                    v = it.get("price") or it.get("amount")
                    if v is not None:
                        try:
                            total += float(v)
                            any_found = True
                        except (TypeError, ValueError):
                            pass
            if any_found:
                return total
    return 0.0


def _trace_store(trace: Any) -> str:
    payload = _trace_field(trace, "payload", {}) or {}
    if isinstance(payload, dict):
        return str(payload.get("store") or payload.get("store_name") or "unknown")
    return "unknown"


def _trace_category(trace: Any) -> str:
    payload = _trace_field(trace, "payload", {}) or {}
    if isinstance(payload, dict):
        return str(payload.get("category") or "uncategorized")
    return "uncategorized"


def _trace_canonical(trace: Any) -> str:
    payload = _trace_field(trace, "payload", {}) or {}
    if isinstance(payload, dict):
        cn = payload.get("canonical_name")
        if cn:
            return str(cn)
        inp = payload.get("input")
        if isinstance(inp, dict):
            cn = inp.get("canonical_name")
            if cn:
                return str(cn)
    return ""


def aggregate_analytics(
    traces: Iterable[Any],
    *,
    window_days: int = 180,
    today: datetime | None = None,
) -> HouseholdAnalytics:
    """Compute household-level analytics from a trace stream.

    Args:
        traces: Iterable of trace objects (dataclass or dict).
        window_days: How far back to look for the trend.
        today: Override "now" for deterministic tests.
    """
    if today is None:
        today = datetime.now().replace(tzinfo=None)
    cutoff = today - timedelta(days=window_days)
    month_start = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    year_start = today.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    spend_by_store: Counter[str] = Counter()
    spend_by_category: Counter[str] = Counter()
    spend_by_item: Counter[str] = Counter()
    spend_by_month: defaultdict[str, float] = defaultdict(float)
    spend_this_month = 0.0
    spend_this_year = 0.0
    use_soon_count = 0
    consume_count = 0
    purchase_count = 0
    new_items_added = 0
    merchants: Counter[str] = Counter()

    for tr in traces:
        dt = _trace_dt(tr)
        if dt is None or dt < cutoff:
            continue
        action = str(_trace_field(tr, "action_type") or _trace_field(tr, "action") or "")
        if action == "add_purchase" or action == "purchase":
            purchase_count += 1
            amount = _trace_amount(tr)
            store = _trace_store(tr)
            cat = _trace_category(tr)
            item = _trace_canonical(tr)
            if amount > 0:
                spend_by_store[store] += amount
                spend_by_category[cat] += amount
                if item:
                    spend_by_item[item] += amount
                spend_by_month[dt.strftime("%Y-%m")] += amount
                if dt >= month_start:
                    spend_this_month += amount
                if dt >= year_start:
                    spend_this_year += amount
            merchants[store] += 1
        elif action == "consume" or action == "consume_item":
            consume_count += 1
        elif action == "use_soon" or action == "waste":
            use_soon_count += 1
        elif action == "add_inventory_item":
            new_items_added += 1

    # Sort and trim
    top_items = spend_by_item.most_common(10)
    top_merchants = merchants.most_common(5)
    # Build spend trend: last 6 months, oldest first
    spend_trend: list[tuple[str, float]] = []
    for i in range(5, -1, -1):
        m = (today.replace(day=1) - timedelta(days=30 * i)).strftime("%Y-%m")
        spend_trend.append((m, round(spend_by_month.get(m, 0.0), 2)))

    return HouseholdAnalytics(
        spend_this_month=round(spend_this_month, 2),
        spend_this_year=round(spend_this_year, 2),
        spend_by_store=dict(spend_by_store.most_common()),
        spend_by_category=dict(spend_by_category.most_common()),
        top_items=top_items,
        spend_trend=spend_trend,
        use_soon_count=use_soon_count,
        consume_count=consume_count,
        purchase_count=purchase_count,
        window_days=window_days,
        new_items_added=new_items_added,
        top_merchants=top_merchants,
    )


# ─── HTML rendering ────────────────────────────────────────────


def _bar(pct: float, color: str = "var(--accent, #176B49)") -> str:
    return (
        f"<div class='ha-bar-track'><div class='ha-bar-fill' style='width:{max(0, min(100, pct)):.0f}%;background:{color};'></div>"
        f"</div>"
    )


def render_analytics_html(analytics: HouseholdAnalytics) -> str:
    """Render the analytics dashboard as a single XSS-safe HTML block.

    Sections:
    1. Headline metrics (spend this month / year / purchases).
    2. Spend trend (last 6 months as small bars).
    3. Top items (chips with amounts).
    4. Top merchants (chips with counts).
    5. Waste rate (small badge).
    """
    if not analytics.purchase_count:
        return home_card(
            style="text-align:center;padding:16px;color:var(--text-dim);",
            body="📊 No purchase history yet. Add a few receipts to see analytics.",
        )
    parts: list[str] = []
    parts.append("<div class='ha-block'>")
    # Headline metrics
    parts.append(
        "<div class='ha-headline'>"
        f"<strong>₹{analytics.spend_this_month:,.0f}</strong> spent this month · <strong>₹{analytics.spend_this_year:,.0f}</strong> this year · "
        f"<strong>{analytics.purchase_count}</strong> purchases · <strong>{analytics.new_items_added}</strong> new items"
        "</div>"
    )
    # Spend trend
    if analytics.spend_trend:
        max_spend = max(s for _, s in analytics.spend_trend) or 1
        rows = "".join(
            f"<div class='ha-bar-row'><div class='ha-bar-label'>{escape(month)}</div>"
            f"{_bar(spend / max_spend * 100)}<div class='ha-bar-value'>₹{spend:,.0f}</div>"
            f"</div>"
            for month, spend in analytics.spend_trend
        )
        parts.append(f"<div class='ha-section-h'>Monthly trend</div>{rows}")
    # Top items
    if analytics.top_items:
        chips = "".join(
            f"<span class='ha-chip'>{escape(name.replace('_', ' ').title())} "
            f"<span class='ha-chip-amt'>₹{amt:,.0f}</span></span>"
            for name, amt in analytics.top_items[:8]
        )
        parts.append(f"<div class='ha-section-h'>Top items</div><div class='ha-chips'>{chips}</div>")
    # Top merchants
    if analytics.top_merchants:
        chips = "".join(
            f"<span class='ha-chip'>{escape(merchant)} <span class='ha-chip-amt'>{count}</span></span>"
            for merchant, count in analytics.top_merchants
        )
        parts.append(f"<div class='ha-section-h'>Top merchants</div><div class='ha-chips'>{chips}</div>")
    # Waste rate
    if analytics.consume_count > 0:
        rate = analytics.waste_rate_pct
        rate_color = (
            "var(--green, #176B49)" if rate < 20 else
            "var(--amber, #A76012)" if rate < 40 else
            "var(--red, #A63F31)"
        )
        parts.append(
            "<div class='ha-waste'>"
            f"Waste rate (use-soon / consume): <strong style='color:{rate_color};'>{rate}%</strong> "
            f"({analytics.use_soon_count} / {analytics.consume_count})"
            "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


__all__ = [
    "HouseholdAnalytics",
    "aggregate_analytics",
    "render_analytics_html",
]
