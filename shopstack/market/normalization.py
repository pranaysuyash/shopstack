"""Market product normalization — canonical names, aliases, size parsing.

DELEGATION LAYER: All public symbols delegate to shopstack.domain.unit_price,
which is the canonical implementation. This module exists for backward
compatibility and will be removed after all callers have migrated.

See shopstack/domain/unit_price.py for the canonical implementations.
"""

from __future__ import annotations

from shopstack.domain.unit_price import (
    CANONICAL_MAP,
    ITEM_ALIASES,
    SizeParseResult,
    canonicalize_name,
    compute_unit_prices,
    normalize_item_name,
    parse_size,
    resolve_canonical,
)

__all__ = [
    "CANONICAL_MAP",
    "ITEM_ALIASES",
    "SizeParseResult",
    "canonicalize_name",
    "compute_unit_prices",
    "normalize_item_name",
    "parse_size",
    "resolve_canonical",
]
