from __future__ import annotations

from shopstack.schemas.models import DecisionResult
from shopstack.services.market_intelligence import MarketCluster, MarketIntelligenceGraph, MarketTruthScore


def test_market_intelligence_view_renders_graph(monkeypatch):
    from shopstack.ui.screens import market_intelligence as screen

    graph = MarketIntelligenceGraph(
        snapshot_source="swiggy",
        snapshot_captured_at="2026-06-01",
        snapshot_freshness="stale",
        snapshot_freshness_label="Captured 11 days ago (2026-06-01)",
        source_count=1,
        source_names=["swiggy"],
        summary={"items_scored": 1, "buy": 1, "skip": 0, "use_soon": 0, "compare": 0, "substitute": 0, "wait": 0, "stale": 1, "sponsored": 0},
        clusters=[
            MarketCluster(
                canonical_name="tomato",
                display_name="Tomato",
                lane="buy",
                graph_lane="buy",
                decision=DecisionResult(canonical_name="tomato", display_name="Tomato", action="buy", market_price=28, market_price_per_kg=56, market_available=True),
                home_quantity=0.0,
                home_unit="kg",
                home_lot_count=0,
                market_records=[],
                market_source_count=1,
                market_price=28,
                market_price_per_kg=56,
                market_available=True,
                market_raw_size="500g",
                market_freshness="stale",
                market_freshness_label="Captured 11 days ago (2026-06-01)",
                market_source="swiggy",
                price_memory_last=32,
                price_memory_median=34,
                price_memory_observations=2,
                price_memory_trend="down",
                deal_score="good",
                truth_score=MarketTruthScore(score=0.88, label="reliable"),
                nodes=[],
                edges=[],
                warnings=["Market data is stale"],
                reasons=["Available on market"],
            )
        ],
        nodes=[],
        edges=[],
    )

    monkeypatch.setattr(screen, "build_market_intelligence_graph", lambda db, inventory, user_id="": graph)

    html = screen.market_intelligence_view()
    assert "Market Intelligence Graph" in html
    assert "Tomato" in html
    assert "Buy Now" in html
    assert "Truth" in html

