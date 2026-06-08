from shopstack.decisions.types import (
    Decision,
    DECISION_COLORS,
    DECISION_ICONS,
    ItemDecision,
    DecisionSet,
    Reason,
    Evidence,
    MarketEvidence,
)
from shopstack.decisions.rules import (
    classify_all,
    _classify,
    _get_produce_meta,
    detect_purchase_cadence,
    detect_waste_patterns,
    check_swiggy_availability,
)

# Backward-compatible render wrappers — new code should import
# directly from shopstack.ui.renderers.decision_cards.
from shopstack.ui.renderers import (
    render_market_basket,
    render_inventory_overview,
    render_my_list_panel,
    render_compare_panel,
    render_decision_panel,
)

# Db-dependent wrappers (fetch data then delegate to renderers):
from shopstack._legacy_decisions import (
    render_what_changed,
    render_cadence_insights,
    render_waste_warnings,
    render_swiggy_soldout_warning,
    render_needs_confirmation,
    _badge_html,
)

ItemDecision.badge_html = _badge_html

__all__ = [
    "Decision",
    "DECISION_COLORS",
    "DECISION_ICONS",
    "ItemDecision",
    "DecisionSet",
    "Reason",
    "Evidence",
    "MarketEvidence",
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
