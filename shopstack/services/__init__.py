from shopstack.services.shopping import (
    ShoppingPlan,
    classify_shopping_items,
    enrich_items_with_swiggy,
    normalize_item_name,
)
from shopstack.services.market_lens import MarketLensResult, analyze_market_lens
from shopstack.services.dashboard import DashboardState, build_dashboard_state
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

__all__ = [
    "ShoppingPlan",
    "classify_shopping_items",
    "enrich_items_with_swiggy",
    "normalize_item_name",
    "MarketLensResult",
    "analyze_market_lens",
    "DashboardState",
    "build_dashboard_state",
    "SearchResult",
    "semantic_search",
    "build_item_embeddings",
    "WeatherState",
    "get_weather",
    "get_shopping_weather_recommendation",
    "TripAdvice",
    "get_trip_advice",
    "format_trip_advice_html",
    "NutritionInfo",
    "NutritionSummary",
    "load_nutrition_reference",
    "get_nutrition_info",
    "get_inventory_nutrition_summary",
    "format_nutrition_html",
    "ReceiptLine",
    "ReceiptResult",
    "parse_receipt_text",
    "confirm_receipt",
    "CompletionItem",
    "PurchaseResultItem",
    "ShoppingCompletionResult",
    "MarkPurchasedResult",
]
