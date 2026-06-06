"""Decision engine: classify household items into actionable categories.

Every item the household interacts with gets classified into one of:
  BUY       — needed and reasonably priced
  SKIP      — already have enough / bad price / not needed
  USE_SOON  — consume existing before buying more
  OPTIONAL  — okay but not urgent
  COMPARE   — need price/store/pack comparison
  CONFIRM   — uncertain data, needs human verification
  WATCH     — not urgent, monitor

This classification powers the Today dashboard, shopping list enrichment,
and market basket generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from html import escape
from typing import Any

from shopstack.persistence.database import Database
from shopstack.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class Decision(str, Enum):
    BUY = "buy"
    SKIP = "skip"
    USE_SOON = "use_soon"
    OPTIONAL = "optional"
    COMPARE = "compare"
    CONFIRM = "confirm"
    WATCH = "watch"


DECISION_COLORS: dict[str, str] = {
    "buy": "#22c55e",
    "skip": "#6b7280",
    "use_soon": "#f59e0b",
    "optional": "#3b82f6",
    "compare": "#8b5cf6",
    "confirm": "#ef4444",
    "watch": "#9ca3af",
}

DECISION_ICONS: dict[str, str] = {
    "buy": "&#x1F6D2;",
    "skip": "&#x23F9;",
    "use_soon": "&#x23F0;",
    "optional": "&#x2794;",
    "compare": "&#x2696;",
    "confirm": "&#x2753;",
    "watch": "&#x1F441;",
}


@dataclass
class ItemDecision:
    canonical_name: str
    display_name: str
    decision: str
    reason: str
    confidence: float
    quantity_at_home: float
    unit: str
    market_price: float | None
    market_price_per_kg: float | None
    market_available: bool
    market_raw_size: str
    shopping_list_status: str
    waste_risk: str
    shelf_life_days: int
    last_purchase_date: date | None
    location: str

    def badge_html(self) -> str:
        color = DECISION_COLORS.get(self.decision, "var(--text-dim)")
        icon = DECISION_ICONS.get(self.decision, "")
        return (
            f"<span style='background:{color}20;color:{color};"
            f"padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;'>"
            f"{icon} {self.decision.upper()}</span>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "display_name": self.display_name,
            "decision": self.decision,
            "reason": self.reason,
            "confidence": self.confidence,
            "quantity_at_home": self.quantity_at_home,
            "unit": self.unit,
            "market_price": self.market_price,
            "market_price_per_kg": self.market_price_per_kg,
            "market_available": self.market_available,
            "market_raw_size": self.market_raw_size,
            "shopping_list_status": self.shopping_list_status,
            "waste_risk": self.waste_risk,
            "shelf_life_days": self.shelf_life_days,
            "location": self.location,
        }


@dataclass
class DecisionSet:
    decisions: list[ItemDecision] = field(default_factory=list)

    @property
    def buy(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.BUY.value]

    @property
    def skip(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.SKIP.value]

    @property
    def use_soon(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.USE_SOON.value]

    @property
    def optional(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.OPTIONAL.value]

    @property
    def compare(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.COMPARE.value]

    @property
    def confirm(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.CONFIRM.value]

    @property
    def watch(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.WATCH.value]

    @property
    def estimated_basket_total(self) -> float:
        return round(sum(d.market_price or 0 for d in self.buy), 2)


_LOW_STOCK_THRESHOLD = 0.5
_USE_SOON_DAYS = 3
_RECENT_PURCHASE_DAYS = 2


def classify_all(
    db: Database,
    tools: ToolRegistry,
    market_snapshot=None,
) -> DecisionSet:
    """Build decisions for every active inventory item + shopping list item + market signal.

    Args:
        db: ShopStack database
        tools: tool registry
        market_snapshot: optional MarketSnapshot for price/availability signals
    """
    active_inv = [l for l in db.get_inventory() if l.status == "active"]
    use_soon_items = tools.get_use_soon_items(days=_USE_SOON_DAYS).get("items", [])
    active_list = db.get_active_shopping_list()
    purchases = db.get_purchase_events(limit=50)
    recent_dates: set[date] = set()
    for p in purchases:
        try:
            pdate = p.timestamp.date() if hasattr(p.timestamp, "date") else p.timestamp
            if pdate and pdate >= date.today() - timedelta(days=_RECENT_PURCHASE_DAYS):
                recent_dates.add(pdate)
        except Exception:
            pass

    use_soon_names = {item.get("canonical_name", "") for item in use_soon_items}
    list_names: set[str] = set()
    if active_list and active_list.items:
        list_names = {item.canonical_name for item in active_list.items if item.status in ("pending", "seen")}

    market_by_canonical: dict[str, Any] = {}
    if market_snapshot is not None:
        for r in market_snapshot.normalized_records:
            if r.is_available and r.is_weight_based and not r.is_combo:
                existing = market_by_canonical.get(r.canonical_name)
                if existing is None or (r.price_per_kg and existing.price_per_kg and r.price_per_kg < existing.price_per_kg):
                    market_by_canonical[r.canonical_name] = r

    seen: set[str] = set()
    decisions: list[ItemDecision] = []

    for lot in active_inv:
        cname = lot.canonical_name
        if cname in seen:
            continue
        seen.add(cname)

        meta = _get_produce_meta(cname)
        market = market_by_canonical.get(cname)

        use_soon_match = cname in use_soon_names
        low_stock = lot.quantity <= _LOW_STOCK_THRESHOLD or lot.status == "low"
        on_list = cname in list_names
        recently_bought = lot.purchase_date and lot.purchase_date in recent_dates

        decision, reason, confidence = _classify(
            quantity=lot.quantity,
            unit=lot.unit,
            low_stock=low_stock,
            use_soon=use_soon_match,
            on_list=on_list,
            recently_bought=bool(recently_bought),
            has_market=bool(market),
            waste_risk=meta.waste_risk if meta else "unknown",
        )

        decisions.append(ItemDecision(
            canonical_name=cname,
            display_name=lot.display_name,
            decision=decision,
            reason=reason,
            confidence=confidence,
            quantity_at_home=lot.quantity,
            unit=lot.unit,
            market_price=market.price_inr if market else None,
            market_price_per_kg=market.price_per_kg if market else None,
            market_available=bool(market),
            market_raw_size=market.raw_size if market else "",
            shopping_list_status="on_list" if on_list else "",
            waste_risk=meta.waste_risk if meta else "unknown",
            shelf_life_days=meta.shelf_life_days if meta else 0,
            last_purchase_date=lot.purchase_date,
            location=lot.storage_location_id or "",
        ))

    if active_list and active_list.items:
        for item in active_list.items:
            if item.status not in ("pending", "seen"):
                continue
            if item.canonical_name in seen:
                continue
            seen.add(item.canonical_name)

            inv_match = next((l for l in active_inv if l.canonical_name == item.canonical_name), None)
            meta = _get_produce_meta(item.canonical_name)
            market = market_by_canonical.get(item.canonical_name)
            qty = inv_match.quantity if inv_match else 0
            low_stock = qty <= _LOW_STOCK_THRESHOLD
            use_soon_match = item.canonical_name in use_soon_names

            if inv_match is None:
                decision = Decision.BUY.value
                reason = "On your list, not in inventory"
                confidence = 0.9
            else:
                decision, reason, confidence = _classify(
                    quantity=qty,
                    unit=inv_match.unit,
                    low_stock=low_stock,
                    use_soon=use_soon_match,
                    on_list=True,
                    recently_bought=False,
                    has_market=bool(market),
                    waste_risk=meta.waste_risk if meta else "unknown",
                )

            decisions.append(ItemDecision(
                canonical_name=item.canonical_name,
                display_name=item.canonical_name.replace("_", " ").title(),
                decision=decision,
                reason=reason,
                confidence=confidence,
                quantity_at_home=qty,
                unit=inv_match.unit if inv_match else "unit",
                market_price=market.price_inr if market else None,
                market_price_per_kg=market.price_per_kg if market else None,
                market_available=bool(market),
                market_raw_size=market.raw_size if market else "",
                shopping_list_status="on_list",
                waste_risk=meta.waste_risk if meta else "unknown",
                shelf_life_days=meta.shelf_life_days if meta else 0,
                last_purchase_date=inv_match.purchase_date if inv_match else None,
                location=inv_match.storage_location_id if inv_match else "",
            ))

    if market_snapshot is not None:
        for cname, r in market_by_canonical.items():
            if cname in seen:
                continue
            seen.add(cname)

            meta = _get_produce_meta(cname)
            price_ppk = r.price_per_kg or 0
            if price_ppk <= 0:
                continue

            all_weighted = [
                rec for rec in market_snapshot.normalized_records
                if rec.canonical_name == cname and rec.is_weight_based and not rec.is_combo
            ]
            if len(all_weighted) >= 2:
                prices = [rec.price_per_kg for rec in all_weighted if rec.price_per_kg]
                if prices and price_ppk <= min(prices) * 1.05:
                    decision = Decision.OPTIONAL.value
                    reason = f"Good price: &#8377;{price_ppk:.0f}/kg on Swiggy"
                    confidence = 0.7
                else:
                    decision = Decision.WATCH.value
                    reason = f"Available at &#8377;{price_ppk:.0f}/kg"
                    confidence = 0.5
            else:
                decision = Decision.WATCH.value
                reason = f"Available at &#8377;{price_ppk:.0f}/kg"
                confidence = 0.5

            decisions.append(ItemDecision(
                canonical_name=cname,
                display_name=cname.replace("_", " ").title(),
                decision=decision,
                reason=reason,
                confidence=confidence,
                quantity_at_home=0,
                unit="",
                market_price=r.price_inr,
                market_price_per_kg=r.price_per_kg,
                market_available=True,
                market_raw_size=r.raw_size,
                shopping_list_status="",
                waste_risk=meta.waste_risk if meta else "unknown",
                shelf_life_days=meta.shelf_life_days if meta else 0,
                last_purchase_date=None,
                location="",
            ))

    return DecisionSet(decisions=decisions)


def _classify(
    quantity: float,
    unit: str,
    low_stock: bool,
    use_soon: bool,
    on_list: bool,
    recently_bought: bool,
    has_market: bool,
    waste_risk: str,
) -> tuple[str, str, float]:
    """Core classification logic. Returns (decision, reason, confidence)."""

    if use_soon and quantity > 0:
        if low_stock:
            return Decision.USE_SOON.value, "Use remaining before it expires, then restock", 0.85
        return Decision.USE_SOON.value, "Use existing before buying more", 0.9

    if low_stock and quantity <= 0:
        if has_market:
            return Decision.BUY.value, "Out of stock, available on Swiggy", 0.9
        return Decision.BUY.value, "Out of stock", 0.85

    if low_stock:
        if has_market:
            return Decision.BUY.value, f"Running low ({quantity} {unit} left)", 0.85
        return Decision.BUY.value, f"Running low ({quantity} {unit} left)", 0.8

    if on_list and quantity > 0:
        if waste_risk == "high":
            return Decision.SKIP.value, "Already have enough, high waste risk if you buy more", 0.8
        return Decision.SKIP.value, "Already have enough at home", 0.75

    if quantity > 0 and not low_stock and not use_soon:
        if recently_bought:
            return Decision.SKIP.value, "Recently purchased", 0.8
        if waste_risk == "high":
            return Decision.SKIP.value, "Stocked, high waste risk", 0.7
        return Decision.SKIP.value, "Well stocked", 0.7

    return Decision.WATCH.value, "Monitor", 0.5


def _get_produce_meta(canonical_name: str):
    try:
        from shopstack.market.metadata import get_produce_metadata
        return get_produce_metadata(canonical_name)
    except Exception:
        return None


def render_market_basket(ds: DecisionSet) -> str:
    """Render the proposed market basket from a DecisionSet."""
    buy_items = ds.buy
    if not buy_items:
        return (
            "<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
            "<h3>Today's Market Basket</h3>"
            "<div style='color:var(--text-dim);'>Nothing to buy right now. Your pantry is in good shape.</div>"
            "</div>"
        )

    rows = []
    total = 0
    for d in sorted(buy_items, key=lambda x: x.confidence, reverse=True):
        price = d.market_price or 0
        total += price
        price_str = f"&#8377;{price:.0f}" if price > 0 else "price unknown"
        ppk = f" (&#8377;{d.market_price_per_kg:.0f}/kg)" if d.market_price_per_kg else ""
        rows.append(
            f"<div style='display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--border);'>"
            f"<div>"
            f"<div style='font-weight:600;'>{escape(d.display_name)}</div>"
            f"<div style='font-size:11px;color:var(--text-dim);'>{escape(d.reason)}{ppk}</div>"
            f"</div>"
            f"<div style='font-weight:600;color:#22c55e;'>{price_str}</div>"
            f"</div>"
        )

    skip_count = len(ds.skip)
    use_soon_count = len(ds.use_soon)
    savings_note = ""
    if skip_count > 0 or use_soon_count > 0:
        parts = []
        if skip_count:
            parts.append(f"{skip_count} item{'s' if skip_count != 1 else ''} skipped")
        if use_soon_count:
            parts.append(f"{use_soon_count} use-soon")
        savings_note = (
            f"<div style='margin-top:8px;font-size:11px;color:var(--text-dim);'>"
            f"Waste prevention: {' + '.join(parts)}"
            f"</div>"
        )

    return (
        f"<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
        f"<h3>Today's Market Basket</h3>"
        f"{''.join(rows)}"
        f"<div style='margin-top:8px;padding-top:8px;border-top:2px solid var(--border);display:flex;justify-content:space-between;'>"
        f"<span style='font-weight:600;'>Estimated total</span>"
        f"<span style='font-weight:700;font-size:16px;'>&#8377;{total:.0f}</span>"
        f"</div>"
        f"{savings_note}"
        f"</div>"
    )


def render_inventory_overview(all_inv: list[Any]) -> str:
    """Render a summary card for what is currently at home."""
    active_items = [lot for lot in all_inv if getattr(lot, "status", "") == "active"]
    total = len(active_items)
    location_counts: dict[str, int] = {}
    duplicates: dict[str, int] = {}
    recent = []
    for lot in active_items:
        location = lot.storage_location_id or "Unknown"
        location_counts[location] = location_counts.get(location, 0) + 1
        duplicates[lot.canonical_name] = duplicates.get(lot.canonical_name, 0) + 1
        purchase_date = getattr(lot, "purchase_date", None)
        if purchase_date:
            recent.append((purchase_date, lot.display_name, lot.quantity, lot.unit))

    duplicate_count = sum(1 for count in duplicates.values() if count > 1)
    recent = sorted(recent, key=lambda x: x[0], reverse=True)[:3]
    location_html = ", ".join(f"{escape(loc)}: {count}" for loc, count in sorted(location_counts.items(), key=lambda x: x[1], reverse=True))
    recent_html = "".join(
        f"<div style='padding:4px 0;border-bottom:1px solid var(--border);'><strong>{escape(name)}</strong> — {qty} {escape(unit)}</div>"
        for _date, name, qty, unit in recent
    )

    no_recent = "<div style='color:var(--text-dim);'>No recent additions recorded.</div>"

    return (
        "<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
        "<h3>What I Have</h3>"
        f"<div style='margin-bottom:8px;color:var(--text-dim);'>Total active inventory items: {total}</div>"
        f"<div style='font-size:12px;margin-bottom:8px;'>Locations: {escape(location_html or 'None')}</div>"
        f"<div style='font-size:12px;margin-bottom:8px;'>Duplicates: {duplicate_count}</div>"
        "<div style='font-weight:600;margin-bottom:4px;'>Recently added</div>"
        f"{recent_html or no_recent}"
        "</div>"
    )


def render_my_list_panel(ds: DecisionSet, active_list: Any) -> str:
    """Render the user's own shopping list enriched with decision annotations."""
    if not active_list or not getattr(active_list, "items", None):
        return (
            "<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
            "<h3>My Own List</h3>"
            "<div style='color:var(--text-dim);'>No active shopping list.</div>"
            "</div>"
        )

    rows = []
    for item in active_list.items[:10]:
        decision = next((d for d in ds.decisions if d.canonical_name == item.canonical_name), None)
        label = decision.decision.replace("_", " ").title() if decision else "Unknown"
        reason = decision.reason if decision else "No decision available"
        badge_color = DECISION_COLORS.get(decision.decision, "var(--text-dim)") if decision else "var(--text-dim)"
        rows.append(
            f"<div style='padding:6px 0;border-bottom:1px solid var(--border);'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<span>{escape(item.canonical_name.replace('_', ' ').title())}</span>"
            f"<span style='color:{badge_color};font-weight:600;'>{escape(label)}</span>"
            f"</div>"
            f"<div style='font-size:11px;color:var(--text-dim);'>{escape(reason)}</div>"
            f"</div>"
        )

    return (
        "<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
        "<h3>My Own List</h3>"
        f"{''.join(rows)}"
        "</div>"
    )


