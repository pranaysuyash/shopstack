"""ShopStack — household shopping intelligence platform.

Public API surface:
- Domain layer: pure business logic (unit pricing, freshness, alerts, matching)
- Config: Settings, app_context singletons
"""

from __future__ import annotations

# Domain layer — zero-dependency business logic
from shopstack.domain import (
    # Unit pricing & normalization
    parse_size,
    compute_unit_prices,
    SizeParseResult,
    CANONICAL_MAP,
    ITEM_ALIASES,
    resolve_canonical,
    normalize_item_name,
    canonicalize_name,
    # Freshness classification
    classify_freshness,
    classify_snapshot_freshness,
    inventory_freshness_label,
    inventory_confidence,
    needs_confirmation,
    confirmation_prompt,
    FreshnessReport,
    # Inventory alerts
    classify_inventory_alert,
    InventoryAlert,
    AlertLevel,
    # Storage locations
    is_parent_of,
    get_location_hierarchy,
    LocationNode,
    # Product matching
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
