from __future__ import annotations

from collections.abc import Mapping
from typing import Any, List, Optional

from shopstack.config import settings
from shopstack.persistence.database import Database
from shopstack.market.schema import MarketSnapshot, NormalizedMarketRecord


def _build_registry(db: Database):
    from shopstack.market.sources import MarketSnapshotRepository, build_registry

    repository = MarketSnapshotRepository(db)
    return build_registry(repository=repository)


def load_market_registry(
    db: Optional[Database] = None,
    force: bool = False,
) -> tuple[Any, dict[str, str]]:
    """Build a registry and load all registered sources.

    Returns a tuple of `(registry, load_errors)`, where load_errors is keyed by
    source id and contains a short failure message for any source that could not
    be loaded.
    """
    if db is None:
        db = Database(settings.db_path)

    registry = _build_registry(db)
    load_errors: dict[str, str] = {}
    for source_id in registry.registered():
        try:
            should_load = force or registry.latest(source_id) is None
            if should_load:
                registry.load(source_id)
        except Exception as exc:
            load_errors[source_id] = str(exc)
    return registry, load_errors


def source_status_report(
    db: Optional[Database] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Return per-source status with load result and latest snapshot metadata."""
    if db is None:
        db = Database(settings.db_path)

    registry, load_errors = load_market_registry(db=db, force=force)

    report: dict[str, Any] = {}
    for source_id in registry.registered():
        snapshot = registry.latest(source_id)
        if snapshot is None:
            status = "missing"
            freshness = {"is_stale": True, "label": "No snapshot loaded", "captured_at": None}
        else:
            try:
                freshness = registry.freshness_of(source_id)
            except Exception:
                freshness = {"is_stale": True, "label": "Freshness unavailable", "captured_at": None}
            status = "loaded"

        source_error = load_errors.get(source_id)
        if source_error:
            status = "error"

        report[source_id] = {
            "status": status,
            "snapshot_id": snapshot.snapshot_id if snapshot else None,
            "captured_at": snapshot.captured_at if snapshot else None,
            "source_category": snapshot.source_category if snapshot else None,
            "record_count": len(snapshot.normalized_records) if snapshot else 0,
            "freshness": freshness,
            "error": source_error,
        }

    return report


def load_source_snapshot(
    snapshot_id: str,
    db: Optional[Database] = None,
) -> Optional[MarketSnapshot]:
    if db is None:
        db = Database(settings.db_path)
    return db.get_market_snapshot(snapshot_id)


def load_all_available_snapshots(db: Optional[Database] = None) -> List[MarketSnapshot]:
    if db is None:
        db = Database(settings.db_path)

    registry = _build_registry(db)
    snapshots: list[MarketSnapshot] = []
    if hasattr(registry, "all_snapshots"):
        existing = registry.all_snapshots()
        if isinstance(existing, Mapping):
            snapshots.extend(list(existing.values()))
        else:
            snapshots.extend(list(existing))
    else:
        for source_id in registry.registered():
            snap = registry.latest(source_id)
            if snap is not None:
                snapshots.append(snap)
    return snapshots


def get_latest_snapshot(
    source_id: str,
    db: Optional[Database] = None,
) -> Optional[MarketSnapshot]:
    if db is None:
        db = Database(settings.db_path)

    registry, _ = load_market_registry(db=db, force=False)
    cached = registry.latest(source_id)
    if cached is not None:
        return cached
    return db.get_latest_market_snapshot(source_id)


def get_records_by_canonical(
    canonical_name: str,
    db: Optional[Database] = None,
) -> list[NormalizedMarketRecord]:
    if db is None:
        db = Database(settings.db_path)

    return db.get_records_by_canonical(canonical_name)


# Backward-compatible alias for existing callsites.
load_latest_market_snapshot = get_latest_snapshot
