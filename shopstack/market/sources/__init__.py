"""Market source abstraction — adapters and repository for market data sources.

This package defines the MarketSourceAdapter protocol that every market data
source (Swiggy, Blinkit, Zepto, DMart, etc.) must implement, plus a
MarketSnapshotRepository for caching and storing snapshots.

New sources register via SourceRegistry::

    from shopstack.market.sources import SourceRegistry, SwiggyAdapter

    registry = SourceRegistry()
    registry.register("swiggy", SwiggyAdapter())
    snapshot = registry.load("swiggy")
"""

from __future__ import annotations

from shopstack.market.sources._adapter import MarketSourceAdapter, MarketSourceError
from shopstack.market.sources._registry import SourceRegistry
from shopstack.market.sources._repository import MarketSnapshotRepository, snapshot_freshness
from shopstack.market.sources._swiggy_adapter import SwiggyAdapter
from shopstack.market.sources._blinkit_adapter import BlinkitAdapter
from shopstack.market.sources._zepto_adapter import ZeptoAdapter
from shopstack.market.sources._dmart_adapter import DmartAdapter
from shopstack.market.sources._comparison import (
    CrossSourcePrice,
    compare_across_sources,
    format_cross_source_html,
)

__all__ = [
    "MarketSourceAdapter",
    "MarketSourceError",
    "MarketSnapshotRepository",
    "SourceRegistry",
    "SwiggyAdapter",
    "BlinkitAdapter",
    "ZeptoAdapter",
    "DmartAdapter",
    "CrossSourcePrice",
    "compare_across_sources",
    "format_cross_source_html",
    "snapshot_freshness",
]
