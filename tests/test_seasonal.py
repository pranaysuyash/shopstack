"""Tests for the seasonal / weather-aware shopping recommendation service.

Covers:

- Weather classification: rain, heat, cold, AQI extraction.
- Each rule producer: when it fires and when it doesn't.
- Highest-priority selection (the score-based tiebreaker).
- Default fallback when nothing fires.
- HTML rendering: XSS-safe, severity colors.
- End-to-end integration: a known weather + use-soon combination
  produces the expected recommendation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from shopstack.services.seasonal import (
    SeasonalRecommendation,
    recommend_seasonal,
    render_seasonal_html,
)


@dataclass
class _FakeWeather:
    """Minimal weather stub for testing."""
    condition: str = ""
    temp_c: float | None = None
    aqi: int | None = None


def _use_soon(*names: str) -> list[dict]:
    return [
        {"canonical_name": n, "display_name": n.replace("_", " ").title()}
        for n in names
    ]


def _price_drop(name: str, pct: float) -> dict:
    return {
        "canonical_name": name,
        "display_name": name.replace("_", " ").title(),
        "drop_pct": pct,
    }


# ── Weather classification ─────────────────────────────────────────────


class TestWeatherClassification:
    def test_rain_detected_from_condition(self):
        rec = recommend_seasonal(_FakeWeather(condition="Heavy rain"))
        assert "Rain" in rec.title
        assert rec.icon == "🌧️"

    def test_drizzle_detected_as_rain(self):
        rec = recommend_seasonal(_FakeWeather(condition="Light drizzle"))
        assert "Rain" in rec.title

    def test_heat_advisory_at_38c(self):
        rec = recommend_seasonal(_FakeWeather(condition="Sunny", temp_c=38.0))
        assert "Heat" in rec.title
        assert "38" in rec.title

    def test_cold_snap_at_2c(self):
        rec = recommend_seasonal(_FakeWeather(condition="Snow", temp_c=2.0))
        assert "Cold" in rec.title or "cold" in rec.title.lower()

    def test_unhealthy_air_at_aqi_250(self):
        rec = recommend_seasonal(_FakeWeather(condition="Hazy", aqi=250))
        assert "Air quality" in rec.title
        assert rec.severity == "danger"

    def test_sunny_no_weather_alerts(self):
        rec = recommend_seasonal(_FakeWeather(condition="Sunny", temp_c=25.0, aqi=50))
        # No rain, heat, cold, AQI. No use_soon, no price_drops.
        # So default "Good day" should fire.
        assert rec.icon == "☀️"
        assert "Good day" in rec.title

    def test_none_weather_returns_default(self):
        rec = recommend_seasonal(None)
        assert rec.icon == "☀️"
        assert "Good day" in rec.title


# ── Use-soon and price-drops rules ────────────────────────────────────────


class TestUseSoonAndPriceDrops:
    def test_use_soon_fires_with_3_items(self):
        rec = recommend_seasonal(
            _FakeWeather(condition="Sunny", temp_c=25.0, aqi=50),
            use_soon_items=_use_soon("tomato", "milk", "paneer"),
        )
        assert rec.icon == "🥬"
        assert "3 items" in rec.title

    def test_use_soon_with_1_item_singular(self):
        rec = recommend_seasonal(
            _FakeWeather(),
            use_soon_items=_use_soon("tomato"),
        )
        # use_soon has score 6+0.5=6.5. The sunny default has score 1.
        # So use_soon wins.
        assert rec.icon == "🥬"
        assert "1 item" in rec.title
        assert "items" not in rec.title  # singular

    def test_use_soon_empty_list_does_not_fire(self):
        rec = recommend_seasonal(_FakeWeather(), use_soon_items=[])
        assert rec.icon == "☀️"

    def test_price_drops_fires_with_1_item(self):
        rec = recommend_seasonal(
            _FakeWeather(),
            price_drops=[_price_drop("tomato", 30.0)],
        )
        assert rec.icon == "💸"
        assert "1 price drop" in rec.title
        # Pct is in the body, not the title
        assert "30" in rec.body
        assert "Tomato" in rec.body

    def test_price_drops_with_multiple_items(self):
        rec = recommend_seasonal(
            _FakeWeather(),
            price_drops=[
                _price_drop("tomato", 30.0),
                _price_drop("onion", 20.0),
                _price_drop("rice", 15.0),
            ],
        )
        assert "3 price drops" in rec.title


# ── Priority selection ─────────────────────────────────────────────────


class TestPrioritySelection:
    def test_rain_outranks_default(self):
        rec = recommend_seasonal(_FakeWeather(condition="Heavy rain"))
        # Rain score 8.0, default 1.0. Rain wins.
        assert "Rain" in rec.title

    def test_aqi_danger_outranks_rain(self):
        # AQI 9.0, rain 8.0. AQI should win.
        rec = recommend_seasonal(_FakeWeather(condition="Heavy rain", aqi=300))
        assert "Air quality" in rec.title
        assert rec.severity == "danger"

    def test_use_soon_outranks_price_drops(self):
        rec = recommend_seasonal(
            _FakeWeather(),
            use_soon_items=_use_soon("tomato", "milk", "paneer"),  # score ~6.5
            price_drops=[_price_drop("rice", 25.0)],  # score 5.4
        )
        assert rec.icon == "🥬"  # use_soon wins

    def test_rain_outranks_use_soon(self):
        rec = recommend_seasonal(
            _FakeWeather(condition="Heavy rain"),  # score 8.0
            use_soon_items=_use_soon("tomato", "milk", "paneer"),  # score 6.5
        )
        assert "Rain" in rec.title


# ── HTML rendering ──────────────────────────────────────────────────────


class TestRenderSeasonalHtml:
    def test_renders_recommendation(self):
        rec = recommend_seasonal(_FakeWeather(condition="Heavy rain"))
        html = render_seasonal_html(rec)
        assert "Rain" in html
        assert "🌧️" in html

    def test_renders_action_when_present(self):
        rec = recommend_seasonal(
            _FakeWeather(condition="Heavy rain"),
            price_drops=[_price_drop("rice", 25.0)],
        )
        # The rain rec has an action
        html = render_seasonal_html(rec)
        assert "Suggested:" in html

    def test_renders_severity_color(self):
        rec = recommend_seasonal(_FakeWeather(condition="Hazy", aqi=300))
        html = render_seasonal_html(rec)
        # Danger severity → red color
        assert "var(--red)" in html

    def test_html_escapes_xss(self):
        # Forge a malicious title
        rec = SeasonalRecommendation(
            severity="info",
            icon="⚠️",
            title="<script>alert(1)</script>",
            body="xss body",
        )
        html = render_seasonal_html(rec)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


# ── Edge cases ─────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_no_weather_no_inventory_no_drops(self):
        rec = recommend_seasonal(None, use_soon_items=None, price_drops=None)
        assert rec.icon == "☀️"

    def test_partial_weather_object(self):
        """A weather object with only temp_c (no condition, no aqi) should
        not crash and should still apply the heat rule if applicable."""
        rec = recommend_seasonal(_FakeWeather(temp_c=37.0))
        # No condition means no rain; temp 37 triggers heat
        assert "Heat" in rec.title

    def test_rec_to_dict(self):
        rec = recommend_seasonal(_FakeWeather(condition="Heavy rain"))
        d = rec.to_dict()
        assert d["severity"] == "warning"
        assert d["icon"] == "🌧️"
        assert "Rain" in d["title"]
        assert "score" in d

    def test_default_does_not_override_real_signals(self):
        """When real signals fire, default is ignored. Specifically
        test: sunny weather + 5 use_soon items → use_soon wins (not sunny)."""
        rec = recommend_seasonal(
            _FakeWeather(condition="Sunny", temp_c=25.0, aqi=50),
            use_soon_items=_use_soon("a", "b", "c", "d", "e"),
        )
        assert rec.icon == "🥬"
