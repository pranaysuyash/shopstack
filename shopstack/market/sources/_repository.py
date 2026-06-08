"""MarketSnapshotRepository — caching and lifecycle for market snapshots.

Stores snapshots so the same data isn't re-parsed on every dashboard load,
and tracks freshness metadata so consumers know how current the data is.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
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
        return self._cache.get(snapshot_id)

    def latest(self, source: str = "") -> MarketSnapshot | None:
        candidates = [
            s for s in self._cache.values()
            if not source or s.source == source
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda s: s.captured_at)

    def list(self, source: str = "") -> list[MarketSnapshot]:
        snapshots = list(self._cache.values())
        if source:
            snapshots = [s for s in snapshots if s.source == source]
        snapshots.sort(key=lambda s: s.captured_at, reverse=True)
        return snapshots

    def clear(self, source: str = "") -> int:
        if source:
            keys = [k for k in self._cache if self._cache[k].source == source]
        else:
            keys = list(self._cache.keys())
        for k in keys:
            del self._cache[k]
        return len(keys)

    def _persist(self, snapshot: MarketSnapshot) -> None:
        if self._db is None:
            return
        try:
            table = """
                CREATE TABLE IF NOT EXISTS market_snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    source TEXT,
                    source_category TEXT,
                    captured_at TEXT,
                    analytics TEXT,
                    record_count INTEGER,
                    stored_at TEXT
                )
            """
            self._db.conn.execute(table)
            self._db.conn.execute(
                """INSERT OR REPLACE INTO market_snapshots
                   (snapshot_id, source, source_category, captured_at, analytics, record_count, stored_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot.snapshot_id,
                    snapshot.source,
                    snapshot.source_category or "",
                    snapshot.captured_at,
                    json.dumps(snapshot.analytics) if snapshot.analytics else "{}",
                    len(snapshot.normalized_records),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            self._db.conn.commit()
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
