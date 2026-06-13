"""Inline price sparkline — Phase 5 #22 (Tier 4 #22).

Renders a tiny SVG sparkline of an item's price history so the user
can see at a glance: "this is up 8% vs last month" or "this is at
its lowest in a year".

**Design choices:**

- Pure inline SVG, no JS, no external libs. The browser renders the
  SVG natively; the line is just a ``<polyline>`` of normalized
  price points.
- A small dot marks the most recent observation. A horizontal dashed
  line marks the all-time median for quick "above/below" intuition.
- Dark-mode aware: the polyline, axis, and median line use CSS
  custom properties (``var(--text-muted)`` etc.) so they re-tint
  with the rest of the app.
- Compact: target dimensions are 120×32 px so it can sit inline in
  the price memory row, the market lens result, or the cookbook
  card detail view.
- The accompanying text (current price, % change vs last month,
  trend arrow) is rendered next to the SVG so screen readers and
  users who can't see the line still get the data.

**Pure functions:**

- :func:`normalize_prices` is the only piece of business logic. It
  converts a list of (date, price) tuples to (x, y) coordinates
  inside a 0..1 box, so the SVG renderer can scale to any size.
- :func:`trend_arrow` is a tiny string helper for the trend glyph
  (↑/↓/→/—) based on the slope of the line.

The sparkline is **never interactive** in v1: the user clicks the
row in the price memory tab to drill down. Future work could add
a hover tooltip on the polyline.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date
from html import escape
from typing import Any, Iterable, Sequence

logger = logging.getLogger(__name__)


# ─── Constants ──────────────────────────────────────────────────────────

DEFAULT_WIDTH: int = 120
DEFAULT_HEIGHT: int = 32
PADDING: float = 2.0  # px of inner padding on each side


# ─── Pure functions ────────────────────────────────────────────────────


@dataclass
class SparklinePoint:
    """A single normalized (x, y) point in 0..1 coordinates."""

    x: float
    y: float
    raw: Any  # the original observation (for tooltip / debugging)


def normalize_prices(
    observations: Sequence[dict[str, Any]],
    *,
    width: float = DEFAULT_WIDTH,
    height: float = DEFAULT_HEIGHT,
) -> list[SparklinePoint]:
    """Map a list of price observations to ``SparklinePoint``s.

    The y-axis is normalized so the highest price sits at the top of
    the SVG (y=0) and the lowest at the bottom (y=1). The x-axis is
    normalized to time, oldest at x=0 and most recent at x=1.

    Observations are sorted by date (oldest first). Observations with
    missing or zero/negative prices are filtered out so the line
    doesn't break on bad data.
    """
    # Sort by date
    dated: list[tuple[Any, float]] = []
    for obs in observations:
        price = obs.get("price")
        if price is None:
            continue
        try:
            p = float(price)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(p) or p <= 0:
            continue
        dated.append((obs.get("date"), p))
    if not dated:
        return []
    dated.sort(key=lambda d: (d[0] is None, d[0]))

    n = len(dated)
    if n == 1:
        # A single point: center it
        prices_only = [p for _, p in dated]
        return [
            SparklinePoint(
                x=0.5,
                y=0.5,
                raw={"price": prices_only[0], "date": dated[0][0]},
            )
        ]

    pmin = min(p for _, p in dated)
    pmax = max(p for _, p in dated)
    prange = pmax - pmin

    points: list[SparklinePoint] = []
    for i, (d, p) in enumerate(dated):
        # X: evenly spaced by index
        x = i / (n - 1) if n > 1 else 0.5
        # Y: invert (top = high price) and normalize
        if prange == 0:
            y = 0.5
        else:
            y = 1.0 - (p - pmin) / prange
        points.append(SparklinePoint(x=x, y=y, raw={"price": p, "date": d}))
    return points


def trend_arrow(prices: Sequence[float]) -> str:
    """Return a trend arrow for a list of prices.

    Compares the last price to the median of the rest. Returns:
    - ``"↑"`` if up > 5%
    - ``"↓"`` if down > 5%
    - ``"—"`` if flat (within 5%)
    - ``"—"`` for empty / single-element lists
    """
    if not prices or len(prices) < 2:
        return "—"
    last = float(prices[-1])
    rest = [float(p) for p in prices[:-1] if p is not None]
    if not rest:
        return "—"
    rest_sorted = sorted(rest)
    n = len(rest_sorted)
    median = rest_sorted[n // 2] if n % 2 == 1 else (rest_sorted[n // 2 - 1] + rest_sorted[n // 2]) / 2
    if median <= 0:
        return "—"
    change = (last - median) / median
    if change > 0.05:
        return "↑"
    if change < -0.05:
        return "↓"
    return "—"


def percent_change(prices: Sequence[float]) -> float | None:
    """Return the % change of the last price vs the median of the rest.

    Returns ``None`` if the median is zero or unknown.
    """
    if not prices or len(prices) < 2:
        return None
    last = float(prices[-1])
    rest = [float(p) for p in prices[:-1] if p is not None]
    if not rest:
        return None
    rest_sorted = sorted(rest)
    n = len(rest_sorted)
    median = rest_sorted[n // 2] if n % 2 == 1 else (rest_sorted[n // 2 - 1] + rest_sorted[n // 2]) / 2
    if median <= 0:
        return None
    return (last - median) / median * 100.0


# ─── HTML rendering ───────────────────────────────────────────────────


def _points_to_polyline(
    points: list[SparklinePoint],
    width: int,
    height: int,
) -> str:
    """Convert normalized points to an SVG ``points="x,y x,y ..."`` string."""
    pad = PADDING
    inner_w = max(1.0, width - 2 * pad)
    inner_h = max(1.0, height - 2 * pad)
    out: list[str] = []
    for p in points:
        x = pad + p.x * inner_w
        y = pad + p.y * inner_h
        out.append(f"{x:.1f},{y:.1f}")
    return " ".join(out)


def render_sparkline_svg(
    observations: Sequence[dict[str, Any]],
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    stroke: str = "currentColor",
    stroke_width: float = 1.5,
) -> str:
    """Return an inline ``<svg>`` sparkline string.

    Returns an empty SVG (with a "no data" hint) when observations is
    empty. The SVG uses ``currentColor`` for the stroke by default so
    the parent's text color drives the line tint.
    """
    if not observations:
        return (
            f"<svg width='{width}' height='{height}' "
            f"viewBox='0 0 {width} {height}' "
            f"aria-label='No price history' role='img'>"
            f"<text x='{width // 2}' y='{height // 2 + 4}' "
            f"text-anchor='middle' font-size='9' fill='var(--text-dim, #94a3b8)'>"
            f"no data</text></svg>"
        )
    points = normalize_prices(observations, width=width, height=height)
    if not points:
        return (
            f"<svg width='{width}' height='{height}' "
            f"viewBox='0 0 {width} {height}' "
            f"aria-label='No price history' role='img'>"
            f"<text x='{width // 2}' y='{height // 2 + 4}' "
            f"text-anchor='middle' font-size='9' fill='var(--text-dim, #94a3b8)'>"
            f"no data</text></svg>"
        )
    poly = _points_to_polyline(points, width, height)
    # Mark the last point with a small dot
    last = points[-1]
    pad = PADDING
    inner_w = max(1.0, width - 2 * pad)
    inner_h = max(1.0, height - 2 * pad)
    last_x = pad + last.x * inner_w
    last_y = pad + last.y * inner_h
    return (
        f"<svg width='{width}' height='{height}' "
        f"viewBox='0 0 {width} {height}' "
        f"aria-label='Price history sparkline' role='img'>"
        f"<polyline points='{poly}' fill='none' stroke='{stroke}' "
        f"stroke-width='{stroke_width}' stroke-linecap='round' "
        f"stroke-linejoin='round' opacity='0.85'/>"
        f"<circle cx='{last_x:.1f}' cy='{last_y:.1f}' r='2' "
        f"fill='{stroke}'/>"
        f"</svg>"
    )


def render_sparkline_row_html(
    observations: Sequence[dict[str, Any]],
    *,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    locale: str = "en",
) -> str:
    """Render a sparkline + a small label block as a single HTML row.

    The label block shows the trend arrow and a percentage delta vs
    the median of the historical data. Suitable for placement in a
    table row, dashboard tile, or cookbook card detail.
    """
    prices = [
        float(o["price"]) for o in observations
        if o.get("price") is not None
    ]
    arrow = trend_arrow(prices)
    pct = percent_change(prices)
    svg = render_sparkline_svg(observations, width=width, height=height)
    if pct is None:
        pct_text = "—"
        pct_color = "var(--text-dim, #94a3b8)"
    else:
        sign = "+" if pct >= 0 else ""
        pct_text = f"{sign}{pct:.1f}%"
        pct_color = "var(--red, #dc2626)" if pct > 5 else (
            "var(--green, #16a34a)" if pct < -5 else "var(--text-muted, #475569)"
        )
    arrow_color = "var(--red, #dc2626)" if arrow == "↑" else (
        "var(--green, #16a34a)" if arrow == "↓" else "var(--text-dim, #94a3b8)"
    )
    return (
        "<span class='sparkline-row' style='display:inline-flex;align-items:center;gap:6px;'>"
        f"{svg}"
        f"<span class='sparkline-arrow' style='font-size:14px;color:{arrow_color};'>{arrow}</span>"
        f"<span class='sparkline-pct' style='font-size:11px;color:{pct_color};'>{pct_text}</span>"
        f"</span>"
    )


# ─── Convenience: extract observations from PriceMemoryService ───────


def observations_from_history(history: Any) -> list[dict[str, Any]]:
    """Convert a ``PriceHistory`` object (or ``to_dict()``) to observation dicts.

    The price memory service exposes observations in two shapes:
    - ``PriceHistory.all_prices`` is a list of dicts (already our shape)
    - ``PriceHistory.to_dict()`` is a nested dict (different shape)

    This helper handles both, and also accepts a raw list of dicts.
    """
    if history is None:
        return []
    if isinstance(history, list):
        return list(history)
    # Try .all_prices first
    all_prices = getattr(history, "all_prices", None)
    if all_prices is not None:
        return list(all_prices)
    # Try to_dict()
    to_dict = getattr(history, "to_dict", None)
    if callable(to_dict):
        d = to_dict()
        if isinstance(d, dict):
            ap = d.get("all_prices") or d.get("prices") or []
            if isinstance(ap, list):
                return ap
    return []


__all__ = [
    "DEFAULT_HEIGHT",
    "DEFAULT_WIDTH",
    "PADDING",
    "SparklinePoint",
    "normalize_prices",
    "observations_from_history",
    "percent_change",
    "render_sparkline_row_html",
    "render_sparkline_svg",
    "trend_arrow",
]
