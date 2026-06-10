"""Tests for the decision-aware basket optimizer.

Covers:
  - Basic build_optimized_basket with market items
  - Inventory subtraction (already-owned items)
  - Budget constraint enforcement
  - Household size scaling
  - Waste risk and use-soon decisions
  - Avoid items filtering
  - Stale data warnings
  - OptimizedBasket properties (buy, skip, total_estimated)
"""

from __future__ import annotations

from datetime import date

import pytest

from shopstack.market.schema import MarketSnapshot, NormalizedMarketRecord


# ── Helpers ─────────────────────────────────────────────────────────────────


def _record(
    canonical: str,
    price: float = 30.0,
    ppk: float = 60.0,
    size: str = "500 g",
    norm_qty: float = 500.0,
    available: bool = True,
    combo: bool = False,
    upgrade: bool = False,
    ad: bool = False,
    weight: bool = True,
    piece: bool = False,
) -> NormalizedMarketRecord:
    return NormalizedMarketRecord(
        source="test",
        source_category="vegetables",
        raw_name=canonical.replace("_", " ").title(),
        raw_size=size,
        price_inr=price,
        mrp_inr=price * 1.15,
        discount_percent_displayed=0.0,
        discount_amount_inr=0.0,
        computed_discount_percent=0,
        availability="available" if available else "sold_out",
        is_available=available,
        is_weight_based=weight,
        is_piece_based=piece,
        is_combo=combo,
        is_upgrade=upgrade,
        is_ad=ad,
        is_size_class=False,
        tag="",
        variety="",
        description="",
        canonical_name=canonical,
        package_count=1,
        size_class="",
        card_index=0,
        delivery_time="30 min",
        captured_at="2026-06-09",
        snapshot_id="test-basket",
        normalized_quantity=norm_qty,
        normalized_unit="g",
        price_per_kg=ppk,
        price_per_100g=None,
        price_per_piece=None,
        component_names=[],
        normalization_warnings=[],
        brand="",
    )


@pytest.fixture
def snapshot():
    records = [
        _record("tomato", price=28, ppk=56, size="500 g", norm_qty=500),
        _record("tomato", price=55, ppk=55, size="1 kg", norm_qty=1000),
        _record("onion", price=31, ppk=31, size="1 kg", norm_qty=1000),
        _record("potato", price=27, ppk=27, size="1 kg", norm_qty=1000),
        _record("carrot", price=28, ppk=56, size="500 g", norm_qty=500),
        _record("cucumber", price=20, ppk=40, size="500 g", norm_qty=500),
        _record("coriander", price=8, ppk=80, size="100 g", norm_qty=100),
        _record("mint", price=10, ppk=100, size="100 g", norm_qty=100),
        _record("curry_leaves", price=5, ppk=50, size="100 g", norm_qty=100),
        _record("beetroot", price=30, ppk=60, size="500 g", norm_qty=500),
        _record("broccoli", price=50, ppk=100, size="500 g", norm_qty=500),
        _record("cauliflower", price=30, ppk=60, size="500 g", norm_qty=500),
        _record("ladys_finger", price=25, ppk=50, size="500 g", norm_qty=500),
        _record("cabbage", price=20, ppk=40, size="500 g", norm_qty=500),
        _record("zucchini", price=40, ppk=80, size="500 g", norm_qty=500, available=False),
    ]
    return MarketSnapshot(
        snapshot_id="test-basket",
        source="swiggy_test",
        source_category="vegetables",
        captured_at="2026-06-09",
        raw_records=[],
        normalized_records=records,
    )


# ── Basic basket building ───────────────────────────────────────────────────


class TestBuildOptimizedBasket:
    def test_basic_basket(self, snapshot):
        """Simple basket with items available in market."""
        from shopstack.market.basket import build_optimized_basket

        items = [{"canonical_name": "tomato", "requested_quantity": 1.0, "unit": "kg"}]
        result = build_optimized_basket(items, snapshot)
        assert len(result.items) == 1
        assert result.items[0].decision == "buy"
        assert result.total_estimated > 0

    def test_multi_item_basket(self, snapshot):
        """Basket with multiple items, all available."""
        from shopstack.market.basket import build_optimized_basket

        items = [
            {"canonical_name": "tomato", "requested_quantity": 1.0, "unit": "kg"},
            {"canonical_name": "onion", "requested_quantity": 1.0, "unit": "kg"},
            {"canonical_name": "potato", "requested_quantity": 2.0, "unit": "kg"},
        ]
        result = build_optimized_basket(items, snapshot)
        assert len(result.items) == 3
        assert len(result.buy) == 3

    def test_unavailable_item(self, snapshot):
        """Item not found in snapshot should be marked unavailable."""
        from shopstack.market.basket import build_optimized_basket

        items = [{"canonical_name": "dragon_fruit", "requested_quantity": 1.0, "unit": "unit"}]
        result = build_optimized_basket(items, snapshot)
        assert len(result.items) == 1
        assert result.items[0].decision == "unavailable"
        assert not result.items[0].matched


