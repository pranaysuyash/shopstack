"""Tests for shopstack.services.sparkline (Phase 5 #22 inline price memory)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from shopstack.services.sparkline import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    SparklinePoint,
    normalize_prices,
    observations_from_history,
    percent_change,
    render_sparkline_row_html,
    render_sparkline_svg,
    trend_arrow,
)


# ── normalize_prices ─────────────────────────────────────────────


def test_normalize_prices_empty_returns_empty():
    assert normalize_prices([]) == []


def test_normalize_prices_filters_zero_and_negative():
    obs = [
        {"price": 0, "date": date(2024, 1, 1)},
        {"price": -1, "date": date(2024, 1, 2)},
        {"price": 5, "date": date(2024, 1, 3)},
    ]
    out = normalize_prices(obs)
    assert len(out) == 1
    assert out[0].raw["price"] == 5


def test_normalize_prices_filters_non_finite():
    obs = [
        {"price": float("inf"), "date": date(2024, 1, 1)},
        {"price": float("nan"), "date": date(2024, 1, 2)},
        {"price": 10, "date": date(2024, 1, 3)},
    ]
    out = normalize_prices(obs)
    assert len(out) == 1


def test_normalize_prices_filters_non_numeric():
    obs = [
        {"price": "abc", "date": date(2024, 1, 1)},
        {"price": None, "date": date(2024, 1, 2)},
        {"price": 5, "date": date(2024, 1, 3)},
    ]
    out = normalize_prices(obs)
    assert len(out) == 1


def test_normalize_prices_sorts_by_date():
    obs = [
        {"price": 5, "date": date(2024, 1, 3)},
        {"price": 3, "date": date(2024, 1, 1)},
        {"price": 4, "date": date(2024, 1, 2)},
    ]
    out = normalize_prices(obs)
    assert [p.raw["price"] for p in out] == [3, 4, 5]


def test_normalize_prices_y_inverted_so_high_is_top():
    obs = [
        {"price": 1, "date": date(2024, 1, 1)},
        {"price": 5, "date": date(2024, 1, 2)},
        {"price": 3, "date": date(2024, 1, 3)},
    ]
    out = normalize_prices(obs)
    # Highest price is 5; it should have the smallest y
    highest = next(p for p in out if p.raw["price"] == 5)
    lowest = next(p for p in out if p.raw["price"] == 1)
    assert highest.y < lowest.y


def test_normalize_prices_x_monotonic():
    obs = [
        {"price": 1, "date": date(2024, 1, i + 1)} for i in range(5)
    ]
    out = normalize_prices(obs)
    xs = [p.x for p in out]
    assert xs == sorted(xs)
    assert xs[0] == 0.0
    assert xs[-1] == 1.0


def test_normalize_prices_single_point_centers():
    obs = [{"price": 5, "date": date(2024, 1, 1)}]
    out = normalize_prices(obs)
    assert len(out) == 1
    assert out[0].x == 0.5
    assert out[0].y == 0.5


def test_normalize_prices_flat_series():
    # All prices equal → y=0.5
    obs = [{"price": 5, "date": date(2024, 1, i + 1)} for i in range(3)]
    out = normalize_prices(obs)
    for p in out:
        assert p.y == 0.5


# ── trend_arrow ─────────────────────────────────────────────────


def test_trend_arrow_empty_returns_dash():
    assert trend_arrow([]) == "—"


def test_trend_arrow_single_returns_dash():
    assert trend_arrow([5.0]) == "—"


def test_trend_arrow_up():
    # Last price is 50% above the median
    assert trend_arrow([1, 1, 1, 1.5]) == "↑"


def test_trend_arrow_down():
    # Last price is 50% below the median
    assert trend_arrow([2, 2, 2, 1]) == "↓"


def test_trend_arrow_flat():
    # Within 5% band
    assert trend_arrow([1, 1, 1, 1.02]) == "—"


def test_trend_arrow_filters_nones():
    assert trend_arrow([None, 5, 5, 5, 6]) in ("↑", "—")


def test_trend_arrow_handles_zero_median():
    # Median of 0 → no meaningful change, returns dash
    assert trend_arrow([0, 0, 0, 5]) == "—"


# ── percent_change ───────────────────────────────────────────────


def test_percent_change_empty_returns_none():
    assert percent_change([]) is None


def test_percent_change_single_returns_none():
    assert percent_change([5.0]) is None


def test_percent_change_up():
    pct = percent_change([1, 1, 1, 2])
    assert pct is not None
    assert pct > 50  # 2 vs median(1) = +100%


def test_percent_change_down():
    pct = percent_change([4, 4, 4, 2])
    assert pct is not None
    assert pct < -25


def test_percent_change_zero_median_returns_none():
    assert percent_change([0, 0, 0, 5]) is None


# ── render_sparkline_svg ────────────────────────────────────────


def test_render_sparkline_svg_empty():
    svg = render_sparkline_svg([])
    assert "<svg" in svg
    assert "no data" in svg.lower()
    assert "aria-label" in svg


def test_render_sparkline_svg_includes_polyline():
    obs = [
        {"price": 1, "date": date(2024, 1, 1)},
        {"price": 5, "date": date(2024, 1, 2)},
    ]
    svg = render_sparkline_svg(obs)
    assert "<polyline" in svg
    assert "<circle" in svg  # last-point marker


def test_render_sparkline_svg_uses_current_color_by_default():
    obs = [{"price": 5, "date": date(2024, 1, 1)}]
    svg = render_sparkline_svg(obs)
    assert "currentColor" in svg


def test_render_sparkline_svg_respects_custom_size():
    obs = [{"price": 5, "date": date(2024, 1, 1)}]
    svg = render_sparkline_svg(obs, width=200, height=50)
    assert "width='200'" in svg
    assert "height='50'" in svg


def test_render_sparkline_svg_uses_custom_stroke():
    obs = [{"price": 5, "date": date(2024, 1, 1)}]
    svg = render_sparkline_svg(obs, stroke="red")
    assert "stroke='red'" in svg


def test_render_sparkline_svg_has_accessibility_attributes():
    obs = [{"price": 5, "date": date(2024, 1, 1)}]
    svg = render_sparkline_svg(obs)
    assert "role='img'" in svg
    assert "aria-label" in svg


def test_render_sparkline_svg_xss_safe():
    obs = [
        {"price": 1, "date": date(2024, 1, 1)},
        {"price": 5, "date": date(2024, 1, 2)},
    ]
    svg = render_sparkline_svg(obs)
    assert "<script" not in svg.lower()


# ── render_sparkline_row_html ──────────────────────────────────


def test_render_sparkline_row_html_includes_svg_and_arrow():
    obs = [{"price": 1, "date": date(2024, 1, 1)},
           {"price": 5, "date": date(2024, 1, 2)}]
    html = render_sparkline_row_html(obs)
    assert "<svg" in html
    assert "sparkline-row" in html


def test_render_sparkline_row_html_shows_percent_change():
    obs = [{"price": 1, "date": date(2024, 1, 1)},
           {"price": 1, "date": date(2024, 1, 2)},
           {"price": 1, "date": date(2024, 1, 3)},
           {"price": 1.5, "date": date(2024, 1, 4)}]
    html = render_sparkline_row_html(obs)
    # Should contain a "+X.X%" string
    assert "+" in html
    assert "%" in html


def test_render_sparkline_row_html_handles_empty():
    html = render_sparkline_row_html([])
    assert "—" in html


def test_render_sparkline_row_html_colors_trend_up_red():
    obs = [{"price": 1, "date": date(2024, 1, 1)},
           {"price": 1, "date": date(2024, 1, 2)},
           {"price": 2, "date": date(2024, 1, 3)}]  # last price 2x median
    html = render_sparkline_row_html(obs)
    # Up trend with >5% delta → red
    assert "var(--red" in html or "#dc2626" in html


def test_render_sparkline_row_html_colors_trend_down_green():
    obs = [{"price": 4, "date": date(2024, 1, 1)},
           {"price": 4, "date": date(2024, 1, 2)},
           {"price": 1, "date": date(2024, 1, 3)}]  # last price 1 vs median 4
    html = render_sparkline_row_html(obs)
    # Down trend with >5% delta → green
    assert "var(--green" in html or "#16a34a" in html


# ── observations_from_history ────────────────────────────────


class _FakeHistory:
    def __init__(self, all_prices):
        self.all_prices = all_prices


def test_observations_from_history_list():
    obs = [{"price": 1}, {"price": 2}]
    assert observations_from_history(obs) == obs


def test_observations_from_history_object_with_all_prices():
    hist = _FakeHistory([{"price": 1}, {"price": 2}])
    assert observations_from_history(hist) == [{"price": 1}, {"price": 2}]


def test_observations_from_history_none():
    assert observations_from_history(None) == []


def test_observations_from_history_object_with_to_dict():
    class _H:
        def to_dict(self):
            return {"all_prices": [{"price": 5}]}

    assert observations_from_history(_H()) == [{"price": 5}]


# ── End-to-end ────────────────────────────────────────────────


def test_sparkline_end_to_end_with_realistic_history():
    today = date.today()
    obs = []
    base = 100.0
    for i in range(30):
        # Simulate a slight upward drift
        obs.append({
            "price": base + i * 0.5,
            "date": today - timedelta(days=30 - i),
        })
    svg = render_sparkline_svg(obs)
    assert "<svg" in svg
    assert "<polyline" in svg
    # 30 points → 30 (x,y) pairs in the polyline (space-separated).
    # Each pair contributes 1 comma, so 30 pairs = 30 commas.
    assert svg.count(",") == 30
    # And 29 spaces between the 30 pairs
    poly_start = svg.index("points='") + len("points='")
    poly_end = svg.index("'", poly_start)
    poly_str = svg[poly_start:poly_end]
    assert poly_str.count(" ") == 29


def test_sparkline_with_lots_of_observations_renders_fast():
    # Regression: 365 daily observations should not blow up
    today = date.today()
    obs = [
        {"price": 50 + (i % 30), "date": today - timedelta(days=365 - i)}
        for i in range(365)
    ]
    svg = render_sparkline_svg(obs)
    assert "<svg" in svg
    # Should not raise; size is bounded by polyline length, not by obs count
    assert len(svg) < 100_000


def test_default_dimensions_match_documented_constants():
    assert DEFAULT_WIDTH == 120
    assert DEFAULT_HEIGHT == 32
