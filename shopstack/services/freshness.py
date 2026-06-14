"""Data freshness service — delegates to shopstack.domain.market_freshness.

All pure business logic for freshness classification, inventory confidence,
and confirmation prompts now lives in ``shopstack.domain.market_freshness``.

This module is a thin re-export shim for backward compatibility.
New code should import from ``shopstack.domain`` or ``shopstack.domain.market_freshness``.
"""

from __future__ import annotations

import warnings
from datetime import date

from shopstack.domain.market_freshness import (
    FreshnessReport as FreshnessReport,
    classify_freshness as classify_freshness,
    classify_snapshot_freshness as classify_snapshot_freshness,
    confirmation_prompt as confirmation_prompt,
    inventory_confidence as inventory_confidence,
    inventory_freshness_label as inventory_freshness_label,
    needs_confirmation as needs_confirmation,
)

__all__ = [
    "FreshnessReport",
    "classify_freshness",
    "classify_snapshot_freshness",
    "inventory_freshness_label",
    "inventory_confidence",
    "needs_confirmation",
    "confirmation_prompt",
]

# Emit deprecation warning only when this module is imported directly
# (the first import triggers it, subsequent imports from services/__init__
#  are cached and won't re-trigger the warning).
warnings.warn(
    "shopstack.services.freshness is deprecated. "
    "Import from shopstack.domain.market_freshness or shopstack.domain instead.",
    DeprecationWarning,
    stacklevel=2,
)
