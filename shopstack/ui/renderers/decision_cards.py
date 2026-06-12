"""HTML renderers for decision cards — buy/skip/use-soon panels and dashboard widgets.

Every function in this module takes typed data and returns an HTML string.
No decision logic, no database calls, no provider invocations.
"""

from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

from shopstack.schemas.models import DecisionSet, _ACTION_COLORS as DECISION_COLORS
from shopstack.ui.components.cards import render_action_grid, render_unified_decision_card

_LOW_STOCK_THRESHOLD = 0.5
_USE_SOON_DAYS = 3

_CARD_OPEN = "<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
_CARD_ALERT_OPEN = "<div class='stat-card' style='text-align:left;margin-bottom:12px;border-left:3px solid var(--red);'>"


def render_market_basket(ds: DecisionSet) -> str:
    buy_items = ds.buy
    if not buy_items:
        return (
            f"{_CARD_OPEN}<h3>Today's Market Basket</h3>"
            "<div style='color:var(--text-dim);'>Nothing to buy right now. Your pantry is in good shape.</div></div>"
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
            f"<div style='font-weight:600;color:var(--decision-buy);'>{price_str}</div>"
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
            f"Waste prevention: {' + '.join(parts)}</div>"
        )

    return (
        f"{_CARD_OPEN}<h3>Today's Market Basket</h3>"
        f"{''.join(rows)}"
        f"<div style='margin-top:8px;padding-top:8px;border-top:2px solid var(--border);display:flex;justify-content:space-between;'>"
        f"<span style='font-weight:600;'>Estimated total</span>"
        f"<span style='font-weight:700;font-size:16px;'>&#8377;{total:.0f}</span></div>"
        f"{savings_note}</div>"
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
        f"{_CARD_OPEN}<h3>What I Have</h3>"
        f"<div style='margin-bottom:8px;color:var(--text-dim);'>Total active inventory items: {total}</div>"
        f"<div style='font-size:12px;margin-bottom:8px;'>Locations: {escape(location_html or 'None')}</div>"
        f"<div style='font-size:12px;margin-bottom:8px;'>Duplicates: {duplicate_count}</div>"
        f"<div style='font-weight:600;margin-bottom:4px;'>Recently added</div>"
        f"{recent_html or no_recent}</div>"
    )


def render_my_list_panel(ds: DecisionSet, active_list: Any) -> str:
    if not active_list or not getattr(active_list, "items", None):
        return (
            f"{_CARD_OPEN}<h3>My Own List</h3>"
            "<div style='color:var(--text-dim);'>No active shopping list.</div></div>"
        )

    rows = []
    for item in active_list.items[:10]:
        decision = next((d for d in ds.decisions if d.canonical_name == item.canonical_name), None)
        label = decision.action.replace("_", " ").title() if decision else "Unknown"
        reason = decision.reason if decision else "No decision available"
        badge_color = DECISION_COLORS.get(decision.action, "var(--text-dim)") if decision else "var(--text-dim)"
        rows.append(
            f"<div style='padding:6px 0;border-bottom:1px solid var(--border);'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<span>{escape(item.canonical_name.replace('_', ' ').title())}</span>"
            f"<span style='color:{badge_color};font-weight:600;'>{escape(label)}</span></div>"
            f"<div style='font-size:11px;color:var(--text-dim);'>{escape(reason)}</div></div>"
        )

    return f"{_CARD_OPEN}<h3>My Own List</h3>{''.join(rows)}</div>"


def render_compare_panel(ds: DecisionSet) -> str:
    compare_items = ds.compare
    wait_items = ds.wait

    if not compare_items and not wait_items:
        return (
            f"{_CARD_OPEN}<h3>Compare / Market Signals</h3>"
            "<div style='color:var(--text-dim);'>No comparison signals available.</div></div>"
        )

    rows = []
    for d in compare_items[:4]:
        rows.append(render_unified_decision_card(d))
    for d in wait_items[:4]:
        rows.append(render_unified_decision_card(d))

    bridge_actions = [
        {
            "label": "Open Shopping",
            "subtitle": "Turn compare items into a list",
            "tab_id": "basket",
            "tone": "primary",
        },
        {
            "label": "Open Pantry",
            "subtitle": "Check what is already covered",
            "tab_id": "reconcile",
            "tone": "default",
        },
        {
            "label": "Open Memory",
            "subtitle": "Compare against your price baseline",
            "tab_id": "memory",
            "tone": "default",
        },
    ]

    compare_preview = ""
    if compare_items:
        preview_rows = []
        for d in compare_items[:3]:
            preview_rows.append(
                f"<div style='display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid var(--border);'>"
                f"<strong>{escape(d.display_name)}</strong>"
                f"<span style='color:var(--text-dim);font-size:12px;'>{escape(d.reason or 'Compare signal')}</span>"
                "</div>"
            )
        compare_preview = (
            "<div style='margin:6px 0 10px 0;padding:8px;border:1px solid var(--border);border-radius:8px;'>"
            "<div style='font-size:12px;font-weight:600;margin-bottom:6px;'>Compare bridge</div>"
            + "".join(preview_rows)
            + "</div>"
        )

    note = (
        "<div style='font-size:11px;color:var(--text-dim);margin:6px 0 10px 0;'>"
        "Market Map adds freshness, combo overlap, and substitute context for these signals."
        "</div>"
    )
    return f"{_CARD_OPEN}<h3>Compare / Market Signals</h3>{note}{compare_preview}{render_action_grid(bridge_actions)}{''.join(rows)}</div>"


