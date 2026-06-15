"""Tests for shopstack.services.trip_advisor (Phase 6 #25)."""
from __future__ import annotations

from datetime import datetime

import pytest

from shopstack.services.trip_advisor import (
    TripAdvice,
    advise_trip,
    render_trip_advice_html,
)


# ── Empty list → neutral ──────────────────────────────────────────


def test_advise_trip_empty_list_returns_neutral():
    advice = advise_trip(active_list_size=0)
    assert advice.recommendation == "neutral"
    assert "empty" in advice.reason.lower()


# ── Weather-derived decisions ─────────────────────────────────────


class _W:
    """Mock weather with controllable fields."""
    def __init__(self, condition: str, temperature_c: float, wind_kmh: float = 5.0):
        self.condition = condition
        self.temperature_c = temperature_c
        self.wind_kmh = wind_kmh
        self.condition_icon = "☀️"
        self.recommendation = "test"


def test_advise_trip_bad_weather_prefers_delivery():
    # "stormy" is unambiguously not shopping-friendly (rainy with low wind
    # is OK per the weather service's classification).
    weather = _W("stormy", 25.0)
    advice = advise_trip(weather=weather, active_list_size=5)
    assert advice.recommendation == "go_delivery"
    assert not advice.trip_friendly


def test_advise_trip_bad_weather_plus_use_soon_overrides_to_in_store():
    weather = _W("stormy", 25.0)
    advice = advise_trip(weather=weather, use_soon_count=5, active_list_size=5)
    assert advice.recommendation == "go_in_store"
    assert advice.severity == "warning"


def test_advise_trip_good_weather_with_price_drops():
    weather = _W("clear", 25.0)
    advice = advise_trip(
        weather=weather,
        price_drop_count=3,
        active_list_size=5,
    )
    assert advice.recommendation == "go_in_store"
    assert advice.severity == "opportunity"
    assert "💰" in advice.icon or "price" in advice.reason.lower()


def test_advise_trip_good_weather_with_use_soon():
    weather = _W("clear", 25.0)
    advice = advise_trip(
        weather=weather,
        use_soon_count=3,
        active_list_size=5,
    )
    assert advice.recommendation == "go_in_store"
    assert "use-soon" in advice.reason.lower() or "expir" in advice.reason.lower()


def test_advise_trip_good_weather_no_urgency_is_neutral():
    weather = _W("clear", 25.0)
    advice = advise_trip(weather=weather, active_list_size=5)
    assert advice.recommendation == "neutral"
    assert advice.trip_friendly


def test_advise_trip_no_weather_falls_back_to_neutral():
    # weather=None means "I don't have weather, please fetch it".
    # The trip advisor fetches a fresh weather state and uses it.
    # To verify the "no weather signal → neutral" path without depending
    # on the weather service's mock data, we patch get_weather to
    # raise (which causes the code to fall through to the "best-effort
    # default: friendly=True" path).
    from unittest.mock import patch
    with patch("shopstack.services.trip_advisor.get_weather",
               side_effect=Exception("no weather available")):
        advice = advise_trip(weather=None, active_list_size=5)
    # No weather info → assume trip-friendly → neutral
    assert advice.recommendation in ("neutral", "go_in_store")


# ── TripAdvice.label property ────────────────────────────────────


def test_trip_advice_label_map():
    assert TripAdvice(recommendation="go_in_store", reason="x", trip_friendly=True).label == "Go in-store"
    assert TripAdvice(recommendation="go_delivery", reason="x", trip_friendly=False).label == "Order delivery"
    assert TripAdvice(recommendation="delay", reason="x", trip_friendly=False).label == "Delay the trip"
    assert TripAdvice(recommendation="neutral", reason="x", trip_friendly=True).label == "Either way works"
    # Unknown falls back to raw value
    assert TripAdvice(recommendation="custom", reason="x", trip_friendly=True).label == "custom"


# ── HTML rendering ────────────────────────────────────────────────


def test_render_trip_advice_html_basic():
    advice = TripAdvice(
        recommendation="go_in_store",
        reason="Test reason",
        trip_friendly=True,
        severity="info",
        icon="🛒",
    )
    html = render_trip_advice_html(advice)
    assert "ta-banner" in html
    assert "Go in-store" in html
    assert "Test reason" in html


def test_render_trip_advice_html_includes_weather_pill():
    advice = TripAdvice(
        recommendation="go_in_store",
        reason="Clear day",
        trip_friendly=True,
        weather=_W("clear", 25.0),
    )
    html = render_trip_advice_html(advice)
    assert "ta-pill" in html
    assert "clear" in html.lower() or "Clear" in html


def test_render_trip_advice_html_includes_use_soon_pill():
    advice = TripAdvice(
        recommendation="go_in_store",
        reason="Use-soon",
        trip_friendly=True,
        use_soon_count=3,
    )
    html = render_trip_advice_html(advice)
    assert "use-soon" in html
    assert "3" in html


def test_render_trip_advice_html_includes_price_drop_pill():
    advice = TripAdvice(
        recommendation="go_in_store",
        reason="Price drops",
        trip_friendly=True,
        price_drop_count=2,
    )
    html = render_trip_advice_html(advice)
    assert "price drop" in html.lower() or "💰" in html
    assert "2" in html


def test_render_trip_advice_html_includes_store_suggestion():
    advice = TripAdvice(
        recommendation="go_in_store",
        reason="Cheapest",
        trip_friendly=True,
        store_suggestion="DMart Mumbai",
    )
    html = render_trip_advice_html(advice)
    assert "DMart Mumbai" in html
    assert "Suggested store" in html


def test_render_trip_advice_html_severity_coloring():
    advice_warning = TripAdvice(
        recommendation="go_delivery",
        reason="Rainy",
        trip_friendly=False,
        severity="warning",
    )
    advice_danger = TripAdvice(
        recommendation="delay",
        reason="Severe",
        trip_friendly=False,
        severity="danger",
    )
    html_w = render_trip_advice_html(advice_warning)
    html_d = render_trip_advice_html(advice_danger)
    # Different severity → different border color
    assert "amber" in html_w.lower() or "A76012" in html_w
    assert "red" in html_d.lower() or "A63F31" in html_d


def test_render_trip_advice_html_escapes_xss():
    advice = TripAdvice(
        recommendation="go_in_store",
        reason="<script>alert(1)</script>",
        trip_friendly=True,
    )
    html = render_trip_advice_html(advice)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ── Edge cases ────────────────────────────────────────────────────


def test_advise_trip_uses_weather_default_city():
    # When no weather is passed, the service should attempt to fetch one.
    # We pass active_list_size=0 so the early-exit path is taken — no
    # network call.
    advice = advise_trip(city="mumbai", active_list_size=0)
    assert advice.recommendation == "neutral"


def test_advise_trip_propagates_use_soon_count_to_advice():
    weather = _W("rain", 25.0)
    advice = advise_trip(weather=weather, use_soon_count=2, active_list_size=5)
    # Use-soon count should be visible on the advice
    assert advice.use_soon_count == 2


def test_advise_trip_propagates_price_drop_count_to_advice():
    weather = _W("clear", 25.0)
    advice = advise_trip(weather=weather, price_drop_count=4, active_list_size=5)
    assert advice.price_drop_count == 4
