"""SourceRegistry — pluggable registry of market source adapters.

New sources (Blinkit, Zepto, DMart, etc.) are registered once at startup.
All service-level code resolves market data through this registry, never
by importing a specific source directly.
"""

from __future__ import annotations

import logging
from typing import Any

from shopstack.market.schema import MarketSnapshot
from shopstack.market.sources._adapter import MarketSourceAdapter
from shopstack.market.sources._repository import MarketSnapshotRepository

logger = logging.getLogger(__name__)


class SourceRegistry:
    """Registry of available market source adapters.

    Usage::

        registry = SourceRegistry()
        registry.register("swiggy", SwiggyAdapter())

        # Load from a specific source
        snap = registry.load("swiggy")

        # Or discover sources for a category
        for source in registry.for_category("fresh_vegetables"):
            snap = registry.load(source.source_id)

    """

    def __init__(self, repository: MarketSnapshotRepository | None = None):
        self._adapters: dict[str, MarketSourceAdapter] = {}
        self._repository = repository or MarketSnapshotRepository()

    def register(self, source_id: str, adapter: MarketSourceAdapter) -> None:
        if not isinstance(adapter, MarketSourceAdapter):
            logger.warning(
                "Adapter for %s does not satisfy MarketSourceAdapter protocol",
                source_id,
            )
        self._adapters[source_id] = adapter
        logger.info("Registered market source: %s (%s)", source_id, adapter.source_category)

    def registered(self) -> list[str]:
        return list(self._adapters.keys())

    def get(self, source_id: str) -> MarketSourceAdapter:
        adapter = self._adapters.get(source_id)
        if adapter is None:
            raise KeyError(f"Unknown market source: {source_id}. Registered: {list(self._adapters)}")
        return adapter

    def load(self, source_id: str) -> MarketSnapshot:
        adapter = self.get(source_id)
        snapshot = adapter.load_snapshot()
        self._repository.store(snapshot)
        return snapshot

    def load_all(self, force: bool = False) -> list[tuple[str, MarketSnapshot]]:
        """Load snapshots for all registered adapters.

        - `force=False`: load only when cache / DB has no entry for source.
        - `force=True`: always refresh each source.
        """
        loaded: list[tuple[str, MarketSnapshot]] = []
        for source_id, adapter in list(self._adapters.items()):
            try:
                snapshot = self._repository.latest(source_id) if not force else None
                if snapshot is None:
                    snapshot = self.load(source_id)
                if snapshot is not None:
                    loaded.append((source_id, snapshot))
            except Exception as exc:
                logger.warning("Failed to load market source %s: %s", source_id, exc)
                continue
        return loaded

    def latest(self, source: str) -> MarketSnapshot | None:
        return self._repository.latest(source)

    def all_sources_latest(self) -> dict[str, MarketSnapshot]:
        return self.all_snapshots()

    def for_category(self, category: str) -> list[MarketSourceAdapter]:
        return [a for a in self._adapters.values() if a.source_category == category]

    def all_snapshots(self) -> dict[str, MarketSnapshot]:
        result: dict[str, MarketSnapshot] = {}
        for sid in self._adapters:
            snap = self._repository.latest(sid)
            if snap is not None:
                result[sid] = snap
        return result

    def freshness_of(self, source_id: str) -> dict[str, Any]:
        snap = self._repository.latest(source_id)
        if snap is None:
            return {"source_id": source_id, "is_stale": True, "label": "No snapshot loaded"}
        adapter = self.get(source_id)
        return adapter.freshness(snap)

    @property
    def repository(self) -> MarketSnapshotRepository:
        return self._repository
