from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from shopstack.market.schema import MarketSnapshot, NormalizedMarketRecord
from shopstack.services import market_sources


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
        snapshot_id="snap-001",
        price_per_kg=50.0,
        price_per_100g=5.0,
        price_per_piece=None,
    )


def _make_snapshot(source: str, normalized_count: int = 1) -> MarketSnapshot:
    records = [_make_record(f"{source}_{idx}", source) for idx in range(normalized_count)]
    return MarketSnapshot(
        snapshot_id=f"{source}-snapshot",
        source=source,
        source_category="fresh_vegetables",
        captured_at="2026-06-10T00:00:00",
        raw_records=[],
        normalized_records=records,
        analytics={},
    )


class _FakeRegistry:
    def __init__(self, latest: dict[str, MarketSnapshot | None], load_handlers: dict[str, Any], source_ids: list[str]):
        self._latest = dict(latest)
        self._load_handlers = load_handlers
        self._source_ids = source_ids
        self.load_calls: list[str] = []

    def registered(self):
        return list(self._source_ids)

    def all_snapshots(self):
        return {sid: snap for sid, snap in self._latest.items() if snap is not None}

    def latest(self, source: str):
        return self._latest.get(source)

    def load(self, source: str):
        self.load_calls.append(source)
        result = self._load_handlers[source]()
        self._latest[source] = result
        return result

    def freshness_of(self, source: str):
        snap = self._latest.get(source)
        if snap is None:
            return {"source_id": source, "is_stale": True, "label": "No snapshot loaded", "captured_at": None}
        return {"source_id": source, "is_stale": False, "label": "Fresh", "captured_at": snap.captured_at}


def _install_fake_registry(monkeypatch, registry: _FakeRegistry):
    monkeypatch.setattr(market_sources, "_build_registry", lambda _db: registry)


def test_load_market_registry_loads_missing_sources(monkeypatch):
    fake_snap = _make_snapshot("swiggy")
    registry = _FakeRegistry(
        latest={"swiggy": None, "blinkit": None},
        load_handlers={
            "swiggy": lambda: fake_snap,
            "blinkit": lambda: (_ for _ in ()).throw(RuntimeError("missing file")),
        },
        source_ids=["swiggy", "blinkit"],
    )
    _install_fake_registry(monkeypatch, registry)

    _registry, errors = market_sources.load_market_registry()

    assert _registry is registry
    assert registry.load_calls == ["swiggy", "blinkit"]
    assert registry.latest("swiggy") == fake_snap
    assert errors == {"blinkit": "missing file"}


def test_load_market_registry_respects_cached_snapshot(monkeypatch):
    fake_snap = _make_snapshot("swiggy")
    registry = _FakeRegistry(
        latest={"swiggy": fake_snap},
        load_handlers={
            "swiggy": lambda: (_ for _ in ()).throw(RuntimeError("should not load")),
        },
        source_ids=["swiggy"],
    )
    _install_fake_registry(monkeypatch, registry)

    _registry, errors = market_sources.load_market_registry(force=False)

    assert registry.load_calls == []
    assert _registry is registry
    assert registry.latest("swiggy") == fake_snap
    assert errors == {}


def test_load_market_registry_force_refreshes_cached_source(monkeypatch):
    fake_snap_v1 = _make_snapshot("swiggy", normalized_count=1)
    fake_snap_v2 = _make_snapshot("swiggy", normalized_count=2)
    calls = {"count": 0}

    def _load() -> MarketSnapshot:
        calls["count"] += 1
        return fake_snap_v2

    registry = _FakeRegistry(
        latest={"swiggy": fake_snap_v1},
        load_handlers={"swiggy": _load},
        source_ids=["swiggy"],
    )
    _install_fake_registry(monkeypatch, registry)

    _registry, errors = market_sources.load_market_registry(force=True)

    assert registry.load_calls == ["swiggy"]
    assert registry.latest("swiggy") == fake_snap_v2
    assert calls["count"] == 1
    assert errors == {}


def test_source_status_report_includes_loaded_and_missing(monkeypatch):
    registry = _FakeRegistry(
        latest={"swiggy": _make_snapshot("swiggy", normalized_count=2), "blinkit": None},
        load_handlers={
            "swiggy": lambda: _make_snapshot("swiggy"),
            "blinkit": lambda: _make_snapshot("blinkit"),
        },
        source_ids=["swiggy", "blinkit"],
    )
    _install_fake_registry(monkeypatch, registry)

    report = market_sources.source_status_report(force=False)

    assert report["swiggy"]["status"] == "loaded"
    assert report["swiggy"]["snapshot_id"] == "swiggy-snapshot"
    assert report["swiggy"]["record_count"] == 2
    assert report["blinkit"]["status"] == "loaded"
    assert report["blinkit"]["snapshot_id"] == "blinkit-snapshot"


def test_load_all_available_snapshots_returns_loaded_data(monkeypatch):
    swiggy_snapshot = _make_snapshot("swiggy")
    registry = _FakeRegistry(
        latest={"swiggy": swiggy_snapshot, "blinkit": None},
        load_handlers={
            "swiggy": lambda: swiggy_snapshot,
            "blinkit": lambda: _make_snapshot("blinkit"),
        },
        source_ids=["swiggy", "blinkit"],
    )
    _install_fake_registry(monkeypatch, registry)

    snapshots = market_sources.load_all_available_snapshots()

    assert [s.snapshot_id for s in snapshots] == [swiggy_snapshot.snapshot_id]


def test_get_latest_snapshot_uses_db_fallback(monkeypatch):
    db = SimpleNamespace(
        get_latest_market_snapshot=lambda source: _make_snapshot("swiggy")
    )
    registry = _FakeRegistry(
        latest={"swiggy": None},
        load_handlers={
            "swiggy": lambda: (_ for _ in ()).throw(RuntimeError("source missing")),
        },
        source_ids=["swiggy"],
    )
    _install_fake_registry(monkeypatch, registry)

    snapshot = market_sources.get_latest_snapshot("swiggy", db=db)

    assert snapshot is not None
    assert snapshot.source == "swiggy"
