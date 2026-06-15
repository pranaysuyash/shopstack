from __future__ import annotations

import hashlib
import logging
import urllib.request
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

__all__ = [
    "CITY_COORDS",
    "WeatherState",
    "get_weather",
    "get_shopping_weather_recommendation",
]

CITY_COORDS: dict[str, tuple[float, float]] = {
    "mumbai": (19.076, 72.8777),
    "delhi": (28.7041, 77.1025),
    "bangalore": (12.9716, 77.5946),
    "hyderabad": (17.385, 78.4867),
    "chennai": (13.0827, 80.2707),
    "kolkata": (22.5726, 88.3639),
    "pune": (18.5204, 73.8567),
    "ahmedabad": (23.0225, 72.5714),
}

_STALE_MINUTES = 30

_weather_cache: dict[str, tuple[datetime, "WeatherState"]] = {}


@dataclass
class WeatherState:
    temperature_c: float
    feels_like_c: float
    condition: str
    humidity_pct: float
    wind_kmh: float
    is_shopping_friendly: bool
    recommendation: str
    fetched_at: datetime

    @property
    def is_stale(self) -> bool:
        age = datetime.now(timezone.utc) - self.fetched_at
        return age > timedelta(minutes=_STALE_MINUTES)

    @property
    def condition_icon(self) -> str:
        icons: dict[str, str] = {
            "sunny": "\u2600\ufe0f",
            "partly_cloudy": "\u26c5",
            "cloudy": "\u2601\ufe0f",
            "rainy": "\U0001f327\ufe0f",
            "stormy": "\u26c8\ufe0f",
            "foggy": "\U0001f32b\ufe0f",
            "cold": "\u2744\ufe0f",
            "hot": "\U0001f525",
            "pleasant": "\u2600\ufe0f",
        }
        return icons.get(self.condition, "\U0001f4ca")


def get_weather(city: str = "mumbai") -> WeatherState:
    city_key = city.strip().lower()
    cached = _weather_cache.get(city_key)
    if cached and not cached[1].is_stale:
        return cached[1]

    coords = CITY_COORDS.get(city_key)
    if coords:
        fresh = _fetch_open_meteo(coords[0], coords[1])
        if fresh is not None:
            _weather_cache[city_key] = (datetime.now(timezone.utc), fresh)
            return fresh

    fallback = _mock_weather(city_key)
    _weather_cache[city_key] = (datetime.now(timezone.utc), fallback)
    return fallback


def _fetch_open_meteo(lat: float, lon: float) -> WeatherState | None:
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m&timezone=auto"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ShopStack/1.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        logger.info("Open-Meteo fetch failed: %s", exc)
        return None

    current = data.get("current", {})
    temp = current.get("temperature_2m", 0.0)
    feels = current.get("apparent_temperature", temp)
    humidity = current.get("relative_humidity_2m", 50.0)
    wind = current.get("wind_speed_10m", 0.0)
    wmo = current.get("weather_code", 0)

    condition = _wmo_to_condition(wmo, temp)
    friendly = _is_shopping_friendly(condition, temp, wind)
    rec = get_shopping_weather_recommendation(condition, temp)

    return WeatherState(
        temperature_c=temp,
        feels_like_c=feels,
        condition=condition,
        humidity_pct=humidity,
        wind_kmh=wind,
        is_shopping_friendly=friendly,
        recommendation=rec,
        fetched_at=datetime.now(timezone.utc),
    )


def _wmo_to_condition(code: int, temp: float) -> str:
    if code in (95, 96, 99):
        return "stormy"
    if code in (61, 63, 65, 66, 67, 80, 81, 82):
        return "rainy"
    if code in (45, 48, 51, 53, 55, 56, 57):
        return "foggy"
    if code in (51, 53, 55):
        return "foggy"
    if code >= 3:
        return "cloudy"
    if code == 2:
        return "partly_cloudy"
    if temp > 38:
        return "hot"
    if temp < 15:
        return "cold"
    return "sunny"


def _is_shopping_friendly(condition: str, temp: float, wind: float) -> bool:
    if condition in ("stormy",):
        return False
    if condition == "rainy" and wind > 20:
        return False
    if temp > 42 or temp < 8:
        return False
    return True


def _mock_weather(city: str) -> WeatherState:
    h = int(hashlib.md5(city.encode()).hexdigest()[:8], 16)
    temp = 25.0 + (h % 15) - 5
    feels = temp + (h % 3) - 1
    conditions = ["sunny", "partly_cloudy", "cloudy", "rainy", "pleasant", "hot", "cold"]
    condition = conditions[h % len(conditions)]
    friendly = _is_shopping_friendly(condition, temp, 10.0)
    rec = get_shopping_weather_recommendation(condition, temp)
    return WeatherState(
        temperature_c=temp,
        feels_like_c=feels,
        condition=condition,
        humidity_pct=40.0 + (h % 40),
        wind_kmh=5.0 + (h % 20),
        is_shopping_friendly=friendly,
        recommendation=rec,
        fetched_at=datetime.now(timezone.utc),
    )


def get_shopping_weather_recommendation(condition: str, temp: float = 0.0) -> str:
    if condition == "rainy":
        return "Covered market recommended. Consider ordering online for dry goods."
    if condition == "stormy":
        return "Consider postponing. Check if essentials are stocked."
    if condition == "hot" or temp > 38:
        return "Shop early morning or evening. Cold items may spoil in transit."
    if condition == "cold" or temp < 15:
        return "Good day for hot beverages stocking. Check if you need warm-weather produce."
    if condition == "foggy":
        return "Drive carefully if heading out. Visibility may be low on the way to market."
    return "Great day for market shopping!"
