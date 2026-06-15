"""Global search HTTP endpoint — mounts ``/api/global_search``.

The JS palette (see ``shopstack.services.global_search.render_palette_script``)
hits ``/api/global_search?q=...`` on every keystroke (debounced
to 120ms). This module wires that endpoint onto the Gradio app's
underlying FastAPI app.

**Why a thin transport module (motto_v3 §0.15 three-layer rule):**

The search logic lives in ``shopstack.services.global_search``.
This module is purely the HTTP boundary:

1. Parse the query string.
2. Build a ``SearchSources`` bundle from the DB and cookbook.
3. Call ``search(query, sources)``.
4. Return the results as JSON.

No business logic, no caching, no auth (the endpoint is
read-only and returns only data the user can already see in
their household). The endpoint is mounted unconditionally —
unlike the SMS webhook, there is no write surface.

**Performance:**

The search runs synchronously in the request thread. For a
household with 100 items and 30 recipes this is sub-10ms. If
the household grows to 10k items, this becomes a bottleneck;
the right fix is to cache the inventory index in memory (not
in this module — that's a follow-up).

**Cross-household scoping (motto_v3 §0.6 risk):**

The endpoint accepts a ``user_id`` query parameter. The DB layer
enforces per-household scoping on every read, so a missing or
empty ``user_id`` falls through to "no results" (the DB's
default user_id filter returns the caller's active household).
This is the same pattern as the existing ``get_inventory``
helpers.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import gradio as gr

from shopstack.app_context import current_user_id, db
from shopstack.services.global_search import (
    SearchSources,
    search,
    GlobalSearchResult,
)

logger = logging.getLogger(__name__)


def _serialize_result(r: GlobalSearchResult) -> dict[str, Any]:
    """Convert a :class:`GlobalSearchResult` to a JSON-safe dict."""
    return {
        "kind": r.kind,
        "title": r.title,
        "meta": r.meta,
        "score": r.score,
        "action_kind": r.action_kind,
        "action_target": r.action_target,
    }


def _global_search_endpoint(request):  # noqa: ANN001 — Starlette Request
    """Handle ``GET /api/global_search?q=...&user_id=...``.

    Returns ``{"results": [...]}`` as JSON. The palette JS
    reads ``data.results`` and renders each entry.
    """
    try:
        params = dict(request.query_params)
        query = params.get("q", "").strip()
        # user_id is optional; when missing we use the active
        # household (the DB layer scopes reads to the caller).
        user_id = params.get("user_id") or current_user_id() or ""

        if not query:
            return {"results": []}

        sources = SearchSources(database=db, user_id=user_id)
        try:
            from shopstack.services.recipes import all_recipes
            sources.cookbook = all_recipes()
        except Exception:  # noqa: BLE001
            # Cookbook is optional; the search degrades to the
            # other sources when it's missing.
            pass

        results = search(query, sources)
        return {"results": [_serialize_result(r) for r in results]}
    except Exception as exc:  # noqa: BLE001
        # Never let the palette crash the page; return empty
        # results and log the error for the operator.
        logger.warning("global_search endpoint failed: %s", exc)
        return {"results": [], "error": "search failed"}


def mount_global_search(app: gr.Blocks) -> None:
    """Mount ``GET /api/global_search`` on the app's FastAPI router.

    Best-effort: if the route can't be registered (e.g. the app
    is already started), logs a warning and continues. The
    palette will fall back to "no results" if the endpoint is
    unreachable, which is the correct degraded experience.
    """
    try:
        app.app.add_route(
            "/api/global_search",
            _global_search_endpoint,
            methods=["GET"],
        )
        logger.info("global search mounted at /api/global_search")
    except Exception as exc:  # noqa: BLE001
        logger.warning("global search mount failed: %s", exc)


__all__ = ["mount_global_search"]
