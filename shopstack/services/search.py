from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from shopstack.persistence.database import Database


@dataclass
class SearchResult:
    canonical_name: str
    display_name: str
    category: str
    match_type: Literal["exact", "prefix", "semantic"]
    score: float


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
            query_embs = embedding_provider.embed([q])
            if not query_embs:
                return results
            query_emb = query_embs[0]
            item_texts = list(items.keys())
            item_embs = embedding_provider.embed(item_texts)
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
        embeddings = provider.embed(names)
    except Exception:
        return {}
    return dict(zip(names, embeddings))
