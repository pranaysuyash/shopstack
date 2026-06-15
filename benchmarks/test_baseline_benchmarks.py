"""Baseline latency + throughput benchmarks for providers, DB, and tools.

Restored 2026-06-14 from ``test_benchmarks_legacy.py.bak`` (motto_v3 §4
Local Work Preservation + §7 Supersession Rule). The .bak file held
real benchmark coverage (provider mock latency, DB bulk insert/query,
tool registry throughput) that was not duplicated in the active
``test_benchmarks.py``. Rather than delete the .bak as junk, we restore
it under a canonical name so the coverage lives in an importable,
discoverable location.

Why these benchmarks matter (motto_v3 §0.6 Risk-Based Verification +
§0.10 Observability Is Delivery):

  * Provider latency regressions surface as user-visible UI slowdowns
    (a 5× slowdown in mock STT would make the Ask tab feel broken even
    though every unit test still passes).
  * DB bulk-insert is the hottest path for receipt import and seed
    scripts — a regression here turns a 1s import into a 30s import.
  * Tool-registry execute is on the critical path of every Gradio
    button. Throughput regressions compound across the dashboard.

These run under the ``benchmark`` marker (see pyproject.toml) so they
don't slow down the default ``pytest tests/`` run.
"""
import tempfile
import time
from contextlib import contextmanager
from typing import Any

import pytest

pytestmark = pytest.mark.benchmark


class TestProviderBenchmarks:
    def test_mock_stt_latency(self, providers):
        samples = ["short utterance", "a " * 50, "a " * 200]
        for sample in samples:
            with temp_audio(sample) as path_file:
                path = path_file
                start = time.perf_counter()
                providers.stt.transcribe(path)
                elapsed = time.perf_counter() - start
                assert elapsed < 0.5, f"STT too slow: {elapsed:.3f}s"

    def test_mock_vision_latency(self, providers):
        start = time.perf_counter()
        providers.vision.understand("/dev/null")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Vision too slow: {elapsed:.3f}s"

    def test_mock_object_detection_latency(self, providers):
        start = time.perf_counter()
        providers.object_detection.detect("/dev/null")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Object detection too slow: {elapsed:.3f}s"

    def test_mock_planner_latency(self, providers):
        start = time.perf_counter()
        providers.planner.plan("what should I cook for dinner")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Planner too slow: {elapsed:.3f}s"

    def test_mock_ocr_latency(self, providers):
        start = time.perf_counter()
        providers.ocr.extract("/dev/null")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"OCR too slow: {elapsed:.3f}s"


class TestDatabaseBenchmarks:
    def test_bulk_insert(self, db):
        from shopstack.schemas.models import InventoryLot

        n = 100
        start = time.perf_counter()
        for i in range(n):
            db.add_inventory_lot(InventoryLot(canonical_name=f"item-{i}", display_name=f"Item {i}", quantity=1.0, unit="unit"))
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"Bulk insert too slow: {elapsed:.3f}s for {n} items"

    def test_bulk_query(self, db):
        n = db.conn.execute("SELECT COUNT(*) FROM inventory_lots").fetchone()[0]
        start = time.perf_counter()
        items = db.get_inventory()
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Query too slow: {elapsed:.3f}s for {n} items"
        assert len(items) == n


class TestToolBenchmarks:
    def test_add_item_throughput(self, tool_registry):
        n = 50
        start = time.perf_counter()
        for i in range(n):
            tool_registry.execute("add_inventory_item", canonical_name=f"bench-item-{i}", quantity=1.0, unit="unit")
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, f"Tool throughput too slow: {elapsed:.3f}s for {n} items"

    def test_find_item_latency(self, tool_registry):
        start = time.perf_counter()
        tool_registry.execute("find_item", query="bench")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.5, f"Search too slow: {elapsed:.3f}s"


@contextmanager
def temp_audio(content: str) -> Any:
    with tempfile.NamedTemporaryFile(suffix=".wav", mode="w", delete=False) as f:
        f.write(content)
        yield f.name
