from __future__ import annotations

from html import escape
import logging

from shopstack.app_context import APP_DESCRIPTION, APP_NAME, db, tools, current_user_id
from shopstack.services.dashboard import build_dashboard_state
from shopstack.ui.components.cards import card as ui_card
from shopstack.ui.components.cards import badge_html
from shopstack.ui.components.cards import render_action_grid, render_hero_panel
from shopstack.ui.components.primitives import (
    home_card,
    item_row,
    last_updated_stamp,
    stat_card,
)
from shopstack.ui.renderers import (
    render_cadence_insights,
    render_waste_warnings,
    render_price_drops,
    render_cook_tonight,
    render_seasonal,
)
from shopstack.services.waste_coach import render_waste_coach_html
from shopstack.ui.renderers.decision_cards import (
    render_restock_predictions,
    render_price_deals,
    render_best_store,
    render_optimized_basket_summary,
    # 2026-06-15 (Pass 17+18): Migrated from the legacy
    # `shopstack.decisions.render_what_changed` /
    # `render_needs_confirmation` shims (which took ``db`` and
    # pre-fetched internally). The canonical versions take
    # pre-fetched data; we fetch here. Pass 18 DELETED the legacy
    # shim entirely, so the canonical path is the only path.
    render_what_changed,
    render_needs_confirmation,
)
from shopstack.ui.renderers.image_cards import (
    cards_to_grid,
    render_decision_card as render_svg_decision_card,
    render_shopping_summary_card as render_svg_summary,
)
from shopstack.ui.errors import safe_render_html
from shopstack.ui.screens.other import inventory_alerts, what_is_in_fridge_now

logger = logging.getLogger(__name__)


def _details_section(title: str, body: str, description: str = "", count_label: str = "", open: bool = False) -> str:
    """Render a collapsible details section for the dashboard.

    The ``<details>`` element is a native HTML element; passing
    ``open=True`` makes the section start expanded. Use this to
    surface the most relevant info (Cook tonight, Use first, etc.)
    on first load instead of hiding everything behind "Tap to
    expand" chips.

    Args:
        title: The section heading shown in the summary row.
        body: The full content (rendered when expanded).
        description: One-line hint shown under the title.
        count_label: Optional badge text (e.g. "3 items").
        open: When True, the section starts expanded. Default False
            (collapsed). Use True sparingly for the most-relevant
            sections — too many expanded sections re-create the
            information-overload problem this accordion is solving.
    """
    summary_html = (
        "<div class='home-details-summary'>"
        "<div class='home-details-copy'>"
        f"<span class='home-details-title'>{escape(title)}</span><span class='home-details-hint'>{escape(description)}</span>"
        "</div>"
        "<div class='home-details-meta'>"
        f"{f'<span class=\"home-details-count\">{escape(count_label)}</span>' if count_label else ''}"
        f"<span class='home-details-chip'>{'Open' if open else 'Tap to expand'}</span>"
        "</div>"
        "</div>"
        if description or count_label
        else f"<div class='home-details-summary'><span class='home-details-title'>{escape(title)}</span><span class='home-details-chip'>{'Open' if open else 'Tap to expand'}</span></div>"
    )
    open_attr = " open" if open else ""
    return (
        f"<details class='home-details'{open_attr}><summary>{summary_html}</summary>"
        f"{body}"
        "</details>"
    )


def today_dashboard():
    try:
        return _today_dashboard_inner()
    except Exception:
        err = safe_render_html(
            lambda: "",
            user_message="Couldn't load dashboard",
            help_tab="today",
        )
        return [err, "", "", "", "", ""]