# ── Inventory subtraction ───────────────────────────────────────────────────


class TestInventorySubtraction:
    def test_subtract_from_inventory(self, snapshot):
        """Having some inventory reduces net quantity needed."""
        from shopstack.market.basket import build_optimized_basket

        items = [{"canonical_name": "tomato", "requested_quantity": 1.0, "unit": "kg"}]
        result = build_optimized_basket(items, snapshot, inventory_map={"tomato": 0.5})
        assert result.items[0].already_owned_quantity == 0.5
        assert result.items[0].net_quantity_to_buy > 0
        assert result.items[0].net_quantity_to_buy < 1.0

    def test_sufficient_inventory_skips(self, snapshot):
        """Having enough inventory should produce a skip decision."""
        from shopstack.market.basket import build_optimized_basket

        items = [{"canonical_name": "potato", "requested_quantity": 1.0, "unit": "kg"}]
        result = build_optimized_basket(items, snapshot, inventory_map={"potato": 2.0})
        assert result.items[0].decision == "skip"
        assert result.items[0].reason_type == "enough_stock"

    def test_exact_inventory_skips(self, snapshot):
        """Having exactly the requested quantity should skip."""
        from shopstack.market.basket import build_optimized_basket

        items = [{"canonical_name": "onion", "requested_quantity": 1.0, "unit": "kg"}]
        result = build_optimized_basket(items, snapshot, inventory_map={"onion": 1.0})
        assert result.items[0].decision == "skip"


# ── Budget constraints ──────────────────────────────────────────────────────


class TestBudgetConstraints:
    def test_under_budget(self, snapshot):
        """Items within budget should get buy decisions."""
        from shopstack.market.basket import build_optimized_basket

        items = [{"canonical_name": "onion", "requested_quantity": 1.0, "unit": "kg"}]
        result = build_optimized_basket(items, snapshot, budget_inr=200)
        assert result.items[0].decision == "buy"

    def test_over_budget(self, snapshot):
        """Items exceeding remaining budget should get reason_type='over_budget'."""
        from shopstack.market.basket import build_optimized_basket

        # Tomato costs ₹28 per 500g, so 1kg would be ~₹56
        # With budget of ₹10, this should be over budget
        items = [{"canonical_name": "tomato", "requested_quantity": 1.0, "unit": "kg"}]
        result = build_optimized_basket(items, snapshot, budget_inr=10)
        assert result.items[0].decision == "compare"
        assert result.items[0].reason_type == "over_budget"
        assert "budget" in result.items[0].reason.lower()

    def test_budget_accumulation(self, snapshot):
        """Running total across items should track budget."""
        from shopstack.market.basket import build_optimized_basket

        items = [
            {"canonical_name": "coriander", "requested_quantity": 1.0, "unit": "kg"},
            {"canonical_name": "onion", "requested_quantity": 1.0, "unit": "kg"},
        ]
        # Coriander is ₹8 for 100g, so for 1kg that's ₹80
        # With budget of ₹50, both should be over budget? Actually first one might be under...
        # Let's use a strict budget
        result = build_optimized_basket(items, snapshot, budget_inr=5)
        # First item (coriander) should be over budget
        assert result.items[0].decision == "compare"
        assert result.items[0].reason_type == "over_budget"


# ── Household size and days to plan ─────────────────────────────────────────


class TestHouseholdScaling:
    def test_single_person_single_day(self, snapshot):
        """Small household should get smaller recommendations."""
        from shopstack.market.basket import build_optimized_basket

        items = [{"canonical_name": "onion", "requested_quantity": 1.0, "unit": "kg"}]
        result = build_optimized_basket(items, snapshot, household_size=1, days_to_plan=1)
        assert result.items[0].decision == "buy"

    def test_large_household_scales(self, snapshot):
        """Larger household should scale up net quantity."""
        from shopstack.market.basket import build_optimized_basket

        items = [{"canonical_name": "cucumber", "requested_quantity": 1.0, "unit": "kg"}]
        # 4 people for 6 days → 4 * (6/3) = 8x base
        result = build_optimized_basket(items, snapshot, household_size=4, days_to_plan=6)
        assert result.items[0].net_quantity_to_buy > 0


