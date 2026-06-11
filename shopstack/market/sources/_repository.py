"""MarketSnapshotRepository — caching and lifecycle for market snapshots.

Stores snapshots so the same data isn't re-parsed on every dashboard load,
and tracks freshness metadata so consumers know how current the data is.
"""

from __future__ import annotations

import logging
from typing import Any

from shopstack.market.schema import MarketSnapshot

logger = logging.getLogger(__name__)


class MarketSnapshotRepository:
    """In-memory snapshot cache with optional persistence.

    The default instance is process-scoped; pass a database to enable
    cross-session persistence.
    """

    def __init__(self, db=None):
        self._cache: dict[str, MarketSnapshot] = {}
        self._db: Any | None = db

    def store(self, snapshot: MarketSnapshot) -> None:
        self._cache[snapshot.snapshot_id] = snapshot
        if self._db is not None:
            self._persist(snapshot)

    def get(self, snapshot_id: str) -> MarketSnapshot | None:
        if not snapshot_id:
            return None
        if snapshot_id in self._cache:
            return self._cache[snapshot_id]
        if self._db is None:
            return None
        return self._load_snapshot_from_db(snapshot_id)

    def latest(self, source: str = "") -> MarketSnapshot | None:
        candidates = list(self._cache.values())

        if not source:
            if candidates:
                return max(candidates, key=lambda s: s.captured_at)
            return self._latest_snapshot_any()

        source = source.strip()
        candidates = [s for s in candidates if s.source == source]
        if candidates:
            return max(candidates, key=lambda s: s.captured_at)

        return self._latest_snapshot_from_db(source)

    def list(self, source: str = "") -> list[MarketSnapshot]:
        snapshots = list(self._cache.values())
        if source:
            snapshots = [s for s in snapshots if s.source == source]

        if self._db is None:
            snapshots.sort(key=lambda s: s.captured_at, reverse=True)
            return snapshots

        db_snapshots = self._list_snapshots_from_db(source=source)
        seen: set[str] = set()
        merged: list[MarketSnapshot] = []
        for snap in db_snapshots + snapshots:
            if snap.snapshot_id in seen:
                continue
            seen.add(snap.snapshot_id)
            merged.append(snap)

        merged.sort(key=lambda s: s.captured_at, reverse=True)
        return merged

    def clear(self, source: str = "") -> int:
        if source:
            keys = [k for k in self._cache if self._cache[k].source == source]
        else:
            keys = list(self._cache.keys())
        for k in keys:
            del self._cache[k]
        return len(keys)

    def _load_snapshot_from_db(self, snapshot_id: str) -> MarketSnapshot | None:
        try:
            snap = self._db.get_market_snapshot(snapshot_id)
        except Exception:
            return None
        if snap is None:
            return None
        self._cache[snap.snapshot_id] = snap
        return snap

    def _latest_snapshot_from_db(self, source: str | None = None) -> MarketSnapshot | None:
        if self._db is None:
            return None
        source = (source or "").strip()
        try:
            if source:
                row = self._db.conn.execute(
                    "SELECT snapshot_id FROM market_snapshots WHERE source = ? ORDER BY captured_at DESC LIMIT 1",
                    (source,),
                ).fetchone()
            else:
                row = self._db.conn.execute(
                    "SELECT snapshot_id FROM market_snapshots ORDER BY captured_at DESC LIMIT 1"
                ).fetchone()
        except Exception as exc:
            logger.warning("Failed to read latest snapshot from DB: %s", exc)
            return None
        if not row:
            return None
        return self._load_snapshot_from_db(row["snapshot_id"])

    def _latest_snapshot_any(self) -> MarketSnapshot | None:
        return self._latest_snapshot_from_db()

    def _list_snapshots_from_db(self, source: str = "") -> list[MarketSnapshot]:
        if self._db is None:
            return []
        try:
            if source:
                rows = self._db.conn.execute(
                    "SELECT snapshot_id FROM market_snapshots WHERE source = ? ORDER BY captured_at DESC",
                    (source,),
                ).fetchall()
            else:
                rows = self._db.conn.execute(
                    "SELECT snapshot_id FROM market_snapshots ORDER BY captured_at DESC"
                ).fetchall()
        except Exception as exc:
            logger.warning("Failed to list snapshots from DB: %s", exc)
            return []

        snapshots: list[MarketSnapshot] = []
        for row in rows:
            snap = self._load_snapshot_from_db(row["snapshot_id"])
            if snap is not None:
                snapshots.append(snap)
        return snapshots

    # Backward-compatible API retained for callers that imported `latest` directly.
    def latest_snapshot(self, source: str = "") -> MarketSnapshot | None:
        return self.latest(source)

    # Backward-compatible API retained for callers that imported `list` directly.
    def list_snapshots(self, source: str = "") -> list[MarketSnapshot]:
        return self.list(source)

    # Keep existing method names for compatibility with `build_registry` callers.
    def clear_cache(self, source: str = "") -> int:
        return self.clear(source)

    def get_cache_size(self) -> int:
        return len(self._cache)

    def _persist(self, snapshot: MarketSnapshot) -> None:
        if self._db is None:
            return
        try:
            self._db.save_market_snapshot(snapshot)
        except Exception as exc:
            logger.warning("Failed to persist snapshot %s: %s", snapshot.snapshot_id, exc)


def snapshot_freshness(snapshot: MarketSnapshot) -> dict[str, Any]:
    """Compute freshness metadata for any MarketSnapshot.

    Returns dict with:
      - age_days: int
      - is_stale: bool
      - label: str
      - captured_at: str
    """
    from datetime import date

    if not snapshot or not snapshot.captured_at:
        return {"age_days": 0, "is_stale": False, "label": "unknown"}

    try:
        captured = date.fromisoformat(snapshot.captured_at[:10])
        age = (date.today() - captured).days
    except (ValueError, TypeError):
        return {"age_days": 0, "is_stale": False, "label": "unknown"}

    is_stale = age > 1
    if age == 0:
        label = "Today's data"
    elif age == 1:
        label = "Yesterday's data"
    else:
        label = f"{age} days old"

    return {
        "age_days": age,
        "is_stale": is_stale,
        "label": label,
        "captured_at": snapshot.captured_at,
    }
