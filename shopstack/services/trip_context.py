from __future__ import annotations

import logging
from dataclasses import dataclass, field
from html import escape
from typing import Any

from shopstack.services.weather import WeatherState, get_weather

logger = logging.getLogger(__name__)

__all__ = [
    "TripAdvice",
    "get_trip_advice",
    "render_weather_card",
    "format_trip_advice_html",
]


@dataclass
class TripAdvice:
    worth_it: bool
    confidence: str
    reason: str
    weather: WeatherState | None = None
    estimated_savings: float = 0.0
    items_to_buy: list[str] = field(default_factory=list)


def get_trip_advice(
    database: Any,
    store_name: str,
    items_on_list: list[str],
    distance_km: float = 0.0,
    city: str = "mumbai",
) -> TripAdvice:
    weather = None
    try:
        weather = get_weather(city)
    except Exception as exc:
        logger.info("Weather fetch failed for trip advice: %s", exc)

    has_urgent = _has_urgent_items(database, items_on_list)
    price_advantage = _estimate_price_advantage(database, store_name, items_on_list)

    if has_urgent:
        return TripAdvice(
            worth_it=True,
            confidence="confident",
            reason="Urgent items needed — go regardless of weather.",
            weather=weather,
            estimated_savings=price_advantage,
            items_to_buy=items_on_list,
        )

    if weather and weather.condition in ("stormy",) and distance_km > 2:
        return TripAdvice(
            worth_it=False,
            confidence="confident",
            reason="Stormy weather and no urgent needs. Postpone the trip.",
            weather=weather,
            items_to_buy=items_on_list,
        )

    if weather and weather.condition == "rainy" and distance_km > 5:
        return TripAdvice(
            worth_it=False,
            confidence="likely",
            reason="Rainy weather with a long trip. Consider waiting or ordering online.",
            weather=weather,
            items_to_buy=items_on_list,
        )

    if price_advantage >= 50:
        return TripAdvice(
            worth_it=True,
            confidence="likely",
            reason=f"Good prices at {escape(store_name)} — estimated saving around \u20b9{price_advantage:.0f}.",
            weather=weather,
            estimated_savings=price_advantage,
            items_to_buy=items_on_list,
        )

    if weather and not weather.is_shopping_friendly and distance_km > 3:
        return TripAdvice(
            worth_it=False,
            confidence="uncertain",
            reason=f"Weather is not ideal ({weather.condition}). Short trip might be ok, but consider ordering online.",
            weather=weather,
            items_to_buy=items_on_list,
        )

    reason_parts = []
    if weather and weather.is_shopping_friendly:
        reason_parts.append(f"Weather is fine ({weather.condition})")
    elif weather:
        reason_parts.append(f"Weather is {weather.condition}")
    reason_parts.append(f"{len(items_on_list)} items to pick up at {escape(store_name)}.")
    if price_advantage > 0:
        reason_parts.append(f"Potential saving: \u20b9{price_advantage:.0f}")

    return TripAdvice(
        worth_it=True,
        confidence="likely" if (weather and weather.is_shopping_friendly) else "uncertain",
        reason=" ".join(reason_parts),
        weather=weather,
        estimated_savings=price_advantage,
        items_to_buy=items_on_list,
    )


def _has_urgent_items(database: Any, items_on_list: list[str]) -> bool:
    try:
        inventory = database.get_inventory(status="active")
        low_names = {
            lot.canonical_name
            for lot in inventory
            if lot.quantity <= 0.5 or lot.status == "low"
        }
        for name in items_on_list:
            if name.lower() in low_names:
                return True
    except Exception:
        pass
    return False


