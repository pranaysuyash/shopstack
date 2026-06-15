from __future__ import annotations

import pytest
from datetime import date, timedelta

from shopstack.schemas.models import PriceObservation
from shopstack.market.schema import MarketSnapshot, NormalizedMarketRecord
from shopstack.services.price_memory import PriceMemoryService


def test_price_memory_merges_market_records_and_receipts(db):
    canonical_name = "tomato"

    # 1. Save a receipt observation in the DB
    receipt_obs = PriceObservation(
        canonical_name=canonical_name,
        quantity=1.0,
        unit="kg",
        price=40.0,
        currency="INR",
        store_name="Local Kirana",
        observation_date=date.today() - timedelta(days=2),
    )
    db.record_price(receipt_obs)

    # 2. Save a market snapshot in the DB
    record_fresh = NormalizedMarketRecord(
        source="swiggy",
        source_category="fresh_vegetables",
        raw_name="Tomato Hybrid 500g",
        canonical_name=canonical_name,
        description="",
        raw_size="500 g",
        normalized_quantity=0.5,
        normalized_unit="kg",
        package_count=1,
        is_combo=False,
        is_weight_based=True,
        is_piece_based=False,
        is_size_class=False,
        size_class="",
        price_inr=30.0,
        mrp_inr=35.0,
        discount_percent_displayed=14.2,
        discount_amount_inr=5.0,
        computed_discount_percent=14.2,
        availability="In stock",
        is_available=True,
        tag="",
        is_ad=False,
        is_upgrade=False,
        card_index=0,
        delivery_time="",
        captured_at=date.today().isoformat(),
        snapshot_id="snap_vegetables_today",
        price_per_kg=60.0,
        price_per_100g=6.0,
        price_per_piece=None,
    )
    record_ad = NormalizedMarketRecord(
        source="swiggy",
        source_category="fresh_vegetables",
        raw_name="Tomato Local 500g (Sponsored)",
        canonical_name=canonical_name,
        description="",
        raw_size="500 g",
        normalized_quantity=0.5,
        normalized_unit="kg",
        package_count=1,
        is_combo=False,
        is_weight_based=True,
        is_piece_based=False,
        is_size_class=False,
        size_class="",
        price_inr=28.0,
        mrp_inr=32.0,
        discount_percent_displayed=12.5,
        discount_amount_inr=4.0,
        computed_discount_percent=12.5,
        availability="In stock",
        is_available=True,
        tag="Ad",
        is_ad=True,  # ad record - should be skipped in price history query
        is_upgrade=False,
        card_index=1,
        delivery_time="",
        captured_at=date.today().isoformat(),
        snapshot_id="snap_vegetables_today",
        price_per_kg=56.0,
        price_per_100g=5.6,
        price_per_piece=None,
    )

    snapshot = MarketSnapshot(
        snapshot_id="snap_vegetables_today",
        source="swiggy",
        source_category="fresh_vegetables",
        captured_at=date.today().isoformat(),
        raw_records=[],
        normalized_records=[record_fresh, record_ad],
        analytics={},
    )
    db.save_market_snapshot(snapshot)

    # 3. Query price summary
    pm = PriceMemoryService(db)
    summary = pm.get_summary(canonical_name)

    # Total observations should be 2 (1 receipt + 1 non-ad market record)
    assert summary.observations == 2
    assert summary.min_price == 30.0  # market record price
    assert summary.max_price == 40.0  # receipt observation price
    assert summary.median_price == 35.0  # average of 30.0 and 40.0
