from __future__ import annotations

import pytest
from datetime import date, timedelta, datetime

from shopstack.schemas.models import InventoryLot
from shopstack.services.decision_engine import should_buy, should_skip
from shopstack.services.dashboard import build_dashboard_state


def test_decision_engine_dynamic_confidence_and_warning():
    # 1. Fresh item (purchased today) -> high confidence, no warning
    today = date.today()
    res_buy = should_buy(
        canonical_name="coriander",
        display_name="Coriander",
        quantity_at_home=0.3,  # running low
        unit="g",
        last_purchase_date=today,
        shelf_life_days=5,
        last_confirmed=today,
    )
    assert res_buy is not None
    inv_evidence = next(e for e in res_buy.evidence if e.source == "inventory")
    assert inv_evidence.confidence > 0.9
    assert not any(w.code == "inventory_unconfirmed" for w in res_buy.warnings)

    # 2. Expired item (purchased 6 days ago with 5-day shelf life) -> low confidence, warning attached
    six_days_ago = today - timedelta(days=6)
    res_buy_expired = should_buy(
        canonical_name="coriander",
        display_name="Coriander",
        quantity_at_home=0.3,
        unit="g",
        last_purchase_date=six_days_ago,
        shelf_life_days=5,
        last_confirmed=six_days_ago,
    )
    assert res_buy_expired is not None
    inv_evidence_expired = next(e for e in res_buy_expired.evidence if e.source == "inventory")
    assert inv_evidence_expired.confidence < 0.4
    assert any(w.code == "inventory_unconfirmed" for w in res_buy_expired.warnings)


def test_should_skip_dynamic_confidence_and_warning():
    today = date.today()
    six_days_ago = today - timedelta(days=6)

    # Low stock skipped item with low confidence
    res_skip = should_skip(
        canonical_name="coriander",
        display_name="Coriander",
        quantity_at_home=2.0,  # stocked
        unit="g",
        recently_bought=False,
        shelf_life_days=5,
        last_confirmed=six_days_ago,
    )
    assert res_skip is not None
    inv_evidence = next(e for e in res_skip.evidence if e.source == "inventory")
    assert inv_evidence.confidence < 0.4
    assert any(w.code == "inventory_unconfirmed" for w in res_skip.warnings)


def test_dashboard_populates_items_needing_confirmation(db):
    # Seed a fresh lot and a stale lot in DB
    fresh_lot = InventoryLot(
        canonical_name="milk",
        display_name="Milk",
        quantity=1.0,
        unit="L",
        status="active",
        purchase_date=date.today(),
        user_id="default_household",
    )
    stale_lot = InventoryLot(
        canonical_name="coriander",
        display_name="Coriander",
        quantity=1.0,
        unit="g",
        status="active",
        purchase_date=date.today() - timedelta(days=10),
        user_id="default_household",
    )
    stale_lot.updated_at = datetime.now() - timedelta(days=10)

    db.add_inventory_lot(fresh_lot)
    db.add_inventory_lot(stale_lot)

    # Build dashboard state
    state = build_dashboard_state(db, inventory=[], city="mumbai", user_id="default_household")

    # Stale item should be in items_needing_confirmation, but fresh item should not
    needing_conf_names = {item["canonical_name"] for item in state.items_needing_confirmation}
    assert "coriander" in needing_conf_names
    assert "milk" not in needing_conf_names

    # Check structure
    stale_entry = next(item for item in state.items_needing_confirmation if item["canonical_name"] == "coriander")
    assert stale_entry["lot_id"] == stale_lot.lot_id
    assert stale_entry["confidence"] < 0.4
    assert "Coriander" in stale_entry["prompt"]
