from __future__ import annotations

import contextvars
from typing import Optional

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

# ── Request-scoped household context (v1 API, 2026-06-16) ──────────
# When the v1 API surface resolves a bearer token, it sets this
# ContextVar for the duration of the request. ``current_user_id()``
# checks the ContextVar first and falls back to the persistent
# ``db.active_household_id`` for Gradio/synchronous callers. This
# way the same service function works for both surfaces without
# any signature change.
#
# Per motto_v3 §0.1 (missed-anything), this is the smallest
# additive change that gives the v1 surface request-scoped
# identity. The Gradio default path is unchanged.
_current_household_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "shopstack_current_household_id", default=None
)


def set_request_household(household_id: Optional[str]) -> contextvars.Token:
    """Bind a household_id to the current request's ContextVar.

    Returns a Token that the caller MUST pass to
    :func:`reset_request_household` after the request finishes,
    even on exception (use try/finally). This is the standard
    ContextVar pattern.
    """
    return _current_household_id.set(household_id)


def reset_request_household(token: contextvars.Token) -> None:
    """Restore the ContextVar to its prior state."""
    _current_household_id.reset(token)


def request_household() -> Optional[str]:
    """Return the current request's household_id, or None.

    Raw ContextVar read. The Gradio-friendly
    :func:`current_user_id` calls this first and falls back to
    the persistent active_household_id.
    """
    return _current_household_id.get()

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

# Resolve active household from stored config, so every DB operation
# is scoped to the current household automatically.
_household_id = db.active_household_id

providers = ProviderRegistry(settings)
# Wire embeddings provider into ToolRegistry for semantic search fallback.
# The embedding provider is lazy-resolved from ProviderRegistry; if BGE-M3
# or sentence-transformers is unavailable, semantic_find_item falls back to
# prefix search automatically.
tools = ToolRegistry(db, embedding_provider=providers.embeddings)
planner = PlannerEngine(db, tools, providers)
model_registry = get_registry()


# ── Service singletons (wired from app_context) ────────────────────
from shopstack.services.trace import TraceService  # noqa: E402 — circular import

_trace_service: TraceService | None = None


def get_trace_service() -> TraceService:
    global _trace_service
    if _trace_service is None:
        _trace_service = TraceService(db)
    return _trace_service


def current_user_id() -> str:
    """Return the currently active household/user ID for DB scoping.

    Screen builders should call this and pass the result as ``user_id``
    to every ``db.*()`` call that accepts the parameter. This ensures
    all inventory, shopping list, and trace queries are scoped to the
    active household.

    Resolution order (2026-06-16, v1 API surface):
    1. Request-scoped ``ContextVar`` set by the v1 API router.
    2. ``db.active_household_id`` (the persistent Gradio default).

    The two are unified here so the same service function works
    for both the Gradio UI and the v1 API without any signature
    change. Gradio calls (no ContextVar set) get the persistent
    active_household_id; v1 API calls (ContextVar set in a
    FastAPI dependency) get the per-request value.
    """
    scoped = _current_household_id.get()
    if scoped:
        return scoped
    return db.active_household_id


def switch_household(household_id: str) -> bool:
    """Switch the active household. Returns True if successful."""
    if not household_id:
        return False
    # Verify the household exists
    households = db.list_households()
    if not any(h["household_id"] == household_id for h in households):
        return False
    db.active_household_id = household_id
    return True


def list_households() -> list[dict[str, str]]:
    """List all registered households."""
    return db.list_households()


def add_household(household_id: str, name: str) -> bool:
    """Register a new household."""
    return db.add_household(household_id, name)


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
