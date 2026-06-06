from __future__ import annotations

import logging
from html import escape

from shopstack.app_context import db, tools
from shopstack.ui import render_action_grid, render_hero_panel, render_metric
from shopstack.ui.screens._utils import (
    safe_render,
    render_home_advice,
    render_list_summary,
)
from shopstack.ui.screens.other import inventory_alerts, what_is_in_fridge_now

logger = logging.getLogger(__name__)


@safe_render
def today_dashboard():
    from shopstack.decisions import (
        classify_all,
        render_decision_panel,
        render_market_basket,
        render_inventory_overview,
        render_my_list_panel,
        render_compare_panel,
        render_what_changed,
        render_needs_confirmation,
        render_cadence_insights,
        render_waste_warnings,
    )

    try:
        from shopstack.market.sources.swiggy import load_snapshot
        market_snapshot = load_snapshot()
    except Exception as exc:
        logger.info("Swiggy market data unavailable: %s", exc)
        market_snapshot = None

    ds = classify_all(db, tools, market_snapshot)

    use_soon = tools.get_use_soon_items(days=3)
    soon_count = use_soon.get("count", len(use_soon.get("items", [])))
    use_soon_items = use_soon.get("items", [])
    active_list = db.get_active_shopping_list()
    all_inv = db.get_inventory()
    active_inv = [l for l in all_inv if l.status == "active"]
    low_items = [l for l in active_inv if l.quantity <= 0.5 or l.status == "low"]
    purchases = db.get_purchase_events(limit=5)

    hero = render_hero_panel(
        "Good day. What should your home remember today?",
        f"{len(ds.buy)} to buy, {len(ds.skip)} to skip, {len(ds.use_soon)} to use soon.",
        "Household Memory",
    )

    quick_actions = (
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:12px 0 16px 0;'>"
        f"{render_metric('Active items', str(len(active_inv)), tab_id='inventory')}"
        f"{render_metric('Use soon', str(soon_count), tab_id='usesoon')}"
        f"{render_metric('Low stock', str(len(low_items)), tab_id='usesoon')}"
        f"{render_metric('Recent purchases', str(len(purchases)), tab_id='purchase')}"
        "</div>"
    )

    action_bar = render_action_grid([
        {
            "label": "Market Lens",
            "subtitle": "Check a shelf item before buying",
            "tab_id": "market",
            "tone": "primary",
        },
        {
            "label": "Add Purchase",
            "subtitle": "Teach the home what changed",
            "tab_id": "purchase",
            "tone": "default",
        },
        {
            "label": "Inventory",
            "subtitle": "Find what is already at home",
            "tab_id": "inventory",
            "tone": "default",
        },
    ])

    decision_panel = render_decision_panel(ds)
    market_basket = render_market_basket(ds)
    list_panel = render_my_list_panel(ds, active_list)
    inventory_overview = render_inventory_overview(all_inv)
    compare_panel = render_compare_panel(ds)

    alert_html = inventory_alerts(days_since_purchase=3)
    fridge_html = what_is_in_fridge_now()
    what_changed = render_what_changed(db)
    needs_confirm = render_needs_confirmation(db)
    cadence_html = render_cadence_insights(db)
    waste_html = render_waste_warnings(db)

    long_grid = (
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px;margin-bottom:10px;'>{inventory_overview}{compare_panel}</div>"
        + f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;'>{fridge_html}{alert_html}{needs_confirm}{cadence_html}{waste_html}</div>"
    )

    return [
        f"{hero}{action_bar}{quick_actions}",
        decision_panel,
        market_basket,
        list_panel,
        long_grid,
        f"{what_changed}",
    ]
