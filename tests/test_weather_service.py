from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shopstack.services.weather import (
    CITY_COORDS,
    WeatherState,
    _is_shopping_friendly,
    _mock_weather,
    _wmo_to_condition,
    get_shopping_weather_recommendation,
)


def test_city_coords_has_major_cities():
    assert "mumbai" in CITY_COORDS
    assert "delhi" in CITY_COORDS
    assert "bangalore" in CITY_COORDS
    for city, coords in CITY_COORDS.items():
        assert len(coords) == 2
        assert -90 <= coords[0] <= 90
        assert -180 <= coords[1] <= 180


def test_weather_state_is_stale():
    old = WeatherState(
        temperature_c=25.0, feels_like_c=26.0, condition="sunny",
        humidity_pct=50.0, wind_kmh=10.0, is_shopping_friendly=True,
        recommendation="Go!", fetched_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    assert old.is_stale is True


def test_weather_state_not_stale():
    fresh = WeatherState(
        temperature_c=25.0, feels_like_c=26.0, condition="sunny",
        humidity_pct=50.0, wind_kmh=10.0, is_shopping_friendly=True,
        recommendation="Go!", fetched_at=datetime.now(timezone.utc),
    )
    assert fresh.is_stale is False


def test_weather_state_condition_icon():
    sunny = WeatherState(
        temperature_c=25.0, feels_like_c=25.0, condition="sunny",
        humidity_pct=50.0, wind_kmh=5.0, is_shopping_friendly=True,
        recommendation="", fetched_at=datetime.now(timezone.utc),
    )
    assert sunny.condition_icon != ""


def test_wmo_to_condition_codes():
    assert _wmo_to_condition(95, 25.0) == "stormy"
    assert _wmo_to_condition(61, 25.0) == "rainy"
    assert _wmo_to_condition(45, 25.0) == "foggy"
    assert _wmo_to_condition(3, 25.0) == "cloudy"
    assert _wmo_to_condition(2, 25.0) == "partly_cloudy"
    assert _wmo_to_condition(0, 25.0) == "sunny"
    assert _wmo_to_condition(0, 42.0) == "hot"
    assert _wmo_to_condition(0, 10.0) == "cold"


def test_is_shopping_friendly():
    assert _is_shopping_friendly("sunny", 25.0, 10.0) is True
    assert _is_shopping_friendly("stormy", 25.0, 10.0) is False
    assert _is_shopping_friendly("rainy", 25.0, 25.0) is False
    assert _is_shopping_friendly("rainy", 25.0, 10.0) is True
    assert _is_shopping_friendly("sunny", 45.0, 10.0) is False
    assert _is_shopping_friendly("sunny", 5.0, 10.0) is False


def test_get_shopping_weather_recommendation():
    assert "online" in get_shopping_weather_recommendation("rainy")
    assert "postpon" in get_shopping_weather_recommendation("stormy").lower()
    assert "early morning" in get_shopping_weather_recommendation("hot")
    assert "Great" in get_shopping_weather_recommendation("sunny", temp=25.0)
    assert "hot beverages" in get_shopping_weather_recommendation("sunny", temp=10.0).lower()


def test_mock_weather_returns_valid_state():
    weather = _mock_weather("mumbai")
    assert isinstance(weather, WeatherState)
    assert weather.temperature_c > 0
    assert weather.condition in ("sunny", "partly_cloudy", "cloudy", "rainy", "pleasant", "hot", "cold")


def test_mock_weather_deterministic():
    w1 = _mock_weather("delhi")
    w2 = _mock_weather("delhi")
    assert w1.temperature_c == w2.temperature_c
    assert w1.condition == w2.condition
