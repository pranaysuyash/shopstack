from __future__ import annotations

from html import escape
import logging

from shopstack.app_context import APP_DESCRIPTION, APP_NAME, db, tools, current_user_id
from shopstack.services.dashboard import build_dashboard_state
from shopstack.ui.components.cards import card as ui_card
from shopstack.ui.components.cards import badge_html
from shopstack.ui.components.cards import render_action_grid, render_hero_panel
from shopstack.ui.components.primitives import stat_card, item_row
from shopstack.ui.renderers import (
    render_cadence_insights,
    render_waste_warnings,
    render_price_drops,
)
from shopstack.services.waste_coach import render_waste_coach_html
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


def _details_section(title: str, body: str, description: str = "") -> str:
    description_html = (
        f"<div class='muted' style='margin:8px 0 12px;'>{escape(description)}</div>"
        if description
        else ""
    )
    return (
        "<details class='home-details'>"
        f"<summary>{escape(title)}</summary>"
        f"{description_html}"
        f"{body}"
        "</details>"
    )


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

    state = build_dashboard_state(db, tools.inventory, user_id=uid)
    ds = state.decision_set
    market_graph = _build_market_graph(uid)

    hero = render_hero_panel(
        f"Good day. {APP_DESCRIPTION}",
        f"{len(ds.buy)} to buy, {len(ds.skip)} to skip, {len(ds.use_soon)} to use soon.",
        APP_NAME,
    )
    market_chips = _render_market_summary_chips(market_graph)

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
            "label": "Shopping",
            "subtitle": "Plan what to buy, skip, or compare",
            "tab_id": "basket",
            "tone": "primary",
        },
        {
            "label": "Scan & Compare",
            "subtitle": "Check a shelf item before buying",
            "tab_id": "market",
            "tone": "default",
        },
        {
            "label": "Pantry",
            "subtitle": "Log purchases, update stock, check expiries",
            "tab_id": "reconcile",
            "tone": "default",
        },
        {
            "label": "Insights",
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
    waste_coach_html = render_waste_coach_html(state.waste_data)
    restock_html = render_restock_predictions(state.restock_predictions)
    deals_html = render_price_deals(state.price_deals)
    drops_html = render_price_drops(state.price_drops)
    best_store_html = render_best_store(state.best_store)
    basket_summary_html = render_optimized_basket_summary(state.optimized_basket)

    show_empty_hints = (
        not state.active_inventory
        and not state.recent_purchases
        and state.active_list is None
    )
    onboarding = _render_today_empty_hints(state, ds) if show_empty_hints else _render_today_start_here(state, ds)

    shopping_path = _details_section(
        "Shopping path",
        market_basket,
        "Use this when you are ready to plan, compare, or build the list.",
    )
    attention_panel = _details_section(
        "What needs attention",
        decision_panel,
        "The decisions that most likely deserve a closer look.",
    )
    list_snapshot = _details_section(
        "Shopping list",
        list_panel,
        "Your active list, if one is open.",
    )
    household_state = _details_section(
        "Household state",
        f"{inventory_overview}{fridge_html}{alert_html}{needs_confirm}{what_changed}",
        "Freshness, inventory, and recent changes live here.",
    )
    market_signals = _details_section(
        "Market signals",
        f"{_render_compare_preview(market_graph)}{compare_panel}{cadence_html}{waste_html}{waste_coach_html}{restock_html}{deals_html}{drops_html}{best_store_html}{basket_summary_html}",
        "Deeper price, compare, and substitution cues.",
    )

    return [
        f"{hero}{market_chips}{onboarding}{quick_actions}{loop_actions}",
        attention_panel,
        shopping_path,
        list_snapshot,
        household_state,
        market_signals,
    ]


def _render_today_start_here(state, ds) -> str:
    if state.active_list is not None:
        item_count = len(state.active_list.items or [])
        subtitle = (
            f"You have an active shopping list with {item_count} item"
            f"{'' if item_count == 1 else 's'}."
        )
        action_label = "Finish your list"
        body = "Complete the list, then reconcile the purchase into inventory."
        actions = [
            {
                "label": "Finish list",
                "subtitle": "Review items and close the loop",
                "tab_id": "basket",
                "tone": "primary",
            },
            {
                "label": "Update pantry",
                "subtitle": "Log what came home and where it lives",
                "tab_id": "reconcile",
                "tone": "default",
            },
            {
                "label": "Review history",
                "subtitle": "See what changed across the household",
                "tab_id": "memory",
                "tone": "default",
            },
        ]
    elif ds.use_soon:
        subtitle = f"{len(ds.use_soon)} item{'' if len(ds.use_soon) == 1 else 's'} are ready to use soon."
        action_label = "Use what you have"
        body = "Use soon items first, then restock only the gap you still need."
        actions = [
            {
                "label": "Use soon",
                "subtitle": "Open the pantry items to use first",
                "tab_id": "reconcile",
                "tone": "primary",
            },
            {
                "label": "Plan shopping",
                "subtitle": "Build a list around the missing items",
                "tab_id": "basket",
                "tone": "default",
            },
            {
                "label": "Check prices",
                "subtitle": "Compare before buying more",
                "tab_id": "basket",
                "tone": "default",
            },
        ]
    elif ds.buy:
        subtitle = f"{len(ds.buy)} item{'' if len(ds.buy) == 1 else 's'} are marked to buy."
        action_label = "Plan the buy"
        body = "Use the buying list, then compare price or source before checkout."
        actions = [
            {
                "label": "Open shopping",
                "subtitle": "Turn buy decisions into a list",
                "tab_id": "basket",
                "tone": "primary",
            },
            {
                "label": "Compare prices",
                "subtitle": "Check whether a better store exists",
                "tab_id": "basket",
                "tone": "default",
            },
            {
                "label": "Open pantry",
                "subtitle": "See what stock already exists at home",
                "tab_id": "reconcile",
                "tone": "default",
            },
        ]
    else:
        subtitle = "The household is steady right now. Keep the loop light and check history when you need it."
        action_label = "Stay oriented"
        body = "No urgent action is required, but the main paths remain one click away."
        actions = [
            {
                "label": "Open shopping",
                "subtitle": "Plan the next grocery run",
                "tab_id": "basket",
                "tone": "primary",
            },
            {
                "label": "Scan a shelf item",
                "subtitle": "Compare while you are in the store",
                "tab_id": "market",
                "tone": "default",
            },
            {
                "label": "Review history",
                "subtitle": "See what the household learned",
                "tab_id": "memory",
                "tone": "default",
            },
        ]

    return ui_card(
        action_label,
        f"<div class='muted' style='margin-bottom:8px;'>{subtitle}</div>"
        f"<div style='margin-bottom:10px;'>{body}</div>"
        f"{render_action_grid(actions)}",
    )


def _render_today_empty_hints(state, ds) -> str:
    return (
        "<div class='home-card' style='margin-top:10px;text-align:left;'>"
        "<h3>Start here</h3>"
        "<div class='muted' style='margin-bottom:8px;'>No household data yet. Add one real fact and the rest of the loop can start learning.</div>"
        "<div style='margin-bottom:10px;'>Add a purchase, build a shopping list, scan a shelf item, or paste a receipt.</div>"
        f"{render_action_grid([
            {
                "label": "Add purchase",
                "subtitle": "Seed the pantry with one real item",
                "tab_id": "reconcile",
                "tone": "primary",
            },
            {
                "label": "Build shopping list",
                "subtitle": "Turn free text into a real list",
                "tab_id": "basket",
                "tone": "default",
            },
            {
                "label": "Scan receipt",
                "subtitle": "Parse a bill into inventory facts",
                "tab_id": "reconcile",
                "tone": "default",
            },
            {
                "label": "Scan shelf item",
                "subtitle": "Compare a product before you buy it",
                "tab_id": "market",
                "tone": "default",
            },
        ])}"
        "</div>"
    )