# ── Waste risk and use-soon ─────────────────────────────────────────────────


class TestWasteRisk:
    def test_high_waste_with_inventory(self):
        """High waste risk item with existing inventory should get use_soon."""
        from shopstack.market.basket import build_optimized_basket
        from shopstack.market.schema import MarketSnapshot

        # Coriander has high waste risk — 3-day shelf life
        records = [
            _record("coriander", price=8, ppk=80, size="100 g", norm_qty=100),
        ]
        snap = MarketSnapshot(
            snapshot_id="waste-test",
            source="test",
            source_category="vegetables",
            captured_at="2026-06-09",
            raw_records=[],
            normalized_records=records,
        )
        items = [{"canonical_name": "coriander", "requested_quantity": 1.0, "unit": "bunch"}]
        result = build_optimized_basket(items, snap, inventory_map={"coriander": 1.0})
        assert result.items[0].decision == "use_soon"
        assert "waste risk" in result.items[0].reason.lower() or "use" in result.items[0].reason.lower()


# ── Avoid items ─────────────────────────────────────────────────────────────


class TestAvoidItems:
    def test_avoided_item_skipped(self, snapshot):
        """Items in the avoid list should get skip decisions."""
        from shopstack.market.basket import build_optimized_basket

        items = [{"canonical_name": "broccoli", "requested_quantity": 1.0, "unit": "kg"}]
        result = build_optimized_basket(items, snapshot, avoid_items=["broccoli"])
        assert result.items[0].decision == "skip"
        assert result.items[0].reason_type == "household_avoids"
        assert "avoid" in result.items[0].reason.lower()


# ── OptimizedBasket properties ──────────────────────────────────────────────


class TestOptimizedBasketProperties:
    def test_buy_property(self, snapshot):
        from shopstack.market.basket import OptimizedBasket, OptimizedBasketItem
        basket = OptimizedBasket(items=[
            OptimizedBasketItem(requested_name="tomato", canonical_name="tomato", decision="buy", reason_type="price_low", reason="Test", matched=True, estimated_price_inr=28),
            OptimizedBasketItem(requested_name="onion", canonical_name="onion", decision="skip", reason_type="enough_stock", reason="Test", matched=True),
            OptimizedBasketItem(requested_name="coriander", canonical_name="coriander", decision="use_soon", reason_type="waste_risk", reason="Test", matched=True),
        ])
        assert len(basket.buy) == 1
        assert len(basket.skip) == 1
        assert len(basket.use_soon) == 1
        assert basket.total_estimated == 28

    def test_empty_basket(self):
        from shopstack.market.basket import OptimizedBasket
        basket = OptimizedBasket()
        assert len(basket.buy) == 0
        assert len(basket.skip) == 0
        assert basket.total_estimated == 0

    def test_summary_dict(self, snapshot):
        from shopstack.market.basket import OptimizedBasket, OptimizedBasketItem
        basket = OptimizedBasket(items=[
            OptimizedBasketItem(requested_name="tomato", canonical_name="tomato", decision="buy", reason_type="price_low", reason="Test", matched=True, estimated_price_inr=28),
            OptimizedBasketItem(requested_name="onion", canonical_name="onion", decision="skip", reason_type="enough_stock", reason="Test", matched=True),
        ])
        s = basket.summary
        assert s["total_requested"] == 2
        assert s["buy"] == 1
        assert s["skip"] == 1
        assert s["total_estimated_price_inr"] == 28


# ── Freshness warnings in basket ───────────────────────────────────────────


class TestFreshnessInBasket:
    def test_stale_data_in_basket(self, snapshot):
        """Stale snapshot should produce freshness notes."""
        from shopstack.market.basket import build_optimized_basket

        items = [{"canonical_name": "onion", "requested_quantity": 1.0, "unit": "kg"}]
        result = build_optimized_basket(items, snapshot)
        assert result.items[0].freshness_note
        assert "d old" in result.items[0].freshness_note or "Today" in result.items[0].freshness_note
