"""MarketSourceAdapter — protocol for pluggable market data sources.

Every source (Swiggy, Blinkit, Zepto, DMart, etc.) implements this protocol
so the decision engine and basket optimizer can work with any source uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from shopstack.market.schema import MarketSnapshot


class MarketSourceError(Exception):
    pass


@runtime_checkable
class MarketSourceAdapter(Protocol):
    """Protocol each market source must satisfy.

    A market source is anything that can produce a MarketSnapshot:
    an API client, a CSV file reader, a web scraper, etc.
    """

    source_id: str
    source_category: str

    def load_snapshot(self) -> MarketSnapshot:
        """Load the latest snapshot from this source.

        Returns a fully normalized MarketSnapshot ready for analytics.
        Raises MarketSourceError on failure.
        """
        ...

    def freshness(self, snapshot: MarketSnapshot) -> dict[str, Any]:
        """Return freshness metadata for a snapshot from this source.

        Returns dict with keys:
          - age_days: int
          - is_stale: bool
          - label: str (human-readable freshness description)
          - captured_at: str
        """
        ...

    def available_canonical_names(self, snapshot: MarketSnapshot) -> set[str]:
        """Return the set of canonical names available in this snapshot."""
        ...


@dataclass
class SourceMetadata:
    """Persisted metadata about a market source and its snapshots."""

    source_id: str
    source_category: str
    last_snapshot_id: str = ""
    last_captured_at: str = ""
    snapshot_count: int = 0
    total_records: int = 0
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def now(cls) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
