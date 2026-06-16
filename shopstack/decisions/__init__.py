from shopstack.decisions.types import (
    Decision,
    DECISION_COLORS,
    DECISION_ICONS,
    ACTION_MAP,
)
from shopstack.schemas.models import (
    DecisionEvidence,
    DecisionResult,
    DecisionSet,
    DecisionWarning,
    FreshnessStatus,
)
from shopstack.decisions.rules import (
    classify_all,
    _classify,
    _get_produce_meta,
    detect_purchase_cadence,
    detect_waste_patterns,
    check_swiggy_availability,
)

_RENDER_NAMES = {
    "render_market_basket",
    "render_inventory_overview",
    "render_my_list_panel",
    "render_compare_panel",
    "render_decision_panel",
}

# 2026-06-15 (Pass 18): _LEGACY_NAMES routing REMOVED.
# The legacy shim ``shopstack._legacy_decisions`` was deleted in
# this pass. Any caller that imports the 5 legacy functions via
# ``shopstack.decisions`` now raises AttributeError. This is
# the durable first-principles fix: removing the shim eliminates
# the dual-source-of-truth that the reversion pattern was
# exploiting. Callers must use the canonical path:
#   from shopstack.ui.renderers.decision_cards import render_*
# (or from shopstack.ui.renderers for the 5 _RENDER_NAMES). See
# tests/test_decisions_canonical_only.py for the regression test
# that pins this contract.


def __getattr__(name: str):
    """Lazy re-exports for the canonical renderers (decision_cards + ui.renderers).

    New code should import directly from ``shopstack.ui.renderers``
    or ``shopstack.ui.renderers.decision_cards``. This ``__getattr__``
    exists for backward-compat with code that historically imported
    from ``shopstack.decisions``. The legacy 5-function shim was
    deleted in Pass 18 — see the regression test in
    ``tests/test_decisions_canonical_only.py`` for the contract.

    The ``__getattr__`` avoids a circular import: decisions →
    renderers → decisions that would otherwise crash when any
    code path triggers both packages.
    """
    if name in _RENDER_NAMES:
        import shopstack.ui.renderers as _r
        return getattr(_r, name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "Decision",
    "DECISION_COLORS",
    "DECISION_ICONS",
    "ACTION_MAP",
    "DecisionEvidence",
    "DecisionResult",
    "DecisionSet",
    "DecisionWarning",
    "FreshnessStatus",
    "classify_all",
    "_classify",
    "_get_produce_meta",
    "detect_purchase_cadence",
    "detect_waste_patterns",
    "check_swiggy_availability",
    "render_market_basket",
    "render_inventory_overview",
    "render_my_list_panel",
    "render_compare_panel",
    "render_decision_panel",
]