def _build_market_graph(uid: str):
    from shopstack.services.market_intelligence import build_market_intelligence_graph

    graph = build_market_intelligence_graph(db, tools.inventory, user_id=uid)
    return graph


def _render_market_summary_chips(graph) -> str:
    chips = [
        badge_html(f"{graph.summary.get('items_scored', 0)} items", "blue"),
        badge_html(f"{graph.summary.get('compare', 0)} compare", "blue"),
        badge_html(f"{graph.summary.get('substitute', 0)} substitute", "red"),
        badge_html(f"{graph.summary.get('stale', 0)} stale", "red" if graph.summary.get("stale", 0) else "gray"),
    ]
    return (
        "<div style='margin-top:-2px;margin-bottom:8px;display:flex;gap:6px;flex-wrap:wrap;'>"
        + "".join(chips)
        + "</div>"
    )


def _render_market_next_steps(graph) -> str:
    actions = []
    if graph.summary.get("buy", 0):
        actions.append(
            {
                "label": "Open Shopping",
                "subtitle": "Turn buy items into the list",
                "tab_id": "basket",
                "tone": "primary",
            }
        )
    if graph.summary.get("compare", 0):
        actions.append(
            {
                "label": "Review Compare",
                "subtitle": "Check overlap and substitutions",
                "tab_id": "basket",
                "tone": "default",
            }
        )
    if graph.summary.get("substitute", 0):
        actions.append(
            {
                "label": "Review Substitutes",
                "subtitle": "See better replacements",
                "tab_id": "basket",
                "tone": "default",
            }
        )
    if graph.summary.get("stale", 0):
        actions.append(
            {
                "label": "Inspect Freshness",
                "subtitle": "Treat stale cards as references",
                "tab_id": "basket",
                "tone": "default",
            }
        )

    if not actions:
        return (
            "<div class='home-card' style='text-align:left;margin-top:8px;'>"
            "<h3>Next steps</h3>"
            "<div class='muted'>No market actions to prioritize yet.</div>"
            "</div>"
        )

    top_signals = []
    if graph.compare:
        top_signals.append(f"{graph.compare[0].display_name}: compare")
    if graph.substitute:
        top_signals.append(f"{graph.substitute[0].display_name}: substitute")
    if graph.buy:
        top_signals.append(f"{graph.buy[0].display_name}: buy")

    return ui_card(
        "Next steps",
        f"<div class='muted' style='margin-bottom:8px;'>"
        f"{' · '.join(top_signals) if top_signals else 'The graph is quiet right now.'}"
        f"</div>"
        f"{render_action_grid(actions)}",
    )


