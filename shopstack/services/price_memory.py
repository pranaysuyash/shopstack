"""Price memory service — time-series price history, deal quality scoring.

The review (§4.5) identifies price memory as a long-term moat:
    tomato → price snapshots over time by source, size, variety
    onion → price snapshots
    potato → price snapshots

This service provides:
  - Historical price queries (median, min, max, trend)
  - Deal quality scoring against historical prices
  - Price anomaly detection
  - Source-specific price comparisons

PriceObservation records are written by the reconciliation service and
receipt capture. This service reads them through the database interface.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "PriceHistory",
    "PriceSummary",
    "DealScore",
    "StorePriceRanking",
    "BestStoreResult",
    "PriceMemoryService",
    "build_price_memory_service",
]

# ── How many days back to consider for "recent" price history ────────────────
_RECENT_WINDOW_DAYS = 30
_FULL_WINDOW_DAYS = 365


@dataclass
class PriceSummary:
    """Statistical summary of price observations for a canonical product."""
    canonical_name: str
    observations: int = 0
    min_price: float | None = None
    max_price: float | None = None
    median_price: float | None = None
    avg_price: float | None = None
    last_price: float | None = None
    last_seen: date | None = None
    first_seen: date | None = None
    sources: list[str] = field(default_factory=list)
    unit: str = "unit"
    normalized_per_kg: float | None = None  # median per-kg price if weight-based

    @property
    def price_range(self) -> float | None:
        if self.min_price is not None and self.max_price is not None:
            return round(self.max_price - self.min_price, 2)
        return None

    @property
    def is_price_volatile(self) -> bool:
        """Price is volatile if range > 30% of median."""
        if self.price_range and self.median_price and self.median_price > 0:
            return self.price_range / self.median_price > 0.3
        return False


@dataclass
class PriceHistory:
    """Full price history for a canonical product with trend analysis."""
    canonical_name: str
    summary: PriceSummary | None = None
    recent_prices: list[dict[str, Any]] = field(default_factory=list)
    all_prices: list[dict[str, Any]] = field(default_factory=list)

    @property
    def trend(self) -> str:
        """Trend direction: 'up' | 'down' | 'stable' | 'insufficient_data'."""
        if not self.recent_prices or len(self.recent_prices) < 3:
            return "insufficient_data"

        sorted_prices = sorted(self.recent_prices, key=lambda p: p.get("date", ""))
        if len(sorted_prices) < 2:
            return "insufficient_data"

        first_price = sorted_prices[0].get("price_per_kg") or sorted_prices[0].get("price", 0)
        last_price = sorted_prices[-1].get("price_per_kg") or sorted_prices[-1].get("price", 0)

        if first_price <= 0 or last_price <= 0:
            return "insufficient_data"

        change = (last_price - first_price) / first_price
        if change > 0.1:
            return "up"
        if change < -0.1:
            return "down"
        return "stable"


@dataclass
class DealScore:
    """Quality score for a price against historical data."""
    product: str
    current_price: float
    current_per_kg: float | None = None
    score: str = "unknown"  # great | good | fair | poor | unknown
    savings_vs_median: float | None = None
    savings_vs_median_pct: float | None = None
    reason: str = ""

    @property
    def is_good_deal(self) -> bool:
        return self.score in ("great", "good")


@dataclass
class StorePriceRanking:
    """Price comparison across stores for a single product."""
    canonical_name: str
    store_prices: list[dict[str, Any]] = field(default_factory=list)
    best_store: str = ""
    best_price: float | None = None
    best_per_kg: float | None = None
    worst_store: str = ""
    worst_price: float | None = None
    spread_pct: float | None = None
    observations: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "best_store": self.best_store,
            "best_price": self.best_price,
            "best_per_kg": self.best_per_kg,
            "worst_store": self.worst_store,
            "worst_price": self.worst_price,
            "spread_pct": self.spread_pct,
            "observations": self.observations,
            "store_prices": self.store_prices,
        }


@dataclass
class BestStoreResult:
    """Best store recommendation across multiple items."""
    store: str
    items_with_best_price: int = 0
    total_items_compared: int = 0
    estimated_savings_vs_worst: float = 0.0
    avg_position: float = 0.0
    item_details: list[dict[str, Any]] = field(default_factory=list)

    @property
    def coverage_pct(self) -> float:
        if self.total_items_compared <= 0:
            return 0.0
        return round(self.items_with_best_price / self.total_items_compared * 100, 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "store": self.store,
            "items_with_best_price": self.items_with_best_price,
            "total_items_compared": self.total_items_compared,
            "estimated_savings_vs_worst": round(self.estimated_savings_vs_worst, 2),
            "avg_position": round(self.avg_position, 2),
            "coverage_pct": self.coverage_pct,
            "item_details": self.item_details,
        }


class PriceMemoryService:
    """Query price observations and compute price intelligence.

    This service reads from the database and returns structured price
    summaries, trends, deal quality assessments, and store-specific
    comparisons.

    Usage::

        service = PriceMemoryService(database)
        summary = service.get_summary("tomato")
        deal = service.score_deal("tomato", current_price=35, per_kg=70)
        best = service.get_best_store(["tomato", "onion", "rice"])
    """

    def __init__(self, db: Any):
        self._db = db

    # ── Single-product queries ──────────────────────────────────────

    def get_summary(self, canonical_name: str, days: int = _FULL_WINDOW_DAYS) -> PriceSummary:
        """Get price summary for a canonical product over the given window."""
        observations = self._query_observations(canonical_name, days)
        if not observations:
            return PriceSummary(canonical_name=canonical_name)

        prices = [o.price for o in observations if o.price > 0]
        per_kg_prices = [
            self._price_per_kg(o) for o in observations
            if o.price > 0
        ]
        sorted_prices = sorted(prices)
        sources = list({o.store_name or "unknown" for o in observations if o.store_name})

        n = len(sorted_prices)
        median = sorted_prices[n // 2] if n % 2 == 1 else (sorted_prices[n // 2 - 1] + sorted_prices[n // 2]) / 2 if n >= 2 else sorted_prices[0]
        valid_ppk = [p for p in per_kg_prices if p is not None and p > 0]
        median_ppk = sorted(valid_ppk)[len(valid_ppk) // 2] if valid_ppk else None

        dates = [o.observation_date for o in observations if o.observation_date]
        last_obs = max(observations, key=lambda o: o.observation_date) if observations else None

        return PriceSummary(
            canonical_name=canonical_name,
            observations=n,
            min_price=min(prices) if prices else None,
            max_price=max(prices) if prices else None,
            median_price=round(median, 2) if median else None,
            avg_price=round(sum(prices) / len(prices), 2) if prices else None,
            last_price=last_obs.price if last_obs else None,
            last_seen=last_obs.observation_date if last_obs else None,
            first_seen=min(dates) if dates else None,
            sources=sources,
            normalized_per_kg=round(median_ppk, 2) if median_ppk else None,
        )

    def get_history(self, canonical_name: str, days: int = _FULL_WINDOW_DAYS) -> PriceHistory:
        """Get full price history with trend analysis."""
        observations = self._query_observations(canonical_name, days)
        recent_cutoff = date.today() - timedelta(days=_RECENT_WINDOW_DAYS)

        all_prices = []
        recent_prices = []
        for o in observations:
            entry = {
                "price": o.price,
                "price_per_kg": self._price_per_kg(o),
                "date": o.observation_date,
                "source": o.store_name or "unknown",
                "quantity": o.quantity,
                "unit": o.unit,
            }
            all_prices.append(entry)
            if o.observation_date and o.observation_date >= recent_cutoff:
                recent_prices.append(entry)

        summary = self.get_summary(canonical_name, days)
        return PriceHistory(
            canonical_name=canonical_name,
            summary=summary,
            recent_prices=recent_prices,
            all_prices=all_prices,
        )

    def score_deal(
        self,
        canonical_name: str,
        current_price: float,
        per_kg: float | None = None,
        days: int = _FULL_WINDOW_DAYS,
    ) -> DealScore:
        """Score a current price against historical data.

        Returns a DealScore rating whether the current price is a great,
        good, fair, or poor deal relative to historical prices.
        """
        summary = self.get_summary(canonical_name, days)

        if summary.observations < 1 or summary.avg_price is None or summary.avg_price <= 0:
            return DealScore(
                product=canonical_name,
                current_price=current_price,
                current_per_kg=per_kg,
                score="unknown",
                reason="No historical price data available for comparison.",
            )

        # Use per-kg if available and meaningful, otherwise absolute price
        if per_kg is not None and per_kg > 0 and summary.normalized_per_kg is not None:
            compare_price = per_kg
            baseline = summary.normalized_per_kg
            unit_label = "/kg"
        else:
            compare_price = current_price
            baseline = summary.avg_price
            unit_label = ""

        if baseline <= 0:
            return DealScore(
                product=canonical_name,
                current_price=current_price,
                current_per_kg=per_kg,
                score="unknown",
                reason="Historical baseline price unavailable.",
            )

        savings = baseline - compare_price
        pct_savings = savings / baseline

        if pct_savings > 0.15:
            score = "great"
            reason = f"₹{compare_price:.0f}{unit_label} is {pct_savings:.0%} below historical avg ₹{baseline:.0f}{unit_label}!"
        elif pct_savings > 0.05:
            score = "good"
            reason = f"₹{compare_price:.0f}{unit_label} is {pct_savings:.0%} below historical avg ₹{baseline:.0f}{unit_label}."
        elif pct_savings > -0.05:
            score = "fair"
            reason = f"₹{compare_price:.0f}{unit_label} is in line with historical avg ₹{baseline:.0f}{unit_label}."
        elif pct_savings > -0.15:
            score = "poor"
            reason = f"₹{compare_price:.0f}{unit_label} is {abs(pct_savings):.0%} above historical avg ₹{baseline:.0f}{unit_label}."
        else:
            score = "poor"
            reason = f"₹{compare_price:.0f}{unit_label} is significantly above historical avg ₹{baseline:.0f}{unit_label}."

        return DealScore(
            product=canonical_name,
            current_price=current_price,
            current_per_kg=per_kg,
            score=score,
            savings_vs_median=round(savings, 2),
            savings_vs_median_pct=round(pct_savings * 100, 1),
            reason=reason,
        )

    # ── Store intelligence ──────────────────────────────────────────

    def get_store_comparison(self, canonical_name: str, days: int = _RECENT_WINDOW_DAYS) -> StorePriceRanking:
        """Compare prices across stores for a single product.

        Groups observations by store and computes per-store median
        prices, then ranks stores from cheapest to most expensive.
        """
        observations = self._query_observations(canonical_name, days)
        if not observations:
            return StorePriceRanking(canonical_name=canonical_name)

        store_data: dict[str, list[float]] = {}
        store_ppk: dict[str, list[float]] = {}
        store_last_seen: dict[str, date] = {}
        for o in observations:
            store = o.store_name or "unknown"
            if o.price > 0:
                store_data.setdefault(store, []).append(o.price)
                ppk = self._price_per_kg(o)
                if ppk is not None and ppk > 0:
                    store_ppk.setdefault(store, []).append(ppk)
                if o.observation_date and (
                    store not in store_last_seen or o.observation_date > store_last_seen[store]
                ):
                    store_last_seen[store] = o.observation_date

        if not store_data:
            return StorePriceRanking(canonical_name=canonical_name)

        store_prices = []
        for store, prices in sorted(store_data.items()):
            sorted_p = sorted(prices)
            median_p = sorted_p[len(sorted_p) // 2]
            ppks = store_ppk.get(store, [])
            median_ppk = sorted(ppks)[len(ppks) // 2] if ppks else None
            store_prices.append({
                "store": store,
                "median_price": round(median_p, 2),
                "min_price": round(min(prices), 2),
                "observations": len(prices),
                "median_per_kg": round(median_ppk, 2) if median_ppk else None,
                "last_seen": store_last_seen.get(store).isoformat() if store_last_seen.get(store) else None,
            })

        # Rank by per-kg if available, otherwise by absolute price
        def _sort_key(entry: dict) -> float:
            ppk = entry.get("median_per_kg")
            if ppk is not None and ppk > 0:
                return ppk
            return entry["median_price"]

        store_prices.sort(key=_sort_key)

        best = store_prices[0]
        worst = store_prices[-1]
        best_price = best["median_price"]
        worst_price = worst["median_price"]
        spread = None
        if worst_price and worst_price > 0 and best_price != worst_price:
            spread = round((worst_price - best_price) / worst_price * 100, 1)

        return StorePriceRanking(
            canonical_name=canonical_name,
            store_prices=store_prices,
            best_store=best["store"],
            best_price=best_price,
            best_per_kg=best.get("median_per_kg"),
            worst_store=worst["store"],
            worst_price=worst_price,
            spread_pct=spread,
            observations=sum(s["observations"] for s in store_prices),
        )

    def get_best_store(self, canonical_names: list[str], days: int = _RECENT_WINDOW_DAYS) -> BestStoreResult:
        """Find the best store across multiple products.

        For each product, ranks stores by price. Then computes an overall
        ranking based on how often each store has the best price and the
        average price position across all items.
        """
        if not canonical_names:
            return BestStoreResult(store="")

        # Collect per-product store rankings
        product_rankings: dict[str, StorePriceRanking] = {}
        for name in canonical_names:
            ranking = self.get_store_comparison(name, days)
            if ranking.store_prices:
                product_rankings[name] = ranking

        if not product_rankings:
            return BestStoreResult(store="", total_items_compared=len(canonical_names))

        # Aggregate store performance across products
        store_scores: dict[str, dict[str, float]] = {}
        for name, ranking in product_rankings.items():
            for rank_idx, entry in enumerate(ranking.store_prices):
                store = entry["store"]
                scores = store_scores.setdefault(store, {
                    "best_count": 0, "total_positions": 0, "items_ranked": 0,
                    "savings_vs_worst": 0.0,
                })
                scores["items_ranked"] += 1
                scores["total_positions"] += rank_idx + 1
                if rank_idx == 0:
                    scores["best_count"] += 1
                # Compute savings vs worst store for this product
                worst_entry = ranking.store_prices[-1]
                savings = (worst_entry.get("median_per_kg") or worst_entry["median_price"]) - \
                          (entry.get("median_per_kg") or entry["median_price"])
                if savings > 0:
                    scores["savings_vs_worst"] += savings

        # Build item-level details for the top stores
        item_details = []
        for name, ranking in product_rankings.items():
            if ranking.store_prices:
                best = ranking.store_prices[0]
                item_details.append({
                    "canonical_name": name,
                    "best_store": best["store"],
                    "best_price": best["median_price"],
                    "best_per_kg": best.get("median_per_kg"),
                    "stores_compared": len(ranking.store_prices),
                    "spread_pct": ranking.spread_pct,
                })

        # Pick the overall best store
        def _store_sort(name: str) -> tuple[float, float]:
            s = store_scores[name]
            avg_pos = s["total_positions"] / max(s["items_ranked"], 1)
            return (-s["best_count"], avg_pos)

        ranked_stores = sorted(store_scores, key=_store_sort)
        winner = ranked_stores[0]
        winner_data = store_scores[winner]

        return BestStoreResult(
            store=winner,
            items_with_best_price=int(winner_data["best_count"]),
            total_items_compared=len(canonical_names),
            estimated_savings_vs_worst=round(winner_data["savings_vs_worst"], 2),
            avg_position=round(winner_data["total_positions"] / max(winner_data["items_ranked"], 1), 2),
            item_details=item_details,
        )

    def get_top_deals(self, market_snapshot: Any, limit: int = 5) -> list[DealScore]:
        """Score all available items in a market snapshot and return top deals.

        Only scores items that have historical data.
        """
        if not market_snapshot or not hasattr(market_snapshot, "normalized_records"):
            return []

        scored: list[DealScore] = []
        for record in market_snapshot.normalized_records:
            if not record.is_available or record.is_combo:
                continue
            if record.price_inr <= 0:
                continue
            deal = self.score_deal(
                canonical_name=record.canonical_name,
                current_price=record.price_inr,
                per_kg=record.price_per_kg,
            )
            if deal.score in ("great", "good"):
                scored.append(deal)
            if len(scored) >= limit * 2:  # score extras, filter best below
                continue

        scored.sort(key=lambda d: d.savings_vs_median_pct or 0, reverse=True)
        return scored[:limit]

    # ── Internal ────────────────────────────────────────────────────

    def _query_observations(self, canonical_name: str, days: int) -> list[Any]:
        """Query price observations from the database."""
        try:
            cutoff = date.today() - timedelta(days=days)
            all_obs = self._db.get_price_history(canonical_name)
            return [
                o for o in all_obs
                if o.observation_date and o.observation_date >= cutoff
            ]
        except Exception as exc:
            logger.debug("Price observation query failed for %s: %s", canonical_name, exc)
            return []

    @staticmethod
    def _price_per_kg(observation: Any) -> float | None:
        """Compute per-kg price from an observation."""
        try:
            qty = observation.quantity or 0
            unit = (observation.unit or "").lower()
            price = observation.price or 0
            if qty <= 0 or price <= 0:
                return None
            if unit in ("g", "gram", "grams"):
                return price / qty * 1000
            if unit in ("kg", "kilo", "kilos"):
                return price / qty
            if unit in ("l", "litre", "liter", "litres", "liters"):
                return price / qty * 1000
            if unit in ("ml", "milliliter", "millilitre"):
                return price / qty * 1000
            return None
        except Exception:
            return None


def build_price_memory_service(db: Any) -> PriceMemoryService:
    """Factory — build a PriceMemoryService with the given database."""
    return PriceMemoryService(db)
