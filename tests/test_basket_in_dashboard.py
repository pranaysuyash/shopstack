from __future__ import annotations

import pytest
from shopstack.services.dashboard import build_dashboard_state
from shopstack.schemas.models import ShoppingList, ShoppingListItem
from shopstack.market.schema import MarketSnapshot, NormalizedMarketRecord

def _make_record(name: str, source: str) -> NormalizedMarketRecord:
    return NormalizedMarketRecord(
        source=source,
        source_category="fresh_vegetables",
        raw_name=name,
        canonical_name=name,
        description="",
        raw_size="1 kg",
        normalized_quantity=1.0,
        normalized_unit="kg",
        package_count=1,
        is_combo=False,
        is_weight_based=True,
        is_piece_based=False,
        is_size_class=False,
        size_class="",
        price_inr=50.0,
        mrp_inr=60.0,
        discount_percent_displayed=16.7,
        discount_amount_inr=10.0,
        computed_discount_percent=16.7,
        availability="In stock",
        is_available=True,
        tag="",
        is_ad=False,
        is_upgrade=False,
        card_index=0,
        delivery_time="",
        captured_at="2026-06-10T00:00:00",
        snapshot_id="test_snap",
        price_per_kg=50.0,
        price_per_100g=5.0,
        price_per_piece=None,
    )

def test_basket_in_dashboard_with_active_list(db):
    # Setup mock inventory helper
    class MockInventory:
        def get_use_soon(self, days, user_id=""):
            return {"count": 0, "items": []}
        def get_use_soon_items(self, days):
            return {"count": 0, "items": []}

    inventory = MockInventory()

    # Use the same user_id the dashboard queries with
    from shopstack.app_context import current_user_id
    user_id = current_user_id()

    # Verify initially optimized_basket is None (no active shopping list or snapshot)
    state = build_dashboard_state(db, inventory)
    assert state.optimized_basket is None

    # Insert a mock market snapshot into the DB
    from datetime import datetime
    snapshot = MarketSnapshot(
        snapshot_id="test_snap",
        source="swiggy",
        source_category="grocery",
        captured_at=datetime.now().isoformat(),
        raw_records=[],
        normalized_records=[
            _make_record("milk", "swiggy")
        ],
        analytics={},
    )
    db.save_market_snapshot(snapshot)

    # Create active shopping list (scoped to the current user)
    lst = ShoppingList(list_id="list_1", name="Trip", is_active=True)
    db.conn.execute(
        "INSERT INTO shopping_lists (list_id, name, is_active, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?, ?)",
        (lst.list_id, lst.name, 1 if lst.is_active else 0, lst.created_at.isoformat(), lst.updated_at.isoformat(), user_id),
    )
    item = ShoppingListItem(list_item_id="item_1", canonical_name="milk", requested_quantity=2.0, unit="L")
    db.add_list_item(lst.list_id, item)

    # Re-run build_dashboard_state and check optimized_basket is populated
    state = build_dashboard_state(db, inventory)
    assert state.optimized_basket is not None
    assert len(state.optimized_basket.items) == 1
    assert state.optimized_basket.items[0].canonical_name == "milk"
    # Milk should be buy since we don't have it in inventory
    assert state.optimized_basket.items[0].decision == "buy"
