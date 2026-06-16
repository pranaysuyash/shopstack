from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from shopstack.persistence.database import Database

__all__ = [
    "SearchResult",
    "semantic_search",
    "build_item_embeddings",
]


@dataclass
class SearchResult:
    canonical_name: str
    display_name: str
    category: str
    match_type: Literal["exact", "prefix", "semantic"]
    score: float


def _canonicalize_query(query: str) -> str | None:
    """Try to canonicalize a Hinglish/regional query into the canonical English name.

    Returns the canonical name if ``resolve_canonical`` recognises the query
    (e.g. "doodh" → "milk", "pyaaz" → "onion"), otherwise ``None``. The caller
    should fall through to prefix/semantic search when this returns ``None``.

    This bridges the gap between Hinglish household vocabulary and the English
    canonical names that market snapshots use, without requiring every
    household to re-train their brain to English.
    """
    try:
        from shopstack.domain import resolve_canonical

        return resolve_canonical(query)
    except Exception:
        return None


def _extract_unique_items(database: Database) -> dict[str, dict[str, str]]:
    items: dict[str, dict[str, str]] = {}
    for lot in database.get_inventory():
        if lot.canonical_name not in items:
            items[lot.canonical_name] = {
                "display_name": lot.display_name,
                "category": lot.category,
            }
    return items


def semantic_search(
    database: Database,
    query: str,
    threshold: float = 0.6,
    embedding_provider: Any = None,
) -> list[SearchResult]:
    q = query.strip().lower()
    if not q:
        return []

    items = _extract_unique_items(database)
    results: list[SearchResult] = []

    # 0. Hinglish/regional canonicalization. "doodh" → "milk" hits the exact
    #    branch below; "tamatar" → "tomato" same. This is the most-common
    #    search pattern for an Indian household app.
    canonical_q = _canonicalize_query(query)
    if canonical_q and canonical_q != q and canonical_q in items:
        results.append(SearchResult(
            canonical_name=canonical_q,
            display_name=items[canonical_q]["display_name"],
            category=items[canonical_q]["category"],
            match_type="exact",
            score=1.0,
        ))
        return results

    for cname in items:
        if cname.lower() == q:
            results.append(SearchResult(
                canonical_name=cname,
                display_name=items[cname]["display_name"],
                category=items[cname]["category"],
                match_type="exact",
                score=1.0,
            ))

    if not results:
        for cname in items:
            dname = items[cname]["display_name"]
            if q in cname.lower() or q in dname.lower():
                results.append(SearchResult(
                    canonical_name=cname,
                    display_name=dname,
                    category=items[cname]["category"],
                    match_type="prefix",
                    score=0.8,
                ))

    if not results and embedding_provider is not None:
        try:
            from shopstack.eval.recorder import CAP_EMBEDDINGS, SHAPE_STRUCTURED, record_model_call
            with record_model_call(
                domain_route="semantic_search",
                capability=CAP_EMBEDDINGS,
                capability_expected_shape=SHAPE_STRUCTURED,
            ) as rec:
                rec.set_prompt(f"embed_query:{q}|embed_docs:{list(items.keys())}")
                query_embs = embedding_provider.embed([q])
                if not query_embs:
                    return results
                query_emb = query_embs[0]
                item_texts = list(items.keys())
                item_embs = embedding_provider.embed(item_texts)
                rec.set_output(f"query_emb_dim={len(query_emb) if query_emb else 0},doc_count={len(item_embs) if item_embs else 0}")
            if not item_embs or len(item_embs) != len(item_texts):
                return results
            scored: list[tuple[float, str]] = []
            for i, cname in enumerate(item_texts):
                sim = embedding_provider.similarity(query_emb, item_embs[i])
                if sim >= threshold:
                    scored.append((sim, cname))
            scored.sort(key=lambda x: x[0], reverse=True)
            results = [
                SearchResult(
                    canonical_name=cname,
                    display_name=items[cname]["display_name"],
                    category=items[cname]["category"],
                    match_type="semantic",
                    score=round(sim, 4),
                )
                for sim, cname in scored
            ]
        except Exception:
            pass

    return results


def build_item_embeddings(
    database: Database,
    provider: Any,
) -> dict[str, list[float]]:
    items = _extract_unique_items(database)
    names = list(items.keys())
    try:
        from shopstack.eval.recorder import CAP_EMBEDDINGS, SHAPE_STRUCTURED, record_model_call
        with record_model_call(
            domain_route="build_item_embeddings",
            capability=CAP_EMBEDDINGS,
            capability_expected_shape=SHAPE_STRUCTURED,
        ) as rec:
            rec.set_prompt(f"embed_items:{names[:20]}... ({len(names)} total)")
            embeddings = provider.embed(names)
            rec.set_output(f"embed_count={len(embeddings) if embeddings else 0}")
    except Exception:
        return {}
    return dict(zip(names, embeddings))
