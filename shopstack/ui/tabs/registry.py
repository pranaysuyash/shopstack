"""Registry-driven tab composition — the single source of truth for tab wiring.

This module maps tab IDs from ``module_registry.TAB_ORDER`` to their builder
functions and provides ``build_all_tabs()`` which iterates ``TAB_ORDER`` and
calls each builder in sequence.

``app.py`` calls ``build_all_tabs()`` instead of 21 hardcoded ``build_*_tab()``
calls. This makes ``module_registry.TAB_ORDER`` the true single source of truth
for both *what tabs exist* and *what order they appear in*, eliminating the
declarative/imperative drift that existed when app.py hardcoded the tab sequence
separately from the registry.

Adding a new tab is now a three-line change:
  1. Add the tab_id + order to ``TAB_ORDER`` and ``TAB_LABELS`` in module_registry.
  2. Import the builder function and add it to ``_TAB_BUILDERS`` here.
  3. Optionally add the tab_id to the appropriate module's ``tab_ids``.

No changes to ``app.py`` are needed for new tabs.

**2026-06-15 update (Home screen review):** the registry now supports a
``use_primary_nav=True`` flag that switches from the legacy 5-group
nested nav to the new 6-item user-facing primary nav (Home / Pantry /
Shopping / Recipes / Trips / Memory). Each primary nav item is a single
``gr.Tab`` that points at the canonical destination tab, with the
remaining advanced tabs reachable as nested subtabs inside. The old
``TAB_GROUPS`` layout is still the default for back-compat.

**2026-06-15 update (Primary-nav consolidation):** the advanced
subtabs in ``PRIMARY_NAV_ADVANCED`` are no longer rendered as
immediate nested sub-tabs. Instead, they sit inside a collapsed
``gr.Accordion(label="More", open=False)`` so the user sees the
destination view first and the advanced tabs only on demand.
This is the hide-not-delete treatment (motto_v3 §11): the
registry still EXPOSES every advanced tab, but the default
user-facing surface stays focused. The legacy 5-group layout
is untouched.
"""

from __future__ import annotations

from typing import Any, Callable

import gradio as gr

from shopstack.module_registry import (
    PRIMARY_NAV,
    PRIMARY_NAV_ADVANCED,
    group_order,
    group_tab_ids,
    group_label as _group_label,
)
from shopstack.ui.tabs.context import TabContext
from shopstack.ui.tabs.today import build_today_tab
from shopstack.ui.tabs.cookbook import build_cookbook_tab
from shopstack.ui.tabs.basket import build_basket_tab
from shopstack.ui.tabs.market_intel import build_market_intel_tab
from shopstack.ui.tabs.trip_advisor import build_trip_advisor_tab
from shopstack.ui.tabs.market import build_market_tab
from shopstack.ui.tabs.scanner import build_scanner_tab
from shopstack.ui.tabs.photo_map import build_photo_map_tab
from shopstack.ui.tabs.reconcile import build_reconcile_tab
from shopstack.ui.tabs.timeline import build_timeline_tab
from shopstack.ui.tabs.find_trail import build_find_trail_tab
from shopstack.ui.tabs.store_mode import build_store_mode_tab
from shopstack.ui.tabs.memory import build_memory_tab
from shopstack.ui.tabs.nutrition_coach import build_nutrition_coach_tab
from shopstack.ui.tabs.smart_basket import build_smart_basket_tab
from shopstack.ui.tabs.analytics import build_analytics_tab
from shopstack.ui.tabs.repair_inbox import build_repair_inbox_tab
from shopstack.ui.tabs.consumption import build_consumption_tab
from shopstack.ui.tabs.recipe import build_recipe_tab
from shopstack.ui.tabs.parser import build_parser_tab
from shopstack.ui.tabs.community import build_community_tab

# Ordered mapping: tab_id → builder function.
# The builder signature is (blocks, app, ctx) → Any (usually None or a handles dataclass).
# The order of this dict does NOT matter — the iteration order comes from TAB_ORDER.
_TAB_BUILDERS: dict[str, Callable[..., Any]] = {
    "today":         build_today_tab,
    "cookbook":      build_cookbook_tab,
    "basket":        build_basket_tab,
    "market_intel":  build_market_intel_tab,
    "trip_advisor":  build_trip_advisor_tab,
    "market":        build_market_tab,
    "scanner":       build_scanner_tab,
    "photo_map":     build_photo_map_tab,
    "reconcile":     build_reconcile_tab,
    "timeline":      build_timeline_tab,
    "find_trail":    build_find_trail_tab,
    "store_mode":    build_store_mode_tab,
    "memory":        build_memory_tab,
    "nutrition":     build_nutrition_coach_tab,
    "smart_basket":  build_smart_basket_tab,
    "analytics":     build_analytics_tab,
    "repair_inbox":  build_repair_inbox_tab,
    "consumption":   build_consumption_tab,
    "recipe":        build_recipe_tab,
    "parser":        build_parser_tab,
    "community":     build_community_tab,
}