def render_compare_panel(ds: DecisionSet) -> str:
    """Render price and availability comparison signals for market intelligence."""
    compare_items = ds.compare
    watch_items = ds.watch
    confirm_items = ds.confirm

    if not compare_items and not watch_items and not confirm_items:
        return (
            "<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
            "<h3>Compare / Market Signals</h3>"
            "<div style='color:var(--text-dim);'>No comparison signals available.</div>"
            "</div>"
        )

    rows = []
    for d in compare_items[:4]:
        price = f" &#8377;{d.market_price_per_kg:.0f}/kg" if d.market_price_per_kg else ""
        rows.append(
            f"<div style='padding:6px 0;border-bottom:1px solid var(--border);'>"
            f"<strong style='color:#8b5cf6;'>Compare</strong> {escape(d.display_name)}"
            f"<div style='font-size:11px;color:var(--text-dim);'>{escape(d.reason)}{price}</div>"
            f"</div>"
        )
    for d in watch_items[:4]:
        rows.append(
            f"<div style='padding:6px 0;border-bottom:1px solid var(--border);'>"
            f"<strong style='color:#9ca3af;'>Watch</strong> {escape(d.display_name)}"
            f"<div style='font-size:11px;color:var(--text-dim);'>{escape(d.reason)}</div>"
            f"</div>"
        )
    for d in confirm_items[:4]:
        rows.append(
            f"<div style='padding:6px 0;border-bottom:1px solid var(--border);'>"
            f"<strong style='color:#ef4444;'>Confirm</strong> {escape(d.display_name)}"
            f"<div style='font-size:11px;color:var(--text-dim);'>{escape(d.reason)}</div>"
            f"</div>"
        )

    return (
        "<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
        "<h3>Compare / Market Signals</h3>"
        f"{''.join(rows)}"
        "</div>"
    )


