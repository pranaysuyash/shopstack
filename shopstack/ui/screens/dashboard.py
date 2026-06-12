from __future__ import annotations

import logging

from shopstack.app_context import APP_DESCRIPTION, APP_NAME, db, tools, current_user_id
from shopstack.services.dashboard import build_dashboard_state
from shopstack.ui.components.cards import render_action_grid, render_hero_panel
from shopstack.ui.components.primitives import stat_card, item_row
from shopstack.ui.renderers import render_cadence_insights, render_waste_warnings
from shopstack.ui.renderers.decision_cards import (
    render_restock_predictions,
    render_price_deals,
    render_best_store,
    render_optimized_basket_summary,
)
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
    uid = current_user_id()
    from shopstack.decisions import (
        render_decision_panel,
        render_market_basket,
        render_inventory_overview,
        render_my_list_panel,
        render_compare_panel,
        render_what_changed,
        render_needs_confirmation,
    )
    from shopstack.ui.screens.model_stack import runtime_proof_view

    state = build_dashboard_state(db, tools.inventory, user_id=uid)
    ds = state.decision_set

    hero = render_hero_panel(
        f"Good day. {APP_DESCRIPTION}",
        f"{len(ds.buy)} to buy, {len(ds.skip)} to skip, {len(ds.use_soon)} to use soon.",
        APP_NAME,
    )
    runtime_proof = runtime_proof_view()

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
    restock_html = render_restock_predictions(state.restock_predictions)
    deals_html = render_price_deals(state.price_deals)
    best_store_html = render_best_store(state.best_store)
    basket_summary_html = render_optimized_basket_summary(state.optimized_basket)

    show_empty_hints = (
        not state.active_inventory
        and not state.recent_purchases
        and state.active_list is None
    )
    empty_state = _render_today_empty_hints() if show_empty_hints else ""

    svg_section = ""

    long_grid = (
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px;margin-bottom:10px;'>{inventory_overview}{compare_panel}</div>"
        + f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;'>{fridge_html}{alert_html}{needs_confirm}{cadence_html}{waste_html}{restock_html}</div>"
        + f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;'>{deals_html}{best_store_html}{basket_summary_html}</div>"
        + f"{what_changed}"
    )

    return [
        f"{hero}{runtime_proof}{loop_actions}{quick_actions}{empty_state}",
        decision_panel,
        svg_section,
        market_basket,
        list_panel,
        long_grid,
    ]


def _render_today_empty_hints() -> str:
    return (
        "<div class='home-card' style='margin-top:10px;'>"
        "<h3>Start your first flow</h3>"
        "<div class='muted' style='margin-bottom:8px;'>No inventory data yet — try one path to begin:</div>"
        f"{render_action_grid([
            {
                "label": "Build a basket",
                "subtitle": "Create shopping list from free text or compare list",
                "tab_id": "basket",
                "tone": "primary",
            },
            {
                "label": "Scan with ShopLens",
                "subtitle": "Capture shelf items and compare to home inventory",
                "tab_id": "market",
                "tone": "default",
            },
            {
                "label": "Log a purchase",
                "subtitle": "Add purchase records and seed your pantry",
                "tab_id": "reconcile",
                "tone": "default",
            },
            {
                "label": "Try receipt flow",
                "subtitle": "Paste or upload receipts to reconcile",
                "tab_id": "reconcile",
                "tone": "default",
            },
        ])}"
        "</div>"
    )
