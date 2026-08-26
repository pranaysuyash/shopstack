"""Provider-neutral retrieval evaluation cases for ShopStack.

The corpus describes intent and expected ranking, not an embedding provider.
It is deliberately small and synthetic until independently labeled household
queries are curated. A hard-negative case is a query whose intended item must
rank ahead of named neighboring inventory items.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalCase:
    """One retrieval query with an explicit positive or abstention contract."""

    case_id: str
    query: str
    expected: str | None
    category: str
    no_match: bool = False
    hard_negatives: tuple[str, ...] = ()


def build_retrieval_corpus() -> tuple[RetrievalCase, ...]:
    """Return the versioned starter corpus used by retrieval evaluations."""
    positives = (
        ("milk", "milk", "english"),
        ("rice", "rice", "english"),
        ("eggs", "eggs", "english"),
        ("onion", "onion", "english"),
        ("tomato", "tomato", "english"),
        ("potato", "potato", "english"),
        ("curd", "curd", "english"),
        ("butter", "butter", "english"),
        ("bread", "bread", "english"),
        ("dal", "dal", "english"),
        ("doodh", "milk", "hindi"),
        ("dahi", "curd", "hindi"),
        ("chawal", "rice", "hindi"),
        ("aloo", "potato", "hindi"),
        ("anda", "eggs", "hindi"),
        ("pyaaz", "onion", "hindi"),
        ("tamatar", "tomato", "hindi"),
    )
    hard_negatives = (
        RetrievalCase("HN-001", "dairy spread", "butter", "hard_negative", hard_negatives=("milk", "curd")),
        RetrievalCase("HN-002", "fermented dairy", "curd", "hard_negative", hard_negatives=("milk", "butter")),
        RetrievalCase("HN-003", "red salad vegetable", "tomato", "hard_negative", hard_negatives=("onion", "potato")),
        RetrievalCase("HN-004", "root vegetable", "potato", "hard_negative", hard_negatives=("onion", "tomato")),
        RetrievalCase("HN-005", "breakfast loaf", "bread", "hard_negative", hard_negatives=("rice", "flour")),
        RetrievalCase("HN-006", "grain for cooking", "rice", "hard_negative", hard_negatives=("dal", "flour")),
    )
    no_match = (
        RetrievalCase("NM-001", "laptop charger", None, "no_match", no_match=True),
        RetrievalCase("NM-002", "shampoo", None, "no_match", no_match=True),
        RetrievalCase("NM-003", "toothpaste", None, "no_match", no_match=True),
        RetrievalCase("NM-004", "coffee", None, "no_match", no_match=True),
        RetrievalCase("NM-005", "dishwasher", None, "no_match", no_match=True),
        RetrievalCase("NM-006", "coriander", None, "no_match", no_match=True),
    )
    return tuple(
        RetrievalCase(f"POS-{index:03d}", query, expected, category)
        for index, (query, expected, category) in enumerate(positives, start=1)
    ) + hard_negatives + no_match


def validate_retrieval_corpus(cases: tuple[RetrievalCase, ...] | None = None) -> tuple[str, ...]:
    """Return structural errors without loading a model or application state."""
    rows = cases if cases is not None else build_retrieval_corpus()
    errors: list[str] = []
    ids: set[str] = set()
    for case in rows:
        if case.case_id in ids:
            errors.append(f"duplicate case id: {case.case_id}")
        ids.add(case.case_id)
        if not case.query.strip():
            errors.append(f"empty query: {case.case_id}")
        if case.no_match and case.expected is not None:
            errors.append(f"no-match case has expected item: {case.case_id}")
        if not case.no_match and not case.expected:
            errors.append(f"positive case missing expected item: {case.case_id}")
        if case.expected in case.hard_negatives:
            errors.append(f"expected item is also hard negative: {case.case_id}")
    return tuple(errors)