def render_decision_panel(ds: DecisionSet) -> str:
    """Render the main Buy/Skip/Use-Soon decision panel for the dashboard."""
    buy = ds.buy
    skip = ds.skip
    use_soon = ds.use_soon

    if not buy and not skip and not use_soon:
        return (
            "<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
            "<h3>Today's Decisions</h3>"
            "<div style='color:var(--text-dim);'>No decisions yet. Add inventory or a shopping list to get started.</div>"
            "</div>"
        )

    sections: list[str] = []

    if buy:
        buy_rows = []
        for d in buy[:6]:
            price = f" &#8377;{d.market_price_per_kg:.0f}/kg" if d.market_price_per_kg else ""
            buy_rows.append(
                f"<div style='padding:5px 0;border-bottom:1px solid var(--border);'>"
                f"<strong style='color:#22c55e;'>Buy</strong> {escape(d.display_name)} "
                f"<span style='font-size:11px;color:var(--text-dim);'>{escape(d.reason)}{price}</span>"
                f"</div>"
            )
        sections.append("".join(buy_rows))

    if use_soon:
        us_rows = []
        for d in use_soon[:4]:
            us_rows.append(
                f"<div style='padding:5px 0;border-bottom:1px solid var(--border);'>"
                f"<strong style='color:#f59e0b;'>Use Soon</strong> {escape(d.display_name)} "
                f"<span style='font-size:11px;color:var(--text-dim);'>{escape(d.reason)}</span>"
                f"</div>"
            )
        sections.append("".join(us_rows))

    if skip:
        skip_rows = []
        for d in skip[:4]:
            skip_rows.append(
                f"<div style='padding:5px 0;border-bottom:1px solid var(--border);'>"
                f"<strong style='color:var(--text-dim);'>Skip</strong> {escape(d.display_name)} "
                f"<span style='font-size:11px;color:var(--text-dim);'>{escape(d.reason)}</span>"
                f"</div>"
            )
        sections.append("".join(skip_rows))

    return (
        f"<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
        f"<h3>Today's Decisions</h3>"
        f"{''.join(sections)}"
        f"</div>"
    )