def render_decision_panel(ds: DecisionSet) -> str:
    buy = ds.buy
    skip = ds.skip
    use_soon = ds.use_soon

    if not buy and not skip and not use_soon:
        return (
            f"{_CARD_OPEN}<h3>Today's Decisions</h3>"
            "<div style='color:var(--text-dim);'>No decisions yet. Add inventory or a shopping list to get started.</div></div>"
        )

    sections: list[str] = []

    if buy:
        buy_rows = [render_unified_decision_card(d) for d in buy[:6]]
        sections.append("".join(buy_rows))

    if use_soon:
        us_rows = [render_unified_decision_card(d) for d in use_soon[:4]]
        sections.append("".join(us_rows))

    if skip:
        skip_rows = [render_unified_decision_card(d) for d in skip[:4]]
        sections.append("".join(skip_rows))

    return f"<div style='margin-bottom:12px;'><h3>Today's Decisions</h3>{''.join(sections)}</div>"


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
            f"<span>{icon} {escape(desc)}</span></div>"
        )

    return f"{_CARD_OPEN}<h3>What Changed</h3>{''.join(rows)}</div>"


def render_cadence_insights(cadence: dict[str, dict[str, Any]], today: date | None = None) -> str:
    if not cadence:
        return ""

    today = today or date.today()
    upcoming: list[tuple[int, str, str, Any]] = []
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
        cadence_note = f"every {float(avg_days):.0f}d" if float(avg_days) > 0 else ""
        rows.append(
            f"<div style='display:flex;justify-content:space-between;align-items:center;padding:4px 0;border-bottom:1px solid var(--border);'>"
            f"<span style='font-weight:600;'>{escape(display)}</span>"
            f"<span style='font-size:11px;color:var(--text-dim);'>{escape(label)} {escape(cadence_note)}</span></div>"
        )

    return f"{_CARD_OPEN}<h3>Purchase Rhythm</h3>{''.join(rows)}</div>"


def render_waste_warnings(signals: list[dict[str, Any]]) -> str:
    if not signals:
        return ""

    rows = []
    for s in signals[:3]:
        rows.append(
            f"<div style='padding:4px 0;border-bottom:1px solid var(--border);'>"
            f"<strong style='color:var(--red);'>&#x26A0; {escape(s['display_name'])}</strong> "
            f"<span style='font-size:11px;color:var(--text-dim);'>{escape(s['reason'])}</span></div>"
        )

    return f"{_CARD_ALERT_OPEN}<h3>Waste Prevention</h3>{''.join(rows)}</div>"


def render_swiggy_soldout_warning(availability: dict[str, dict[str, Any]]) -> str:
    sold_out = {name: info for name, info in availability.items() if not info.get("available")}
    if not sold_out:
        return ""

    rows = []
    for cname, info in sold_out.items():
        display = cname.replace("_", " ").title()
        rows.append(
            f"<div style='padding:4px 0;border-bottom:1px solid var(--border);'>"
            f"<strong style='color:var(--red);'>&#x26A0; {escape(display)}</strong> "
            f"<span style='font-size:11px;color:var(--text-dim);'>Sold out on Swiggy Instamart</span></div>"
        )

    return f"{_CARD_ALERT_OPEN}<h3>Availability Alert</h3>{''.join(rows)}</div>"


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
            f"<span style='font-size:11px;color:var(--text-dim);'>{escape(reason)}</span></div>"
        )

    return f"{_CARD_ALERT_OPEN}<h3>Needs Confirmation</h3>{''.join(rows)}</div>"


