"""Tests for the restored market renderer functions in dashboard.py.

These tests prevent future removal without test coverage —
the functions were previously deleted in violation of motto_v3 §7
(inventory before deletion) and §11 (don't delete speculative features).
See Docs/DECISION_RECORDS_CODE_REMOVALS_2026-06-13.md for context.
"""
from __future__ import annotations

from types import SimpleNamespace

from shopstack.ui.screens.dashboard import (
    _render_market_next_steps,
    _render_market_map_teaser,
)


def _make_graph(
    *,
    items_scored: int = 0,
    buy: int = 0,
    compare: int = 0,
    substitute: int = 0,
    stale: int = 0,
    compare_items: list | None = None,
    substitute_items: list | None = None,
    buy_items: list | None = None,
    snapshot_freshness: str | None = None,
    snapshot_freshness_label: str | None = None,
):
    """Build a lightweight graph-like object for testing renderers."""
    return SimpleNamespace(
        summary={
            "items_scored": items_scored,
            "buy": buy,
            "compare": compare,
            "substitute": substitute,
            "stale": stale,
        },
        compare=compare_items or [],
        substitute=substitute_items or [],
        buy=buy_items or [],
        snapshot_freshness=snapshot_freshness,
        snapshot_freshness_label=snapshot_freshness_label,
    )


def _make_signal(name: str, reason: str = ""):
    """Build a lightweight signal/cluster object for compare/substitute lists."""
    return SimpleNamespace(
        display_name=name,
        reason=reason,
        reasons=[reason] if reason else [],
    )


def _make_state(*, market_snapshot=None):
    """Build a lightweight state object for _render_market_map_teaser."""
    return SimpleNamespace(market_snapshot=market_snapshot)


# ── _render_market_next_steps ─────────────────────────────────────


class TestRenderMarketNextSteps:
    def test_empty_graph_shows_no_actions_message(self):
        graph = _make_graph()
        html = _render_market_next_steps(graph)
        assert "Next steps" in html
        assert "No market signals yet" in html

    def test_buy_signal_shows_open_groceries(self):
        graph = _make_graph(buy=2)
        html = _render_market_next_steps(graph)
        assert "Open Groceries" in html
        assert "Turn buy items into the list" in html

    def test_compare_signal_shows_review_compare(self):
        graph = _make_graph(compare=1)
        html = _render_market_next_steps(graph)
        assert "Review Compare" in html
        assert "Check overlap and substitutions" in html

    def test_substitute_signal_shows_review_substitutes(self):
        graph = _make_graph(substitute=3)
        html = _render_market_next_steps(graph)
        assert "Review Substitutes" in html
        assert "See better replacements" in html

    def test_stale_signal_shows_inspect_freshness(self):
        graph = _make_graph(stale=1)
        html = _render_market_next_steps(graph)
        assert "Inspect Freshness" in html
        assert "Treat stale cards as references" in html

    def test_multiple_signals_render_all_cards(self):
        graph = _make_graph(buy=1, compare=1, substitute=1, stale=1)
        html = _render_market_next_steps(graph)
        assert "Open Groceries" in html
        assert "Review Compare" in html
        assert "Review Substitutes" in html
        assert "Inspect Freshness" in html

    def test_top_signals_line_shows_compare(self):
        signal = _make_signal("Tomato", "price dropped")
        graph = _make_graph(compare=1, compare_items=[signal])
        html = _render_market_next_steps(graph)
        assert "Tomato: compare" in html

    def test_top_signals_line_shows_substitute(self):
        signal = _make_signal("Butter", "sold out at DMart")
        graph = _make_graph(substitute=1, substitute_items=[signal])
        html = _render_market_next_steps(graph)
        assert "Butter: substitute" in html

    def test_top_signals_line_shows_buy(self):
        signal = _make_signal("Milk", "low stock")
        graph = _make_graph(buy=1, buy_items=[signal])
        html = _render_market_next_steps(graph)
        assert "Milk: buy" in html

    def test_returns_valid_html(self):
        graph = _make_graph(buy=1)
        html = _render_market_next_steps(graph)
        assert isinstance(html, str)
        assert len(html) > 0
        assert "<div" in html

    def test_no_action_grid_when_empty(self):
        graph = _make_graph()
        html = _render_market_next_steps(graph)
        assert "action-grid" not in html

    def test_action_grid_present_when_signals(self):
        graph = _make_graph(buy=1)
        html = _render_market_next_steps(graph)
        assert "action-grid" in html


# ── _render_market_map_teaser ──────────────────────────────────────


class TestRenderMarketMapTeaser:
    def test_empty_graph_no_snapshot(self):
        state = _make_state(market_snapshot=None)
        graph = _make_graph()
        html = _render_market_map_teaser(state, graph)
        assert "Market Map" in html
        assert "No market snapshot" in html

    def test_shows_freshness_label(self):
        state = _make_state(market_snapshot="snapshot")
        graph = _make_graph(snapshot_freshness_label="2 hours ago")
        html = _render_market_map_teaser(state, graph)
        assert "2 hours ago" in html

    def test_shows_freshness_fallback(self):
        state = _make_state(market_snapshot="snapshot")
        graph = _make_graph(snapshot_freshness="stale")
        html = _render_market_map_teaser(state, graph)
        assert "stale" in html

    def test_shows_signal_summary(self):
        state = _make_state(market_snapshot="snapshot")
        graph = _make_graph(items_scored=12, buy=3, compare=2, substitute=1)
        html = _render_market_map_teaser(state, graph)
        assert "12 items scored" in html
        assert "3 buy" in html
        assert "2 compare" in html
        assert "1 substitute" in html

    def test_includes_compare_preview(self):
        signal = _make_signal("Rice", "cheaper at Blinkit")
        state = _make_state(market_snapshot="snapshot")
        graph = _make_graph(compare=1, compare_items=[signal])
        html = _render_market_map_teaser(state, graph)
        assert "Compare preview" in html
        assert "Rice" in html
        assert "cheaper at Blinkit" in html

    def test_includes_action_grid(self):
        state = _make_state(market_snapshot="snapshot")
        graph = _make_graph()
        html = _render_market_map_teaser(state, graph)
        assert "Open Market Map" in html
        assert "Check Pantry" in html
        assert "Open Memory" in html
        assert "action-grid" in html

    def test_returns_valid_html(self):
        state = _make_state(market_snapshot="snapshot")
        graph = _make_graph(items_scored=5)
        html = _render_market_map_teaser(state, graph)
        assert isinstance(html, str)
        assert len(html) > 0
        assert "<div" in html

    def test_no_snapshot_zero_scored_shows_empty_message(self):
        state = _make_state(market_snapshot=None)
        graph = _make_graph(items_scored=0)
        html = _render_market_map_teaser(state, graph)
        assert "No market snapshot" in html

    def test_has_snapshot_with_data_shows_summary(self):
        state = _make_state(market_snapshot="loaded")
        graph = _make_graph(items_scored=8, buy=2, compare=1, substitute=1)
        html = _render_market_map_teaser(state, graph)
        assert "8 items scored" in html
        assert "No market snapshot" not in html