def render_what_changed(db: Database) -> str:
    """Render recent activity timeline."""
    purchases = db.get_purchase_events(limit=5)
    traces = db.get_traces(limit=5)

    events: list[tuple[str, str, str]] = []

    for p in purchases[:3]:
        name = p.canonical_name.replace("_", " ").title()
        try:
            dt = p.timestamp if hasattr(p, "timestamp") else None
            date_str = dt.strftime("%b %d") if dt else "recently"
        except Exception:
            date_str = "recently"
        events.append((date_str, f"Added {name}", "purchase"))

    for t in traces[:3]:
        goal = (t.user_goal or "workflow").replace("_", " ").title()
        date_str = t.timestamp.strftime("%b %d %H:%M") if t.timestamp else "recently"
        events.append((date_str, goal, "trace"))

    if not events:
        return ""

    rows = []
    for date_str, desc, kind in events[:6]:
        icon = {"purchase": "&#x1F6D2;", "trace": "&#x1F50E;"}.get(kind, "&#x25CF;")
        rows.append(
            f"<div style='display:flex;gap:8px;padding:4px 0;border-bottom:1px solid var(--border);'>"
            f"<span style='font-size:11px;color:var(--text-dim);min-width:50px;'>{escape(date_str)}</span>"
            f"<span>{icon} {escape(desc)}</span>"
            f"</div>"
        )

    return (
        f"<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
        f"<h3>What Changed</h3>"
        f"{''.join(rows)}"
        f"</div>"
    )


