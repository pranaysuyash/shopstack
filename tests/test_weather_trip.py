from __future__ import annotations

from datetime import datetime, timedelta, timezone

from shopstack.services.weather import (
    WeatherState,
    get_weather,
    get_shopping_weather_recommendation,
    _mock_weather,
    _weather_cache,
)
from shopstack.services.trip_context import (
    TripAdvice,
    get_trip_advice,
    format_trip_advice_html,
    render_weather_card,
)


def test_weather_state_is_stale():
    fresh = WeatherState(
        temperature_c=25.0,
        feels_like_c=26.0,
        condition="sunny",
        humidity_pct=50.0,
        wind_kmh=10.0,
        is_shopping_friendly=True,
        recommendation="Great day for market shopping!",
        fetched_at=datetime.now(timezone.utc),
    )
    assert not fresh.is_stale

    old = WeatherState(
        temperature_c=25.0,
        feels_like_c=26.0,
        condition="sunny",
        humidity_pct=50.0,
        wind_kmh=10.0,
        is_shopping_friendly=True,
        recommendation="Great day!",
        fetched_at=datetime.now(timezone.utc) - timedelta(minutes=60),
    )
    assert old.is_stale


def test_weather_state_condition_icon():
    sunny = WeatherState(
        temperature_c=25.0, feels_like_c=26.0, condition="sunny",
        humidity_pct=50.0, wind_kmh=10.0, is_shopping_friendly=True,
        recommendation="", fetched_at=datetime.now(timezone.utc),
    )
    assert sunny.condition_icon == "\u2600\ufe0f"

    rainy = WeatherState(
        temperature_c=20.0, feels_like_c=18.0, condition="rainy",
        humidity_pct=90.0, wind_kmh=15.0, is_shopping_friendly=True,
        recommendation="", fetched_at=datetime.now(timezone.utc),
    )
    assert rainy.condition_icon == "\U0001f327\ufe0f"


def test_mock_weather_deterministic():
    w1 = _mock_weather("mumbai")
    w2 = _mock_weather("mumbai")
    assert w1.temperature_c == w2.temperature_c
    assert w1.condition == w2.condition


def test_mock_weather_different_cities():
    w1 = _mock_weather("mumbai")
    w2 = _mock_weather("delhi")
    assert w1.temperature_c != w2.temperature_c or w1.condition != w2.condition


def test_get_weather_returns_state():
    _weather_cache.clear()
    weather = get_weather("pune")
    assert isinstance(weather, WeatherState)
    assert -20 <= weather.temperature_c <= 60
    assert weather.condition != ""


def test_get_weather_uses_cache():
    _weather_cache.clear()
    w1 = get_weather("bangalore")
    w2 = get_weather("bangalore")
    assert w1.fetched_at == w2.fetched_at


def test_shopping_recommendation_rainy():
    rec = get_shopping_weather_recommendation("rainy")
    assert "covered" in rec.lower() or "online" in rec.lower()


def test_shopping_recommendation_hot():
    rec = get_shopping_weather_recommendation("hot")
    assert "early morning" in rec.lower() or "evening" in rec.lower()


def test_shopping_recommendation_cold():
    rec = get_shopping_weather_recommendation("cold")
    assert "hot beverages" in rec.lower() or "warm" in rec.lower()


def test_shopping_recommendation_stormy():
    rec = get_shopping_weather_recommendation("stormy")
    assert "postpone" in rec.lower() or "essentials" in rec.lower()


def test_shopping_recommendation_sunny():
    rec = get_shopping_weather_recommendation("sunny", temp=28.0)
    assert "great" in rec.lower()


def test_shopping_recommendation_foggy():
    rec = get_shopping_weather_recommendation("foggy", temp=22.0)
    assert "visibility" in rec.lower() or "carefully" in rec.lower()


def test_trip_advice_empty_list(db):
    advice = get_trip_advice(db, "DMart", [], distance_km=5.0)
    assert isinstance(advice, TripAdvice)
    assert advice.items_to_buy == []


def test_trip_advice_urgent_items(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="milk",
        display_name="Milk",
        quantity=0.2,
        unit="L",
    )
    advice = get_trip_advice(db, "Local Kirana", ["milk"])
    assert advice.worth_it is True
    assert "urgent" in advice.reason.lower() or "regardless" in advice.reason.lower()


def test_trip_advice_no_urgent(db):
    advice = get_trip_advice(db, "DMart", ["rice", "flour"], distance_km=1.0)
    assert isinstance(advice, TripAdvice)
    assert advice.items_to_buy == ["rice", "flour"]


def test_trip_advice_confidence_values(db):
    advice = get_trip_advice(db, "Big Bazaar", ["onion"])
    assert advice.confidence in ("confident", "likely", "uncertain")


def test_format_trip_advice_html_go():
    advice = TripAdvice(
        worth_it=True,
        confidence="confident",
        reason="Good prices available.",
        items_to_buy=["milk", "bread"],
    )
    html = format_trip_advice_html(advice)
    assert "Go" in html
    assert "Good prices" in html


def test_format_trip_advice_html_wait():
    advice = TripAdvice(
        worth_it=False,
        confidence="likely",
        reason="Stormy weather.",
    )
    html = format_trip_advice_html(advice)
    assert "Wait" in html
    assert "Stormy" in html


def test_format_trip_advice_html_with_savings():
    advice = TripAdvice(
        worth_it=True,
        confidence="likely",
        reason="Good deal.",
        estimated_savings=120.0,
        items_to_buy=["rice"],
    )
    html = format_trip_advice_html(advice)
    assert "\u20b9120" in html


def test_render_weather_card_with_state():
    weather = WeatherState(
        temperature_c=32.0,
        feels_like_c=35.0,
        condition="sunny",
        humidity_pct=45.0,
        wind_kmh=12.0,
        is_shopping_friendly=True,
        recommendation="Great day for market shopping!",
        fetched_at=datetime.now(timezone.utc),
    )
    html = render_weather_card(weather)
    assert "32" in html
    assert "Weather" in html


def test_render_weather_card_none():
    html = render_weather_card(None)
    assert "unavailable" in html.lower()
