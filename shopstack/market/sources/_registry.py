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
        for source in self.for_category("fresh_vegetables"):
            snap = registry.load(source.source_id)

    """

    def __init__(self, repository: MarketSnapshotRepository | None = None):
        self._adapters: dict[str, MarketSourceAdapter] = {}
        self._repository = repository or MarketSnapshotRepository()
        # Track sources whose data we have already logged-about as
        # missing on a previous load. Prevents per-boot log spam
        # when Blinkit / Zepto / DMart data fixtures aren't on disk
        # (the adapters are registered but the data isn't shipped).
        # Additive (2026-06-15): no existing call site changes.
        self._known_missing: set[str] = set()

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

    def load_all(self, timeout_per_source: float = 5.0) -> dict[str, MarketSnapshot]:
        """Load snapshots for all registered adapters actively.

        Iterates registered adapters, loads each, and returns a dictionary
        mapping source_id to MarketSnapshot. Failures are logged ONCE
        per source per registry lifetime (subsequent failures are
        silent) and skipped. Sources that have no data fixture on
        disk produce a single debug-level message and are added to
        ``self._known_missing`` so the UI can show them as
        "available but not loaded" rather than as errors.
        """
        import concurrent.futures
        loaded: dict[str, MarketSnapshot] = {}
        for source_id in list(self._adapters.keys()):
            # If we already know this source is missing (e.g. its
            # data fixture isn't shipped), skip the load entirely
            # to avoid per-boot log spam and per-boot latency.
            if source_id in self._known_missing:
                continue
            try:
                # Only load if not already in the repository/cache to avoid duplicate overhead
                snapshot = self._repository.latest(source_id)
                if snapshot is not None:
                    loaded[source_id] = snapshot
                    continue

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(self.load, source_id)
                    snapshot = future.result(timeout=timeout_per_source)
                if snapshot is not None:
                    loaded[source_id] = snapshot
            except FileNotFoundError as exc:
                # Expected when a data fixture isn't shipped.
                # Log at debug level (not warning) and remember.
                if source_id not in self._known_missing:
                    logger.debug(
                        "No data fixture for market source %s: %s",
                        source_id, exc,
                    )
                    self._known_missing.add(source_id)
                continue
            except Exception as exc:
                # Real error — log once at warning level.
                if source_id not in self._known_missing:
                    logger.warning(
                        "Failed to actively load market source %s: %s",
                        source_id, exc,
                    )
                    self._known_missing.add(source_id)
                continue
        return loaded

    def get_missing_sources(self) -> list[str]:
        """Return the list of registered source_ids that have no
        data fixture on disk.

        The UI uses this to render a "available but not loaded" hint
        in the market intelligence panel. Updated on each
        ``load_all`` call.
        """
        return sorted(self._known_missing)

    def get_available_sources(self) -> list[str]:
        """Return the list of registered source_ids that have data
        loaded. Inverse of ``get_missing_sources``.
        """
        missing = set(self._known_missing)
        return sorted(s for s in self._adapters.keys() if s not in missing)

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
            return {
                "source_id": source_id,
                "is_stale": True,
                "label": "No snapshot loaded yet — import a snapshot to start comparing prices.",
            }
        adapter = self.get(source_id)
        return adapter.freshness(snap)

    @property
    def repository(self) -> MarketSnapshotRepository:
        return self._repository
