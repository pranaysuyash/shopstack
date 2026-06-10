from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .analytics import (
    available_canonical_names,
    find_all_options,
    find_cheapest_weight_option,
)
from .metadata import get_produce_metadata
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


# ─── Decision-Aware Basket Optimizer ───────────────────────────────────────


@dataclass
class OptimizedBasketItem:
    requested_name: str
    canonical_name: str
    decision: str  # "buy" | "skip" | "use_soon" | "compare" | "unavailable"
    reason_type: str  # "enough_stock" | "waste_risk" | "stale_data" | "no_availability" | "price_low" | "price_high" | "inventory_subtracted"
    reason: str
    matched: bool
    requested_quantity: float = 1.0
    unit: str = "unit"
    already_owned_quantity: float = 0.0
    net_quantity_to_buy: float = 0.0
    recommended_record: NormalizedMarketRecord | None = None
    alternatives: list[NormalizedMarketRecord] = field(default_factory=list)
    estimated_price_inr: float | None = None
    estimated_price_per_kg: float | None = None
    waste_risk: str = "unknown"
    freshness_note: str = ""


@dataclass
class OptimizedBasket:
    items: list[OptimizedBasketItem] = field(default_factory=list)

    @property
    def buy(self) -> list[OptimizedBasketItem]:
        return [i for i in self.items if i.decision == "buy"]

    @property
    def skip(self) -> list[OptimizedBasketItem]:
        return [i for i in self.items if i.decision == "skip"]

    @property
    def use_soon(self) -> list[OptimizedBasketItem]:
        return [i for i in self.items if i.decision == "use_soon"]

    @property
    def total_estimated(self) -> float:
        return round(sum(
            i.estimated_price_inr or 0 for i in self.buy
        ), 2)

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "total_requested": len(self.items),
            "buy": len(self.buy),
            "skip": len(self.skip),
            "use_soon": len(self.use_soon),
            "total_estimated_price_inr": self.total_estimated,
        }


def _normalize_unit_to_grams(qty: float, unit: str) -> float:
    """Convert a quantity in user-facing units to grams for price calculation."""
    u = unit.lower().strip()
    if u in ("kg", "kilo", "kilos", "kilogram", "kilograms"):
        return qty * 1000
    if u in ("g", "gram", "grams"):
        return qty
    if u in ("l", "litre", "liter", "litres", "liters"):
        return qty * 1000
    if u in ("ml", "milliliter", "millilitre"):
        return qty
    # For piece-based items, return as-is (matched against piece records)
    return qty


