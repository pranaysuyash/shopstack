"""Tests for the Zepto market source adapter."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from shopstack.market.schema import MarketSnapshot
from shopstack.market.sources._zepto_adapter import (
    ZeptoAdapter,
    DEFAULT_CAPTURED_AT,
    DEFAULT_SNAPSHOT_ID,
    load_raw,
    load_snapshot,
    normalize_record,
    snapshot_freshness,
)

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


# ---------- Raw loader ----------


class TestZeptoLoader:
    def test_load_raw(self):
        raw = load_raw(_FIXTURE_DIR)
        assert len(raw) == 6

    def test_load_snapshot(self):
        snapshot = load_snapshot(data_dir=_FIXTURE_DIR)
        assert isinstance(snapshot, MarketSnapshot)
        assert len(snapshot.normalized_records) == 6

    def test_snapshot_id(self):
        snapshot = load_snapshot(data_dir=_FIXTURE_DIR)
        assert snapshot.snapshot_id.startswith("zepto_")
        assert snapshot.source == "zepto"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="No zepto_fresh_vegetables_"):
            load_raw(Path("/nonexistent"))


# ---------- Normalization ----------


class TestZeptoNormalization:
    def test_tomato_normalization(self):
        raw = load_raw(_FIXTURE_DIR)
        record = normalize_record(raw[0])
        assert record.source == "zepto"
        assert record.raw_name == "Hybrid Tomato"
        assert record.canonical_name == "tomato"
        assert record.raw_size == "500 g"
        assert record.normalized_quantity == 500
        assert record.normalized_unit == "g"
        assert record.is_weight_based is True
        assert record.is_available is True
        assert record.price_inr == 29.0  # sale_price
        assert record.mrp_inr == 36.0  # original_price
        assert record.price_per_kg == 58.0
        assert record.price_per_100g == 5.8

    def test_onion_normalization(self):
        raw = load_raw(_FIXTURE_DIR)
        record = normalize_record(raw[1])
        assert record.canonical_name == "onion"
        assert record.raw_size == "1 kg"
        assert record.normalized_quantity == 1000
        assert record.price_inr == 26.0
        assert record.mrp_inr == 32.0
        assert record.price_per_kg == 26.0

    def test_sold_out_carrot(self):
        raw = load_raw(_FIXTURE_DIR)
        record = normalize_record(raw[3])
        assert record.canonical_name == "carrot"
        assert record.is_available is False

    def test_upgrade_tagged_item(self):
        raw = load_raw(_FIXTURE_DIR)
        record = normalize_record(raw[4])
        assert record.is_upgrade is True
        assert record.is_ad is False
        assert record.tag == "upgrade"

    def test_combo_item(self):
        raw = load_raw(_FIXTURE_DIR)
        record = normalize_record(raw[5])
        assert record.is_combo is True
        assert record.price_per_kg is None

    def test_missing_fields_avoid_crash(self):
        record = normalize_record({})
        assert record.raw_name == ""
        assert record.price_inr == 0.0
        assert record.is_available is False

    def test_promotional_discount(self):
        raw = load_raw(_FIXTURE_DIR)
        record = normalize_record(raw[1])
        assert record.computed_discount_percent > 0
        assert record.discount_percent_displayed == 18.8


# ---------- Freshness ----------


class TestZeptoFreshness:
    def test_freshness_current(self):
        snapshot = load_snapshot(data_dir=_FIXTURE_DIR, captured_at="2026-06-06")
        freshness = snapshot_freshness(snapshot, today=date(2026, 6, 6))
        assert freshness["age_days"] == 0
        assert freshness["is_stale"] is False

    def test_freshness_yesterday(self):
        snapshot = load_snapshot(data_dir=_FIXTURE_DIR, captured_at="2026-06-05")
        freshness = snapshot_freshness(snapshot, today=date(2026, 6, 6))
        assert freshness["age_days"] == 1
        assert freshness["is_stale"] is False

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


# ---------- Adapter class ----------


class TestZeptoAdapter:
    def test_adapter_instantiate(self):
        adapter = ZeptoAdapter(data_dir=_FIXTURE_DIR)
        assert adapter.source_id == "zepto"
        assert adapter.source_category == "fresh_vegetables"

    def test_adapter_load_snapshot(self):
        adapter = ZeptoAdapter(data_dir=_FIXTURE_DIR)
        snapshot = adapter.load_snapshot()
        assert isinstance(snapshot, MarketSnapshot)
        assert snapshot.source == "zepto"

    def test_adapter_freshness(self):
        adapter = ZeptoAdapter(data_dir=_FIXTURE_DIR)
        snapshot = adapter.load_snapshot()
        freshness = adapter.freshness(snapshot)
        assert "age_days" in freshness
        assert "is_stale" in freshness
        assert "label" in freshness

    def test_adapter_available_names(self):
        adapter = ZeptoAdapter(data_dir=_FIXTURE_DIR)
        snapshot = adapter.load_snapshot()
        names = adapter.available_canonical_names(snapshot)
        assert "tomato" in names
        assert "onion" in names
        assert "potato" in names
        assert "carrot" not in names  # sold out

    def test_adapter_loads_from_any_directory(self):
        adapter = ZeptoAdapter(data_dir=_FIXTURE_DIR)
        snapshot = adapter.load_snapshot()
        assert len(snapshot.normalized_records) == 6