def detect_purchase_cadence(db: Database) -> dict[str, dict[str, Any]]:
    """Analyze purchase history to detect buying rhythm per item.

    Returns: {canonical_name: {avg_interval_days, last_bought, typical_qty, next_expected}}
    """
    purchases = db.get_purchase_events(limit=200)
    by_item: dict[str, list[Any]] = {}
    for p in purchases:
        try:
            dt = p.timestamp if hasattr(p.timestamp, "year") else None
        except Exception:
            dt = None
        if dt is None:
            continue
        by_item.setdefault(p.canonical_name, []).append(p)

    cadence: dict[str, dict[str, Any]] = {}
    for cname, events in by_item.items():
        events.sort(key=lambda e: e.timestamp, reverse=True)
        if len(events) < 2:
            continue
        intervals = []
        for i in range(len(events) - 1):
            d1 = events[i].timestamp.date() if hasattr(events[i].timestamp, "date") else events[i].timestamp
            d2 = events[i + 1].timestamp.date() if hasattr(events[i + 1].timestamp, "date") else events[i + 1].timestamp
            if d1 and d2:
                gap = (d1 - d2).days
                if gap > 0:
                    intervals.append(gap)
        if not intervals:
            continue
        avg_interval = sum(intervals) / len(intervals)
        last = events[0].timestamp.date() if hasattr(events[0].timestamp, "date") else events[0].timestamp
        next_expected = last + timedelta(days=round(avg_interval))
        typical_qty = sum(e.quantity for e in events) / len(events)
        cadence[cname] = {
            "avg_interval_days": round(avg_interval, 1),
            "last_bought": last,
            "typical_qty": round(typical_qty, 2),
            "typical_unit": events[0].unit,
            "next_expected": next_expected,
            "purchase_count": len(events),
        }
    return cadence


