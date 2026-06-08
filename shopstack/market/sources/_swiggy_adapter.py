"""SwiggyAdapter — wraps Swiggy market source into MarketSourceAdapter protocol.

This adapter lets the source-agnostic registry (SourceRegistry) treat
Swiggy like any other market source. New sources (Blinkit, Zepto, DMart)
should create their own adapter in a separate module and register it.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from shopstack.market.schema import MarketSnapshot
from shopstack.market.sources._adapter import MarketSourceAdapter
from shopstack.market.analytics import available_canonical_names as _swiggy_available
from shopstack.market.sources.swiggy import (
    load_snapshot as _load_snapshot,
    snapshot_freshness as _snapshot_freshness,
    SOURCE_ID,
    SOURCE_CATEGORY,
)


class SwiggyAdapter(MarketSourceAdapter):
    """Adapter wrapping the existing Swiggy loader into the protocol."""

    source_id: str = SOURCE_ID
    source_category: str = SOURCE_CATEGORY

    def __init__(self, data_dir: Path | None = None):
        self._data_dir = data_dir

    def load_snapshot(self) -> MarketSnapshot:
        return _load_snapshot(data_dir=self._data_dir)

    def freshness(self, snapshot: MarketSnapshot) -> dict[str, Any]:
        return _snapshot_freshness(snapshot, today=date.today())

    def available_canonical_names(self, snapshot: MarketSnapshot) -> set[str]:
        return _swiggy_available(snapshot)


__all__ = ["SwiggyAdapter"]
