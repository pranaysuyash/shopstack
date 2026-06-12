from shopstack.services.shopping import (
    ShoppingPlan,
    classify_shopping_items,
    enrich_items_with_swiggy,
    normalize_item_name,
)
from shopstack.services.market_lens import MarketLensResult, analyze_market_lens
from shopstack.services.dashboard import DashboardState, build_dashboard_state
from shopstack.services.market_intelligence import (
    ReasonAtom,
    EvidenceClaim,
    TruthScoreBreakdown,
    GraphActionIntent,
    MarketGraphProjection,
    MarketTruthScore,
    MarketCluster,
    MarketIntelligenceGraph,
    project_today,
    project_unified_shopping,
    project_market_lens,
    project_ask_context,
    build_market_intelligence_graph,
)
from shopstack.services.search import SearchResult, semantic_search, build_item_embeddings
from shopstack.services.weather import WeatherState, get_weather, get_shopping_weather_recommendation
from shopstack.services.trip_context import TripAdvice, get_trip_advice, format_trip_advice_html
from shopstack.services.nutrition import (
    NutritionInfo,
    NutritionSummary,
    load_nutrition_reference,
    get_nutrition_info,
    get_inventory_nutrition_summary,
    format_nutrition_html,
)
from shopstack.services.receipt import ReceiptLine, ReceiptResult, parse_receipt_text, confirm_receipt
from shopstack.services.results import (
    CompletionItem,
    PurchaseResultItem,
    ShoppingCompletionResult,
    MarkPurchasedResult,
)
from shopstack.services.freshness import (
    FreshnessReport,
    classify_freshness,
    classify_snapshot_freshness,
    inventory_freshness_label,
)
from shopstack.services.decision_engine import (
    should_buy,
    should_skip,
    use_soon,
    compare_candidates,
    detect_stale_snapshot_warnings,
)
from shopstack.services.reconciliation import (
    ReconciliationResult,
    reconcile_shopping_trip,
    build_correction_event,
)
from shopstack.services.preference import (
    PreferenceService,
    build_preference_service,
)

__all__ = [
    # Shopping
    "ShoppingPlan",
    "classify_shopping_items",
    "enrich_items_with_swiggy",
    "normalize_item_name",
    # Market
    "MarketLensResult",
    "analyze_market_lens",
    # Dashboard
    "DashboardState",
    "build_dashboard_state",
    # Market intelligence graph
    "ReasonAtom",
    "EvidenceClaim",
    "TruthScoreBreakdown",
    "GraphActionIntent",
    "MarketGraphProjection",
    "MarketTruthScore",
    "MarketCluster",
    "MarketIntelligenceGraph",
    "project_today",
    "project_unified_shopping",
    "project_market_lens",
    "project_ask_context",
    "build_market_intelligence_graph",
    # Search
    "SearchResult",
    "semantic_search",
    "build_item_embeddings",
    # Weather / Trip
    "WeatherState",
    "get_weather",
    "get_shopping_weather_recommendation",
    "TripAdvice",
    "get_trip_advice",
    "format_trip_advice_html",
    # Nutrition
    "NutritionInfo",
    "NutritionSummary",
    "load_nutrition_reference",
    "get_nutrition_info",
    "get_inventory_nutrition_summary",
    "format_nutrition_html",
    # Receipt
    "ReceiptLine",
    "ReceiptResult",
    "parse_receipt_text",
    "confirm_receipt",
    # Results
    "CompletionItem",
    "PurchaseResultItem",
    "ShoppingCompletionResult",
    "MarkPurchasedResult",
    # Data freshness
    "FreshnessReport",
    "classify_freshness",
    "classify_snapshot_freshness",
    "inventory_freshness_label",
    # Decision engine
    "should_buy",
    "should_skip",
    "use_soon",
    "compare_candidates",
    "detect_stale_snapshot_warnings",
    # Reconciliation
    "ReconciliationResult",
    "reconcile_shopping_trip",
    "build_correction_event",
    # Preference
    "PreferenceService",
    "build_preference_service",
]
