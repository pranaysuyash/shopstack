from __future__ import annotations

import logging

from shopstack.app_context import APP_DESCRIPTION, APP_NAME, db, tools
from shopstack.services.dashboard import build_dashboard_state
from shopstack.ui.components.cards import render_action_grid, render_hero_panel
from shopstack.ui.components.primitives import stat_card, item_row
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

    state = build_dashboard_state(db, tools.inventory)
    ds = state.decision_set

    hero = render_hero_panel(
        f"Good day. {APP_DESCRIPTION}",
        f"{len(ds.buy)} to buy, {len(ds.skip)} to skip, {len(ds.use_soon)} to use soon.",
        APP_NAME,
    )

    quick_actions = (
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:12px 0 16px 0;'>"
        f"{stat_card(str(len(state.active_inventory)), 'Active items', on_click_tab='reconcile')}"
        f"{stat_card(str(state.use_soon_count), 'Use soon', variant='warning', on_click_tab='reconcile')}"
        f"{stat_card(str(len(state.low_items)), 'Low stock', variant='danger', on_click_tab='reconcile')}"
        f"{stat_card(str(len(state.recent_purchases)), 'Recent buys', on_click_tab='reconcile')}"
        "</div>"
    )

    loop_actions = render_action_grid([
        {
            "label": "Basket",
            "subtitle": "Plan what to buy, skip, or compare",
            "tab_id": "basket",
            "tone": "primary",
        },
        {
            "label": "ShopLens",
            "subtitle": "Check a shelf item before buying",
            "tab_id": "market",
            "tone": "default",
        },
        {
            "label": "Reconcile",
            "subtitle": "Log purchases, update stock, check expiries",
            "tab_id": "reconcile",
            "tone": "default",
        },
        {
            "label": "Memory",
            "subtitle": "Notes, traces, nutrition, what we learned",
            "tab_id": "memory",
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

    svg_section = ""

    long_grid = (
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px;margin-bottom:10px;'>{inventory_overview}{compare_panel}</div>"
        + f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;'>{fridge_html}{alert_html}{needs_confirm}{cadence_html}{waste_html}</div>"
        + f"{what_changed}"
    )

    return [
        f"{hero}{loop_actions}{quick_actions}",
        decision_panel,
        svg_section,
        market_basket,
        list_panel,
        long_grid,
    ]