def build_optimized_basket(
    requested_items: list[dict[str, Any]],
    snapshot: MarketSnapshot,
    inventory_map: dict[str, float] | None = None,
    available_only: bool = True,
    budget_inr: float | None = None,
    household_size: int = 1,
    days_to_plan: int = 3,
    avoid_items: list[str] | None = None,
) -> OptimizedBasket:
    """Build a decision-aware basket from requested items and market snapshot.

    Each item is classified into buy / skip / use_soon / compare / unavailable
    with an explicit ``reason_type`` explaining the classification logic.

    Args:
        requested_items: List of dicts with ``canonical_name``, ``requested_quantity``, ``unit``.
        snapshot: Market snapshot with normalized records.
        inventory_map: Map of canonical_name -> total quantity owned (inventory subtraction).
        available_only: If True, only consider available items when recommending.
        budget_inr: Optional budget cap in INR. If set, items beyond budget get ``over_budget`` reason_type.
        household_size: Number of people. Adjusts recommended quantities.
        days_to_plan: Number of days to plan for. Adjusts recommended quantities.
        avoid_items: List of canonical names the household wants to avoid.

    Returns:
        An ``OptimizedBasket`` with per-item classifications.
    """
    inventory_map = inventory_map or {}
    avoid_set = {a.lower().strip() for a in (avoid_items or [])}
    available = available_canonical_names(snapshot)
    snapshot_date = _parse_date(snapshot.captured_at) if snapshot.captured_at else date.today()
    age_days = (date.today() - snapshot_date).days if snapshot_date else 0
    is_stale = age_days > 1
    freshness_note = f"Snapshot {age_days}d old" if is_stale else "Today's data"

    results: list[OptimizedBasketItem] = []
    running_total = 0.0

    for raw in requested_items:
        name = raw.get("canonical_name", "").strip()
        if not name:
            continue
        qty = float(raw.get("requested_quantity", 1.0) or 1.0)
        unit = raw.get("unit", "unit") or "unit"

        # Inventory subtraction
        owned = inventory_map.get(name.lower(), 0.0)
        net_needed = max(qty - owned, 0.0)

        # Match to snapshot
        canonical = _match_canonical(name, available)
        if canonical is None:
            results.append(OptimizedBasketItem(
                requested_name=name,
                canonical_name=name,
                decision="unavailable",
                reason_type="no_availability",
                reason=f"No market data found for {name}",
                matched=False,
                requested_quantity=qty,
                unit=unit,
                already_owned_quantity=owned,
                net_quantity_to_buy=qty,
                freshness_note=freshness_note,
            ))
            continue

        # Produce metadata for waste risk
        meta = _get_produce_meta(canonical)
        waste_risk = meta.waste_risk if meta else "unknown"
        shelf_life = meta.shelf_life_days if meta else 0

        # Check for "use soon" signal from produce metadata
        if owned > 0 and shelf_life > 0 and shelf_life <= 3:
            results.append(OptimizedBasketItem(
                requested_name=name,
                canonical_name=canonical,
                decision="use_soon",
                reason_type="waste_risk",
                reason=f"Use existing {owned} {unit} before buying more",
                matched=True,
                requested_quantity=qty,
                unit=unit,
                already_owned_quantity=owned,
                net_quantity_to_buy=0,
                waste_risk=waste_risk,
                freshness_note=freshness_note,
            ))
            continue

        # Skip if enough already owned
        if net_needed <= 0:
            results.append(OptimizedBasketItem(
                requested_name=name,
                canonical_name=canonical,
                decision="skip",
                reason_type="enough_stock",
                reason=f"Already have {owned} {unit} at home",
                matched=True,
                requested_quantity=qty,
                unit=unit,
                already_owned_quantity=owned,
                net_quantity_to_buy=0,
                waste_risk=waste_risk,
                freshness_note=freshness_note,
            ))
            continue

        # Waste risk for high-waste items
        if waste_risk == "high" and owned > 0:
            results.append(OptimizedBasketItem(
                requested_name=name,
                canonical_name=canonical,
                decision="skip",
                reason_type="waste_risk",
                reason=f"High waste risk — you have {owned} {unit} already",
                matched=True,
                requested_quantity=qty,
                unit=unit,
                already_owned_quantity=owned,
                net_quantity_to_buy=0,
                waste_risk=waste_risk,
                freshness_note=freshness_note,
            ))
            continue

        # Stale data warning
        if is_stale and not available_only:
            results.append(OptimizedBasketItem(
                requested_name=name,
                canonical_name=canonical,
                decision="compare",
                reason_type="stale_data",
                reason=f"Market data {age_days} days old — verify prices before checkout",
                matched=True,
                requested_quantity=qty,
                unit=unit,
                already_owned_quantity=owned,
                net_quantity_to_buy=net_needed,
                waste_risk=waste_risk,
                freshness_note=freshness_note,
            ))
            continue

        # Skip items the household avoids
        if name.lower().strip() in avoid_set:
            results.append(OptimizedBasketItem(
                requested_name=name,
                canonical_name=canonical,
                decision="skip",
                reason_type="household_avoids",
                reason=f"{name.title().replace('_', ' ')} is on your household avoid list",
                matched=True,
                requested_quantity=qty,
                unit=unit,
                already_owned_quantity=owned,
                net_quantity_to_buy=0,
                waste_risk=waste_risk or "unknown",
                freshness_note=freshness_note,
            ))
            continue

        # Scale quantity by household size and days to plan
        scaled_qty = qty * household_size * (days_to_plan / 3.0) if household_size > 0 else qty
        net_needed = max(scaled_qty - owned, 0.0)

        # Find cheapest market option
        cheapest = find_cheapest_weight_option(snapshot, canonical, available_only)
        all_opts = find_all_options(snapshot, canonical, available_only)

        if cheapest is not None:
            # Convert net_needed to grams to match normalized_quantity (always in grams)
            net_needed_grams = _normalize_unit_to_grams(net_needed, unit)
            nq = cheapest.normalized_quantity
            if nq is not None and nq > 0 and net_needed_grams > 0:
                _price = cheapest.price_inr * (net_needed_grams / nq)
            else:
                _price = cheapest.price_inr

            # Budget cap check
            if budget_inr is not None and running_total + _price > budget_inr:
                results.append(OptimizedBasketItem(
                    requested_name=name,
                    canonical_name=canonical,
                    decision="compare",
                    reason_type="over_budget",
                    reason=f"Exceeds remaining budget of \u20b9{budget_inr - running_total:.0f} (\u20b9{_price:.0f} needed)",
                    matched=True,
                    requested_quantity=qty,
                    unit=unit,
                    already_owned_quantity=owned,
                    net_quantity_to_buy=net_needed,
                    recommended_record=cheapest,
                    alternatives=[r for r in all_opts if r is not cheapest][:3],
                    estimated_price_inr=cheapest.price_inr,
                    estimated_price_per_kg=cheapest.price_per_kg,
                    waste_risk=waste_risk,
                    freshness_note=freshness_note,
                ))
                continue
            running_total += _price

            results.append(OptimizedBasketItem(
                requested_name=name,
                canonical_name=canonical,
                decision="buy",
                reason_type="price_low",
                reason=f"Buy {net_needed:.1f} {unit} at \u20b9{cheapest.price_inr:.0f} (\u20b9{cheapest.price_per_kg:.0f}/kg)",
                matched=True,
                requested_quantity=qty,
                unit=unit,
                already_owned_quantity=owned,
                net_quantity_to_buy=net_needed,
                recommended_record=cheapest,
                alternatives=[r for r in all_opts if r is not cheapest][:3],
                estimated_price_inr=cheapest.price_inr,
                estimated_price_per_kg=cheapest.price_per_kg,
                waste_risk=waste_risk,
                freshness_note=freshness_note,
            ))
        else:
            # No weight-based option found — try piece-based
            non_weight = [
                r for r in all_opts
                if not r.is_weight_based and not r.is_combo
            ]
            if non_weight:
                rec = min(non_weight, key=lambda r: r.price_inr)
                results.append(OptimizedBasketItem(
                    requested_name=name,
                    canonical_name=canonical,
                    decision="buy",
                    reason_type="price_low",
                    reason=f"Buy {net_needed:.1f} {unit} — piece-based at \u20b9{rec.price_inr:.0f}",
                    matched=True,
                    requested_quantity=qty,
                    unit=unit,
                    already_owned_quantity=owned,
                    net_quantity_to_buy=net_needed,
                    recommended_record=rec,
                    alternatives=non_weight[:3],
                    estimated_price_inr=rec.price_inr,
                    waste_risk=waste_risk,
                    freshness_note=freshness_note,
                ))
            else:
                results.append(OptimizedBasketItem(
                    requested_name=name,
                    canonical_name=canonical,
                    decision="unavailable",
                    reason_type="no_availability",
                    reason="No available weight or piece options",
                    matched=True,
                    requested_quantity=qty,
                    unit=unit,
                    already_owned_quantity=owned,
                    net_quantity_to_buy=net_needed,
                    freshness_note=freshness_note,
                ))

    return OptimizedBasket(items=results)


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def _get_produce_meta(canonical_name: str):
    try:
        return get_produce_metadata(canonical_name)
    except Exception:
        return None


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
