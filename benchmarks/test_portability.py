from __future__ import annotations

import json

import pytest

from shopstack.portability import (
    export_csv_inventory,
    export_json,
    export_trace_bundle,
    import_json,
    validate_import_json,
)

pytestmark = pytest.mark.benchmark(group="portability")


def test_export_json_full(benchmark, bench_db):
    result = benchmark(export_json, bench_db)
    assert len(result["inventory"]) >= 50
    assert len(result["price_observations"]) >= 50


def test_export_csv_inventory(benchmark, bench_db):
    result = benchmark(export_csv_inventory, bench_db)
    lines = result.strip().split("\n")
    assert len(lines) >= 51


def test_export_trace_bundle(benchmark, bench_db):
    result = benchmark(export_trace_bundle, bench_db)
    assert result["export_type"] == "trace_bundle"
    assert result["lot_count"] >= 50


def test_import_json_merge(benchmark, bench_db):
    payload = {
        "schema_version": "1.0",
        "inventory": [
            {"canonical_name": "merge_test_item", "display_name": "Merge Test", "quantity": 2.0, "unit": "kg"},
            {"canonical_name": "another_merge", "display_name": "Another", "quantity": 1.0, "unit": "unit"},
        ],
        "price_observations": [
            {"canonical_name": "merge_test_item", "price": 99.0, "quantity": 1.0, "unit": "kg", "store_name": "Test"},
        ],
    }

    result = benchmark(import_json, bench_db, payload, import_mode="merge")
    assert result.items_added + result.items_updated >= 1


def test_import_json_replace(benchmark, fresh_db):
    from shopstack.schemas.models import InventoryLot

    for i in range(10):
        lot = InventoryLot(
            canonical_name=f"preexisting-{i}",
            display_name=f"Item {i}",
            quantity=1.0,
            unit="unit",
        )
        fresh_db.add_inventory_lot(lot)

    payload = {
        "schema_version": "1.0",
        "inventory": [
            {"canonical_name": "replace_item", "display_name": "Replace Test", "quantity": 5.0, "unit": "kg"},
        ],
    }

    result = benchmark(import_json, fresh_db, payload, import_mode="replace")
    assert result.items_added >= 1


def test_validate_import_json(benchmark, bench_db):
    payload = {
        "schema_version": "1.0",
        "inventory": [
            {"canonical_name": "validate_item", "display_name": "Validate Test", "quantity": 1.0, "unit": "unit"},
            {"canonical_name": "another_validate", "display_name": "Another Validate", "quantity": 2.0, "unit": "kg"},
            {"canonical_name": "rice", "display_name": "Rice", "quantity": 5.0, "unit": "kg"},
        ],
        "price_observations": [
            {"canonical_name": "validate_item", "price": 50.0, "quantity": 1.0, "unit": "unit"},
        ],
    }

    result = benchmark(validate_import_json, bench_db, payload)
    assert result.items_added >= 1
    assert "Dry-run" in result.messages[0]


def test_export_json_serialization_size(benchmark, bench_db):
    def serialize():
        data = export_json(bench_db)
        return json.dumps(data)

    result = benchmark(serialize)
    parsed = json.loads(result)
    assert "inventory" in parsed
