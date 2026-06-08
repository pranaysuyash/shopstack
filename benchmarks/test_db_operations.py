from __future__ import annotations

from datetime import date, timedelta

import pytest

from shopstack.schemas.models import InventoryLot, PriceObservation

pytestmark = pytest.mark.benchmark(group="db")


def test_db_init(benchmark):
    import tempfile
    from pathlib import Path

    from shopstack.persistence.database import Database

    def create_fresh_db():
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        d = Database(path)
        Path(path).unlink(missing_ok=True)
        return d

    benchmark(create_fresh_db)


def test_add_inventory_lot(benchmark, fresh_db):
    lot = InventoryLot(
        canonical_name="bench_item",
        display_name="Bench Item",
        quantity=1.0,
        unit="unit",
    )

    def add_one():
        lot_fresh = InventoryLot(
            canonical_name="bench_item",
            display_name="Bench Item",
            quantity=1.0,
            unit="unit",
        )
        fresh_db.add_inventory_lot(lot_fresh)

    benchmark(add_one)


def test_add_100_inventory_lots(benchmark, fresh_db):
    def add_100():
        for i in range(100):
            lot = InventoryLot(
                canonical_name=f"bulk-item-{i}",
                display_name=f"Bulk Item {i}",
                quantity=1.0,
                unit="unit",
            )
            fresh_db.add_inventory_lot(lot)

    benchmark(add_100)


def test_get_inventory_full(benchmark, bench_db):
    result = benchmark(bench_db.get_inventory)
    assert len(result) >= 50


def test_get_inventory_filtered(benchmark, bench_db):
    result = benchmark(bench_db.get_inventory, canonical_name="rice")
    assert len(result) >= 1


def test_update_inventory_lot(benchmark, bench_db):
    lots = bench_db.get_inventory()
    lot = lots[0]

    def update():
        bench_db.update_inventory_lot(lot.lot_id, {"quantity": lot.quantity + 0.1})

    benchmark(update)


def test_update_100_lots(benchmark, bench_db):
    lots = bench_db.get_inventory()[:100]

    def update_all():
        for lot in lots:
            bench_db.update_inventory_lot(lot.lot_id, {"quantity": lot.quantity + 0.01})

    benchmark(update_all)


def test_record_price_observation(benchmark, bench_db):
    today = date.today()

    def record():
        obs = PriceObservation(
            canonical_name="bench_price_item",
            quantity=1.0,
            unit="kg",
            price=42.0,
            store_name="Test Store",
            observation_date=today,
        )
        bench_db.record_price(obs)

    benchmark(record)


def test_record_100_price_observations(benchmark, bench_db):
    today = date.today()

    def record_100():
        for i in range(100):
            obs = PriceObservation(
                canonical_name=f"price-bench-{i % 10}",
                quantity=1.0,
                unit="kg",
                price=50.0 + i,
                store_name="DMart",
                observation_date=today,
            )
            bench_db.record_price(obs)

    benchmark(record_100)


def test_get_price_history(benchmark, bench_db):
    result = benchmark(bench_db.get_price_history, "rice")
    assert len(result) >= 1


def test_get_price_history_heavy_item(benchmark, bench_db):
    bench_item = SEED_ITEMS[0][0] if (SEED_ITEMS := []) else "rice"
    most_observed = bench_db.conn.execute(
        "SELECT canonical_name, COUNT(*) as cnt FROM price_observations GROUP BY canonical_name ORDER BY cnt DESC LIMIT 1"
    ).fetchone()
    if most_observed:
        result = benchmark(bench_db.get_price_history, most_observed["canonical_name"])
        assert len(result) >= 1


def test_get_purchase_events(benchmark, bench_db):
    result = benchmark(bench_db.get_purchase_events, limit=20)
    assert len(result) >= 1


def test_get_active_shopping_list(benchmark, bench_db):
    benchmark(bench_db.get_active_shopping_list)


def test_get_locations(benchmark, bench_db):
    result = benchmark(bench_db.get_locations)
    assert len(result) >= 10


def test_get_inventory_lot(benchmark, bench_db):
    lots = bench_db.get_inventory()
    lot_id = lots[0].lot_id

    result = benchmark(bench_db.get_inventory_lot, lot_id)
    assert result is not None
