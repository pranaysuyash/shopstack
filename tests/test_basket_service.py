from __future__ import annotations

from shopstack.basket.service import optimize_baskets
from shopstack.schemas.models import DecisionResult, DecisionSet


class _FakeRegistry:
    def __init__(self, snapshots):
        self._snapshots = snapshots

    def all_snapshots(self):
        return self._snapshots

    def registered(self):
        return ["swiggy", "blinkit", "zepto", "dmart"]

    def latest(self, source_id: str):
        return None

    def load(self, source_id: str):
        raise RuntimeError("snapshot file not available")

    def freshness_of(self, source_id: str):
        return {"is_stale": False}


def _buy_decision(*, canonical_name: str, display_name: str) -> DecisionResult:
    return DecisionResult(
        canonical_name=canonical_name,
        display_name=display_name,
        action="buy",
    )


def test_optimize_baskets_falls_back_to_decision_only_if_no_snapshots():
    decision_set = DecisionSet(decisions=[_buy_decision(canonical_name="tomato", display_name="Tomato")])
    baskets = optimize_baskets(decision_set, _FakeRegistry({}))

    assert len(baskets) == 1
    assert baskets[0].source_name == "decision_only"
    assert baskets[0].total_cost == 0
    assert baskets[0].items[0].price_status == "unavailable"


def test_optimize_baskets_falls_back_if_snapshots_have_no_rows():
    class EmptySnapshot:
        normalized_records = []

    decision_set = DecisionSet(decisions=[_buy_decision(canonical_name="tomato", display_name="Tomato")])
    registry = _FakeRegistry({"swiggy": EmptySnapshot()})

    baskets = optimize_baskets(decision_set, registry)
    assert len(baskets) == 1
    assert baskets[0].source_name == "decision_only"
    assert baskets[0].items[0].notes is not None
