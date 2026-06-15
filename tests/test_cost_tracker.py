"""Tests for shopstack.cost_tracker — LLM cost ledger and budget guard.

Per motto_v3 §0.5 (Evidence Tiers), these are Tier 2 tests:
they verify the static behavior of the cost tracker against
realistic inputs and the documented contract.
"""

from __future__ import annotations

from shopstack.cost_tracker import (
    CostRecord,
    CostTracker,
    estimate_cost_usd,
    estimate_model_tier,
)


class TestEstimateModelTier:
    def test_short_request_routes_to_haiku(self):
        """Requests < 300 chars route to haiku (cheapest)."""
        assert estimate_model_tier(text_length=100) == "haiku"

    def test_medium_request_routes_to_sonnet(self):
        """Requests 300-999 chars route to sonnet."""
        assert estimate_model_tier(text_length=500) == "sonnet"

    def test_long_request_routes_to_sonnet(self):
        """Requests >= 1000 chars default to sonnet."""
        assert estimate_model_tier(text_length=5000) == "sonnet"

    def test_few_items_with_short_text_uses_haiku(self):
        """item_count < 30 is required for haiku tier."""
        assert estimate_model_tier(text_length=100, item_count=5) == "haiku"

    def test_many_items_demotes_to_sonnet(self):
        """When item_count >= 30, request demotes to sonnet even for short text."""
        assert estimate_model_tier(text_length=100, item_count=50) == "sonnet"


class TestEstimateCostUsd:
    def test_known_cloud_model_uses_pricing(self):
        """GPT-4o: $2.50/MTok input, $10.00/MTok output."""
        cost = estimate_cost_usd("gpt-4o", input_tokens=1_000_000, output_tokens=1_000_000)
        assert cost == round(2.50 + 10.00, 6) == 12.50

    def test_known_mini_model_uses_pricing(self):
        """GPT-4o-mini: $0.15/MTok input, $0.60/MTok output."""
        cost = estimate_cost_usd("gpt-4o-mini", input_tokens=2_000_000, output_tokens=1_000_000)
        assert cost == round(0.30 + 0.60, 6) == 0.90

    def test_local_model_is_free(self):
        """Local models (MLX, GGUF, Llama) are priced at $0."""
        assert estimate_cost_usd("mlx-community/Llama-3.2-3B-Instruct-4bit", 1000, 1000) == 0.0
        assert estimate_cost_usd("unsloth/Llama-3.2-3B-Instruct-GGUF", 1000, 1000) == 0.0

    def test_mock_model_is_free(self):
        """The mock provider is priced at $0."""
        assert estimate_cost_usd("mock", 1000, 1000) == 0.0

    def test_unknown_cloud_model_falls_back_to_sonnet(self):
        """An unknown model key falls back to the sonnet rate (not $0).

        This is the budget-guard behavior: silent $0 would let a
        cloud-backed model bypass the cost limit.
        """
        cost = estimate_cost_usd("unknown-future-model-xyz", 1_000_000, 1_000_000)
        assert cost > 0  # Not silently $0
        # Conservative sonnet rate (~$4 per MTok total)
        assert cost >= 4.0

    def test_empty_model_key_falls_back_to_sonnet(self):
        """An empty model key is treated as unknown (conservative sonnet rate).

        Per the budget-guard design: don't silently return $0 for
        invalid model keys. Fall through to the conservative sonnet
        rate so the budget guard can still trip.
        """
        cost = estimate_cost_usd("", 1_000_000, 1_000_000)
        assert cost > 0  # Not silently $0
        assert cost >= 4.0  # conservative sonnet rate


class TestCostRecord:
    def test_construction(self):
        """CostRecord accepts all required fields."""
        rec = CostRecord(
            model="gpt-4o",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.0001,
            tier="sonnet",
        )
        assert rec.model == "gpt-4o"
        assert rec.input_tokens == 100
        assert rec.output_tokens == 50
        assert rec.cost_usd == 0.0001
        assert rec.tier == "sonnet"
        assert rec.latency_ms is None  # default

    def test_frozen(self):
        """CostRecord is frozen — attempts to mutate raise."""
        import pytest
        rec = CostRecord(
            model="mock", input_tokens=0, output_tokens=0,
            cost_usd=0.0, tier="mock",
        )
        with pytest.raises((AttributeError, Exception)):
            rec.cost_usd = 0.1  # type: ignore[misc]


class TestCostTracker:
    def test_default_budget(self):
        """Default budget is $1.00."""
        tracker = CostTracker()
        assert tracker.budget_limit == 1.00
        assert tracker.records == ()
        assert tracker.total_cost == 0.0
        assert not tracker.over_budget

    def test_add_returns_new_tracker(self):
        """add() is non-mutating: returns a new tracker."""
        tracker = CostTracker()
        rec = CostRecord(
            model="gpt-4o", input_tokens=100, output_tokens=50,
            cost_usd=0.001, tier="sonnet",
        )
        new_tracker = tracker.add(rec)

        # Original unchanged
        assert tracker.records == ()
        assert tracker.total_cost == 0.0

        # New tracker has the record
        assert len(new_tracker.records) == 1
        assert new_tracker.total_cost == 0.001
        assert new_tracker.total_input_tokens == 100
        assert new_tracker.total_output_tokens == 50

    def test_chained_adds_accumulate(self):
        """Multiple add() calls accumulate cost."""
        tracker = CostTracker(budget_limit=1.0)
        for i in range(5):
            rec = CostRecord(
                model="gpt-4o-mini", input_tokens=100_000, output_tokens=50_000,
                cost_usd=0.01, tier="haiku",
            )
            tracker = tracker.add(rec)

        assert len(tracker.records) == 5
        assert tracker.total_cost == 0.05
        assert tracker.total_input_tokens == 500_000
        assert tracker.total_output_tokens == 250_000
        assert not tracker.over_budget

    def test_over_budget_flag(self):
        """over_budget turns True when total_cost > budget_limit."""
        tracker = CostTracker(budget_limit=0.05)
        rec = CostRecord(
            model="gpt-4o", input_tokens=100, output_tokens=50,
            cost_usd=0.10, tier="sonnet",
        )
        tracker = tracker.add(rec)
        assert tracker.over_budget

    def test_summary_dict_shape(self):
        """summary() returns a JSON-serializable dict with expected keys."""
        tracker = CostTracker(budget_limit=0.50)
        rec = CostRecord(
            model="gpt-4o-mini", input_tokens=1000, output_tokens=500,
            cost_usd=0.001, tier="haiku", latency_ms=234.5,
        )
        tracker = tracker.add(rec)
        summary = tracker.summary()

        assert summary["total_cost"] == 0.001
        assert summary["total_input_tokens"] == 1000
        assert summary["total_output_tokens"] == 500
        assert summary["call_count"] == 1
        assert summary["budget_limit"] == 0.50
        assert summary["over_budget"] is False
        assert isinstance(summary["records"], list)
        assert summary["records"][0]["latency_ms"] == 234.5
