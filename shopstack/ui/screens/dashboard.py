from __future__ import annotations

import logging

from shopstack.app_context import APP_DESCRIPTION, APP_NAME, db, tools
from shopstack.services.dashboard import build_dashboard_state
from shopstack.ui import render_action_grid, render_hero_panel, render_metric
from shopstack.ui.renderers import render_cadence_insights, render_waste_warnings
from shopstack.ui.renderers.image_cards import (
    cards_to_grid,
    render_decision_card as render_svg_decision_card,
    render_shopping_summary_card as render_svg_summary,
)
from shopstack.ui.screens._utils import (
    safe_render,
)
from shopstack.ui.screens.other import inventory_alerts, what_is_in_fridge_now

logger = logging.getLogger(__name__)


@safe_render
def today_dashboard():
    from shopstack.decisions import (
        render_decision_panel,
        render_market_basket,
        render_inventory_overview,
        render_my_list_panel,
        render_compare_panel,
        render_what_changed,
        render_needs_confirmation,
    )

    state = build_dashboard_state(db, tools)
    ds = state.decision_set

    hero = render_hero_panel(
        f"Good day. {APP_DESCRIPTION}",
        f"{len(ds.buy)} to buy, {len(ds.skip)} to skip, {len(ds.use_soon)} to use soon.",
        APP_NAME,
    )

    quick_actions = (
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:12px 0 16px 0;'>"
        f"{render_metric('Active items', str(len(state.active_inventory)), tab_id='inventory')}"
        f"{render_metric('Use soon', str(state.use_soon_count), tab_id='usesoon')}"
        f"{render_metric('Low stock', str(len(state.low_items)), tab_id='usesoon')}"
        f"{render_metric('Recent purchases', str(len(state.recent_purchases)), tab_id='purchase')}"
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
    list_panel = render_my_list_panel(ds, state.active_list)
    inventory_overview = render_inventory_overview(state.all_inventory)
    compare_panel = render_compare_panel(ds)

    alert_html = inventory_alerts(days_since_purchase=3)
    fridge_html = what_is_in_fridge_now()
    what_changed = render_what_changed(db)
    needs_confirm = render_needs_confirmation(db)
    cadence_html = render_cadence_insights(state.cadence_data)
    waste_html = render_waste_warnings(state.waste_data)

    svg_cards: list[str] = []
    for d in ds.buy[:6]:
        svg_cards.append(render_svg_decision_card(d.display_name, "buy", d.reason, d.confidence))
    for d in ds.use_soon[:3]:
        svg_cards.append(render_svg_decision_card(d.display_name, "use_soon", d.reason, d.confidence))
    for d in ds.skip[:3]:
        svg_cards.append(render_svg_decision_card(d.display_name, "skip", d.reason, d.confidence))

    svg_section = ""
    if svg_cards:
        svg_grid = cards_to_grid(svg_cards, columns=3)
        svg_section = (
            f"<div class='stat-card' style='text-align:left;margin-bottom:12px;'>"
            f"<h3>Decision Cards</h3>{svg_grid}</div>"
        )

    if ds.buy or ds.skip:
        svg_summary = render_svg_summary(
            items_bought=len(ds.buy),
            items_skipped=len(ds.skip),
            total_saved=sum(d.market_price or 0 for d in ds.skip),
        )
        svg_section += (
            f"<div class='stat-card' style='margin-bottom:12px;'>"
            f"{svg_summary}</div>"
        )

    long_grid = (
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px;margin-bottom:10px;'>{inventory_overview}{compare_panel}</div>"
        + f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;'>{fridge_html}{alert_html}{needs_confirm}{cadence_html}{waste_html}</div>"
    )

    return [
        f"{hero}{action_bar}{quick_actions}",
        decision_panel,
        svg_section,
        market_basket,
        list_panel,
        long_grid,
        f"{what_changed}",
    ]
