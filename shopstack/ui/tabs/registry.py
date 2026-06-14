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
"""

from __future__ import annotations

from typing import Any, Callable

import gradio as gr

from shopstack.module_registry import tab_order
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


def build_all_tabs(
    blocks: gr.Blocks,
    app: gr.Blocks,
    ctx: TabContext,
) -> dict[str, Any]:
    """Build all tabs in the canonical order defined by ``TAB_ORDER``.

    Returns a dict mapping ``tab_id`` to whatever the builder returned.
    Most builders return ``None``. Tabs in ``HANDLES_TABS`` return
    dataclass handles (e.g. ``TodayTabHandles``, ``ReconcileTabHandles``)
    that ``app.py`` uses for cross-tab event wiring.

    If a tab_id is in ``TAB_ORDER`` but has no registered builder, it is
    silently skipped (allows tabs to be declared in the registry before
    their builder exists, though a test enforces full coverage).
    """
    handles: dict[str, Any] = {}
    for tab_id, _label in tab_order():
        builder = _TAB_BUILDERS.get(tab_id)
        if builder is None:
            continue
        handles[tab_id] = builder(blocks=blocks, app=app, ctx=ctx)
    return handles
