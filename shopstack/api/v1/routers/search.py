"""``/api/v1/search/*`` — global, inventory, and voice-intent endpoints.

**Why this exists (motto_v3 §0 first-principles):**

The ``/api/v1`` surface has inventory list, shopping, dashboard, and
auth. It does NOT have search — the mobile app's most-frequent way
to find items. The backend already has ``global_search.search()``
(cross-source command palette) and ``ShopFindService`` (inventory
+ household objects with semantic fallback). This router exposes
both under a single ``/api/v1/search`` prefix.

**Two endpoints, one wire contract:**

1. ``GET /api/v1/search/global?q=...`` — cross-source search
   (inventory + shopping lists + recipes + actions). Delegates to
   ``shopstack.services.global_search.search()``.

2. ``GET /api/v1/search/inventory?q=...`` — inventory-scoped search
   with semantic embedding fallback. Delegates to
   ``ShopFindService.semantic_find_inventory_compatible()``.

3. ``POST /api/v1/search/voice-intent`` — parse a spoken command or
   transcript into normalized intent fields. Delegates to
   ``shopstack.services.speech_intent.parse_speech_intent``.

**Pattern (per motto_v3 §0.15 three-layer rule):**

* HTTP boundary only.
* Reuses the exact same service layer the Gradio UI uses.
* No business logic leaks into the router.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query

from shopstack.api.v1.deps import HouseholdContext, require_household
from shopstack.api.v1.schemas import (
    SearchResponse,
    SearchResultWire,
    VoiceIntentRequest,
    VoiceIntentResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])

# Singleton BGE-M3 embedding provider for the /inventory search endpoint.
# Module-level to avoid per-request re-init. Lazy-loaded by
# ``BGEM3EmbeddingProvider._ensure_model()`` — SentenceTransformer is not
# imported until the first ``embed()`` or ``available`` check. If
# sentence-transformers is not installed, ``available=False`` and the search
# endpoint degrades gracefully to text-only prefix matching.
from shopstack.providers.embeddings_provider import BGEM3EmbeddingProvider  # noqa: E402

_BGE_M3_PROVIDER = BGEM3EmbeddingProvider()


@router.get(
    "/global",
    response_model=SearchResponse,
    summary="Cross-source global search (inventory, lists, recipes, actions)",
)
def search_global(
    q: str = Query(..., min_length=1, description="Search query"),
    ctx: HouseholdContext = Depends(require_household),
) -> SearchResponse:
    """Search across every relevant data source in parallel.

    Sources: inventory, shopping list, recipes, prices, locations,
    actions. Ranked by relevance score (exact → prefix → contains).
    The mobile app uses this for the command palette / search bar.

    The ``type:`` prefix scopes the search (e.g. ``type:recipe milk``
    searches only recipes).
    """
    return _global_search_response(q, ctx.household_id)


def legacy_search_global(
    q: str = Query("", description="Search query"),
) -> SearchResponse:
    """Serve the Gradio command palette's pre-v1 search contract.

    The palette runs inside the local Gradio UI and has no API bearer token.
    Its identity therefore comes from the same active-household context used
    by synchronous Gradio screens. This adapter intentionally does not weaken
    ``/api/v1/search/global``, which remains bearer-token protected.
    """
    from shopstack.app_context import current_user_id

    try:
        return _global_search_response(q, current_user_id())
    except Exception as exc:  # noqa: BLE001
        # Search is an enhancement to the shell. A transient data-source
        # failure must degrade to an empty palette rather than break hydration.
        logger.warning("legacy global search failed: %s", exc)
        return _global_search_response("", current_user_id())


def _global_search_response(query: str, household_id: str) -> SearchResponse:
    """Build the shared global-search wire response for both transports."""
    from shopstack.app_context import db
    from shopstack.services.global_search import SearchSources, search

    normalized_query = query.strip()
    if not normalized_query:
        results = []
    else:
        results = search(
            normalized_query,
            sources=SearchSources(database=db, user_id=household_id),
        )

    return SearchResponse(
        query=normalized_query,
        search_mode="global",
        semantic_active=False,
        match_type="n/a",
        results=[
            SearchResultWire(
                kind=r.kind,
                title=r.title,
                meta=r.meta,
                score=r.score,
                action_kind=r.action_kind,
                action_target=r.action_target,
                household_id=r.household_id,
            )
            for r in results
        ],
        count=len(results),
    )


@router.get(
    "/inventory",
    response_model=SearchResponse,
    summary="Inventory-scoped search with semantic embedding fallback",
)
def search_inventory(
    q: str = Query(..., min_length=1, description="Search query"),
    ctx: HouseholdContext = Depends(require_household),
) -> SearchResponse:
    """Search inventory lots by name with semantic embedding fallback.

    Uses ``ShopFindService.semantic_find_inventory_compatible`` which:
    1. Tries semantic (embedding) search via BGE-M3 when sentence-transformers
       is available.
    2. Falls back to prefix + alias text matching.
    3. Returns match type and confidence for each result.

    The mobile app uses this to find items when adding to a list or
    checking what's at home.

    **Embedding provider:** BGE-M3 (wired specifically for this endpoint;
    see ``shopstack/providers/embeddings_provider.py``). The model is
    lazily loaded on the first request. If ``sentence-transformers`` is not
    installed or the model fails to load, search degrades gracefully to
    text-only matching.
    """
    from shopstack.app_context import db
    from shopstack.services.find import ShopFindService

    service = ShopFindService(db, embedding_provider=_BGE_M3_PROVIDER)
    result = service.semantic_find_inventory_compatible(
        query=q, user_id=ctx.household_id,
    )
    raw_results = result.get("results", [])
    semantic_active = bool(result.get("semantic_active", False))
    match_type = str(result.get("match_type", "none") or "none")
    return SearchResponse(
        query=q,
        search_mode="inventory-semantic" if semantic_active else "inventory-text",
        semantic_active=semantic_active,
        match_type=match_type,
        expanded_queries=list(result.get("expanded_queries", [])),
        results=[
            SearchResultWire(
                kind="inventory",
                title=r.get("lot", {}).get("display_name", "")
                         or r.get("lot", {}).get("canonical_name", q),
                meta=(
                    f"match: {r.get('match_type', 'none')} "
                    f"confidence: {r.get('confidence', 0.0):.2f}"
                ),
                score=r.get("confidence", 0.0),
                action_kind="tab",
                action_target="pantry",
                household_id=ctx.household_id,
            )
            for r in raw_results
        ],
        count=len(raw_results),
    )


@router.post(
    "/voice-intent",
    response_model=VoiceIntentResponse,
    summary="Parse a spoken shopping command into normalized intent fields",
)
def parse_voice_intent(
    body: VoiceIntentRequest,
) -> VoiceIntentResponse:
    """Parse a transcript into the same voice-intent shape used in the UI.

    This endpoint is intentionally public: it does not touch household data.
    It gives mobile/voice clients a stable parser contract without forcing
    them to re-implement normalization or alias handling.
    """
    from shopstack.services.speech_intent import parse_speech_intent

    parsed = parse_speech_intent(body.text, language=body.language)
    return VoiceIntentResponse(
        original_text=parsed.original_text,
        translated_text=parsed.translated_text,
        language=parsed.language,
        action=parsed.action,
        canonical_items=list(parsed.canonical_items),
        target_scene=parsed.target_scene.value,
        confidence=parsed.confidence,
        notes=list(parsed.notes),
    )


__all__ = ["legacy_search_global", "router"]
