"""Tests for the Blinkit market source adapter."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from shopstack.market.schema import MarketSnapshot
from shopstack.market.sources._blinkit_adapter import (
    BlinkitAdapter,
    DEFAULT_CAPTURED_AT,
    DEFAULT_SNAPSHOT_ID,
    load_raw,
    load_snapshot,
    normalize_record,
    snapshot_freshness,
)

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


# ---------- Raw loader ----------


class TestBlinkitLoader:
    def test_load_raw(self):
        raw = load_raw(_FIXTURE_DIR)
        assert len(raw) == 6

    def test_load_snapshot(self):
        snapshot = load_snapshot(data_dir=_FIXTURE_DIR)
        assert isinstance(snapshot, MarketSnapshot)
        assert len(snapshot.normalized_records) == 6

    def test_snapshot_id(self):
        snapshot = load_snapshot(data_dir=_FIXTURE_DIR)
        assert snapshot.snapshot_id == DEFAULT_SNAPSHOT_ID
        assert snapshot.source == "blinkit"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="No blinkit_fresh_vegetables_"):
            load_raw(Path("/nonexistent"))


# ---------- Normalization ----------


class TestBlinkitNormalization:
    def test_tomato_normalization(self):
        raw = load_raw(_FIXTURE_DIR)
        record = normalize_record(raw[0])
        assert record.source == "blinkit"
        assert record.raw_name == "Hybrid Tomato"
        assert record.canonical_name == "tomato"
        assert record.raw_size == "500 g"
        assert record.normalized_quantity == 500
        assert record.normalized_unit == "g"
        assert record.is_weight_based is True
        assert record.is_available is True
        assert record.price_inr == 28.0
        assert record.mrp_inr == 34.0
        assert abs(record.computed_discount_percent - 17.6) < 0.1
        assert record.discount_percent_displayed == 17.6
        assert record.price_per_kg == 56.0
        assert record.price_per_100g == 5.6
        assert record.price_per_piece is None
        assert record.brand == "Freshly"

    def test_onion_normalization(self):
        raw = load_raw(_FIXTURE_DIR)
        record = normalize_record(raw[1])
        assert record.canonical_name == "onion"
        assert record.raw_size == "1 kg"
        assert record.normalized_quantity == 1000
        assert record.normalized_unit == "g"
        assert record.price_inr == 27.0
        assert record.mrp_inr == 32.0
        assert record.price_per_kg == 27.0
        assert record.brand == "Farm Fresh"

    def test_sold_out_carrot(self):
        raw = load_raw(_FIXTURE_DIR)
        record = normalize_record(raw[3])
        assert record.canonical_name == "carrot"
        assert record.is_available is False
        assert record.availability == "Sold Out"
        assert record.delivery_time == ""

    def test_ad_tagged_item(self):
        raw = load_raw(_FIXTURE_DIR)
        record = normalize_record(raw[4])
        assert record.is_ad is True
        assert record.is_upgrade is False
        assert record.tag == "ad"

    def test_combo_item(self):
        raw = load_raw(_FIXTURE_DIR)
        record = normalize_record(raw[5])
        assert record.is_combo is True
        assert record.price_per_kg is None
        assert record.price_per_piece is None

    def test_default_snapshot_id(self):
        raw = load_raw(_FIXTURE_DIR)
        record = normalize_record(raw[0])
        assert record.snapshot_id == DEFAULT_SNAPSHOT_ID
        assert record.source_category == "fresh_vegetables"

    def test_missing_fields_avoid_crash(self):
        record = normalize_record({})
        assert record.raw_name == ""
        assert record.price_inr == 0.0
        assert record.is_available is False


# ---------- Freshness ----------


class TestBlinkitFreshness:
    def test_freshness_current(self):
        snapshot = load_snapshot(data_dir=_FIXTURE_DIR, captured_at="2026-06-06")
        freshness = snapshot_freshness(snapshot, today=date(2026, 6, 6))
        assert freshness["age_days"] == 0
        assert freshness["is_stale"] is False
        assert "Captured today" in freshness["label"]

    def test_freshness_yesterday(self):
        snapshot = load_snapshot(data_dir=_FIXTURE_DIR, captured_at="2026-06-05")
        freshness = snapshot_freshness(snapshot, today=date(2026, 6, 6))
        assert freshness["age_days"] == 1
        assert freshness["is_stale"] is False
        assert "Captured yesterday" in freshness["label"]

    def test_freshness_stale(self):
        snapshot = load_snapshot(data_dir=_FIXTURE_DIR, captured_at="2026-06-01")
        freshness = snapshot_freshness(snapshot, today=date(2026, 6, 6))
        assert freshness["age_days"] == 5
        assert freshness["is_stale"] is True

    def test_freshness_no_date(self):
        snapshot = load_snapshot(data_dir=_FIXTURE_DIR, captured_at="bad-date")
        freshness = snapshot_freshness(snapshot)
        assert freshness["age_days"] is None
        assert freshness["is_stale"] is True
        assert "unclear" in freshness["label"]


# ---------- Adapter class ----------


class TestBlinkitAdapter:
    def test_adapter_instantiate(self):
        adapter = BlinkitAdapter(data_dir=_FIXTURE_DIR)
        assert adapter.source_id == "blinkit"
        assert adapter.source_category == "fresh_vegetables"

    def test_adapter_load_snapshot(self):
        adapter = BlinkitAdapter(data_dir=_FIXTURE_DIR)
        snapshot = adapter.load_snapshot()
        assert isinstance(snapshot, MarketSnapshot)
        assert snapshot.source == "blinkit"

    def test_adapter_freshness(self):
        adapter = BlinkitAdapter(data_dir=_FIXTURE_DIR)
        snapshot = adapter.load_snapshot()
        freshness = adapter.freshness(snapshot)
        assert "age_days" in freshness
        assert "is_stale" in freshness
        assert "label" in freshness

    def test_adapter_available_names(self):
        adapter = BlinkitAdapter(data_dir=_FIXTURE_DIR)
        snapshot = adapter.load_snapshot()
        names = adapter.available_canonical_names(snapshot)
        assert "tomato" in names
        assert "onion" in names
        assert "cucumber" in names
        assert "carrot" not in names  # sold out

    def test_adapter_loads_from_any_directory(self):
        adapter = BlinkitAdapter(data_dir=_FIXTURE_DIR)
        snapshot = adapter.load_snapshot()
        assert len(snapshot.normalized_records) == 6
