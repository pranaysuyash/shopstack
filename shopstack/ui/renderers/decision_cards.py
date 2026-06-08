"""HTML renderers for decision cards — buy/skip/use-soon panels and dashboard widgets.

Every function in this module takes typed data and returns an HTML string.
No decision logic, no database calls, no provider invocations.
"""

from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

from shopstack.decisions.types import DECISION_COLORS, DecisionSet

_LOW_STOCK_THRESHOLD = 0.5
_USE_SOON_DAYS = 3


def render_market_basket(ds: DecisionSet) -> str:
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
        f"<div style='padding:4px 0;border-bottom:1px solid var(--border);'><strong>{escape(name)}</strong> &mdash; {qty} {escape(unit)}</div>"
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


def render_what_changed(purchases: list[Any], traces: list[Any]) -> str:
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


def render_cadence_insights(cadence: dict[str, dict[str, Any]], today: date | None = None) -> str:
    if not cadence:
        return ""

    today = today or date.today()
    upcoming: list[tuple[int, str, str, str]] = []
    for cname, info in cadence.items():
        days_until = (info["next_expected"] - today).days
        if abs(days_until) <= 3:
            display = cname.replace("_", " ").title()
            if days_until <= 0:
                label = f"Due now ({info['typical_qty']:.0f} {info.get('typical_unit', 'unit')})"
            elif days_until == 1:
                label = "Due tomorrow"
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


def render_waste_warnings(signals: list[dict[str, Any]]) -> str:
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


def render_swiggy_soldout_warning(availability: dict[str, dict[str, Any]]) -> str:
    sold_out = {name: info for name, info in availability.items() if not info.get("available")}
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


def render_needs_confirmation(uncertain: list[Any]) -> str:
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
