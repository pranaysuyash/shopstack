from __future__ import annotations

import pytest

from shopstack.decisions import classify_all
from shopstack.portability import (
    export_csv_inventory,
    export_json,
    export_trace_bundle,
    import_json,
    validate_import_json,
)
from shopstack.services.dashboard import build_dashboard_state
from shopstack.services.receipt import parse_receipt_text
from shopstack.services.search import semantic_search
from shopstack.services.shopping import classify_shopping_items

pytestmark = pytest.mark.benchmark(group="services")


def test_build_dashboard_state(benchmark, bench_db, bench_tools):
    result = benchmark(build_dashboard_state, bench_db, bench_tools)
    assert result.decision_set is not None


def test_classify_all(benchmark, bench_db, bench_tools):
    result = benchmark(classify_all, bench_db, bench_tools)
    assert len(result.decisions) >= 10


def test_semantic_search_exact(benchmark, bench_db):
    result = benchmark(semantic_search, bench_db, "rice")
    assert len(result) >= 1
    assert result[0].match_type == "exact"


def test_semantic_search_prefix(benchmark, bench_db):
    result = benchmark(semantic_search, bench_db, "ric")
    assert len(result) >= 1
    assert result[0].match_type == "prefix"


def test_semantic_search_miss(benchmark, bench_db):
    result = benchmark(semantic_search, bench_db, "zzznonexistent")
    assert len(result) == 0


def test_export_json(benchmark, bench_db):
    result = benchmark(export_json, bench_db)
    assert "inventory" in result
    assert "price_observations" in result


def test_parse_receipt_text(benchmark, sample_receipt_text):
    result = benchmark(parse_receipt_text, sample_receipt_text)
    assert result.merchant == "Sharma General Store"
    assert len(result.lines) >= 10
    assert result.total > 0


def test_classify_shopping_items(benchmark, bench_tools):
    items = [
        {"canonical_name": "milk", "requested_quantity": 2.0, "unit": "L"},
        {"canonical_name": "bread", "requested_quantity": 1.0, "unit": "unit"},
        {"canonical_name": "tomato", "requested_quantity": 1.0, "unit": "kg"},
        {"canonical_name": "onion", "requested_quantity": 2.0, "unit": "kg"},
        {"canonical_name": "egg", "requested_quantity": 1.0, "unit": "dozen"},
    ]

    result = benchmark(classify_shopping_items, items, bench_tools)
    assert len(result.all_items) >= 3
