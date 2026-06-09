"""Tests for the Swiggy market intelligence module."""

from __future__ import annotations

from datetime import date

import pytest

from shopstack.market import (
    MarketSnapshot,
    basket_summary,
    build_basket,
    compute_snapshot_analytics,
    find_cheapest_weight_option,
    get_produce_metadata,
    use_first,
)
from shopstack.market.normalization import (
    canonicalize_name,
    compute_unit_prices,
    parse_size,
)
from shopstack.market.sources.swiggy import (
    DEFAULT_SNAPSHOT_ID,
    load_raw,
    load_snapshot,
    normalize_record,
    snapshot_freshness,
)


# ---------- Size parser ----------


class TestSizeParser:
    def test_500g(self):
        r = parse_size("500 g")
        assert r.is_weight_based is True
        assert r.normalized_quantity == 500
        assert r.normalized_unit == "g"
        assert r.package_count == 1

    def test_1kg(self):
        r = parse_size("1 kg")
        assert r.is_weight_based is True
        assert r.normalized_quantity == 1000
        assert r.normalized_unit == "g"

    def test_250g(self):
        r = parse_size("250 g")
        assert r.normalized_quantity == 250
        assert r.is_weight_based is True

    def test_3kg(self):
        r = parse_size("3 kg")
        assert r.normalized_quantity == 3000
        assert r.is_weight_based is True

    def test_2_medium(self):
        r = parse_size("2 Medium")
        assert r.is_size_class is True
        assert r.size_class == "medium"
        assert r.is_weight_based is True
        assert r.is_piece_based is False
        assert r.normalized_quantity == 240
        assert r.normalized_unit == "g"
        assert r.warnings == ["estimated_size_class_weight:medium:120g_each"]

    def test_size_class_unit_price_is_estimated(self):
        r = parse_size("1 Large")
        prices = compute_unit_prices(36, r.normalized_quantity, r.normalized_unit, r.is_weight_based, r.is_piece_based)
        assert prices["price_per_kg"] == 200.0
        assert prices["price_per_100g"] == 20.0

    def test_4_pieces(self):
        r = parse_size("4 Pieces")
        assert r.is_piece_based is True
        assert r.normalized_quantity == 4
        assert r.normalized_unit == "pieces"

    def test_1_combo(self):
        r = parse_size("1 Combo")
        assert r.is_combo is True
        assert r.is_weight_based is False

    def test_pack(self):
        r = parse_size("1 Pack")
        assert r.is_combo is False
        assert r.is_pack is True

    def test_empty(self):
        r = parse_size("")
        assert r.normalized_quantity is None
        assert r.normalized_unit is None

    def test_bare_number(self):
        r = parse_size("6")
        assert r.is_piece_based is True
        assert r.normalized_quantity == 6


# ---------- Unit price computation ----------


class TestUnitPrices:
    def test_per_kg_from_500g(self):
        prices = compute_unit_prices(28, 500, "g", True, False)
        assert prices["price_per_kg"] == 56.0
        assert prices["price_per_100g"] == 5.6

    def test_per_kg_from_1kg(self):
        prices = compute_unit_prices(31, 1000, "g", True, False)
        assert prices["price_per_kg"] == 31.0

    def test_per_piece(self):
        prices = compute_unit_prices(51, 4, "pieces", False, True)
        assert prices["price_per_piece"] == 12.75
        assert prices["price_per_kg"] is None

    def test_zero_price(self):
        prices = compute_unit_prices(0, 500, "g", True, False)
        assert prices["price_per_kg"] is None


# ---------- Canonical name mapping ----------


class TestCanonicalize:
    def test_indian_tomato(self):
        canonical, variety, components = canonicalize_name("Indian Tomato")
        assert canonical == "tomato"
        assert components == []

    def test_hybrid_tomato(self):
        canonical, _, components = canonicalize_name("Hybrid Tomato")
        assert canonical == "tomato"

    def test_onion_with_kannada(self):
        canonical, variety, components = canonicalize_name("Onion (Eerulli)")
        assert canonical == "onion"
        assert variety == "Eerulli"

    def test_ridge_gourd_with_kannada(self):
        canonical, variety, _ = canonicalize_name("Ridge Gourd (Herekaayi)")
        assert canonical == "ridge_gourd"
        assert variety == "Herekaayi"

    def test_english_cucumber_protected(self):
        canonical, _, _ = canonicalize_name(
            "English Cucumber - Protected Cultivation"
        )
        assert canonical == "cucumber"

    def test_combo(self):
        canonical, _, components = canonicalize_name(
            "Onion, Potato & Desi Tomato"
        )
        assert "combo" in canonical
        assert len(components) >= 2

    def test_nectr_prefix(self):
        canonical, _, _ = canonicalize_name("nectr Ooty Carrot")
        assert canonical == "carrot"

    def test_capsicum(self):
        canonical, _, _ = canonicalize_name("Capsicum")
        assert canonical == "capsicum"

    def test_unknown_falls_back(self):
        canonical, _, _ = canonicalize_name("Dragon Fruit")
        assert canonical == "dragon_fruit"


# ---------- Swiggy loader ----------


