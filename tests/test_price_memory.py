"""Tests for the PriceMemory service.

Covers:
  - PriceSummary computation (median, avg, min, max)
  - PriceHistory trend detection (up/down/stable)
  - DealScore quality assessment
  - get_top_deals from market snapshots
  - Empty/invalid data edge cases
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

# ── Mock database that returns PriceObservation-like objects ────────────────


@dataclass
class MockPriceObservation:
    """Minimal price observation compatible with PriceMemoryService."""
    price: float
    observation_date: date
    store_name: str = "swiggy"
    quantity: float = 1.0
    unit: str = "kg"
    canonical_name: str = ""


class MockDB:
    """Fake database that returns price observations by name."""

    def __init__(self, records: list[MockPriceObservation] | None = None):
        self._records: dict[str, list[MockPriceObservation]] = {}

        if records:
            for r in records:
                name = r.canonical_name
                if name not in self._records:
                    self._records[name] = []
                self._records[name].append(r)

    def add(self, name: str, price: float, days_ago: int, store: str = "swiggy", qty: float = 1.0, unit: str = "kg"):
        if name not in self._records:
            self._records[name] = []
        self._records[name].append(MockPriceObservation(
            price=price,
            observation_date=date(2026, 6, 9) - __import__("datetime").timedelta(days=days_ago),
            store_name=store,
            quantity=qty,
            unit=unit,
            canonical_name=name,
        ))

    def get_price_observations(self, name: str) -> list[MockPriceObservation]:
        return self._records.get(name, [])

    def get_price_history(self, canonical_name: str, **kwargs) -> list[MockPriceObservation]:
        return self._records.get(canonical_name, [])


@pytest.fixture
def db():
    db = MockDB()
    # Tomato prices over time: ₹28–35 range
    for days_ago, price in [(30, 28), (25, 30), (20, 32), (15, 33), (10, 31), (5, 35), (2, 34), (1, 35)]:
        db.add("tomato", price, days_ago)
    # Onion: stable ~₹31
    for days_ago, price in [(30, 30), (20, 31), (10, 31), (5, 32), (1, 31)]:
        db.add("onion", price, days_ago)
    # Coriander: volatile ₹5–40
    for days_ago, price in [(20, 40), (15, 25), (10, 10), (5, 5), (1, 8)]:
        db.add("coriander", price, days_ago, qty=1.0, unit="bunch")
    # Potato: trending up ₹20→27
    for days_ago, price in [(30, 20), (20, 22), (10, 25), (5, 26), (1, 27)]:
        db.add("potato", price, days_ago)
    # Carrot: trending down ₹60→40
    for days_ago, price in [(30, 60), (20, 55), (10, 48), (5, 45), (1, 40)]:
        db.add("carrot", price, days_ago, qty=500, unit="g")
    return db


@pytest.fixture
def service(db):
    from datetime import date

    from shopstack.services.price_memory import PriceMemoryService
    # Reference date matching the mock data base date (2026-06-09)
    return PriceMemoryService(db, reference_date=date(2026, 6, 9))


# ── PriceSummary tests ─────────────────────────────────────────────────────


class TestPriceSummary:
    def test_summary_basic_stats(self, service):
        summary = service.get_summary("tomato")
        assert summary.observations == 8
        assert summary.median_price is not None and summary.median_price > 0
        assert summary.min_price is not None and summary.min_price <= 30
        assert summary.max_price is not None and summary.max_price >= 35
        assert summary.last_price == 35
        assert summary.last_seen == date(2026, 6, 8)  # days_ago=1

    def test_summary_unknown_item(self, service):
        summary = service.get_summary("unknown_item")
        assert summary.observations == 0
        assert summary.min_price is None
        assert summary.avg_price is None

    def test_summary_recent_window(self, service):
        summary = service.get_summary("tomato", days=7)
        # Only last 7 days: prices at days_ago 5, 2, 1 → 3 observations
        assert summary.observations <= 4

    def test_price_range(self, service):
        summary = service.get_summary("tomato")
        assert summary.price_range is not None
        assert summary.price_range > 0

    def test_price_volatility_flag(self, service):
        from shopstack.services.price_memory import PriceSummary
        volatile = PriceSummary(canonical_name="test", min_price=10, max_price=50, median_price=20)
        assert volatile.is_price_volatile

        stable = PriceSummary(canonical_name="test", min_price=30, max_price=35, median_price=32)
        assert not stable.is_price_volatile

    def test_sources_list(self, service):
        summary = service.get_summary("tomato")
        assert len(summary.sources) > 0
        assert "swiggy" in summary.sources


# ── PriceHistory / trend tests ─────────────────────────────────────────────


class TestPriceHistory:
    def test_history_contains_records(self, service):
        history = service.get_history("tomato")
        assert len(history.all_prices) == 8
        assert len(history.recent_prices) > 0

    def test_trend_up(self, service):
        history = service.get_history("potato")
        assert history.trend == "up"

    def test_trend_down(self, service):
        history = service.get_history("carrot")
        assert history.trend == "down"

    def test_trend_stable(self, service):
        history = service.get_history("onion")
        assert history.trend == "stable"

    def test_trend_insufficient_data(self, service):
        db = MockDB()
        db.add("new_item", 50, 0)
        from shopstack.services.price_memory import PriceMemoryService
        svc = PriceMemoryService(db)
        history = svc.get_history("new_item")
        assert history.trend == "insufficient_data"

    def test_history_summary_included(self, service):
        history = service.get_history("coriander")
        assert history.summary is not None
        assert history.summary.observations == 5


# ── DealScore tests ─────────────────────────────────────────────────────────


class TestDealScore:
    def test_great_deal_potato(self, service):
        """35% below historical avg should be 'great'."""
        # Coriander historical avg ~₹17.6, current ₹8 → ~55% below → great
        deal = service.score_deal("coriander", current_price=8, per_kg=None)
        assert deal.score == "great"
        assert deal.is_good_deal

    def test_great_deal(self, service):
        """>15% below historical avg should be 'great'."""
        deal = service.score_deal("potato", current_price=20, per_kg=None)
        assert deal.score == "great"
        assert deal.is_good_deal

    def test_fair_deal(self, service):
        """Close to historical avg should be 'fair'."""
        deal = service.score_deal("onion", current_price=31, per_kg=None)
        assert deal.score in ("fair", "good")

    def test_poor_deal(self, service):
        """25% above historical avg should be 'poor'."""
        deal = service.score_deal("potato", current_price=32, per_kg=None)
        assert deal.score == "poor"

    def test_unknown_when_no_history(self, service):
        deal = service.score_deal("unknown_item", current_price=50)
        assert deal.score == "unknown"
        assert "No historical" in deal.reason or "unavailable" in deal.reason

    def test_deal_with_per_kg(self, service):
        """Using per-kg price should work when observation units are grams."""
        # Carrot: historical per-kg ~₹96, current per-kg ₹80 (~17% below → great)
        deal = service.score_deal("carrot", current_price=40, per_kg=80)
        assert deal.score == "great"
        assert deal.is_good_deal
        assert deal.current_per_kg == 80

    def test_deal_savings_calculated(self, service):
        deal = service.score_deal("onion", current_price=31, per_kg=31)
        assert deal.savings_vs_median is not None
        assert deal.savings_vs_median_pct is not None


# ── get_top_deals tests ─────────────────────────────────────────────────────


class TestTopDeals:
    def test_top_deals_from_snapshot(self, service):
        """Build a mock snapshot and get top deals."""
        from shopstack.market.schema import MarketSnapshot, NormalizedMarketRecord

        records = [
            NormalizedMarketRecord(
                source="test", source_category="vegetables",
                canonical_name="onion",
                raw_name="Onion",
                description="", variety="", brand="",
                raw_size="1 kg",
                package_count=1, size_class="",
                card_index=0, delivery_time="30 min",
                captured_at="2026-06-09",
                snapshot_id="test",
                price_inr=26,  # ~19% below avg 31 → "good"
                mrp_inr=31,
                discount_percent_displayed=0, discount_amount_inr=0,
                computed_discount_percent=0,
                availability="available",
                is_available=True,
                is_weight_based=True,
                is_piece_based=False, is_combo=False,
                is_size_class=False,
                is_ad=False, is_upgrade=False, tag="",
                normalized_quantity=1000,
                normalized_unit="g",
                price_per_kg=26,
                price_per_100g=None,
                price_per_piece=None,
                component_names=[],
                normalization_warnings=[],
            ),
            NormalizedMarketRecord(
                source="test", source_category="vegetables",
                canonical_name="potato",
                raw_name="Potato",
                description="", variety="", brand="",
                raw_size="1 kg",
                package_count=1, size_class="",
                card_index=0, delivery_time="30 min",
                captured_at="2026-06-09",
                snapshot_id="test",
                price_inr=18,  # ~30% below avg 24 → "great"
                mrp_inr=27,
                discount_percent_displayed=0, discount_amount_inr=0,
                computed_discount_percent=0,
                availability="available",
                is_available=True,
                is_weight_based=True,
                is_piece_based=False, is_combo=False,
                is_size_class=False,
                is_ad=False, is_upgrade=False, tag="",
                normalized_quantity=1000,
                normalized_unit="g",
                price_per_kg=18,
                price_per_100g=None,
                price_per_piece=None,
                component_names=[],
                normalization_warnings=[],
            ),
        ]
        snapshot = MarketSnapshot(
            snapshot_id="test",
            source="test",
            source_category="vegetables",
            captured_at="2026-06-09",
            raw_records=[],
            normalized_records=records,
        )

        deals = service.get_top_deals(snapshot, limit=2)
        assert len(deals) == 2
        assert all(d.score in ("great", "good") for d in deals)

    def test_none_snapshot(self, service):
        deals = service.get_top_deals(None)
        assert deals == []

    def test_empty_snapshot(self, service):
        from shopstack.market.schema import MarketSnapshot
        empty = MarketSnapshot(
            snapshot_id="e", source="e", source_category="garden",
            captured_at="2026-06-09", raw_records=[], normalized_records=[],
        )
        deals = service.get_top_deals(empty)
        assert deals == []


# ── Price per-kg computation tests ──────────────────────────────────────────


class TestPricePerKg:
    def test_kg_price_conversion(self):
        from shopstack.services.price_memory import PriceMemoryService

        @dataclass
        class Obs:
            price: float = 100
            quantity: float = 1
            unit: str = "kg"

        ppk = PriceMemoryService._price_per_kg(Obs(price=100, quantity=1, unit="kg"))
        assert ppk == 100

    def test_gram_price_conversion(self):
        from shopstack.services.price_memory import PriceMemoryService

        @dataclass
        class Obs:
            price: float = 50
            quantity: float = 500
            unit: str = "g"

        ppk = PriceMemoryService._price_per_kg(Obs(price=50, quantity=500, unit="g"))
        assert ppk == 100  # 50/500*1000

    def test_ml_price_conversion(self):
        from shopstack.services.price_memory import PriceMemoryService

        @dataclass
        class Obs:
            price: float = 30
            quantity: float = 200
            unit: str = "ml"

        ppk = PriceMemoryService._price_per_kg(Obs(price=30, quantity=200, unit="ml"))
        assert ppk == pytest.approx(150)  # 30/200*1000

    def test_litre_price_conversion(self):
        from shopstack.services.price_memory import PriceMemoryService

        @dataclass
        class Obs:
            price: float = 165
            quantity: float = 1
            unit: str = "L"

        ppk = PriceMemoryService._price_per_kg(Obs(price=165, quantity=1, unit="L"))
        assert ppk == 165  # 1L of cooking oil ~ 1kg, not 165000

    def test_no_quantity_returns_none(self):
        from shopstack.services.price_memory import PriceMemoryService

        @dataclass
        class Obs:
            price: float = 100
            quantity: float = 0
            unit: str = "kg"

        assert PriceMemoryService._price_per_kg(Obs(price=100, quantity=0, unit="kg")) is None


# ── Store comparison tests ────────────────────────────────────────────────────


class TestStoreComparison:
    @pytest.fixture
    def multi_store_db(self):
        db = MockDB()
        # Tomato at multiple stores
        for days_ago, price, store in [
            (10, 28, "swiggy"), (8, 30, "swiggy"), (5, 32, "swiggy"),
            (10, 25, "zepto"), (7, 27, "zepto"), (3, 26, "zepto"),
            (10, 30, "dmart"), (6, 29, "dmart"), (2, 31, "dmart"),
        ]:
            db.add("tomato", price, days_ago, store=store)
        # Onion at two stores
        for days_ago, price, store in [
            (10, 30, "swiggy"), (5, 32, "swiggy"),
            (10, 28, "zepto"), (5, 29, "zepto"),
        ]:
            db.add("onion", price, days_ago, store=store)
        return db

    def test_store_comparison_basic(self, multi_store_db):
        from shopstack.services.price_memory import PriceMemoryService
        svc = PriceMemoryService(multi_store_db)
        ranking = svc.get_store_comparison("tomato")
        assert ranking.observations > 0
        assert ranking.best_store != ""
        assert ranking.best_price is not None
        assert ranking.best_price > 0
        assert len(ranking.store_prices) == 3

    def test_best_store_is_cheapest(self, multi_store_db):
        from shopstack.services.price_memory import PriceMemoryService
        svc = PriceMemoryService(multi_store_db)
        ranking = svc.get_store_comparison("tomato")
        # Zepto has lowest median → should be best
        assert ranking.best_store == "zepto"

    def test_store_comparison_no_data(self):
        from shopstack.services.price_memory import PriceMemoryService
        db = MockDB()
        svc = PriceMemoryService(db)
        ranking = svc.get_store_comparison("nonexistent")
        assert ranking.observations == 0
        assert ranking.best_store == ""

    def test_best_store_multiple_items(self, multi_store_db):
        from shopstack.services.price_memory import PriceMemoryService
        svc = PriceMemoryService(multi_store_db)
        result = svc.get_best_store(["tomato", "onion"])
        assert result.store != ""
        assert result.total_items_compared == 2
        assert result.items_with_best_price > 0

    def test_best_store_empty_list(self, multi_store_db):
        from shopstack.services.price_memory import PriceMemoryService
        svc = PriceMemoryService(multi_store_db)
        result = svc.get_best_store([])
        assert result.store == ""

    def test_best_store_no_data(self):
        from shopstack.services.price_memory import PriceMemoryService
        db = MockDB()
        svc = PriceMemoryService(db)
        result = svc.get_best_store(["ghost_item"])
        assert result.store == ""
        assert result.total_items_compared == 1

    def test_store_comparison_to_dict(self, multi_store_db):
        from shopstack.services.price_memory import PriceMemoryService
        svc = PriceMemoryService(multi_store_db)
        ranking = svc.get_store_comparison("tomato")
        d = ranking.to_dict()
        assert "best_store" in d
        assert "store_prices" in d
        assert d["canonical_name"] == "tomato"

    def test_best_store_to_dict(self, multi_store_db):
        from shopstack.services.price_memory import PriceMemoryService
        svc = PriceMemoryService(multi_store_db)
        result = svc.get_best_store(["tomato", "onion"])
        d = result.to_dict()
        assert "store" in d
        assert "coverage_pct" in d
        assert d["total_items_compared"] == 2
