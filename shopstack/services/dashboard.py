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
    cook_tonight_matches: list[dict[str, Any]] = field(default_factory=list)
    seasonal_recommendation: dict[str, Any] = field(default_factory=dict)
    best_store: dict[str, Any] = field(default_factory=dict)
    optimized_basket: Any | None = None
    restock_predictions: list[dict[str, Any]] = field(default_factory=list)
    items_needing_confirmation: list[dict[str, Any]] = field(default_factory=list)

    @property
    def use_soon_count(self) -> int:
        return int(self.use_soon.get("count", len(self.use_soon.get("items", []))))

    @property
    def use_soon_items(self) -> list[dict[str, Any]]:
        return list(self.use_soon.get("items", []))


def build_dashboard_state(db: Database, inventory, city: str = "mumbai", user_id: str = "") -> DashboardState:
    """Assemble the Today dashboard state from inventory, decisions, market data, and weather.

    Uses a per-user cache (``_DASHBOARD_CACHE``) to avoid redundant
    DB queries when the same user's dashboard is requested multiple
    times in a session. The cache is invalidated by
    :func:`clear_dashboard_cache` whenever the underlying data
    changes (inventory added/removed, prices updated, etc.).

    The cache is keyed by ``user_id`` and by the ``id(db)`` of the
    Database object so different DB instances (e.g. in test isolation)
    don't accidentally share cached state.
    """
    cache_key = (user_id, id(db))
    if cache_key in _DASHBOARD_CACHE:
        logger.debug("Dashboard cache hit for user_id=%s db_id=%s", user_id, id(db))
        return _DASHBOARD_CACHE[cache_key]
    result = _build_dashboard_state_uncached(db, inventory, city=city, user_id=user_id)
    _DASHBOARD_CACHE[cache_key] = result
    return result


