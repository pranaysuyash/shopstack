"""Tab builder exports — the canonical import surface for all tab builders.

Every ``build_*_tab`` / ``build_*`` function in ``shopstack/ui/tabs/`` is
re-exported here so individual tabs can be imported without knowing which
submodule they live in:

    from shopstack.ui.tabs import build_today_tab, build_basket_tab

The registry (``shopstack/ui/tabs/registry.py``) maps tab IDs to builder
functions using the same imports and is the source of truth for tab
wiring order. This module provides direct-access imports for call sites
that need one specific tab builder without going through the registry.
"""

from __future__ import annotations

from shopstack.ui.tabs.today import build_today_tab, TodayTabHandles
from shopstack.ui.tabs.cookbook import build_cookbook_tab
from shopstack.ui.tabs.basket import build_basket_tab
from shopstack.ui.tabs.market_intel import build_market_intel_tab
from shopstack.ui.tabs.trip_advisor import build_trip_advisor_tab
from shopstack.ui.tabs.market import build_market_tab
from shopstack.ui.tabs.scanner import build_scanner_tab
from shopstack.ui.tabs.photo_map import build_photo_map_tab
from shopstack.ui.tabs.reconcile import build_reconcile_tab, ReconcileTabHandles
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
from shopstack.ui.tabs.basket_plan import build_basket_plan, BasketPlanHandles
from shopstack.ui.tabs.basket_shopping_list import build_basket_shopping_list
from shopstack.ui.tabs.basket_compare import build_basket_compare
from shopstack.ui.tabs.basket_add_items import build_basket_add_items
from shopstack.ui.tabs.command_surface import build_command_surface
from shopstack.ui.tabs.ask_panel import build_ask_panel, AskPanelHandles
from shopstack.ui.tabs.voice_memo import build_voice_memo_section
from shopstack.ui.tabs.memory_activity import (
    build_memory_activity,
    build_memory_analytics,
    build_memory_per_member,
)
from shopstack.ui.tabs.memory_data import (
    build_memory_corrections,
    build_memory_facts,
    build_memory_advanced,
    build_memory_backup,
)
from shopstack.ui.tabs.memory_history import build_memory_history
from shopstack.ui.tabs.memory_intelligence import build_memory_intelligence
from shopstack.ui.tabs.memory_nutrition import build_memory_nutrition
from shopstack.ui.tabs.memory_notes import build_memory_notes
from shopstack.ui.tabs.onboarding import build_onboarding_wizard
from shopstack.ui.tabs.cookbook_filter import build_cookbook_filter_row, CookbookFilterHandles

# ── Registry (the single source of truth for tab composition) ─────
from shopstack.ui.tabs.registry import (
    build_all_tabs,
    get_builder,
    registered_tab_ids,
    HANDLES_TABS,
)

__all__ = [
    # Builder functions — each tab has one
    "build_today_tab",
    "build_cookbook_tab",
    "build_basket_tab",
    "build_market_intel_tab",
    "build_trip_advisor_tab",
    "build_market_tab",
    "build_scanner_tab",
    "build_photo_map_tab",
    "build_reconcile_tab",
    "build_timeline_tab",
    "build_find_trail_tab",
    "build_store_mode_tab",
    "build_memory_tab",
    "build_nutrition_coach_tab",
    "build_smart_basket_tab",
    "build_analytics_tab",
    "build_repair_inbox_tab",
    "build_consumption_tab",
    "build_recipe_tab",
    "build_parser_tab",
    "build_community_tab",
    # Sub-builders (composed by the main tab builders above)
    "build_basket_plan",
    "build_basket_shopping_list",
    "build_basket_compare",
    "build_basket_add_items",
    "build_command_surface",
    "build_ask_panel",
    "build_voice_memo_section",
    "build_memory_activity",
    "build_memory_analytics",
    "build_memory_per_member",
    "build_memory_corrections",
    "build_memory_facts",
    "build_memory_advanced",
    "build_memory_backup",
    "build_memory_history",
    "build_memory_intelligence",
    "build_memory_nutrition",
    "build_memory_notes",
    "build_onboarding_wizard",
    "build_cookbook_filter_row",
    # Registry functions
    "build_all_tabs",
    "get_builder",
    "registered_tab_ids",
    "HANDLES_TABS",
    # Handle dataclasses
    "TodayTabHandles",
    "ReconcileTabHandles",
    "BasketPlanHandles",
    "AskPanelHandles",
    "CookbookFilterHandles",
]