def _estimate_price_advantage(database: Any, store_name: str, items_on_list: list[str]) -> float:
    if not items_on_list:
        return 0.0
    try:
        total_store = 0.0
        total_other = 0.0
        matched = 0
        for name in items_on_list:
            history = database.get_price_history(name)
            store_prices = [p for p in history if p.store_name and store_name.lower() in p.store_name.lower()]
            other_prices = [p for p in history if not p.store_name or store_name.lower() not in p.store_name.lower()]
            if store_prices and other_prices:
                avg_store = sum(p.price for p in store_prices) / len(store_prices)
                avg_other = sum(p.price for p in other_prices) / len(other_prices)
                total_store += avg_store
                total_other += avg_other
                matched += 1
        if matched == 0:
            return 0.0
        advantage = (total_other - total_store) / matched * len(items_on_list)
        return max(0.0, advantage)
    except Exception:
        return 0.0


def render_weather_card(weather: WeatherState | None) -> str:
    from shopstack.ui import card

    if weather is None:
        return card(
            "Weather",
            "<div style='color:var(--text-dim);'>Weather unavailable.</div>",
        )

    friendly_color = "var(--green)" if weather.is_shopping_friendly else "var(--amber)"
    friendly_label = "Good for shopping" if weather.is_shopping_friendly else "Consider staying in"

    return card(
        f"{weather.condition_icon} Weather",
        (
            f"<div style='display:flex;gap:16px;align-items:flex-start;'>"
            f"<div style='font-size:28px;font-weight:700;font-family:var(--font-display);'>"
            f"{weather.temperature_c:.0f}&deg;C"
            f"</div>"
            f"<div style='flex:1;'>"
            f"<div style='font-size:13px;color:var(--text-muted);'>"
            f"Feels like {weather.feels_like_c:.0f}&deg;C &middot; "
            f"{escape(weather.condition.replace('_', ' '))}"
            f"</div>"
            f"<div style='font-size:12px;color:var(--text-dim);margin-top:4px;'>"
            f"Humidity {weather.humidity_pct:.0f}% &middot; Wind {weather.wind_kmh:.0f} km/h"
            f"</div>"
            f"</div>"
            f"</div>"
            f"<div style='margin-top:10px;padding-top:8px;border-top:1px solid var(--border);font-size:13px;color:{friendly_color};font-weight:600;'>"
            f"{friendly_label}"
            f"</div>"
            f"<div style='margin-top:6px;font-size:12px;color:var(--text-dim);'>"
            f"{escape(weather.recommendation)}"
            f"</div>"
        ),
    )


def format_trip_advice_html(advice: TripAdvice) -> str:
    from shopstack.ui import card

    if advice.worth_it:
        badge_color = "var(--green)"
        badge_text = "Go"
    else:
        badge_color = "var(--red)"
        badge_text = "Wait"

    confidence_label = {
        "confident": "High confidence",
        "likely": "Moderate confidence",
        "uncertain": "Low confidence",
    }.get(advice.confidence, advice.confidence)

    savings_line = ""
    if advice.estimated_savings > 0:
        savings_line = (
            f"<div style='margin-top:6px;font-size:12px;color:var(--green);'>"
            f"Estimated saving: \u20b9{advice.estimated_savings:.0f}"
            f"</div>"
        )

    items_line = ""
    if advice.items_to_buy:
        items_str = ", ".join(escape(i) for i in advice.items_to_buy[:6])
        if len(advice.items_to_buy) > 6:
            items_str += f" +{len(advice.items_to_buy) - 6} more"
        items_line = (
            f"<div style='margin-top:6px;font-size:12px;color:var(--text-dim);'>"
            f"Items: {items_str}"
            f"</div>"
        )

    return card(
        "\U0001f6d2 Trip Advice",
        (
            f"<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px;'>"
            f"<span style='display:inline-block;padding:3px 10px;border-radius:999px;"
            f"background:{badge_color};color:#fff;font-size:12px;font-weight:700;'>"
            f"{badge_text}</span>"
            f"<span style='font-size:11px;color:var(--text-faint);'>{escape(confidence_label)}</span>"
            f"</div>"
            f"<div style='font-size:13px;color:var(--text);'>{escape(advice.reason)}</div>"
            f"{savings_line}{items_line}"
        ),
    )