def detect_waste_patterns(db: Database) -> list[dict[str, Any]]:
    """Detect items that are frequently bought but possibly wasted.

    Heuristic: item purchased 3+ times, but previous lot was still active when
    the next purchase happened (overlap), or item has high waste-risk metadata
    and is consistently overstocked.
    """
    cadence = detect_purchase_cadence(db)
    waste_signals: list[dict[str, Any]] = []
    inv = db.get_inventory()

    for cname, info in cadence.items():
        if info["purchase_count"] < 3:
            continue
        meta = _get_produce_meta(cname)
        waste_risk = meta.waste_risk if meta else "unknown"
        if waste_risk != "high":
            continue

        lot = next((l for l in inv if l.canonical_name == cname and l.status == "active"), None)
        overstocked = lot and lot.quantity > 1.0
        if overstocked or info["avg_interval_days"] < 2:
            waste_signals.append({
                "canonical_name": cname,
                "display_name": cname.replace("_", " ").title(),
                "reason": f"High waste-risk produce bought every {info['avg_interval_days']:.0f} days",
                "current_quantity": lot.quantity if lot else 0,
                "unit": lot.unit if lot else "unit",
                "waste_risk": waste_risk,
                "avg_interval_days": info["avg_interval_days"],
            })

    return waste_signals


