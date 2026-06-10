from __future__ import annotations

from shopstack.config import settings
from shopstack.model_registry import get_registry
from shopstack.module_registry import (
    ModuleMetadata,
    get_all as get_all_modules,
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
# Wire embeddings provider into ToolRegistry for semantic search fallback.
# The embedding provider is lazy-resolved from ProviderRegistry; if BGE-M3
# or sentence-transformers is unavailable, semantic_find_item falls back to
# prefix search automatically.
tools = ToolRegistry(db, embedding_provider=providers.embeddings)
planner = PlannerEngine(db, tools, providers)
model_registry = get_registry()


def runtime_label() -> str:
    """Return a human-readable label describing the current provider runtime.

    Uses the provider registry to determine whether real AI backends are loaded
    or the app is running in mock mode. Safe to call at import time.
    """
    try:
        runtime = providers.get_runtime_diagnostics()
        loaded_real = [
            r for r in runtime.providers
            if getattr(r, "loaded", False) and getattr(r, "backend", "") != "mock"
        ]
        return "Local runtime" if loaded_real else "Local mock mode"
    except Exception:
        return "Local runtime"
