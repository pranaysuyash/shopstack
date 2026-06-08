"""Market source abstraction — adapters and repository for market data sources.

This package defines the MarketSourceAdapter protocol that every market data
source (Swiggy, Blinkit, Zepto, DMart, etc.) must implement, plus a
MarketSnapshotRepository for caching and storing snapshots.

New sources register via SourceRegistry::

    from shopstack.market.sources import SourceRegistry, build_registry

    registry = build_registry()  # registers all available sources
    snapshot = registry.load("swiggy")
"""

from __future__ import annotations

import logging
from pathlib import Path

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

logger = logging.getLogger(__name__)


def build_registry(repository: MarketSnapshotRepository | None = None, data_dir: Path | None = None) -> SourceRegistry:
    """Construct a fully-populated SourceRegistry with all available market sources.

    Each adapter is constructed inside a try/except so that any adapter init failure
    doesn't prevent the registry from being built — failures simply log a warning.
    Missing data files are handled gracefully at load_snapshot() time.
    """
    registry = SourceRegistry(repository=repository)

    sources: list[tuple[str, MarketSourceAdapter]] = []

    for adapter_cls, source_id in [
        (SwiggyAdapter, "swiggy"),
        (BlinkitAdapter, "blinkit"),
        (ZeptoAdapter, "zepto"),
        (DmartAdapter, "dmart"),
    ]:
        try:
            adapter = adapter_cls(data_dir=data_dir)
            sources.append((source_id, adapter))
        except Exception as exc:
            logger.warning("Failed to create adapter %s: %s", source_id, exc)

    for source_id, adapter in sources:
        registry.register(source_id, adapter)

    return registry


__all__ = [
    "MarketSourceAdapter",
    "MarketSourceError",
    "MarketSnapshotRepository",
    "SourceRegistry",
    "build_registry",
    "SwiggyAdapter",
    "BlinkitAdapter",
    "ZeptoAdapter",
    "DmartAdapter",
    "CrossSourcePrice",
    "compare_across_sources",
    "format_cross_source_html",
    "snapshot_freshness",
]