def _today_dashboard_inner():
    uid = current_user_id()
    from shopstack.decisions import (
        render_decision_panel,
        render_market_basket,
        render_inventory_overview,
        render_my_list_panel,
        render_compare_panel,
        # 2026-06-15 (Pass 17+18): render_what_changed and
        # render_needs_confirmation are now imported from the
        # canonical decision_cards module at the top of the file.
        # Pass 18 DELETED the legacy shim, so the only path
        # forward is the canonical signatures.
    )

    state = build_dashboard_state(db, tools.inventory, user_id=uid)
    ds = state.decision_set
    market_graph = _build_market_graph(uid)

    hero = render_hero_panel(
        "What's happening at home?",
        "Cook tonight, buy next, or use first — ShopStack tells you what matters right now.",
        APP_NAME,
    )
    market_chips = _render_market_summary_chips(market_graph)

    quick_actions = (
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:12px 0 16px 0;'>"
        f"{stat_card(str(len(state.active_inventory)), 'In pantry', on_click_tab='reconcile')}{stat_card(str(state.use_soon_count), 'Use first', variant='warning', on_click_tab='reconcile')}"
        f"{stat_card(str(len(state.low_items)), 'Need shopping', variant='danger', on_click_tab='reconcile')}{stat_card(str(len(state.recent_purchases)), 'Just bought', on_click_tab='reconcile')}"
        "</div>"
    )

    # 2026-06-15 (Pass 19): recurring shopping plan — items the
    # user typically buys on a rhythm and that are due in the
    # next 3 days. Surfaces the existing ``detect_purchase_cadence``
    # data as a "Your shopping rhythm" card. Renders as decision
    # cards with the Why? toggle (Pass 19's other deliverable).
    from shopstack.services.recurring_shopping import build_recurring_shopping_plan
    from shopstack.ui.renderers.recurring_plan import render_recurring_plan_html
    _recurring_plan = build_recurring_shopping_plan(db, user_id=uid, window_days=3)
    recurring_html = render_recurring_plan_html(_recurring_plan)

    loop_actions = render_action_grid([
        {
            "label": "Plan groceries",
            "subtitle": "Make the list before you leave",
            "tab_id": "basket",
            "tone": "primary",
        },
        {
            "label": "Check an item",
            "subtitle": "Compare while you are in the store",
            "tab_id": "market",
            "tone": "default",
        },
        {
            "label": "Put groceries away",
            "subtitle": "Log what came home and where it lives",
            "tab_id": "reconcile",
            "tone": "default",
        },
        {
            "label": "See what changed",
            "subtitle": "Remember what the household learned",
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
    # 2026-06-15 (Pass 17 + 18): pre-fetch the data the canonical
    # renderers need, then call them directly. The legacy
    # `shopstack.decisions.render_what_changed(db)` shim did
    # this internally but also emitted a DeprecationWarning.
    # Pass 18 DELETED the legacy shim entirely (per §7 supersession
    # discipline + user approval for bold long-term cleanup), so
    # the canonical signatures are the only path forward.
    from datetime import date
    _recent_purchases = db.get_purchase_events(limit=5, user_id=uid)
    _recent_traces = db.get_traces(limit=5, user_id=uid)
    what_changed = render_what_changed(_recent_purchases, _recent_traces)
    _all_inv_for_confirm = db.get_inventory(user_id=uid)
    _uncertain = [
        lot for lot in _all_inv_for_confirm
        if lot.status == "active" and lot.quantity > 0 and (
            not lot.purchase_date
            or (date.today() - lot.purchase_date).days > 14
        )
    ]
    needs_confirm = render_needs_confirmation(_uncertain)
    cadence_html = render_cadence_insights(state.cadence_data)
    waste_html = render_waste_warnings(state.waste_data)
    waste_coach_html = render_waste_coach_html(state.waste_data)
    restock_html = render_restock_predictions(state.restock_predictions)
    deals_html = render_price_deals(state.price_deals)
    drops_html = render_price_drops(state.price_drops)
    cook_tonight_html = render_cook_tonight(state.cook_tonight_matches)
    seasonal_html = render_seasonal(state.seasonal_recommendation)
    best_store_html = render_best_store(state.best_store)
    basket_summary_html = render_optimized_basket_summary(state.optimized_basket)

    show_empty_hints = (
        not state.active_inventory
        and not state.recent_purchases
        and state.active_list is None
    )
    # Item 8: First-run onboarding gate — show the onboarding wizard
    # when the household hasn't completed onboarding yet.
    from shopstack.services.onboarding import is_onboarding_complete
    onboarding_complete = is_onboarding_complete(db)
    if show_empty_hints and not onboarding_complete:
        onboarding = _render_onboarding_gate(state, ds)
    elif show_empty_hints:
        onboarding = _render_today_empty_hints(state, ds)
    else:
        onboarding = _render_today_start_here(state, ds)

    tonight_section = _details_section(
        "Tonight",
        f"{cook_tonight_html}{seasonal_html}",
        "What to cook with what you have, plus seasonal picks.",
        f"{len(state.cook_tonight_matches)} recipe{'s' if len(state.cook_tonight_matches) != 1 else ''}",
        open=bool(state.cook_tonight_matches),  # open when there are matches
    )
    # Per the home screen review: Plan section is INCLUDED in the
    # dashboard section list ONLY when there's a trip recommendation
    # (use_soon / buy / compare / substitute items). When included,
    # the section is open by default so the user sees the action
    # items immediately. (DR-031 follow-up: the previous version
    # had open=bool(...) which made the section closed by default
    # and the user had to click to expand — the review said this
    # buried the most actionable content.)
    has_trip_recommendation = bool(
        ds.use_soon or ds.buy or ds.compare or ds.substitute
    )
    state.has_trip_recommendation = has_trip_recommendation
    plan_section = _details_section(
        "Plan the trip",
        f"{decision_panel}{market_basket}",
        "What to buy, compare, or substitute before you go.",
        f"{len(ds.use_soon) + len(ds.buy) + len(ds.compare) + len(ds.substitute)} item{'s' if (len(ds.use_soon) + len(ds.buy) + len(ds.compare) + len(ds.substitute)) != 1 else ''}",
        # Per the home screen review: open=True (the user wants the
        # actionable plan visible by default). The section is
        # CONDITIONALLY INCLUDED in the section list (only when
        # has_trip is True) so the dashboard isn't noisy for users
        # with no trip recommendation.
        open=True,
    )
    list_snapshot = _details_section(
        "Shopping list",
        list_panel,
        "Your active list, if one is open.",
        f"{len(state.active_list.items) if state.active_list else 0} item{'s' if not state.active_list or len(state.active_list.items) != 1 else ''}",
        open=bool(state.active_list and state.active_list.items),
    )
    household_state = _details_section(
        "After you shop",
        f"{inventory_overview}{fridge_html}{alert_html}{needs_confirm}{what_changed}",
        "Put items away, check freshness, and see what changed.",
        f"{len(state.active_inventory)} item{'s' if len(state.active_inventory) != 1 else ''}",
        open=bool(state.active_inventory),  # open when there's something to show
    )
    market_signals = _details_section(
        "Compare and history",
        f"{_render_compare_preview(market_graph)}{compare_panel}{cadence_html}{waste_html}{waste_coach_html}{restock_html}{deals_html}{drops_html}{best_store_html}{basket_summary_html}",
        "Prices, substitutes, waste, and buy history over time.",
        f"{len(market_graph.buy) + len(market_graph.compare) + len(market_graph.substitute)} signal{'s' if (len(market_graph.buy) + len(market_graph.compare) + len(market_graph.substitute)) != 1 else ''}",
    )

    sections = [
        f"{hero}{market_chips}{onboarding}{quick_actions}{loop_actions}",
        tonight_section,
    ]
    if has_trip_recommendation:
        sections.append(plan_section)
    sections.extend([
        list_snapshot,
        household_state,
        market_signals,
    ])
    return sections + [
        # 2026-06-15 (Pass 19): recurring shopping plan
        # ("Your shopping rhythm" card) — only include the
        # section wrapper if there's something to show, so
        # the dashboard isn't noisy for users with no rhythm.
        f"<section class='recurring-plan-section'>{recurring_html}</section>" if _recurring_plan else "",
    ]


def _render_today_start_here(state, ds) -> str:
    cook_with_hint = ""
    if state.active_list is not None:
        item_count = len(state.active_list.items or [])
        subtitle = (
            f"You have a shopping list with {item_count} item{'' if item_count == 1 else 's'}."
        )
        action_label = "Keep shopping moving"
        body = "Finish the list, then put the groceries away when you get home."
        actions = [
            {
                "label": "Open shopping list",
                "subtitle": "See what still needs to be bought",
                "tab_id": "basket",
                "tone": "primary",
            },
            {
                "label": "Put groceries away",
                "subtitle": "Add what came home to the pantry",
                "tab_id": "reconcile",
                "tone": "default",
            },
            {
                "label": "See what changed",
                "subtitle": "Check the household record",
                "tab_id": "memory",
                "tone": "default",
            },
        ]
    elif ds.use_soon:
        use_soon_names = ", ".join(
            str(it.get("display_name", it.get("canonical_name", ""))).replace("_", " ").title()
            for it in (ds.use_soon[:3] if hasattr(ds.use_soon, '__iter__') else [])
        )
        subtitle = f"{len(ds.use_soon)} item{'' if len(ds.use_soon) == 1 else 's'} are ready to use soon."
        action_label = "Use these first"
        body = "Use soon items first, then restock only what is still missing."
        # Item 10: Cook-with-this — suggest recipes that use expiring items
        cook_with_hint = (
            f"<div style='font-size:0.75rem;color:var(--amber);margin-bottom:8px;'>🍳 These can make a meal: {escape(use_soon_names)}. "
            f"<a href='#cookbook' style='color:var(--accent);'>Browse recipes →</a></div>"
            if use_soon_names else ""
        )
        actions = [
            {
                "label": "Cook with these",
                "subtitle": "Find recipes that use expiring items",
                "tab_id": "cookbook",
                "tone": "primary",
            },
            {
                "label": "Open use-first items",
                "subtitle": "See what should be used before shopping",
                "tab_id": "reconcile",
                "tone": "default",
            },
            {
                "label": "Plan groceries",
                "subtitle": "Build a list around the missing items",
                "tab_id": "basket",
                "tone": "default",
            },
        ]
    elif ds.buy:
        subtitle = f"{len(ds.buy)} item{'' if len(ds.buy) == 1 else 's'} are marked to buy."
        action_label = "Plan the trip"
        body = "Use the list, then compare price or source before checkout."
        actions = [
            {
                "label": "Open shopping list",
                "subtitle": "Turn buy decisions into a list",
                "tab_id": "basket",
                "tone": "primary",
            },
            {
                "label": "Compare stores",
                "subtitle": "Check whether a better store exists",
                "tab_id": "basket",
                "tone": "default",
            },
            {
                "label": "Open pantry",
                "subtitle": "See what is already at home",
                "tab_id": "reconcile",
                "tone": "default",
            },
        ]
    else:
        subtitle = "The household is steady right now. Keep the loop simple and only open what you need."
        action_label = "Start with a normal home moment"
        body = "Plan groceries, check a shelf item, put things away, or look back at what changed."
        actions = [
            {
                "label": "Plan groceries",
                "subtitle": "Make the next shopping list",
                "tab_id": "basket",
                "tone": "primary",
            },
            {
                "label": "Check a shelf item",
                "subtitle": "Compare while you are in the store",
                "tab_id": "market",
                "tone": "default",
            },
            {
                "label": "See what changed",
                "subtitle": "Look back at the household record",
                "tab_id": "memory",
                "tone": "default",
            },
        ]

    return ui_card(
        action_label,
        f"<div class='muted' style='margin-bottom:8px;'>{subtitle}</div>{cook_with_hint}"
        f"<div style='margin-bottom:10px;'>{body}</div>{render_action_grid(actions)}",
    )


def _render_onboarding_gate(state, ds) -> str:
    """Render the onboarding gate when the household hasn't completed setup.

    Shows a welcoming first-run screen that guides the user through
    the onboarding wizard instead of a dead dashboard.

    The "Set up my household" button uses a ``custom_onclick`` to
    show the wizard (which has ``elem_id="onboarding-wizard"``) by
    toggling its CSS display. The "Skip for now" button is still a
    tab-jump (to the market tab where users can browse the app).

    Note: a household that has already skipped onboarding will
    never see this gate (because ``should_show_onboarding`` returns
    False in that case — see ``app.py:_show_onboarding_if_first_run``).
    This gate only appears for fresh households that have not yet
    seen the auto-shown wizard.

    **2026-06-15 supersession (motto_v3 §7):** The previous version
    leaked a long inline ``style="margin-top:10px;text-align:left;
    border:2px solid var(--accent, #176B49);"`` string into the
    rendered HTML — visible in screenshots as unstyled text. The
    styling now lives in the ``home-flow-card--setup`` CSS class
    (defined in :mod:`shopstack.ui.theme`), and the card is built
    via the canonical :func:`home_card` primitive instead of a raw
    ``<div>`` string.
    """
    # The custom_onclick body: show the wizard by toggling its
    # CSS display. The wizard has elem_id="onboarding-wizard".
    # We also scroll the user to the wizard so they see it
    # immediately.
    show_wizard_js = (
        "var w=document.getElementById('onboarding-wizard');"
        "if(w){w.style.display='block';"
        "w.scrollIntoView({behavior:'smooth',block:'center'});}"
    )
    action_items = [
        {
            'label': 'Set up my household',
            'subtitle': 'Tell us about your home so we can help',
            'tab_id': '',  # ignored; custom_onclick takes over
            'tone': 'primary',
            'custom_onclick': show_wizard_js,
        },
        {
            'label': 'Skip for now',
            'subtitle': 'Browse the app first, set up later',
            'tab_id': 'market',
            'tone': 'default',
        },
    ]
    body = (
        "<div style='margin-bottom:8px;'>Know what is at home, what to buy next, "
        "and what to skip. " + APP_NAME + " learns your household's buying cycle "
        "so it can tell you. Setup takes about 2 minutes.</div>"
        f"<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:12px;'>{APP_DESCRIPTION}</div>"
        "<div style='font-size:0.8125rem;margin-bottom:12px;'>You'll be asked about: "
        "household size, dietary preference, common staples, preferred stores, "
        "and your city.</div>"
        f"{render_action_grid(action_items)}"
    )
    return home_card(
        title="Welcome to ShopStack",
        body=body,
        extra_class="home-flow-card--setup",
    )


def _render_today_empty_hints(state, ds) -> str:
    body = (
        "<div class='muted' style='margin-bottom:8px;'>No restock or use-soon "
        "predictions yet. Add 5 common items you buy often — milk, bread, rice, "
        "eggs, curd — and ShopStack starts predicting refill dates after a few "
        "purchases.</div>"
        "<div style='margin-bottom:10px;'>Or add what came home, scan a receipt, "
        "or check a shelf item to seed the loop.</div>"
        f"{render_action_grid([
            {
                "label": "Add what came home",
                "subtitle": "Seed the pantry with one real item",
                "tab_id": "reconcile",
                "tone": "primary",
            },
            {
                "label": "Plan groceries",
                "subtitle": "Turn free text into a real list",
                "tab_id": "basket",
                "tone": "default",
            },
            {
                "label": "Scan receipt",
                "subtitle": "Turn a bill into pantry facts",
                "tab_id": "reconcile",
                "tone": "default",
            },
            {
                "label": "Check a shelf item",
                "subtitle": "Compare a product before you buy it",
                "tab_id": "market",
                "tone": "default",
            },
        ])}"
    )
    return home_card(
        title="Start with home life",
        body=body,
        style="margin-top:10px;text-align:left;",
    )