# Tabs that return handles used by app.py for cross-tab wiring.
# These are the only tabs whose return values are consumed outside the registry.
HANDLES_TABS = frozenset({"today", "reconcile"})


def get_builder(tab_id: str) -> Callable[..., Any] | None:
    """Return the builder function for a tab_id, or None if not registered."""
    return _TAB_BUILDERS.get(tab_id)


def registered_tab_ids() -> set[str]:
    """Return the set of tab_ids that have a registered builder."""
    return set(_TAB_BUILDERS)


def _build_in_more_accordion(
    tab_ids: list[str],
    blocks: gr.Blocks,
    app: gr.Blocks,
    ctx: TabContext,
    handles: dict[str, Any],
) -> None:
    """Render the given tab_ids inside a collapsed ``gr.Accordion``.

    Per motto_v3 §11 (hide, not delete): the advanced sub-tabs are
    still EXPOSED in the registry and the user can reach them by
    clicking the "More" disclosure. The default surface stays
    focused on the destination view.

    Additive (2026-06-15): the registry still builds every
    tab; the new disclosure is a presentation-layer change only.
    """
    with gr.Accordion(
        label=f"More ({len(tab_ids)})",
        open=False,
        elem_classes="primary-nav-more",
    ):
        for tab_id in tab_ids:
            builder = _TAB_BUILDERS.get(tab_id)
            if builder is None:
                continue
            # Capture the return value if this is a handles tab;
            # otherwise the builder returns None and we discard it.
            result = builder(blocks=blocks, app=app, ctx=ctx)
            if tab_id in HANDLES_TABS:
                handles[tab_id] = result


def build_all_tabs(
    blocks: gr.Blocks,
    app: gr.Blocks,
    ctx: TabContext,
    *,
    use_primary_nav: bool = False,
) -> dict[str, Any]:
    """Build all tabs in either the new 6-item primary nav or the
    legacy 5-group nested layout.

    Args:
        blocks, app, ctx: Standard builder arguments (see :class:`TabContext`).
        use_primary_nav: When True, render the 6-item user-facing
            primary nav (Home / Pantry / Shopping / Recipes / Trips
            / Memory). The destination tab is shown first; any
            advanced sub-tabs for that primary are placed inside a
            collapsed "More" accordion so the default view stays
            focused. When False (default), use the legacy 5-group
            nested layout from ``TAB_GROUPS``.

    Returns:
        Dict mapping tab_id to whatever the builder returned.
        Most builders return ``None``. Tabs in ``HANDLES_TABS``
        return dataclass handles (e.g. ``TodayTabHandles``,
        ``ReconcileTabHandles``) that ``app.py`` uses for cross-tab
        event wiring.

    Note:
        If a tab_id is in a group but has no registered builder, it
        is silently skipped in both modes.
    """
    handles: dict[str, Any] = {}
    if use_primary_nav:
        for item in PRIMARY_NAV:
            with gr.Tab(item["label"], id=item["id"]):
                # Render the destination tab as the default view
                # of this primary destination. Cross-tab wiring
                # handles are still returned to ``handles`` so
                # ``app.py`` can wire up events (today, reconcile).
                destination = item["destination"]
                dest_builder = _TAB_BUILDERS.get(destination)
                if dest_builder is not None:
                    result = dest_builder(blocks=blocks, app=app, ctx=ctx)
                    if destination in HANDLES_TABS:
                        handles[destination] = result

                # The advanced sub-tabs (excluding the destination)
                # sit inside a collapsed "More" accordion — see
                # ``_build_in_more_accordion`` for the rationale.
                advanced_only = [
                    tid for tid in PRIMARY_NAV_ADVANCED.get(item["id"], [])
                    if tid != destination
                ]
                if advanced_only:
                    _build_in_more_accordion(
                        advanced_only, blocks, app, ctx, handles,
                    )
        return handles

    # Legacy 5-group nested layout (default, back-compat).
    for group_id, _group_label in group_order():
        screen_ids = group_tab_ids(group_id)
        if not screen_ids:
            continue
        with gr.Tab(_group_label, id=group_id):
            with gr.Tabs():
                for tab_id in screen_ids:
                    builder = _TAB_BUILDERS.get(tab_id)
                    if builder is None:
                        continue
                    handles[tab_id] = builder(blocks=blocks, app=app, ctx=ctx)
    return handles

    # Legacy 5-group nested layout (default, back-compat).
    for group_id, _group_label in group_order():
        screen_ids = group_tab_ids(group_id)
        if not screen_ids:
            continue
        with gr.Tab(_group_label, id=group_id):
            with gr.Tabs():
                for tab_id in screen_ids:
                    builder = _TAB_BUILDERS.get(tab_id)
                    if builder is None:
                        continue
                    handles[tab_id] = builder(blocks=blocks, app=app, ctx=ctx)
    return handles