class TestSwiggyLoader:
    def test_load_raw(self):
        raw = load_raw()
        assert len(raw) == 89

    def test_load_snapshot(self):
        snapshot = load_snapshot()
        assert isinstance(snapshot, MarketSnapshot)
        assert len(snapshot.normalized_records) == 89

    def test_snapshot_id(self):
        snapshot = load_snapshot()
        assert snapshot.snapshot_id == DEFAULT_SNAPSHOT_ID

    def test_first_record(self):
        raw = load_raw()
        first = raw[0]
        record = normalize_record(first)
        assert record.raw_name == "Ridge Gourd (Herekaayi)"
        assert record.canonical_name == "ridge_gourd"
        assert record.raw_size == "2 Medium"
        assert record.is_size_class is True
        assert record.is_available is True

    def test_snapshot_freshness_current(self):
        snapshot = load_snapshot()
        freshness = snapshot_freshness(snapshot, today=date(2026, 6, 6))
        assert freshness["age_days"] == 0
        assert freshness["is_stale"] is False
        assert "Captured today" in freshness["label"]

    def test_snapshot_freshness_stale(self):
        snapshot = load_snapshot(captured_at="2026-06-01")
        freshness = snapshot_freshness(snapshot, today=date(2026, 6, 6))
        assert freshness["age_days"] == 5
        assert freshness["is_stale"] is True


# ---------- Analytics ----------


class TestAnalytics:
    @pytest.fixture(scope="class")
    def snapshot(self):
        return load_snapshot()

    @pytest.fixture(scope="class")
    def analytics(self, snapshot):
        return compute_snapshot_analytics(snapshot)

    def test_total(self, analytics):
        assert analytics["total"] == 89

    def test_available(self, analytics):
        assert analytics["available"] == 45

    def test_sold_out(self, analytics):
        assert analytics["sold_out"] == 44

    def test_avg_price(self, analytics):
        assert 40 < analytics["avg_price"] < 55

    def test_median_price(self, analytics):
        assert 25 < analytics["median_price"] < 45

    def test_combos(self, analytics):
        assert analytics["combos"] >= 3

    def test_ads(self, analytics):
        assert analytics["ads"] >= 5

    def test_upgrades(self, analytics):
        assert analytics["upgrades"] >= 10

    def test_weight_records(self, analytics):
        assert analytics["weight_records_count"] > 0

    def test_canonical_counts(self, analytics):
        assert "tomato" in analytics["canonical_counts"]

    def test_best_value_tomato(self, analytics):
        bv = analytics["best_value_by_canonical"]
        assert "tomato" in bv
        assert bv["tomato"]["price_per_kg"] > 0


# ---------- Cheapest option ----------


class TestCheapestOption:
    def test_find_cheapest_tomato(self):
        snapshot = load_snapshot()
        cheapest = find_cheapest_weight_option(snapshot, "tomato")
        assert cheapest is not None
        assert cheapest.canonical_name == "tomato"
        assert cheapest.price_per_kg is not None
        assert cheapest.price_per_kg > 0

    def test_find_cheapest_nonexistent(self):
        snapshot = load_snapshot()
        assert find_cheapest_weight_option(snapshot, "dragon_fruit") is None


# ---------- Basket builder ----------


class TestBasket:
    def test_simple_basket(self):
        snapshot = load_snapshot()
        basket = build_basket(["tomato", "onion", "potato"], snapshot)
        assert len(basket) == 3
        assert all(b.matched for b in basket)
        assert all(b.estimated_price_inr is not None for b in basket)

    def test_unmatched_item(self):
        snapshot = load_snapshot()
        basket = build_basket(["tomato", "dragon fruit"], snapshot)
        assert basket[0].matched is True
        assert basket[1].matched is False
        assert basket[1].reason == "no_match_in_snapshot"

    def test_summary(self):
        snapshot = load_snapshot()
        basket = build_basket(
            ["tomato", "onion", "potato", "carrot"], snapshot
        )
        summary = basket_summary(basket)
        assert summary["matched"] == 4
        assert summary["unmatched"] == 0
        assert summary["total_estimated_price_inr"] > 0


# ---------- Produce metadata ----------


class TestProduceMetadata:
    def test_tomato(self):
        meta = get_produce_metadata("tomato")
        assert meta is not None
        assert meta.canonical_name == "tomato"
        assert meta.shelf_life_days == 7
        assert meta.waste_risk == "medium"

    def test_unknown(self):
        assert get_produce_metadata("dragon_fruit") is None

    def test_use_priority_ordering(self):
        snapshot = load_snapshot()
        available_names = {
            r.canonical_name
            for r in snapshot.normalized_records
            if r.is_available
        }
        candidates = [
            n
            for n in ["tomato", "onion", "cucumber", "coriander"]
            if n in available_names
        ]
        ordered = use_first(candidates)
        assert len(ordered) == len(candidates)

    def test_cucumber_high_risk(self):
        meta = get_produce_metadata("cucumber")
        assert meta.waste_risk == "high"
        assert meta.use_priority <= 2


# ---------- Normalization edge cases ----------


class TestNormalizationEdges:
    def test_combo_has_components(self):
        snapshot = load_snapshot()
        combos = [r for r in snapshot.normalized_records if r.is_combo]
        assert len(combos) >= 1
        for combo in combos:
            if combo.component_names:
                assert len(combo.component_names) >= 2

    def test_no_weight_based_combos_in_price_per_kg(self):
        snapshot = load_snapshot()
        for r in snapshot.normalized_records:
            if r.is_combo:
                assert r.price_per_kg is None

    def test_all_records_have_canonical(self):
        snapshot = load_snapshot()
        for r in snapshot.normalized_records:
            assert r.canonical_name != ""
            assert r.canonical_name is not None

    def test_available_flag(self):
        snapshot = load_snapshot()
        for r in snapshot.normalized_records:
            if r.availability.lower() == "available":
                assert r.is_available is True
            else:
                assert r.is_available is False

    def test_tag_parsing(self):
        snapshot = load_snapshot()
        for r in snapshot.normalized_records:
            if r.tag.lower() == "ad":
                assert r.is_ad is True
            elif r.tag.lower() == "upgrade":
                assert r.is_upgrade is True
