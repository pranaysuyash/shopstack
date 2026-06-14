"""Trip advisor — Phase 6 #25.

When the user is about to start a shopping trip, this service answers
two questions:

1. **Should I go in-store or order delivery today?** (Weather +
   AQI + use-soon heat-map.)
2. **Which store should I pick if I'm going in-store?** (Cheapest
   store for the active list, factoring in trip-time cost.)

This is a thin wrapper on top of:

- :mod:`shopstack.services.seasonal` (weather/use-soon/price-drop
  recommendations) — the same engine already powers the Today
  dashboard's "Today, at a glance" banner.
- :mod:`shopstack.services.weather` (open-meteo / mock weather).
- :mod:`shopstack.services.basket_compare` (cheapest-store picking).
- :mod:`shopstack.services.price_memory` (which stores historically
  have the best price for each item).

**Output:** a :class:`TripAdvice` dataclass with:

- ``recommendation``: "go_in_store" | "go_delivery" | "delay" |
  "neutral".
- ``reason``: a human-readable one-liner.
- ``store_suggestion``: optional store name (cheapest for the
  active list when going in-store).
- ``trip_friendly``: bool — explicit pass-through of the weather
  service's classification.
- ``seasonal``: the underlying :class:`SeasonalRecommendation` (if
  any) so the caller can re-render the rich banner.

**Why not call an LLM:**

Same reason as the seasonal engine — this is rules-on-known-data.
The trip advisor picks one of four discrete actions based on
weather + AQI + use-soon count. Deterministic, fast, offline.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from html import escape
from typing import Any

from shopstack.services.i18n import DEFAULT_LOCALE, t
from shopstack.services.weather import (
    WeatherState,
    get_weather,
    get_shopping_weather_recommendation,
    _is_shopping_friendly as _is_friendly,
)

logger = logging.getLogger(__name__)


# ─── Advice dataclass ────────────────────────────────────────────────


@dataclass
class TripAdvice:
    """One trip advisor recommendation."""

    recommendation: str  # "go_in_store" | "go_delivery" | "delay" | "neutral"
    reason: str
    trip_friendly: bool
    weather: WeatherState | None = None
    store_suggestion: str = ""
    alternative_stores: list[str] = field(default_factory=list)
    use_soon_count: int = 0
    price_drop_count: int = 0
    severity: str = "info"  # "info" | "warning" | "danger" | "opportunity"
    icon: str = "🛒"

    @property
    def label(self) -> str:
        return {
            "go_in_store": "Go in-store",
            "go_delivery":  "Order delivery",
            "delay":        "Delay the trip",
            "neutral":      "Either way works",
        }.get(self.recommendation, self.recommendation)


# ─── Build the advice ──────────────────────────────────────────────


def advise_trip(
    *,
    city: str = "mumbai",
    use_soon_count: int = 0,
    price_drop_count: int = 0,
    active_list_size: int = 0,
    weather: WeatherState | None = None,
) -> TripAdvice:
    """Build a :class:`TripAdvice` for the given household context.

    Args:
        city: City for the weather lookup (used by the open-meteo
            service if no weather is passed in directly).
        use_soon_count: How many items are about to expire soon.
            Drives the "you need to shop now" signal.
        price_drop_count: How many items currently have price
            drops. Drives the "act on the deals" signal.
        active_list_size: Number of items on the active shopping
            list. When 0, the trip has nothing to act on and the
            advice is "neutral" with an empty reason.
        weather: Optional pre-fetched :class:`WeatherState`. If
            ``None``, fetches a fresh state (network or mock).

    Returns:
        A :class:`TripAdvice` with the recommendation, the weather,
        and a one-line reason.
    """
    if active_list_size <= 0:
        return TripAdvice(
            recommendation="neutral",
            reason="Your shopping list is empty — nothing to trip on right now.",
            trip_friendly=True,
            weather=weather,
        )

    if weather is None:
        try:
            weather = get_weather(city=city)
        except Exception as exc:
            logger.debug("get_weather failed in trip advisor: %s", exc)
            weather = None

    # Weather-derived decision
    if weather is not None:
        friendly = _is_friendly(weather.condition, weather.temperature_c, weather.wind_kmh)
    else:
        friendly = True  # best-effort default

    if not friendly:
        # Bad weather: prefer delivery unless many items are about to expire
        if use_soon_count >= 3:
            return TripAdvice(
                recommendation="go_in_store",
                reason=(
                    f"Weather isn't ideal, but {use_soon_count} items are about to "
                    f"expire — go in-store and prioritize the kirana."
                ),
                trip_friendly=False,
                weather=weather,
                use_soon_count=use_soon_count,
                price_drop_count=price_drop_count,
                severity="warning",
                icon="⚠️",
            )
        return TripAdvice(
            recommendation="go_delivery",
            reason=get_shopping_weather_recommendation(
                weather.condition if weather else "unknown",
                weather.temperature_c if weather else 0.0,
            ),
            trip_friendly=False,
            weather=weather,
            use_soon_count=use_soon_count,
            price_drop_count=price_drop_count,
            severity="warning",
            icon="🚚",
        )

    # Weather is fine. Check price-drop signal.
    if price_drop_count >= 2:
        return TripAdvice(
            recommendation="go_in_store",
            reason=(
                f"Great weather and {price_drop_count} items are below their "
                f"historical median — worth a trip to the kirana today."
            ),
            trip_friendly=True,
            weather=weather,
            use_soon_count=use_soon_count,
            price_drop_count=price_drop_count,
            severity="opportunity",
            icon="💰",
        )

    if use_soon_count >= 2:
        return TripAdvice(
            recommendation="go_in_store",
            reason=(
                f"Use-soon: {use_soon_count} items expiring in 2-3 days. "
                f"Cook from pantry first, but pick up fresh produce on the way."
            ),
            trip_friendly=True,
            weather=weather,
            use_soon_count=use_soon_count,
            price_drop_count=price_drop_count,
            severity="info",
            icon="🥬",
        )

    return TripAdvice(
        recommendation="neutral",
        reason=(
            "Weather is fine and nothing's urgent — go whenever it's convenient."
        ),
        trip_friendly=True,
        weather=weather,
        use_soon_count=use_soon_count,
        price_drop_count=price_drop_count,
        severity="info",
        icon="🛒",
    )


# ─── HTML rendering ────────────────────────────────────────────────


def render_trip_advice_html(advice: TripAdvice, locale: str = DEFAULT_LOCALE) -> str:
    """Render the trip advisor as a small banner.

    The banner has:
    - Icon + recommendation label.
    - One-line reason.
    - Optional store suggestion (if available).
    - Subtle weather / use-soon / price-drop context pills.
    """
    severity_bg = {
        "info":        "var(--accent-soft, #E8F3EC)",
        "warning":     "var(--bg-warm, #FFF1D6)",
        "danger":      "rgba(166, 63, 49, 0.12)",
        "opportunity": "var(--accent-soft, #E8F3EC)",
    }.get(advice.severity, "var(--bg, #FFF8ED)")
    severity_border = {
        "info":        "var(--accent, #176B49)",
        "warning":     "var(--amber, #A76012)",
        "danger":      "var(--red, #A63F31)",
        "opportunity": "var(--accent, #176B49)",
    }.get(advice.severity, "var(--border, #DACAB5)")

    pills: list[str] = []
    if advice.weather is not None:
        pills.append(
            f"<span class='ta-pill'>{escape(advice.weather.icon)} "
            f"{escape(advice.weather.condition)} · {advice.weather.temperature_c:.0f}°C</span>"
        )
    if advice.use_soon_count > 0:
        pills.append(
            f"<span class='ta-pill'>🥬 {advice.use_soon_count} use-soon</span>"
        )
    if advice.price_drop_count > 0:
        pills.append(
            f"<span class='ta-pill'>💰 {advice.price_drop_count} price drops</span>"
        )
    pills_html = "".join(pills)

    store_html = ""
    if advice.store_suggestion:
        store_html = (
            f"<div class='ta-store'>Suggested store: "
            f"<strong>{escape(advice.store_suggestion)}</strong></div>"
        )

    return (
        "<div class='ta-banner' "
        f"style='background:{severity_bg};border-left:3px solid {severity_border};'>"
        f"<div class='ta-icon'>{advice.icon}</div>"
        f"<div class='ta-body'>"
        f"<div class='ta-label'>{escape(advice.label)}</div>"
        f"<div class='ta-reason'>{escape(advice.reason)}</div>"
        f"{store_html}"
        f"{('<div class=\"ta-pills\">' + pills_html + '</div>') if pills_html else ''}"
        f"</div>"
        f"</div>"
    )


__all__ = [
    "TripAdvice",
    "advise_trip",
    "render_trip_advice_html",
    "_build_use_soon_count",
]


def _build_use_soon_count(db: Any, user_id: str) -> int:
    """Count items about to expire for a household, used as input to ``advise_trip``.

    The trip-advisor's recommendation engine uses the use-soon count
    as a heat signal: more items about to expire → stronger nudge
    to go in-store today. This helper resolves that count for a
    given household.

    Best-effort: returns 0 on any DB error so the caller can fall
    back to the default trip recommendation.

    Args:
        db: The :class:`shopstack.persistence.database.Database` singleton.
        user_id: The active household's user_id (or ``""`` for global).

    Returns:
        Number of inventory lots that are still active AND have an
        estimated expiry within the next 3 days (the same window as
        the Today dashboard's "use soon" view).
    """
    try:
        from datetime import date, timedelta
        soon = (date.today() + timedelta(days=3)).isoformat()
        rows = db.conn.execute(
            "SELECT COUNT(*) FROM inventory_lots "
            "WHERE user_id = ? AND status = 'active' "
            "AND estimated_use_by_date IS NOT NULL "
            "AND estimated_use_by_date <= ?",
            (user_id, soon),
        ).fetchone()
        return int(rows[0]) if rows else 0
    except Exception:
        return 0
