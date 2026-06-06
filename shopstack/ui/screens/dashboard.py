from __future__ import annotations

from html import escape

from shopstack.app_context import db, tools
from shopstack.ui import card as ui_card, render_metric
from shopstack.ui.screens._utils import (
    WORKFLOW_NAV,
    safe_render,
    workflow_header,
    render_home_advice,
    render_list_summary,
    render_low_stock,
    render_recent_purchases,
)
from shopstack.ui.screens.inventory import seed_demo_inventory
from shopstack.ui.screens.other import inventory_alerts, price_intelligence_view, what_is_in_fridge_now


def _swiggy_top_deals_html() -> str:
    try:
        from shopstack.market.sources.swiggy import load_snapshot
        snapshot = load_snapshot()
    except Exception:
        return ""

    available_weighted = [
        r for r in snapshot.normalized_records
        if r.is_available and r.is_weight_based and not r.is_combo and r.price_per_kg
    ]
    if not available_weighted:
        return ""

    sorted_deals = sorted(available_weighted, key=lambda r: r.price_per_kg)[:5]
    rows = "".join(
        f"<div style='display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid var(--border);'>"
        f"<span>{escape(r.canonical_name.replace('_', ' ').title())}</span>"
        f"<span><strong>&#8377;{r.price_per_kg:.0f}/kg</strong> <span style='color:var(--text-dim);font-size:11px;'>({escape(r.raw_size)})</span></span>"
        f"</div>"
        for r in sorted_deals
    )
    return (
        "<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
        "<h3>Live Market &#8212; Cheapest Produce Today</h3>"
        f"{rows}"
        "<div style='margin-top:6px;font-size:11px;color:var(--text-dim);'>Source: Swiggy Instamart</div>"
        "</div>"
    )


@safe_render
def today_dashboard():
    use_soon = tools.get_use_soon_items(days=3)
    soon_count = use_soon["count"]
    active_list = db.get_active_shopping_list()
    all_inv = db.get_inventory()
    active_inv = [l for l in all_inv if l.status == "active"]
    low_items = [l for l in active_inv if l.quantity <= 0.5 or l.status == "low"]
    purchases = db.get_purchase_events(limit=5)

    hero = (
        "<div class='home-card' style='margin-bottom:10px;'>"
        "<h2>Good day. What should your home remember today?</h2>"
        "<div style='color:var(--text-dim);'>Use what you've got, buy what you need, and skip what you already have.</div>"
        "</div>"
    )
    workflow_preview = (
        "<div class='home-card' style='text-align:left;margin-bottom:12px;'>"
        "<div style='font-size:12px;text-transform:uppercase;letter-spacing:0.4px;color:var(--text-dim);margin-bottom:8px;'>"
        "Workflow previews</div>"
        + "".join(
            f"<div style='padding:7px 0;border-bottom:1px solid var(--border);'><strong>{name}</strong> <span style='color:var(--text-dim);'>\u2014 task-first household workflow</span></div>"
            for name in WORKFLOW_NAV
        )
        + "</div>"
    )
    quick_actions = (
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:12px 0 16px 0;'>"
        f"{render_metric('Active items', str(len(active_inv)), tab_id='inventory')}"
        f"{render_metric('Use soon', str(soon_count), tab_id='usesoon')}"
        f"{render_metric('Low stock', str(len(low_items)), tab_id='usesoon')}"
        f"{render_metric('Recent purchases', str(len(purchases)), tab_id='purchase')}"
        "</div>"
    )

    action_bar = (
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:0 0 10px 0;'>"
        "<a href='#market' class='gr-button' style='text-align:center;text-decoration:none;padding:8px 12px;'>Market Lens</a>"
        "<a href='#purchase' class='gr-button' style='text-align:center;text-decoration:none;padding:8px 12px;'>Add Purchase</a>"
        "<a href='#inventory' class='gr-button' style='text-align:center;text-decoration:none;padding:8px 12px;'>Inventory</a>"
        "</div>"
    )
    alert_html = inventory_alerts(days_since_purchase=3)
    fridge_html = what_is_in_fridge_now()

    try:
        price_alerts = price_intelligence_view()
    except Exception:
        price_alerts = ""

    swiggy_deals = _swiggy_top_deals_html()

    return [
        f"{hero}{workflow_preview}{action_bar}{quick_actions}",
        render_home_advice(active_inv, low_items, use_soon["items"][:3]),
        render_list_summary(active_list),
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;'>{fridge_html}{alert_html}</div>",
        f"<div class='stat-card' style='text-align:left;margin-bottom:12px;'><h3>Low Stock</h3>{render_low_stock(low_items)}</div>",
        f"<div class='stat-card' style='text-align:left;margin-bottom:12px;'><h3>Recent Purchases</h3>{render_recent_purchases(purchases)}</div>"
        + (f"<div style='margin-top:12px;'>{price_alerts}</div>" if price_alerts and "No price intelligence" not in price_alerts else "")
        + (f"<div style='margin-top:12px;'>{swiggy_deals}</div>" if swiggy_deals else ""),
    ]
