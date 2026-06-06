from __future__ import annotations

from shopstack.app_context import db, tools
from shopstack.ui import card as ui_card, render_metric
from shopstack.ui.screens._utils import (
    WORKFLOW_NAV,
    workflow_header,
    render_home_advice,
    render_list_summary,
    render_low_stock,
    render_recent_purchases,
)


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

    return [
        f"{hero}{workflow_preview}{quick_actions}",
        render_home_advice(active_inv, low_items, use_soon["items"][:3]),
        render_list_summary(active_list),
        f"<div class='stat-card' style='text-align:left;margin-bottom:12px;'><h3>Low Stock</h3>{render_low_stock(low_items)}</div>",
        f"<div class='stat-card' style='text-align:left;margin-bottom:12px;'><h3>Recent Purchases</h3>{render_recent_purchases(purchases)}</div>",
    ]