def render_cadence_insights(db: Database) -> str:
    """Render purchase rhythm insights for the dashboard."""
    cadence = detect_purchase_cadence(db)
    if not cadence:
        return ""

    today = date.today()
    upcoming: list[tuple[int, str, str, str]] = []
    for cname, info in cadence.items():
        days_until = (info["next_expected"] - today).days
        if abs(days_until) <= 3:
            display = cname.replace("_", " ").title()
            if days_until <= 0:
                label = f"Due now ({info['typical_qty']:.0f} {info.get('typical_unit', 'unit')})"
            elif days_until == 1:
                label = f"Due tomorrow"
            else:
                label = f"Due in {days_until} days"
            upcoming.append((days_until, display, label, info.get("avg_interval_days", 0)))

    if not upcoming:
        return ""

    upcoming.sort(key=lambda x: x[0])
    rows = []
    for _, display, label, avg_days in upcoming[:5]:
        cadence_note = f"every {avg_days:.0f}d" if avg_days > 0 else ""
        rows.append(
            f"<div style='display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid var(--border);'>"
            f"<span style='font-weight:600;'>{escape(display)}</span>"
            f"<span style='font-size:11px;color:var(--text-dim);'>{escape(label)} {escape(cadence_note)}</span>"
            f"</div>"
        )

    return (
        f"<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
        f"<h3>Purchase Rhythm</h3>"
        f"{''.join(rows)}"
        f"</div>"
    )


