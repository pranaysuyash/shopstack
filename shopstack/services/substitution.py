"""Sold-out substitution engine — suggests alternatives for unavailable items.

The review (§3.6) identifies sold-out awareness as a key intelligence gap:
    "Broccoli sold out, try cauliflower or beans."
    "Chemical-free version sold out; regular version available."
    "Premium version sold out; basic equivalent available."

This service provides structured substitution suggestions from market data,
product metadata, and canonical product relationships.

Substitution types:
  - variety_substitution: same product, different variety (hybrid→desi tomato)
  - premium_to_basic: upgrade/ad version sold out, basic available
  - category_alternative: different product in same category (broccoli→cauliflower)
  - size_substitution: different pack size of same product
  - ingredient_swap: recipe-compatible alternative
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from shopstack.market.schema import MarketSnapshot, NormalizedMarketRecord

logger = logging.getLogger(__name__)

__all__ = [
    "SubstitutionSuggestion",
    "SubstitutionResult",
    "find_substitutions",
    "SUGGEST_SUBSTITUTE_MAP",
]

# ── Canonical substitution map: canonical_name → list of (target, reason_type) ──
# First item is the preferred substitute.
_SUBSTITUTE_MAP: dict[str, list[tuple[str, str]]] = {
    "broccoli": [("cauliflower", "category_alternative"), ("french_beans", "category_alternative"), ("cabbage", "category_alternative"), ("zucchini", "category_alternative")],
    "zucchini": [("cucumber", "category_alternative"), ("bottle_gourd", "category_alternative"), ("ridge_gourd", "category_alternative")],
    "cucumber": [ ("zucchini", "category_alternative"), ("bottle_gourd", "category_alternative")],
    "cauliflower": [("broccoli", "category_alternative"), ("cabbage", "category_alternative")],
    "cabbage": [("cauliflower", "category_alternative"), ("broccoli", "category_alternative")],
    "ridge_gourd": [("bottle_gourd", "ingredient_swap"), ("snake_gourd", "ingredient_swap"), ("pointed_gourd", "ingredient_swap")],
    "bottle_gourd": [("ridge_gourd", "ingredient_swap"), ("snake_gourd", "ingredient_swap")],
    "bitter_gourd": [ ("ridge_gourd", "ingredient_swap"), ("bottle_gourd", "ingredient_swap")],
    "snake_gourd": [("ridge_gourd", "ingredient_swap"), ("pointed_gourd", "ingredient_swap")],
    "pointed_gourd": [("ridge_gourd", "ingredient_swap"), ("bottle_gourd", "ingredient_swap")],
    "french_beans": [("cluster_beans", "category_alternative"), ("haricot_beans", "category_alternative"), ("broad_beans", "category_alternative")],
    "cluster_beans": [("french_beans", "category_alternative"), ("broad_beans", "category_alternative")],
    "broad_beans": [("french_beans", "category_alternative"), ("cluster_beans", "category_alternative")],
    "capsicum": [("bell_pepper", "variety_substitution")],
    "bell_pepper": [("capsicum", "variety_substitution")],
    "brinjal": [("capsicum", "ingredient_swap"), ("potato", "ingredient_swap")],
    "drumstick": [("cluster_beans", "ingredient_swap"), ("radish", "ingredient_swap")],
    "sweet_potato": [("potato", "ingredient_swap"), ("yam", "ingredient_swap")],
    "raw_banana": [("potato", "ingredient_swap"), ("yam", "ingredient_swap")],
    "coriander": [("mint", "ingredient_swap"), ("curry_leaves", "ingredient_swap")],
    "mint": [("coriander", "ingredient_swap"), ("curry_leaves", "ingredient_swap")],
    "curry_leaves": [("coriander", "ingredient_swap"), ("mint", "ingredient_swap")],
    "green_chilli": [("capsicum", "ingredient_swap"), ("bell_pepper", "ingredient_swap")],
    "garlic": [("ginger", "ingredient_swap")],
    "ginger": [("garlic", "ingredient_swap")],
    "ladys_finger": [("french_beans", "category_alternative"), ("cluster_beans", "category_alternative")],
    "beetroot": [("carrot", "ingredient_swap"), ("radish", "ingredient_swap")],
    "radish": [("carrot", "ingredient_swap"), ("beetroot", "ingredient_swap")],
    "carrot": [ ("beetroot", "ingredient_swap"), ("radish", "ingredient_swap")],
    "yam": [("sweet_potato", "ingredient_swap"), ("potato", "ingredient_swap")],
    "coccinia": [("ridge_gourd", "ingredient_swap"), ("bottle_gourd", "ingredient_swap")],
}

# Substitution type labels for display
_SUBSTITUTION_TYPE_LABELS: dict[str, str] = {
    "variety_substitution": "Try a different variety",
    "premium_to_basic": "Regular version available",
    "category_alternative": "Try this instead",
    "size_substitution": "Different pack size available",
    "ingredient_swap": "Swap with this ingredient",
}

# Premium brand/claim keywords that indicate an "upgrade" variant
_UPGRADE_KEYWORDS = [
    "chemical free", "ozone washed", "pesticide free",
    "premium", "organic", "exotic", "nectr", "pluckk",
]

# Premium claim tags in NormalizedMarketRecord fields
_CLAIM_FIELDS = ["tag", "variety", "description", "raw_name"]


@dataclass
class SubstitutionSuggestion:
    """A single substitution suggestion for a sold-out item."""
    original_canonical: str
    substitute_canonical: str
    substitute_display: str
    substitution_type: str  # variety_substitution / premium_to_basic / category_alternative / size_substitution / ingredient_swap
    reason: str
    confidence: float  # 0.0–1.0
    substitute_record: NormalizedMarketRecord | None = None
    price_inr: float | None = None
    price_per_kg: float | None = None
    is_available: bool = True


@dataclass
class SubstitutionResult:
    """All substitution suggestions for a snapshot query."""
    original_canonical: str
    original_display: str
    suggestions: list[SubstitutionSuggestion] = field(default_factory=list)

    @property
    def available_suggestions(self) -> list[SubstitutionSuggestion]:
        return [s for s in self.suggestions if s.is_available]

    @property
    def best_available(self) -> SubstitutionSuggestion | None:
        return self.available_suggestions[0] if self.available_suggestions else None

    @property
    def has_suggestions(self) -> bool:
        return len(self.suggestions) > 0

    @property
    def has_available_alternative(self) -> bool:
        return len(self.available_suggestions) > 0


def find_substitutions(
    canonical_name: str,
    snapshot: MarketSnapshot,
    include_available: bool = False,
) -> SubstitutionResult:
    """Find substitution suggestions for a (sold-out) item from a market snapshot.

    Args:
        canonical_name: The canonical name of the sold-out item.
        snapshot: A MarketSnapshot to search for alternatives.
        include_available: If True, include substitions even if original is available.

    Returns:
        SubstitutionResult with ranked suggestions.
    """
    all_records: list[NormalizedMarketRecord] = snapshot.normalized_records
    available = [r for r in all_records if r.is_available]
    sold_out = [r for r in all_records if not r.is_available]

    # Check if the item is sold-out (or just querying generally)
    original_sold_out = any(
        r.canonical_name == canonical_name and not r.is_available
        for r in all_records
    )
    if not original_sold_out and not include_available:
        return SubstitutionResult(
            original_canonical=canonical_name,
            original_display=canonical_name.replace("_", " ").title(),
        )

    display_name = canonical_name.replace("_", " ").title()
    suggestions: list[SubstitutionSuggestion] = []

    # 1. Premium-to-basic: if the sold-out item has an upgrade tag,
    #    check if a regular (non-upgrade) version is available.
    sold_out_with_upgrade = [
        r for r in sold_out
        if r.canonical_name == canonical_name and (r.is_upgrade or _is_premium(r))
    ]
    if sold_out_with_upgrade:
        regular_available = [
            r for r in available
            if r.canonical_name == canonical_name and not r.is_upgrade and not _is_premium(r)
        ]
        for reg in regular_available:
            suggestions.append(SubstitutionSuggestion(
                original_canonical=canonical_name,
                substitute_canonical=canonical_name,
                substitute_display=f"Regular {display_name}",
                substitution_type="premium_to_basic",
                reason=f"Premium version sold out — basic version available at ₹{reg.price_inr:.0f}",
                confidence=0.85,
                substitute_record=reg,
                price_inr=reg.price_inr,
                price_per_kg=reg.price_per_kg,
                is_available=True,
            ))
            break  # one basic suggestion is enough

    # 2. Size substitution: different pack size of the same item available
    same_item_available = [
        r for r in available
        if r.canonical_name == canonical_name and not r.is_combo
    ]
    if same_item_available and sold_out_with_upgrade:
        # Already have premium-to-basic suggestions; still offer size variants
        for alt in same_item_available[1:3]:  # skip first (used as basic version)
            suggestions.append(SubstitutionSuggestion(
                original_canonical=canonical_name,
                substitute_canonical=canonical_name,
                substitute_display=f"{display_name} ({alt.raw_size})",
                substitution_type="size_substitution",
                reason=f"Available in {alt.raw_size} at ₹{alt.price_inr:.0f}",
                confidence=0.8,
                substitute_record=alt,
                price_inr=alt.price_inr,
                price_per_kg=alt.price_per_kg,
                is_available=True,
            ))
    elif same_item_available:
        # Original item is available — offer size variants if more than one size exists
        if len(same_item_available) > 1:
            for alt in same_item_available[:2]:
                suggestions.append(SubstitutionSuggestion(
                    original_canonical=canonical_name,
                    substitute_canonical=canonical_name,
                    substitute_display=f"{display_name} ({alt.raw_size})",
                    substitution_type="size_substitution",
                    reason=f"Also available in {alt.raw_size} at ₹{alt.price_inr:.0f}",
                    confidence=0.75,
                    substitute_record=alt,
                    price_inr=alt.price_inr,
                    price_per_kg=alt.price_per_kg,
                    is_available=True,
                ))

    # 3. Canonical substitution map: try category alternatives
    substitutes = _SUBSTITUTE_MAP.get(canonical_name, [])
    for sub_canonical, sub_type in substitutes:
        # Find the cheapest available record for this substitute
        matching = [
            r for r in available
            if r.canonical_name == sub_canonical and not r.is_combo
        ]
        if not matching:
            continue
        cheapest = min(matching, key=lambda r: r.price_per_kg or r.price_inr)
        type_label = _SUBSTITUTION_TYPE_LABELS.get(sub_type, "Try instead")
        suggestions.append(SubstitutionSuggestion(
            original_canonical=canonical_name,
            substitute_canonical=sub_canonical,
            substitute_display=sub_canonical.replace("_", " ").title(),
            substitution_type=sub_type,
            reason=f"{type_label}: available at ₹{cheapest.price_inr:.0f} (₹{cheapest.price_per_kg:.0f}/kg)" if cheapest.price_per_kg else f"{type_label}: available at ₹{cheapest.price_inr:.0f}",
            confidence=0.7,
            substitute_record=cheapest,
            price_inr=cheapest.price_inr,
            price_per_kg=cheapest.price_per_kg,
            is_available=True,
        ))

    return SubstitutionResult(
        original_canonical=canonical_name,
        original_display=display_name,
        suggestions=suggestions,
    )


def _is_premium(record: NormalizedMarketRecord) -> bool:
    """Check if a record represents a premium/upgrade product variant."""
    check_fields = [record.raw_name, record.description, record.tag, record.variety]
    for field in check_fields:
        if not field:
            continue
        field_lower = field.lower()
        for kw in _UPGRADE_KEYWORDS:
            if kw in field_lower:
                return True
    if record.is_upgrade:
        return True
    return False


# Expose for testing
SUGGEST_SUBSTITUTE_MAP = _SUBSTITUTE_MAP
