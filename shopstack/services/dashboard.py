from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from shopstack.decisions import DecisionSet, classify_all, detect_purchase_cadence, detect_waste_patterns
from shopstack.persistence.database import Database
from shopstack.services.weather import WeatherState, get_weather

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
    cadence_data: dict[str, dict[str, Any]] = field(default_factory=dict)
    waste_data: list[dict[str, Any]] = field(default_factory=list)
    weather: WeatherState | None = None

    @property
    def use_soon_count(self) -> int:
        return int(self.use_soon.get("count", len(self.use_soon.get("items", []))))

    @property
    def use_soon_items(self) -> list[dict[str, Any]]:
        return list(self.use_soon.get("items", []))


def build_dashboard_state(db: Database, inventory, city: str = "mumbai") -> DashboardState:
    """Assemble the Today dashboard state from inventory, decisions, market data, and weather."""
    market_input = _load_market_snapshot(db)
    # _load_market_snapshot returns (snapshot, registry) or (None, None)
    market_snapshot, source_registry = market_input if isinstance(market_input, tuple) else (market_input, None)
    decision_set = classify_all(db, inventory, market_snapshot=market_snapshot, source_registry=source_registry)
    use_soon = inventory.get_use_soon(days=3) if hasattr(inventory, "get_use_soon") else inventory.get_use_soon_items(days=3)
    active_list = db.get_active_shopping_list()
    all_inventory = db.get_inventory()
    active_inventory = [lot for lot in all_inventory if lot.status == "active"]
    low_items = [lot for lot in active_inventory if lot.quantity <= 0.5 or lot.status == "low"]
    recent_purchases = db.get_purchase_events(limit=5)

    cadence_data = detect_purchase_cadence(db)
    waste_data = detect_waste_patterns(db)

    weather: WeatherState | None = None
    try:
        weather = get_weather(city)
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
        cadence_data=cadence_data,
        waste_data=waste_data,
        weather=weather,
    )


def _load_market_snapshot(db: Database):
    """Load market snapshot(s) — prefers multi-source registry, falls back to Swiggy-only."""
    from shopstack.services.market_sources import load_market_registry

    try:
        registry, _ = load_market_registry(db=db, force=False)
        snapshots = registry.all_snapshots()
        if snapshots:
            latest = max(snapshots.values(), key=lambda snap: snap.captured_at)
            return (latest, registry)
        if registry.registered():
            return (None, registry)
    except Exception as exc:
        logger.debug("Market registry load failed: %s", exc)

    return None, None