# ── Market graph cache (separate from dashboard state — used by
# the Compare sub-tab and the intelligence screen too).
import time as _time
_MGRAPH_TTL = 60  # seconds
_mgraph_cache: dict[str, tuple[float, Any]] = {}


def _build_market_graph(uid: str):
    """Build the market intelligence graph, with a 60-second TTL cache."""
    now = _time.monotonic()
    cached = _mgraph_cache.get(uid)
    if cached and (now - cached[0]) < _MGRAPH_TTL:
        return cached[1]

    from shopstack.services.market_intelligence import build_market_intelligence_graph

    graph = build_market_intelligence_graph(db, tools.inventory, user_id=uid)
    _mgraph_cache[uid] = (now, graph)
    return graph


def _render_market_summary_chips(graph) -> str:
    """Render the market-graph summary chips that appear on the home panel.

    **Why the labels are explicit (motto_v3 §0.11, §0.14):**
    A bare "stale" count is ambiguous — a user reading the home page
    reasonably assumes "stale" refers to their own inventory. The
    number is the count of market clusters whose underlying market
    snapshot is older than the freshness threshold; the chip must
    say so. We also include the snapshot age so the cause is
    visible next to the symptom.
    """
    items_n = int(graph.summary.get("items_scored", 0))
    compare_n = int(graph.summary.get("compare", 0))
    substitute_n = int(graph.summary.get("substitute", 0))
    stale_n = int(graph.summary.get("stale", 0))
    # Pull the snapshot age if available so the chip is self-explanatory
    age_days = ""
    if getattr(graph, "snapshot_freshness_label", ""):
        # The label looks like "Captured 9 days ago (2026-06-06)"
        age_days = graph.snapshot_freshness_label
    # "items" alone is also ambiguous — make it clear these are market-tracked
    # items, not pantry items.
    chips = [
        badge_html(f"{items_n} market items", "blue"),
        badge_html(f"{compare_n} compare", "blue"),
        badge_html(f"{substitute_n} substitute", "red"),
        badge_html(
            f"market data stale · {stale_n}" if stale_n else "market data fresh",
            "red" if stale_n else "gray",
        ),
    ]
    if age_days:
        chips.append(
            f"<span class='muted' style='font-size:0.6875rem;' "
            f"title='{escape(age_days)}'>{escape(age_days)}</span>"
        )
    return (
        "<div style='margin-top:-2px;margin-bottom:8px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;'>"
        + "".join(chips)
        + "</div>"
    )


