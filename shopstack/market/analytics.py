from __future__ import annotations

from collections import Counter
from typing import Any

from .schema import MarketSnapshot, NormalizedMarketRecord


def compute_snapshot_analytics(snapshot: MarketSnapshot) -> dict[str, Any]:
    records = snapshot.normalized_records
    n_total = len(records)

    if n_total == 0:
        return {
            "total": 0,
            "available": 0,
            "sold_out": 0,
            "combos": 0,
            "ads": 0,
            "upgrades": 0,
            "avg_price": 0,
            "median_price": 0,
            "avg_discount": 0,
            "category_counts": {},
            "canonical_counts": {},
            "weight_price_range": {},
            "weight_price_by_canonical": {},
            "best_value_by_canonical": {},
        }

    available = [r for r in records if r.is_available]
    sold_out = [r for r in records if not r.is_available]
    combos = [r for r in records if r.is_combo]
    ads = [r for r in records if r.is_ad]
    upgrades = [r for r in records if r.is_upgrade]

    prices = [r.price_inr for r in records if r.price_inr > 0]
    avg_price = sum(prices) / len(prices) if prices else 0
    median_price = _median(prices) if prices else 0

    discounts = [
        r.computed_discount_percent
        for r in records
        if r.computed_discount_percent > 0
    ]
    avg_discount = sum(discounts) / len(discounts) if discounts else 0

    canonical_counts: dict[str, int] = Counter(
        r.canonical_name for r in records if not r.is_combo
    )

    weight_records = [
        r
        for r in records
        if r.is_weight_based and r.price_per_kg is not None and not r.is_combo
    ]
    by_canonical: dict[str, list[float]] = {}
    for r in weight_records:
        by_canonical.setdefault(r.canonical_name, []).append(r.price_per_kg)
    weight_price_by_canonical = {
        k: {
            "min": round(min(vals), 2),
            "max": round(max(vals), 2),
            "avg": round(sum(vals) / len(vals), 2),
            "count": len(vals),
        }
        for k, vals in by_canonical.items()
    }

    overall_ppa = _percentile_bounds(
        [r.price_per_kg for r in weight_records]
    )

    best_value: dict[str, NormalizedMarketRecord] = {}
    for r in weight_records:
        existing = best_value.get(r.canonical_name)
        if existing is None or r.price_per_kg < existing.price_per_kg:
            best_value[r.canonical_name] = r

    best_value_summary = {
        k: {
            "price_per_kg": v.price_per_kg,
            "price_inr": v.price_inr,
            "raw_name": v.raw_name,
            "raw_size": v.raw_size,
            "is_available": v.is_available,
        }
        for k, v in best_value.items()
    }

    return {
        "total": n_total,
        "available": len(available),
        "sold_out": len(sold_out),
        "combos": len(combos),
        "ads": len(ads),
        "upgrades": len(upgrades),
        "avg_price": round(avg_price, 2),
        "median_price": round(median_price, 2),
        "avg_discount": round(avg_discount, 2),
        "category_counts": dict(Counter(r.source_category for r in records)),
        "canonical_counts": dict(canonical_counts),
        "weight_price_range": overall_ppa,
        "weight_price_by_canonical": weight_price_by_canonical,
        "best_value_by_canonical": best_value_summary,
        "weight_records_count": len(weight_records),
    }


def _median(values: list[float]) -> float:
    if not values:
        return 0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2
    return s[mid]


def _percentile_bounds(
    values: list[float | None],
) -> dict[str, float | None]:
    clean = sorted(v for v in values if v is not None and v > 0)
    if not clean:
        return {"min": None, "max": None, "p25": None, "p50": None, "p75": None}
    n = len(clean)

    def pct(p: float) -> float:
        idx = max(0, min(n - 1, int(n * p) - 1 if n * p >= 1 else 0))
        return round(clean[idx], 2)

    return {
        "min": round(clean[0], 2),
        "max": round(clean[-1], 2),
        "p25": pct(0.25),
        "p50": pct(0.50),
        "p75": pct(0.75),
    }


def find_cheapest_weight_option(
    snapshot: MarketSnapshot,
    canonical_name: str,
    available_only: bool = True,
) -> NormalizedMarketRecord | None:
    candidates = [
        r
        for r in snapshot.normalized_records
        if r.canonical_name == canonical_name
        and r.is_weight_based
        and not r.is_combo
        and r.price_per_kg is not None
        and (r.is_available or not available_only)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda r: r.price_per_kg)


def find_all_options(
    snapshot: MarketSnapshot,
    canonical_name: str,
    available_only: bool = True,
) -> list[NormalizedMarketRecord]:
    return [
        r
        for r in snapshot.normalized_records
        if r.canonical_name == canonical_name
        and (r.is_available or not available_only)
    ]


def available_canonical_names(snapshot: MarketSnapshot) -> set[str]:
    return {
        r.canonical_name
        for r in snapshot.normalized_records
        if r.is_available and not r.is_combo
    }
