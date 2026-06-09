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
_LEGACY_NAMES = {
    "render_what_changed",
    "render_cadence_insights",
    "render_waste_warnings",
    "render_swiggy_soldout_warning",
    "render_needs_confirmation",
}


def __getattr__(name: str):
    """Lazy re-exports for backward-compatible render wrappers.

    New code should import directly from shopstack.ui.renderers.decision_cards
    or shopstack._legacy_decisions.

    This __getattr__ avoids a circular import: decisions → renderers → decisions
    that would otherwise crash when any code path triggers both packages.
    """
    if name in _RENDER_NAMES:
        import shopstack.ui.renderers as _r
        return getattr(_r, name)
    if name in _LEGACY_NAMES:
        import shopstack._legacy_decisions as _l
        return getattr(_l, name)
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
    "render_what_changed",
    "render_cadence_insights",
    "render_waste_warnings",
    "render_swiggy_soldout_warning",
    "render_needs_confirmation",
]
