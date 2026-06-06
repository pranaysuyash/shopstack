from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .analytics import (
    available_canonical_names,
    find_all_options,
    find_cheapest_weight_option,
)
from .schema import MarketSnapshot, NormalizedMarketRecord


@dataclass
class BasketItem:
    requested_name: str
    canonical_name: str
    matched: bool
    reason: str
    recommended_record: NormalizedMarketRecord | None
    alternatives: list[NormalizedMarketRecord]
    estimated_price_inr: float | None
    estimated_price_per_kg: float | None


def build_basket(
    items: list[str],
    snapshot: MarketSnapshot,
    available_only: bool = True,
) -> list[BasketItem]:
    available = available_canonical_names(snapshot)
    results: list[BasketItem] = []

    for raw_item in items:
        cleaned = raw_item.strip()
        if not cleaned:
            continue
        canonical = _match_canonical(cleaned, available)
        if canonical is None:
            results.append(
                BasketItem(
                    requested_name=cleaned,
                    canonical_name="",
                    matched=False,
                    reason="no_match_in_snapshot",
                    recommended_record=None,
                    alternatives=[],
                    estimated_price_inr=None,
                    estimated_price_per_kg=None,
                )
            )
            continue

        cheapest = find_cheapest_weight_option(snapshot, canonical, available_only)
        all_opts = find_all_options(snapshot, canonical, available_only)

        if cheapest is None:
            non_weight = [
                r
                for r in all_opts
                if not r.is_weight_based and not r.is_combo
            ]
            if non_weight:
                rec = min(non_weight, key=lambda r: r.price_inr)
                results.append(
                    BasketItem(
                        requested_name=cleaned,
                        canonical_name=canonical,
                        matched=True,
                        reason="piece_based_only",
                        recommended_record=rec,
                        alternatives=non_weight[:3],
                        estimated_price_inr=rec.price_inr,
                        estimated_price_per_kg=None,
                    )
                )
            else:
                results.append(
                    BasketItem(
                        requested_name=cleaned,
                        canonical_name=canonical,
                        matched=True,
                        reason="no_available_weight_or_piece",
                        recommended_record=None,
                        alternatives=all_opts[:3],
                        estimated_price_inr=None,
                        estimated_price_per_kg=None,
                    )
                )
        else:
            results.append(
                BasketItem(
                    requested_name=cleaned,
                    canonical_name=canonical,
                    matched=True,
                    reason="weight_based_cheapest",
                    recommended_record=cheapest,
                    alternatives=[
                        r for r in all_opts if r is not cheapest
                    ][:3],
                    estimated_price_inr=cheapest.price_inr,
                    estimated_price_per_kg=cheapest.price_per_kg,
                )
            )

    return results


def basket_summary(basket: list[BasketItem]) -> dict[str, Any]:
    matched = [b for b in basket if b.matched]
    unmatched = [b for b in basket if not b.matched]
    total_estimated = sum(
        b.estimated_price_inr for b in matched if b.estimated_price_inr
    )
    return {
        "total_requested": len(basket),
        "matched": len(matched),
        "unmatched": len(unmatched),
        "total_estimated_price_inr": round(total_estimated, 2),
        "unmatched_items": [b.requested_name for b in unmatched],
    }


_DISPLAY_TO_CANONICAL: dict[str, str] = {
    "tomato": "tomato",
    "tomatoes": "tomato",
    "onion": "onion",
    "onions": "onion",
    "potato": "potato",
    "potatoes": "potato",
    "carrot": "carrot",
    "carrots": "carrot",
    "cucumber": "cucumber",
    "cucumbers": "cucumber",
    "brinjal": "brinjal",
    "brinjals": "brinjal",
    "eggplant": "brinjal",
    "capsicum": "capsicum",
    "bell pepper": "bell_pepper",
    "cauliflower": "cauliflower",
    "broccoli": "broccoli",
    "ginger": "ginger",
    "garlic": "garlic",
    "beetroot": "beetroot",
    "radish": "radish",
    "okra": "ladys_finger",
    "lady finger": "ladys_finger",
    "bottle gourd": "bottle_gourd",
    "bitter gourd": "bitter_gourd",
    "ridge gourd": "ridge_gourd",
    "drumstick": "drumstick",
    "mint": "mint",
    "coriander": "coriander",
    "curry leaves": "curry_leaves",
    "green chilli": "green_chilli",
    "green chillies": "green_chilli",
    "coconut": "coconut",
    "sweet potato": "sweet_potato",
    "yam": "yam",
    "raw banana": "raw_banana",
    "raw mango": "raw_mango",
    "french beans": "french_beans",
    "cluster beans": "cluster_beans",
    "zucchini": "zucchini",
    "red cabbage": "red_cabbage",
    "baby potato": "baby_potato",
}


def _match_canonical(query: str, available: set[str]) -> str | None:
    lowered = query.lower().strip()
    if lowered in available:
        return lowered
    mapped = _DISPLAY_TO_CANONICAL.get(lowered)
    if mapped and mapped in available:
        return mapped
    for display, canonical in _DISPLAY_TO_CANONICAL.items():
        if display in lowered or lowered in display:
            if canonical in available:
                return canonical
    partial = [
        a for a in available if lowered in a or a in lowered
    ]
    if partial:
        return partial[0]
    return None
