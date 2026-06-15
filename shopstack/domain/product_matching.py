"""Product matching — fuzzy matching of item names to canonical products.

Pure business logic — no external dependencies.
Supersedes scattered matching logic in shopstack/services/find.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class MatchReason:
    """A single reason why a product matched."""
    factor: str      # "exact" | "alias" | "partial" | "substring" | "prefix" | "none"
    detail: str = ""

    def to_dict(self) -> dict:
        return {"factor": self.factor, "detail": self.detail}


@dataclass
class MatchScore:
    """Score and reasons for a product match."""
    score: float                         # 0.0–1.0
    matched_name: str = ""               # the name that matched
    canonical_name: str = ""             # canonical form if resolved
    reasons: list[MatchReason] = field(default_factory=list)

    @property
    def is_match(self) -> bool:
        return self.score >= 0.5

    def to_dict(self) -> dict:
        return {
            "score": self.score,
            "matched_name": self.matched_name,
            "canonical_name": self.canonical_name,
            "reasons": [r.to_dict() for r in self.reasons],
        }


def _strip_accents(text: str) -> str:
    """Simple accent stripping for comparison."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip, collapse whitespace."""
    t = _strip_accents(text.lower().strip())
    t = re.sub(r"\s+", " ", t)
    return t


# ── Alias tables (extend as needed) ────────────────────────────────────────

_PRODUCT_ALIASES: dict[str, list[str]] = {
    "milk": ["doodh", "dudh", "whole milk", "toned milk", "double toned"],
    "bread": ["roti", "chapati", "pav", "bun"],
    "rice": ["chawal", "basmati", "jeera rice", "sona masoori"],
    "eggs": ["anda", "egg", "hen egg"],
    "cooking_oil": ["oil", "tel", "sunflower oil", "mustard oil", "groundnut oil"],
    "salt": ["namak", "table salt", "rock salt", "sendha namak"],
    "sugar": ["chini", "cheeni", "brown sugar", "powdered sugar"],
    "tea": ["chai", "patti", "tea leaves", "green tea"],
    "flour": ["atta", "wheat flour", "maida", "refined flour"],
    "onions": ["onion", "pyaaz", "red onion"],
    "tomatoes": ["tomato", "tamatar", "cherry tomato"],
    "potatoes": ["potato", "aloo", "baby potato"],
    "garlic": ["lehsun", "lahsun"],
    "ginger": ["adrak"],
    "chicken": ["murg", "chicken breast", "chicken thigh"],
    "paneer": ["cottage cheese"],
    "curd": ["dahi", "yogurt", "yoghurt", "mosaru", "perugu", "thayir"],
    "butter": ["makhan"],
    "lentils": ["dal", "daal", "masoor dal", "moong dal", "toor dal"],
    "soap": ["sabun", "hand soap", "dish soap"],
}

# Build reverse lookup: alias -> canonical
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for canonical, aliases in _PRODUCT_ALIASES.items():
    _ALIAS_TO_CANONICAL[canonical] = canonical
    for alias in aliases:
        _ALIAS_TO_CANONICAL[_normalize(alias)] = canonical
    _ALIAS_TO_CANONICAL[_normalize(canonical)] = canonical


def score_product_match(query: str, candidate: str) -> MatchScore:
    """Score how well a query string matches a candidate product name.

    Returns a MatchScore with 0.0–1.0 score and breakdown reasons.
    Thresholds:
        1.0  = exact match
        0.9  = alias match (e.g., "doodh" matches "milk")
        0.7  = one contains the other
        0.5  = significant word overlap
        0.0  = no match
    """
    q = _normalize(query)
    c = _normalize(candidate)

    if not q or not c:
        return MatchScore(score=0.0, reasons=[MatchReason(factor="none", detail="empty input")])

    reasons: list[MatchReason] = []

    # 1. Exact match
    if q == c:
        return MatchScore(
            score=1.0,
            matched_name=candidate,
            canonical_name=_ALIAS_TO_CANONICAL.get(q, c),
            reasons=[MatchReason(factor="exact", detail=f"'{q}' == '{c}'")],
        )

    # 2. Alias match
    canonical_q = _ALIAS_TO_CANONICAL.get(q)
    canonical_c = _ALIAS_TO_CANONICAL.get(c, c)
    if canonical_q and canonical_q == canonical_c:
        return MatchScore(
            score=0.9,
            matched_name=candidate,
            canonical_name=canonical_q,
            reasons=[MatchReason(factor="alias", detail=f"'{query}' -> '{canonical_q}' == '{candidate}'")],
        )

    # 3. Substring containment
    if q in c:
        return MatchScore(
            score=0.7,
            matched_name=candidate,
            canonical_name=canonical_c,
            reasons=[MatchReason(factor="substring", detail=f"'{q}' contained in '{c}'")],
        )
    if c in q:
        return MatchScore(
            score=0.7,
            matched_name=candidate,
            canonical_name=canonical_c,
            reasons=[MatchReason(factor="substring", detail=f"'{c}' contained in '{q}'")],
        )

    # 4. Prefix match
    if q.startswith(c) or c.startswith(q):
        shorter = min(len(q), len(c))
        longer = max(len(q), len(c))
        ratio = shorter / longer if longer > 0 else 0
        return MatchScore(
            score=0.6 + 0.1 * ratio,
            matched_name=candidate,
            canonical_name=canonical_c,
            reasons=[MatchReason(factor="prefix", detail=f"'{q}' prefix of '{c}' (or vice versa)")],
        )

    # 5. Word overlap
    q_words = set(q.split())
    c_words = set(c.split())
    if q_words and c_words:
        overlap = q_words & c_words
        union = q_words | c_words
        jaccard = len(overlap) / len(union) if union else 0
        if jaccard >= 0.3:
            return MatchScore(
                score=0.4 + 0.3 * jaccard,
                matched_name=candidate,
                canonical_name=canonical_c,
                reasons=[MatchReason(factor="partial", detail=f"word overlap: {overlap}")],
            )

    return MatchScore(
        score=0.0,
        matched_name=candidate,
        canonical_name=canonical_c,
        reasons=[MatchReason(factor="none", detail="no match")],
    )


def best_match(
    query: str,
    candidates: list[str],
    threshold: float = 0.5,
) -> MatchScore | None:
    """Find the best matching candidate for a query string.

    Returns the highest-scoring MatchScore above threshold, or None.
    """
    best: MatchScore | None = None
    for candidate in candidates:
        ms = score_product_match(query, candidate)
        if ms.score >= threshold and (best is None or ms.score > best.score):
            best = ms
    return best
