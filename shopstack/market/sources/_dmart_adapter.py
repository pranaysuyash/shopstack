"""DMart market source adapter — thin config over shared JSON adapter."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from shopstack.market.schema import MarketSnapshot
from shopstack.market.sources._adapter import MarketSourceAdapter
from shopstack.market.sources._json_adapter import (
    JsonSourceConfig,
    _normalize_record_shared,
    _load_raw_json,
    snapshot_freshness,
    load_snapshot as _shared_load_snapshot,
)

SOURCE_ID = "dmart"
SOURCE_CATEGORY = "fresh_vegetables"
DEFAULT_SNAPSHOT_ID = f"{SOURCE_ID}_{SOURCE_CATEGORY}_2026-06-06"
DEFAULT_CAPTURED_AT = "2026-06-06"

CONFIG = JsonSourceConfig(
    source_id=SOURCE_ID,
    source_category=SOURCE_CATEGORY,
    file_glob="dmart_fresh_vegetables_*.json",
    name_field="product",
    price_field="current_price",
    original_price_field="listed_price",
)


def load_raw(data_dir: Path | None = None):
    return _load_raw_json(CONFIG.file_glob, data_dir)


def load_snapshot(
    data_dir: Path | None = None,
    snapshot_id: str | None = None,
    captured_at: str | None = None,
):
    return _shared_load_snapshot(CONFIG, data_dir=data_dir, snapshot_id=snapshot_id, captured_at=captured_at)


def normalize_record(
    raw: dict[str, Any],
    snapshot_id: str = DEFAULT_SNAPSHOT_ID,
    captured_at: str = DEFAULT_CAPTURED_AT,
) -> Any:
    from dataclasses import replace
    cfg = replace(CONFIG, captured_at=captured_at)
    return _normalize_record_shared(raw, cfg)


class DmartAdapter(MarketSourceAdapter):
    source_id: str = SOURCE_ID
    source_category: str = SOURCE_CATEGORY

    def __init__(self, data_dir: Path | None = None):
        self._data_dir = data_dir

    def load_snapshot(self) -> MarketSnapshot:
        return _shared_load_snapshot(CONFIG, data_dir=self._data_dir)

    def freshness(self, snapshot: MarketSnapshot) -> dict[str, Any]:
        return snapshot_freshness(snapshot, today=date.today())

    def available_canonical_names(self, snapshot: MarketSnapshot) -> set[str]:
        from shopstack.market.analytics import available_canonical_names as _available
        return _available(snapshot)


__all__ = [
    "DmartAdapter",
    "CONFIG",
    "DEFAULT_CAPTURED_AT",
    "DEFAULT_SNAPSHOT_ID",
    "SOURCE_ID",
    "load_raw",
    "load_snapshot",
    "normalize_record",
    "snapshot_freshness",
]