def _render_market_map_teaser(state, graph) -> str:
    freshness = graph.snapshot_freshness_label or graph.snapshot_freshness or "unknown"
    compare_preview = _render_compare_preview(graph)
    body = (
        f"{graph.summary.get('items_scored', 0)} items scored · "
        f"{graph.summary.get('buy', 0)} buy · "
        f"{graph.summary.get('compare', 0)} compare · "
        f"{graph.summary.get('substitute', 0)} substitute"
    )
    if state.market_snapshot is None and graph.summary.get("items_scored", 0) == 0:
        body = "No market snapshot is loaded yet. Add one and the graph will start ranking buy / compare / substitute signals."

    actions = [
        {
            "label": "Open Market Map",
            "subtitle": "Inspect the living market graph",
            "tab_id": "basket",
            "tone": "primary",
        },
        {
            "label": "Check Pantry",
            "subtitle": "See what the household already has",
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

    return ui_card(
        "Market Map",
        f"<div class='muted' style='margin-bottom:8px;'>{freshness}</div>"
        f"<div style='margin-bottom:10px;'>{body}</div>"
        f"{compare_preview}"
        f"{render_action_grid(actions)}",
    )


def _render_compare_preview(graph) -> str:
    compare_items = graph.compare[:3]
    if not compare_items:
        return (
            "<div style='margin-bottom:10px;padding:8px;border:1px solid var(--border);border-radius:10px;'>"
            "<div style='font-size:12px;font-weight:600;margin-bottom:6px;'>Compare preview</div>"
            "<div class='muted'>No compare items yet.</div>"
            "</div>"
        )

    rows = []
    for cluster in compare_items:
        signal = cluster.reason or (cluster.reasons[0] if cluster.reasons else "Compare signal available")
        rows.append(
            "<div style='display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid var(--border);'>"
            f"<strong>{cluster.display_name}</strong>"
            f"<span style='color:var(--text-dim);font-size:12px;'>{signal}</span>"
            "</div>"
        )

    return (
        "<div style='margin-bottom:10px;padding:8px;border:1px solid var(--border);border-radius:10px;'>"
        "<div style='font-size:12px;font-weight:600;margin-bottom:6px;'>Compare preview</div>"
        + "".join(rows)
        + "</div>"
    )
