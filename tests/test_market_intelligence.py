from __future__ import annotations

from datetime import date

import pytest

from shopstack.market.schema import MarketSnapshot, NormalizedMarketRecord
from shopstack.schemas.models import DecisionResult
from shopstack.services.market_intelligence import (
    MarketIntelligenceGraph,
    MarketCluster,
    MarketTruthScore,
    build_market_intelligence_graph,
    project_ask_context,
    project_market_lens,
    project_today,
    project_unified_shopping,
)


class _Registry:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    def all_snapshots(self):
        return self._snapshots

    def registered(self):
        return list(self._snapshots)

    def latest(self, source_id: str):
        return self._snapshots.get(source_id)


def _record(
    *,
    source: str,
    canonical_name: str,
    raw_name: str,
    price_inr: float,
    raw_size: str = "500g",
    is_available: bool = True,
    is_combo: bool = False,
    is_weight_based: bool = True,
    is_piece_based: bool = False,
    is_size_class: bool = False,
    tag: str = "",
    is_ad: bool = False,
    is_upgrade: bool = False,
    component_names: list[str] | None = None,
    price_per_kg: float | None = None,
) -> NormalizedMarketRecord:
    return NormalizedMarketRecord(
        source=source,
        source_category="fresh_vegetables",
        raw_name=raw_name,
        canonical_name=canonical_name,
        description=raw_name,
        raw_size=raw_size,
        normalized_quantity=500.0 if is_weight_based else 1.0,
        normalized_unit="g" if is_weight_based else "pieces",
        package_count=1,
        is_combo=is_combo,
        is_weight_based=is_weight_based,
        is_piece_based=is_piece_based,
        is_size_class=is_size_class,
        size_class="",
        price_inr=price_inr,
        mrp_inr=price_inr + 10,
        discount_percent_displayed=0.0,
        discount_amount_inr=0.0,
        computed_discount_percent=0.0,
        availability="available" if is_available else "sold_out",
        is_available=is_available,
        tag=tag,
        is_ad=is_ad,
        is_upgrade=is_upgrade,
        card_index=1,
        delivery_time="20 min",
        captured_at="2026-06-01",
        snapshot_id="snap-1",
        price_per_kg=price_per_kg if price_per_kg is not None else (price_inr * 2 if is_weight_based else None),
        price_per_100g=price_inr / 5 if is_weight_based else None,
        price_per_piece=price_inr if is_piece_based else None,
        normalization_warnings=[],
        component_names=component_names or [],
        variety="",
        brand="",
    )


def test_market_intelligence_graph_combos_substitutions_and_staleness(db, tool_registry, monkeypatch: pytest.MonkeyPatch):
    # Guard: the test expects precise control over inventory and market data
    pre_existing = db.get_inventory()
    assert len(pre_existing) == 0, f"Expected empty db, got {len(pre_existing)} items"

    tool_registry.add_inventory_item(
        canonical_name="onion",
        display_name="Onion",
        quantity=1.0,
        unit="kg",
    )
    tool_registry.add_inventory_item(
        canonical_name="potato",
        display_name="Potato",
        quantity=0.5,
        unit="kg",
    )
    tool_registry.record_price_observation("tomato", 34, quantity=500, unit="g", store_name="Local Kirana")
    tool_registry.record_price_observation("tomato", 32, quantity=500, unit="g", store_name="Swiggy Instamart")

    snapshot = MarketSnapshot(
        snapshot_id="snap-1",
        source="swiggy",
        source_category="fresh_vegetables",
        captured_at="2026-06-01",
        raw_records=[],
        normalized_records=[
            _record(
                source="swiggy",
                canonical_name="tomato",
                raw_name="Tomato",
                price_inr=28,
                tag="ad",
                is_ad=True,
                price_per_kg=56,
            ),
            _record(
                source="swiggy",
                canonical_name="veg_combo",
                raw_name="Onion, Potato & Desi Tomato Combo",
                price_inr=99,
                raw_size="1 combo",
                is_combo=True,
                is_weight_based=False,
                is_piece_based=False,
                component_names=["onion", "potato", "tomato"],
                price_per_kg=None,
            ),
            _record(
                source="swiggy",
                canonical_name="cauliflower",
                raw_name="Cauliflower",
                price_inr=45,
                is_available=False,
                tag="upgrade",
                is_upgrade=True,
                price_per_kg=90,
            ),
            _record(
                source="swiggy",
                canonical_name="cabbage",
                raw_name="Cabbage",
                price_inr=22,
                price_per_kg=44,
            ),
        ],
        analytics={},
    )

    registry = _Registry({"swiggy": snapshot})
    graph = build_market_intelligence_graph(db, tool_registry, registry=registry)

    assert isinstance(graph, MarketIntelligenceGraph)
    assert graph.snapshot_freshness == "stale"
    assert graph.summary["items_scored"] >= 4
    assert graph.summary["sponsored"] >= 1
    assert any(cluster.canonical_name == "veg_combo" and cluster.graph_lane == "compare" for cluster in graph.clusters)
    assert any(cluster.canonical_name == "cauliflower" and cluster.graph_lane == "substitute" for cluster in graph.clusters)

    tomato = next(cluster for cluster in graph.clusters if cluster.canonical_name == "tomato")
    assert tomato.truth_score.label in {"reliable", "reference", "low confidence"}
    assert any("sponsored" in warning.lower() for warning in tomato.warnings)
    assert any("stale" in warning.lower() for warning in tomato.truth_score.warnings)
    assert tomato.price_memory_observations >= 2
    assert tomato.market_source == "swiggy"
    assert tomato.decision is not None
    assert tomato.truth_breakdown.freshness_score == tomato.truth_score.freshness_score
    assert tomato.reason_atoms
    assert tomato.evidence_claims
    assert tomato.action_intent is not None
    assert tomato.evidence_claims[0].claim_type == "snapshot"
    assert tomato.action_intent.primary_action == tomato.lane

    payload = graph.to_dict()
    assert payload["summary"]["items_scored"] == graph.summary["items_scored"]
    assert payload["clusters"]

    today = project_today(graph)
    assert today.title == "Today"
    assert today.summary["items"] >= 1
    assert today.next_actions

    projection = project_unified_shopping(graph, ["tomato", "veg_combo"])
    assert "tomato" in projection.matched_names
    assert any(cluster.canonical_name == "tomato" for cluster in projection.clusters)
    assert projection.title == "Unified Shopping"

    lens = project_market_lens(graph, "tomato")
    assert lens.title == "Market Lens: tomato"
    assert "tomato" in lens.matched_names
    ask = project_ask_context(graph, "tomato")
    assert ask.title.startswith("Ask Context")
    assert ask.clusters


def test_market_intelligence_graph_smoke_empty(db, tool_registry, monkeypatch: pytest.MonkeyPatch):
    # Ensure the fixture db is truly empty (guard against suite-level contamination)
    inv = db.get_inventory()
    assert inv == [], f"smoke_empty test requires empty fixture db, got {len(inv)} items"

    registry = _Registry({})
    graph = build_market_intelligence_graph(db, tool_registry, registry=registry)
    assert graph.summary["items_scored"] == 0, (
        f"Expected 0 items with empty db and registry, got {graph.summary['items_scored']}. "
        "Possible suite-level state contamination from session-scoped app imports."
    )
    assert graph.snapshot_freshness in {"unknown", "stale"}