def _render_compare_preview(graph) -> str:
    compare_items = graph.compare[:3]
    if not compare_items:
        return (
            "<div style='margin-bottom:10px;padding:8px;border:1px solid var(--border);border-radius:10px;'>"
            "<div style='font-size: 0.75rem;font-weight:600;margin-bottom:6px;'>Compare preview</div>"
            "<div class='muted'>No compare items yet.</div>"
            "</div>"
        )

    rows = []
    for cluster in compare_items:
        signal = cluster.reasons[0] if cluster.reasons else "Compare signal available"
        rows.append(
            "<div style='display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid var(--border);'>"
            f"<strong>{cluster.display_name}</strong><span style='color:var(--text-dim);font-size: 0.75rem;'>{signal}</span>"
            "</div>"
        )

    return (
        "<div style='margin-bottom:10px;padding:8px;border:1px solid var(--border);border-radius:10px;'>"
        "<div style='font-size: 0.75rem;font-weight:600;margin-bottom:6px;'>Compare preview</div>"
        + "".join(rows)
        + "</div>"
    )


def _render_market_next_steps(graph) -> str:
    """Render next-step action cards based on the market graph signals."""
    actions = []
    if graph.summary.get("buy", 0):
        actions.append(
            {
                "label": "Open Groceries",
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
        return home_card(
            title="Next steps",
            body=(
                "<div class='muted'>No market signals yet. Add a few items to "
                "your pantry or shopping list, and ShopStack will start "
                "surfacing buy, compare, and substitute recommendations here.</div>"
            ),
            style="text-align:left;margin-top:8px;",
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
        f"<div class='muted' style='margin-bottom:8px;'>{' · '.join(top_signals) if top_signals else 'The graph is quiet right now.'}"
        f"</div>{render_action_grid(actions)}",
    )


def _render_market_map_teaser(state, graph) -> str:
    """Render a teaser card for the market map with freshness and signal summary."""
    freshness = graph.snapshot_freshness_label or graph.snapshot_freshness or "unknown"
    compare_preview = _render_compare_preview(graph)
    body = (
        f"{graph.summary.get('items_scored', 0)} items scored · {graph.summary.get('buy', 0)} buy · "
        f"{graph.summary.get('compare', 0)} compare · {graph.summary.get('substitute', 0)} substitute"
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
        f"{last_updated_stamp(getattr(state.market_snapshot, 'captured_at', None), label='Market data')}"
        f"{compare_preview}{render_action_grid(actions)}",
    )