def render_restock_predictions(predictions: list[dict[str, Any]]) -> str:
    """Render proactive restock suggestions from consumption prediction."""
    if not predictions:
        return ""

    urgency_colors = {"overdue": "var(--red)", "due_today": "var(--amber)", "due_soon": "var(--blue)"}
    rows = []
    for p in predictions[:6]:
        name = escape(p["canonical_name"].replace("_", " ").title())
        urgency = p.get("urgency", "due_soon")
        color = urgency_colors.get(urgency, "var(--text-dim)")
        reason = escape(p.get("reason", ""))
        qty = f"{p.get('typical_qty', 1.0):.0f} {p.get('typical_unit', 'unit')}"
        on_hand = p.get("quantity_at_home", 0)
        on_hand_str = f" ({on_hand:.1f} at home)" if on_hand > 0 else ""
        rows.append(
            f"<div style='padding:4px 0;border-bottom:1px solid var(--border);'>"
            f"<span style='font-weight:600;color:{color};'>&#9679; {name}</span> "
            f"<span style='font-size:11px;color:var(--text-dim);'>{reason}{on_hand_str} &middot; {qty}</span></div>"
        )

    return f"{_CARD_ALERT_OPEN}<h3>Restock Predictions</h3>{''.join(rows)}</div>"


def render_price_deals(deals: list[dict[str, Any]]) -> str:
    """Render price deal scores for buy items."""
    if not deals:
        return ""

    score_colors = {"great": "var(--green)", "good": "var(--green)", "fair": "var(--blue)", "poor": "var(--red)"}
    rows = []
    for d in deals[:6]:
        name = escape(d.get("product", "").replace("_", " ").title())
        score = d.get("score", "unknown")
        color = score_colors.get(score, "var(--text-dim)")
        reason = escape(d.get("reason", ""))
        badge = f"<span style='font-size:10px;font-weight:600;color:{color};'>[{score.upper()}]</span>"
        rows.append(
            f"<div style='padding:4px 0;border-bottom:1px solid var(--border);'>"
            f"<strong>{name}</strong> {badge} "
            f"<span style='font-size:11px;color:var(--text-dim);'>{reason}</span></div>"
        )

    return f"{_CARD_OPEN}<h3>Price Deals</h3>{''.join(rows)}</div>"


def render_best_store(store_data: dict[str, Any]) -> str:
    """Render best store recommendation."""
    if not store_data or not store_data.get("store"):
        return ""

    store = escape(store_data["store"])
    best_count = store_data.get("items_with_best_price", 0)
    total = store_data.get("total_items_compared", 0)
    coverage = store_data.get("coverage_pct", 0)
    savings = store_data.get("estimated_savings_vs_worst", 0)

    return (
        f"{_CARD_OPEN}<h3>Best Store</h3>"
        f"<div style='font-size:14px;padding:4px 0;'>"
        f"<strong>{store}</strong> has the best price for "
        f"{best_count}/{total} items ({coverage:.0f}% coverage)."
        f"</div>"
        f"<div style='font-size:11px;color:var(--text-dim);'>"
        f"Estimated savings vs worst store: &#8377;{savings:.0f}</div></div>"
    )


def render_optimized_basket_summary(basket: Any) -> str:
    """Render a compact optimized basket summary."""
    if basket is None:
        return ""

    buy_items = basket.buy if hasattr(basket, "buy") else []
    skip_items = basket.skip if hasattr(basket, "skip") else []
    total = basket.total_estimated if hasattr(basket, "total_estimated") else 0

    if not buy_items:
        return ""

    rows = []
    for item in buy_items[:6]:
        name = escape(item.canonical_name.replace("_", " ").title())
        price = f"&#8377;{item.estimated_price_inr:.0f}" if item.estimated_price_inr else ""
        reason = escape(item.reason.split(".")[0]) if item.reason else ""
        rows.append(
            f"<div style='display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid var(--border);'>"
            f"<span>{name}</span>"
            f"<span style='font-weight:600;font-size:12px;'>{price}</span></div>"
        )

    skip_note = f"<div style='font-size:11px;color:var(--text-dim);margin-top:4px;'>+ {len(skip_items)} skipped</div>" if skip_items else ""

    return (
        f"{_CARD_OPEN}<h3>Optimized Basket</h3>"
        f"{''.join(rows)}{skip_note}"
        f"<div style='margin-top:6px;font-weight:700;font-size:16px;'>Total: &#8377;{total:.0f}</div></div>"
    )
