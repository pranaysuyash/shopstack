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
    price_deals: list[dict[str, Any]] = field(default_factory=list)
    price_drops: list[dict[str, Any]] = field(default_factory=list)
    best_store: dict[str, Any] = field(default_factory=dict)
    optimized_basket: Any | None = None
    restock_predictions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def use_soon_count(self) -> int:
        return int(self.use_soon.get("count", len(self.use_soon.get("items", []))))

    @property
    def use_soon_items(self) -> list[dict[str, Any]]:
        return list(self.use_soon.get("items", []))


def build_dashboard_state(db: Database, inventory, city: str = "mumbai", user_id: str = "") -> DashboardState:
    """Assemble the Today dashboard state from inventory, decisions, market data, and weather."""
    market_input = _load_market_snapshot(db)
    # _load_market_snapshot returns (snapshot, registry) or (None, None)
    market_snapshot, source_registry = market_input if isinstance(market_input, tuple) else (market_input, None)
    decision_set = classify_all(
        db,
        inventory,
        market_snapshot=market_snapshot,
        source_registry=source_registry,
        user_id=user_id,
    )
    use_soon = inventory.get_use_soon(days=3, user_id=user_id) if hasattr(inventory, "get_use_soon") else inventory.get_use_soon_items(days=3)
    active_list = db.get_active_shopping_list(user_id=user_id)
    all_inventory = db.get_inventory(user_id=user_id)
    active_inventory = [lot for lot in all_inventory if lot.status == "active"]
    low_items = [lot for lot in active_inventory if lot.quantity <= 0.5 or lot.status == "low"]
    recent_purchases = db.get_purchase_events(limit=5, user_id=user_id)

    cadence_data = detect_purchase_cadence(db, user_id=user_id)
    waste_data = detect_waste_patterns(db, user_id=user_id)

    weather: WeatherState | None = None
    try:
        weather = get_weather(city)
    except Exception as exc:
        logger.info("Weather unavailable for dashboard: %s", exc)

    # Price memory enrichment — deal scores for buy items
    price_deals: list[dict[str, Any]] = []
    best_store: dict[str, Any] = {}
    try:
        from shopstack.services.price_memory import PriceMemoryService
        pm = PriceMemoryService(db)
        buy_names = [d.canonical_name for d in decision_set.buy]
        for name in buy_names:
            summary = pm.get_summary(name)
            if summary.last_price and summary.median_price and summary.observations >= 2:
                deal = pm.score_deal(name, summary.last_price, per_kg=summary.normalized_per_kg)
                price_deals.append(deal.__dict__ if hasattr(deal, '__dict__') else {"product": name, "score": deal.score, "reason": deal.reason})
        if len(buy_names) >= 2:
            bs = pm.get_best_store(buy_names)
            best_store = bs.__dict__ if hasattr(bs, '__dict__') else {}
    except Exception as exc:
        logger.debug("Price memory enrichment failed: %s", exc)

    # Build optimized basket if active list and market snapshot are present
    optimized_basket = None
    if active_list and market_snapshot:
        try:
            from shopstack.market.basket import build_optimized_basket
            from shopstack.services.preference import PreferenceService
            pref_service = PreferenceService(db)
            avoid_list = list(pref_service.get_avoid_list(user_id=user_id))
            
            requested_items = [
                {
                    "canonical_name": item.canonical_name,
                    "requested_quantity": item.requested_quantity,
                    "unit": item.unit,
                }
                for item in active_list.items
            ]
            inv_map = {}
            for lot in active_inventory:
                name = lot.canonical_name.lower().strip()
                inv_map[name] = inv_map.get(name, 0.0) + float(lot.quantity or 0.0)
                
            optimized_basket = build_optimized_basket(
                requested_items=requested_items,
                snapshot=market_snapshot,
                inventory_map=inv_map,
                avoid_items=avoid_list,
            )
        except Exception as exc:
            logger.debug("Optimized basket build failed: %s", exc)

    # Restock predictions — proactive "buy before you run out" from cadence
    restock_predictions: list[dict[str, Any]] = []
    try:
        from shopstack.services.decision_engine import predict_restock_needs
        restock_predictions = predict_restock_needs(cadence_data, active_inventory)
    except Exception as exc:
        logger.debug("Restock prediction failed: %s", exc)

    # Price drop alerts — items where current market price is significantly
    # below the household's historical median. Distinct from ``price_deals``
    # (which only covers "buy" decisions) — these are for any item in the
    # current snapshot, not just the user's planned basket.
    price_drops: list[dict[str, Any]] = []
    if market_snapshot is not None:
        try:
            from shopstack.services.price_alerts import detect_price_drops
            from shopstack.services.price_memory import PriceMemoryService

            pm_alerts = PriceMemoryService(db)
            for alert in detect_price_drops(market_snapshot, pm_alerts):
                price_drops.append({
                    "canonical_name": alert.canonical_name,
                    "display_name": alert.display_name,
                    "source": alert.source,
                    "current_price": alert.current_price,
                    "median_price": alert.median_price,
                    "drop_pct": alert.drop_pct,
                    "drop_amount": alert.drop_amount,
                })
        except Exception as exc:
            logger.debug("Price drop detection failed: %s", exc)

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
        price_deals=price_deals,
        price_drops=price_drops,
        best_store=best_store,
        optimized_basket=optimized_basket,
        restock_predictions=restock_predictions,
    )


def _load_market_snapshot(db: Database):
    """Load market snapshot(s) — prefers multi-source registry, falls back to Swiggy-only."""
    from shopstack.services.market_sources import _build_registry

    try:
        registry = _build_registry(db)
        registry.load_all(timeout_per_source=5.0)
        snapshots = registry.all_snapshots()
        if snapshots:
            latest = max(snapshots.values(), key=lambda snap: snap.captured_at)
            return (latest, registry)
        if registry.registered():
            return (None, registry)
    except Exception as exc:
        logger.debug("Market registry load failed: %s", exc)

    return None, None
