"""Seasonal / weather-aware shopping recommendations.

Connects three data sources the Today dashboard already gathers:

- **Weather** (from ``shopstack.services.weather``) — rain, temperature,
  AQI.
- **Use-soon inventory** — items about to expire in 2-3 days.
- **Price drops** — items currently below historical median.

…and produces one short, actionable recommendation for the user.
Not a model — explicit rules per the "1st principles" doctrine. The rules
are *priorities* (highest score wins) so multiple signals compose.

Examples:

  "🌧️ It's raining in Mumbai — delay the walk to the kirana, or
  order from Swiggy."

  "🥵 Heat advisory (38°C) — fresh produce wilts fast. Prefer
  delivery, or shop early."

  "🌫️ Air quality is unhealthy (AQI 280). Prefer delivery today."

  "🍅 Tomatoes dropped 30% this week — buy extra."

  "🥬 3 items expiring in 2 days. Cook at home tonight."

  "☀️ Sunny, AQI 50 — perfect day to walk to the kirana."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from html import escape
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SeasonalRecommendation:
    """One weather/season-aware shopping recommendation."""

    severity: str  # "info" | "warning" | "danger" | "opportunity"
    icon: str
    title: str
    body: str
    score: float = 0.0  # higher = more important
    action: str = ""  # optional suggested action
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "icon": self.icon,
            "title": self.title,
            "body": self.body,
            "score": self.score,
            "action": self.action,
            "notes": self.notes,
        }


# ── Weather classification ───────────────────────────────────────────────


def _classify_weather(weather: Any) -> dict[str, Any]:
    """Extract signals from a WeatherState-like object.

    Returns a dict with keys: condition (str | None), temp_c (float | None),
    aqi (int | None), is_rainy (bool), is_extreme_heat (bool),
    is_unhealthy_air (bool).
    """
    out: dict[str, Any] = {
        "condition": None,
        "temp_c": None,
        "aqi": None,
        "is_rainy": False,
        "is_extreme_heat": False,
        "is_unhealthy_air": False,
        "is_severe": False,
    }
    if weather is None:
        return out

    # Condition / description
    cond = (
        getattr(weather, "condition", None)
        or getattr(weather, "description", None)
        or getattr(weather, "summary", None)
    )
    if isinstance(cond, str):
        out["condition"] = cond.lower().strip()

    # Temperature
    temp = (
        getattr(weather, "temp_c", None)
        or getattr(weather, "temperature", None)
        or getattr(weather, "temp", None)
    )
    try:
        if temp is not None:
            out["temp_c"] = float(temp)
    except (TypeError, ValueError):
        pass

    # AQI
    aqi = getattr(weather, "aqi", None)
    try:
        if aqi is not None:
            out["aqi"] = int(aqi)
    except (TypeError, ValueError):
        pass

    cond_text = (out["condition"] or "")
    out["is_rainy"] = any(
        token in cond_text
        for token in ("rain", "shower", "drizzle", "thunder", "storm")
    )
    if out["temp_c"] is not None and out["temp_c"] >= 35.0:
        out["is_extreme_heat"] = True
    if out["temp_c"] is not None and out["temp_c"] <= 5.0:
        out["is_severe"] = True  # cold advisory
    if out["aqi"] is not None and out["aqi"] >= 200:
        out["is_unhealthy_air"] = True
    return out


# ── Rule producers ──────────────────────────────────────────────────────


def _recommend_rain(weather_cls: dict[str, Any]) -> SeasonalRecommendation | None:
    if not weather_cls["is_rainy"]:
        return None
    return SeasonalRecommendation(
        severity="warning",
        icon="🌧️",
        title="Rain in your area",
        body=(
            "Wet roads make the kirana walk unpleasant, and produce can "
            "get waterlogged. Consider ordering delivery, or wait for the "
            "shower to pass."
        ),
        score=8.0,
        action="Order from Swiggy / Blinkit / Zepto if you have a list ready.",
    )


def _recommend_heat(weather_cls: dict[str, Any]) -> SeasonalRecommendation | None:
    if not weather_cls["is_extreme_heat"]:
        return None
    temp = weather_cls["temp_c"]
    return SeasonalRecommendation(
        severity="warning",
        icon="🥵",
        title=f"Heat advisory ({temp:.0f}°C)",
        body=(
            "Fresh produce wilts fast in this heat. If you're walking to the "
            "kirana, go early. Or prefer delivery so the cold-chain isn't "
            "broken between store and home."
        ),
        score=7.0,
        action="Prefer delivery for dairy, leafy greens, and frozen items.",
    )


def _recommend_cold(weather_cls: dict[str, Any]) -> SeasonalRecommendation | None:
    if not weather_cls["is_severe"]:
        return None
    temp = weather_cls["temp_c"]
    return SeasonalRecommendation(
        severity="info",
        icon="❄️",
        title=f"Cold snap ({temp:.0f}°C)",
        body=(
            "Cold weather — good day for a hot walk to the kirana. "
            "Stock up on warming spices (ginger, garlic, garam masala) "
            "and root vegetables."
        ),
        score=4.0,
    )


def _recommend_aqi(weather_cls: dict[str, Any]) -> SeasonalRecommendation | None:
    if not weather_cls["is_unhealthy_air"]:
        return None
    aqi = weather_cls["aqi"]
    return SeasonalRecommendation(
        severity="danger",
        icon="🌫️",
        title=f"Air quality unhealthy (AQI {aqi})",
        body=(
            "Outdoor exposure is not recommended today. Avoid prolonged "
            "walks; prefer delivery so you don't have to step outside."
        ),
        score=9.0,
        action="Prefer delivery today. If you must go out, consider an N95.",
    )


def _recommend_use_soon(use_soon_items: list[dict[str, Any]] | None) -> SeasonalRecommendation | None:
    if not use_soon_items:
        return None
    n = len(use_soon_items)
    if n == 0:
        return None
    names = ", ".join(
        escape(str(it.get("display_name") or it.get("canonical_name", "?")).replace("_", " ").title())
        for it in use_soon_items[:3]
    )
    more = f" (+{n - 3} more)" if n > 3 else ""
    return SeasonalRecommendation(
        severity="opportunity",
        icon="🥬",
        title=f"{n} item{'s' if n != 1 else ''} about to go bad",
        body=(
            f"{names}{more} will go bad in the next few days. Cook at home "
            "tonight to use them up — this is a no-cost way to save ₹X on "
            "tomorrow's groceries."
        ),
        score=6.0 + min(n, 4) * 0.5,  # more items = slightly higher score
        action="Open the 🍳 Cook Tonight card to see recipes that use them.",
    )


def _recommend_price_drops(price_drops: list[dict[str, Any]] | None) -> SeasonalRecommendation | None:
    if not price_drops:
        return None
    n = len(price_drops)
    if n == 0:
        return None
    biggest = max(price_drops, key=lambda p: p.get("drop_pct", 0))
    pct = float(biggest.get("drop_pct", 0))
    name = escape(str(biggest.get("display_name") or biggest.get("canonical_name", "?")).replace("_", " ").title())
    if n == 1:
        body = f"{name} is {pct:.0f}% below your historical median — good day to buy extra."
    else:
        body = (
            f"{name} dropped {pct:.0f}% this week, plus {n - 1} other item(s). Stock up on what you'll actually use."
        )
    return SeasonalRecommendation(
        severity="opportunity",
        icon="💸",
        title=f"{n} price drop{'s' if n != 1 else ''} this week",
        body=body,
        score=5.0 + min(n, 4) * 0.4,
        action="See the 📉 Price Drops card for details.",
    )


def _recommend_default(weather_cls: dict[str, Any]) -> SeasonalRecommendation:
    """When nothing else fires, return a benign 'all clear' recommendation
    so the UI has something to show (instead of an empty card)."""
    return SeasonalRecommendation(
        severity="info",
        icon="☀️",
        title="Good day to shop",
        body=(
            "Weather is fine and nothing major in your inventory is about "
            "to spoil. Stick to the planned list — no special action."
        ),
        score=1.0,
    )


# ── Public API ───────────────────────────────────────────────────────────


def recommend_seasonal(
    weather: Any,
    use_soon_items: list[dict[str, Any]] | None = None,
    price_drops: list[dict[str, Any]] | None = None,
) -> SeasonalRecommendation:
    """Compute the highest-priority seasonal recommendation.

    Args:
        weather: A WeatherState-like object (from
            ``shopstack.services.weather.get_weather``). Any object with
            ``condition``/``temp_c``/``aqi`` attributes works.
        use_soon_items: Output of the use-soon service (list of dicts
            with ``canonical_name`` and ``display_name``).
        price_drops: Output of the price-alerts service (list of dicts
            with ``canonical_name``, ``display_name``, ``drop_pct``).

    Returns:
        The single highest-scored ``SeasonalRecommendation``. If nothing
        fires, returns a benign default "all clear" message.
    """
    weather_cls = _classify_weather(weather)
    candidates: list[SeasonalRecommendation] = []

    for fn in (
        lambda: _recommend_rain(weather_cls),
        lambda: _recommend_heat(weather_cls),
        lambda: _recommend_cold(weather_cls),
        lambda: _recommend_aqi(weather_cls),
        lambda: _recommend_use_soon(use_soon_items),
        lambda: _recommend_price_drops(price_drops),
    ):
        try:
            rec = fn()
        except Exception as exc:  # noqa: BLE001 — best-effort recommendation
            logger.debug("Seasonal rule failed: %s", exc)
            rec = None
        if rec is not None:
            candidates.append(rec)

    if not candidates:
        return _recommend_default(weather_cls)
    candidates.sort(key=lambda r: r.score, reverse=True)
    return candidates[0]


# ── HTML rendering ──────────────────────────────────────────────────────


_SEVERITY_COLOR = {
    "info": "var(--blue)",
    "warning": "var(--amber)",
    "danger": "var(--red)",
    "opportunity": "var(--green)",
}


def render_seasonal_html(rec: SeasonalRecommendation) -> str:
    """Render a single ``SeasonalRecommendation`` as XSS-safe HTML."""
    color = _SEVERITY_COLOR.get(rec.severity, "var(--text-dim)")
    return (
        f"<div class='home-card' style='margin-bottom:12px;'><h3 style='margin:0 0 4px 0;color:{color};'>{escape(rec.icon)} {escape(rec.title)}</h3>"
        f"<div style='font-size: 0.8125rem;color:var(--text);'>{escape(rec.body)}</div>"
        + (
            f"<div style='font-size: 0.75rem;color:var(--text-dim);margin-top:6px;'><strong>Suggested:</strong> {escape(rec.action)}</div>"
            if rec.action
            else ""
        )
        + "</div>"
    )


__all__ = [
    "SeasonalRecommendation",
    "recommend_seasonal",
    "render_seasonal_html",
]
