from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from shopstack.decisions import DecisionSet, classify_all, detect_purchase_cadence, detect_waste_patterns
from shopstack.persistence.database import Database
from shopstack.services.weather import WeatherState, get_weather
from shopstack.tools.registry import ToolRegistry
from shopstack.ui.renderers.decision_cards import render_cadence_insights, render_waste_warnings

logger = logging.getLogger(__name__)


@dataclass
class DashboardState:
    decision_set: DecisionSet
    market_snapshot: Any | None
    use_soon: dict[str, Any]
    active_list: Any | None
    all_inventory: list[Any] = field(default_factory=list)
    active_inventory: list[Any] = field(default_factory=list)
    low_items: list[Any] = field(default_factory=list)
    recent_purchases: list[Any] = field(default_factory=list)
    cadence_html: str = ""
    waste_html: str = ""
    weather: WeatherState | None = None
    weather_html: str = ""

    @property
    def use_soon_count(self) -> int:
        return int(self.use_soon.get("count", len(self.use_soon.get("items", []))))

    @property
    def use_soon_items(self) -> list[dict[str, Any]]:
        return list(self.use_soon.get("items", []))


def build_dashboard_state(db: Database, tools: ToolRegistry, city: str = "mumbai") -> DashboardState:
    """Assemble the Today dashboard state from inventory, decisions, market data, and weather."""
    market_input = _load_market_snapshot()
    # _load_market_snapshot returns (snapshot, registry) or (None, None)
    market_snapshot, source_registry = market_input if isinstance(market_input, tuple) else (market_input, None)
    decision_set = classify_all(db, tools, market_snapshot=market_snapshot, source_registry=source_registry)
    use_soon = tools.get_use_soon_items(days=3)
    active_list = db.get_active_shopping_list()
    all_inventory = db.get_inventory()
    active_inventory = [lot for lot in all_inventory if lot.status == "active"]
    low_items = [lot for lot in active_inventory if lot.quantity <= 0.5 or lot.status == "low"]
    recent_purchases = db.get_purchase_events(limit=5)

    cadence_data = detect_purchase_cadence(db)
    cadence_html = render_cadence_insights(cadence_data)

    waste_data = detect_waste_patterns(db)
    waste_html = render_waste_warnings(waste_data)

    weather = None
    weather_html = ""
    try:
        from shopstack.services.trip_context import render_weather_card
        weather = get_weather(city)
        weather_html = render_weather_card(weather)
    except Exception as exc:
        logger.info("Weather unavailable for dashboard: %s", exc)

    return DashboardState(
        decision_set=decision_set,
        market_snapshot=market_snapshot,
        use_soon=use_soon,
        active_list=active_list,
        all_inventory=all_inventory,
        active_inventory=active_inventory,
        low_items=low_items,
        recent_purchases=recent_purchases,
        cadence_html=cadence_html,
        waste_html=waste_html,
        weather=weather,
        weather_html=weather_html,
    )


def _load_market_snapshot():
    """Load market snapshot(s) — prefers multi-source registry, falls back to Swiggy-only."""
    try:
        from shopstack.market.sources import build_registry
        registry = build_registry()
        snapshots = registry.all_snapshots()
        if snapshots:
            # Return first available snapshot + registry for multi-source
            return (list(snapshots.values())[0], registry)
    except Exception as exc:
        logger.debug("Multi-source registry not available: %s", exc)

    # Fallback: single Swiggy snapshot
    try:
        from shopstack.market.sources.swiggy import load_snapshot
        return (load_snapshot(), None)
    except Exception as exc:
        logger.info("Swiggy market data unavailable: %s", exc)
        return None, None