def render_waste_warnings(db: Database) -> str:
    """Render waste/overbuying warnings."""
    signals = detect_waste_patterns(db)
    if not signals:
        return ""

    rows = []
    for s in signals[:3]:
        rows.append(
            f"<div style='padding:4px 0;border-bottom:1px solid var(--border);'>"
            f"<strong style='color:#ef4444;'>&#x26A0; {escape(s['display_name'])}</strong> "
            f"<span style='font-size:11px;color:var(--text-dim);'>{escape(s['reason'])}</span>"
            f"</div>"
        )

    return (
        f"<div class='stat-card' style='text-align:left;margin-bottom:12px;border-left:3px solid #ef4444;'>"
        f"<h3>Waste Prevention</h3>"
        f"{''.join(rows)}"
        f"</div>"
    )


def check_swiggy_availability(canonical_names: list[str]) -> dict[str, dict[str, Any]]:
    """Check which items are available/sold-out on Swiggy.

    Returns: {canonical_name: {available: bool, price: float, price_per_kg: float, raw_size: str}}
    """
    try:
        from shopstack.market.sources.swiggy import load_snapshot
        snap = load_snapshot()
    except Exception:
        return {}

    result: dict[str, dict[str, Any]] = {}
    all_records: dict[str, list[Any]] = {}
    for r in snap.normalized_records:
        all_records.setdefault(r.canonical_name, []).append(r)

    for cname in canonical_names:
        records = all_records.get(cname, [])
        if not records:
            continue
        available = [r for r in records if r.is_available]
        sold_out = [r for r in records if not r.is_available]
        if available:
            best = min(
                (r for r in available if r.is_weight_based and not r.is_combo and r.price_per_kg),
                key=lambda r: r.price_per_kg,
                default=available[0],
            )
            result[cname] = {
                "available": True,
                "price": best.price_inr,
                "price_per_kg": best.price_per_kg,
                "raw_size": best.raw_size,
            }
        elif sold_out:
            result[cname] = {
                "available": False,
                "price": sold_out[0].price_inr,
                "price_per_kg": sold_out[0].price_per_kg,
                "raw_size": sold_out[0].raw_size,
            }
    return result


def render_swiggy_soldout_warning(shopping_list_names: list[str]) -> str:
    """Check if any shopping list items are sold out on Swiggy."""
    avail = check_swiggy_availability(shopping_list_names)
    sold_out = {name: info for name, info in avail.items() if not info["available"]}
    if not sold_out:
        return ""

    rows = []
    for cname, info in sold_out.items():
        display = cname.replace("_", " ").title()
        rows.append(
            f"<div style='padding:4px 0;border-bottom:1px solid var(--border);'>"
            f"<strong style='color:#ef4444;'>&#x26A0; {escape(display)}</strong> "
            f"<span style='font-size:11px;color:var(--text-dim);'>Sold out on Swiggy Instamart</span>"
            f"</div>"
        )

    return (
        f"<div class='stat-card' style='text-align:left;margin-bottom:12px;border-left:3px solid #ef4444;'>"
        f"<h3>Availability Alert</h3>"
        f"{''.join(rows)}"
        f"</div>"
    )


def render_needs_confirmation(db: Database) -> str:
    """Render items needing human confirmation."""
    all_inv = db.get_inventory()
    uncertain = [
        l for l in all_inv
        if l.status == "active" and l.quantity > 0 and (
            not l.purchase_date
            or (date.today() - l.purchase_date).days > 14
        )
    ]

    if not uncertain:
        return ""

    rows = []
    for lot in uncertain[:5]:
        days = (date.today() - lot.purchase_date).days if lot.purchase_date else None
        if days is None:
            reason = "No purchase date recorded"
        else:
            reason = f"Last verified {days} days ago"
        rows.append(
            f"<div style='padding:4px 0;border-bottom:1px solid var(--border);'>"
            f"<strong>{escape(lot.display_name)}</strong> "
            f"<span style='font-size:11px;color:var(--text-dim);'>{escape(reason)}</span>"
            f"</div>"
        )

    return (
        f"<div class='stat-card' style='text-align:left;margin-bottom:12px;border-left:3px solid #ef4444;'>"
        f"<h3>Needs Confirmation</h3>"
        f"{''.join(rows)}"
        f"</div>"
    )
