"""Domain layer — pure business logic, no external dependencies.

This package extracts canonical business rules from services/UI into
testable, reusable pure functions. Each module has zero imports from
shopstack.services, shopstack.ui, or shopstack.persistence.

Supersedes scattered logic in:
- shopstack/market/normalization.py (unit price, canonical maps)
- shopstack/services/freshness.py (freshness classification)
- shopstack/services/dashboard.py (inventory alerts)
- shopstack/ui/screens/other.py (location hierarchy)
- shopstack/decisions/rules.py (decision predicates, partially)
"""

from __future__ import annotations

from .unit_price import (
    parse_size,
    compute_unit_prices,
    SizeParseResult,
    CANONICAL_MAP,
    ITEM_ALIASES,
    resolve_canonical,
    normalize_item_name,
    canonicalize_name,
)
from .market_freshness import (
    classify_freshness,
    classify_snapshot_freshness,
    inventory_freshness_label,
    inventory_confidence,
    needs_confirmation,
    confirmation_prompt,
    FreshnessReport,
)
from .inventory_alerts import (
    classify_inventory_alert,
    InventoryAlert,
    AlertLevel,
)
from .storage_locations import (
    is_parent_of,
    get_location_hierarchy,
    LocationNode,
)
from .product_matching import (
    score_product_match,
    MatchScore,
    MatchReason,
)

__all__ = [
    # unit_price
    "parse_size",
    "compute_unit_prices",
    "SizeParseResult",
    "CANONICAL_MAP",
    "ITEM_ALIASES",
    "resolve_canonical",
    "normalize_item_name",
    "canonicalize_name",
    # market_freshness
    "classify_freshness",
    "classify_snapshot_freshness",
    "inventory_freshness_label",
    "inventory_confidence",
    "needs_confirmation",
    "confirmation_prompt",
    "FreshnessReport",
    # inventory_alerts
    "classify_inventory_alert",
    "InventoryAlert",
    "AlertLevel",
    # storage_locations
    "is_parent_of",
    "get_location_hierarchy",
    "LocationNode",
    # product_matching
    "score_product_match",
    "MatchScore",
    "MatchReason",
]