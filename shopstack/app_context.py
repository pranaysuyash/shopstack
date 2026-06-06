from __future__ import annotations

from shopstack.config import settings
from shopstack.model_registry import get_registry
from shopstack.module_registry import (
    ModuleMetadata,
    get_all as get_all_modules,
    get_by_slug,
    get_by_tab_id,
    navigation as _build_navigation,
    summary_table as _build_summary,
)
from shopstack.persistence.database import Database
from shopstack.planner.engine import PlannerEngine
from shopstack.providers.registry import ProviderRegistry
from shopstack.tools.registry import ToolRegistry

# ── Shared product constants (single source of truth) ──────────────
# These derive from config but are exported here so every UI surface
# imports from one place instead of hardcoding copy.
APP_NAME: str = settings.app_name
APP_DESCRIPTION: str = settings.app_description

# ── Module registry (module metadata + lookup helpers) ──────────────
# See shopstack/module_registry.py for all module definitions.
MODULES: list[ModuleMetadata] = get_all_modules()
MODULE_SUMMARY: list[dict[str, str]] = _build_summary()
NAV_ENTRIES: list[tuple[str, str, str]] = _build_navigation()

# ── Core singletons ─────────────────────────────────────────────────
db = Database(settings.db_path)
providers = ProviderRegistry(settings)
tools = ToolRegistry(db)
planner = PlannerEngine(db, tools, providers)
model_registry = get_registry()
