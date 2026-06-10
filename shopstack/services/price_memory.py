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


class PriceMemoryService:
    """Query price observations and compute price intelligence.

    This service reads from the database and returns structured price
    summaries, trends, and deal quality assessments.

    Usage::

        service = PriceMemoryService(database)
        summary = service.get_summary("tomato")
        deal = service.score_deal("tomato", current_price=35, per_kg=70)
    """

    def __init__(self, db: Any):
        self._db = db

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

    def _query_observations(self, canonical_name: str, days: int) -> list[Any]:
        """Query price observations from the database."""
        try:
            cutoff = date.today() - timedelta(days=days)
            all_obs = self._db.get_price_observations(name=canonical_name) if hasattr(self._db, "get_price_observations") else []
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