def _build_dashboard_state_uncached(
    db: Database,
    inventory,
    city: str = "mumbai",
    user_id: str = "",
) -> DashboardState:
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
    if hasattr(inventory, "get_use_soon"):
        use_soon = inventory.get_use_soon(days=3, user_id=user_id)
    elif hasattr(inventory, "get_use_soon_items"):
        use_soon = inventory.get_use_soon_items(days=3, user_id=user_id)
    else:
        # Callers that don't carry an inventory accessor (e.g. the Today
        # Intelligence panel, restock card) pass an empty list. Fall back
        # to a fresh InventoryRepo bound to this db connection.
        from shopstack.repos.inventory import InventoryRepo
        use_soon = InventoryRepo(db).get_use_soon(days=3, user_id=user_id)
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

    # Cook tonight — recipe recommendations based on current inventory +
    # use-soon items. Uses the recipe DB (30 Indian staples). Tied to
    # inventory + use-soon so it directly closes the loop on "what to
    # cook tonight given what's about to go bad".
    cook_tonight_matches: list[dict[str, Any]] = []
    try:
        from shopstack.services.recipes import find_recipes_for_inventory

        # Determine dietary preference from preference_signals
        dietary = "omnivore"
        try:
            for sig in db.get_preference_signals(user_id=user_id):
                if sig.canonical_name and sig.canonical_name.startswith("_diet:"):
                    dietary = sig.canonical_name.split(":", 1)[1]
                    break
        except Exception:
            pass

        use_soon_items = (use_soon or {}).get("items", []) if isinstance(use_soon, dict) else []
        matches = find_recipes_for_inventory(
            all_inventory,
            use_soon_items,
            dietary_preference=dietary,
            max_recipes=4,
        )
        for m in matches:
            cook_tonight_matches.append({
                "recipe_id": m.recipe.id,
                "name": m.recipe.name,
                "cuisine": m.recipe.cuisine,
                "prep_minutes": m.recipe.prep_minutes,
                "cook_minutes": m.recipe.cook_minutes,
                "serves": m.recipe.serves,
                "score": round(m.score, 2),
                "completion_pct": m.completion_pct,
                "use_soon_count": m.use_soon_count,
                "use_soon_names": [i.canonical_name for i in m.use_soon_hits],
                "have_count": m.have_count,
                "missing_count": m.missing_count,
                "missing_names": [i.canonical_name for i in m.missing],
            })
    except Exception as exc:
        logger.debug("Cook tonight recommendations failed: %s", exc)

    # Seasonal / weather-aware recommendation (Phase 4 #19). Connects
    # weather + use-soon + price-drops into one actionable "what should
    # I do today" prompt. Highest-priority recommendation wins.
    seasonal_recommendation: dict[str, Any] = {}
    try:
        from shopstack.services.seasonal import recommend_seasonal
        rec = recommend_seasonal(
            weather=weather,
            use_soon_items=(use_soon or {}).get("items", []) if isinstance(use_soon, dict) else None,
            price_drops=price_drops or None,
        )
        seasonal_recommendation = rec.to_dict()
    except Exception as exc:
        logger.debug("Seasonal recommendation failed: %s", exc)

    # Calculate items needing confirmation from active inventory lots
    items_needing_confirmation: list[dict[str, Any]] = []
    try:
        from datetime import date as d_date
        from shopstack.domain.market_freshness import (
            inventory_confidence,
            needs_confirmation,
            confirmation_prompt,
        )
        from shopstack.market.metadata import get_produce_metadata
        for lot in active_inventory:
            meta = get_produce_metadata(lot.canonical_name)
            shelf_life = meta.shelf_life_days if meta else 0
            
            last_confirmed = None
            if lot.updated_at:
                if hasattr(lot.updated_at, "date"):
                    last_confirmed = lot.updated_at.date()
                elif isinstance(lot.updated_at, d_date):
                    last_confirmed = lot.updated_at
                elif isinstance(lot.updated_at, str):
                    try:
                        last_confirmed = d_date.fromisoformat(lot.updated_at[:10])
                    except Exception:
                        pass

            conf = inventory_confidence(
                purchase_date=lot.purchase_date,
                shelf_life_days=shelf_life,
                last_confirmed=last_confirmed,
            )
            if needs_confirmation(conf):
                prompt = confirmation_prompt(
                    canonical_name=lot.canonical_name,
                    display_name=lot.display_name,
                    confidence=conf,
                    purchase_date=lot.purchase_date,
                    quantity=lot.quantity,
                    unit=lot.unit,
                )
                if prompt:
                    items_needing_confirmation.append({
                        "lot_id": lot.lot_id,
                        "canonical_name": lot.canonical_name,
                        "display_name": lot.display_name,
                        "confidence": round(conf, 2),
                        "prompt": prompt,
                    })
    except Exception as exc:
        logger.debug("Failed computing items needing confirmation for dashboard: %s", exc)

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
        cook_tonight_matches=cook_tonight_matches,
        seasonal_recommendation=seasonal_recommendation,
        best_store=best_store,
        optimized_basket=optimized_basket,
        restock_predictions=restock_predictions,
        items_needing_confirmation=items_needing_confirmation,
    )


# Per-user cache for DashboardState so repeated calls to build_dashboard_state
# in a session skip redundant DB queries. Invalidated by clear_dashboard_cache().
_DASHBOARD_CACHE: dict[str, DashboardState] = {}


def clear_dashboard_cache(user_id: str | None = None) -> None:
    """Invalidate the per-user dashboard cache.

    When ``user_id`` is given, only that user's cached state is dropped.
    When ``user_id`` is None, the entire cache is cleared (e.g. for tests).
    """
    if user_id is None:
        _DASHBOARD_CACHE.clear()
        return
    # Clear any entries for this user_id (across all DB instances)
    keys_to_remove = [k for k in _DASHBOARD_CACHE if k[0] == user_id]
    for k in keys_to_remove:
        _DASHBOARD_CACHE.pop(k, None)
    # Backward-compat: also clear legacy string keys
    _DASHBOARD_CACHE.pop(user_id, None)
    _DASHBOARD_CACHE.pop("", None)


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
