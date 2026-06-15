"""Regression tests for the memory-facts service (2026-06-15).

The memory-facts service extracts concrete "ShopStack remembers" facts
from the household's purchase history and renders them as
intelligence cards. The extraction rules are pinned by these tests.
"""
from __future__ import annotations

from shopstack.services.memory_facts import (
    MEMORY_FACT_THRESHOLDS,
    MemoryFact,
    extract_memory_facts,
    render_memory_facts,
)


class TestExtractMemoryFactsEmpty:
    def test_no_cadence_no_diet(self):
        facts = extract_memory_facts()
        assert facts == []


class TestExtractMemoryFactsCadence:
    def test_cadence_below_threshold_ignored(self):
        cadence = {
            "milk": {"count": 2, "avg_interval_days": 3.0},
        }
        facts = extract_memory_facts(cadence_data=cadence)
        # min_purchases_for_cadence_fact = 3; 2 is below.
        assert facts == []

    def test_cadence_at_threshold_included(self):
        cadence = {
            "milk": {"count": 3, "avg_interval_days": 3.0},
        }
        facts = extract_memory_facts(cadence_data=cadence)
        assert len(facts) == 1
        assert facts[0].title == "Milk"
        assert "every 3 days" in facts[0].fact

    def test_cadence_fact_uses_singular_for_one_day(self):
        cadence = {
            "milk": {"count": 5, "avg_interval_days": 1.0},
        }
        facts = extract_memory_facts(cadence_data=cadence)
        # 1 day, not 1 days
        assert "every 1 day." in facts[0].fact

    def test_cadence_caps_at_max_cards(self):
        # max_cards_in_memory_section = 8
        cadence = {
            f"item_{i}": {"count": 10, "avg_interval_days": float(i + 1)}
            for i in range(20)
        }
        facts = extract_memory_facts(cadence_data=cadence)
        assert len(facts) == MEMORY_FACT_THRESHOLDS["max_cards_in_memory_section"]

    def test_confidence_label_per_fact(self):
        cadence = {
            "milk": {"count": 12, "avg_interval_days": 3.0},
        }
        facts = extract_memory_facts(cadence_data=cadence)
        assert facts[0].confidence is not None
        assert facts[0].confidence.level == "high"


class TestExtractMemoryFactsDietary:
    def test_vegetarian_dietary(self):
        facts = extract_memory_facts(dietary_preference="vegetarian")
        diet = next((f for f in facts if f.title == "Diet"), None)
        assert diet is not None
        assert "Vegetarian" in diet.fact
        assert "filtered" in diet.fact.lower()

    def test_vegan_dietary(self):
        facts = extract_memory_facts(dietary_preference="vegan")
        diet = next((f for f in facts if f.title == "Diet"), None)
        assert diet is not None
        assert "Vegan" in diet.fact

    def test_omnivore_dietary(self):
        facts = extract_memory_facts(dietary_preference="omnivore")
        diet = next((f for f in facts if f.title == "Diet"), None)
        assert diet is not None
        assert "Omnivore" in diet.fact
        # Omnivore does NOT have the "filtered" copy.
        assert "filtered" not in diet.fact.lower()

    def test_dietary_appears_alongside_cadence(self):
        cadence = {"milk": {"count": 5, "avg_interval_days": 3.0}}
        facts = extract_memory_facts(
            cadence_data=cadence, dietary_preference="vegetarian",
        )
        # Both Milk and Diet cards present.
        titles = {f.title for f in facts}
        assert "Milk" in titles
        assert "Diet" in titles


class TestRenderMemoryFacts:
    def test_empty_renders_actionable_state(self):
        # When no facts are known, the renderer should produce an
        # actionable empty state — not a wall of zeros.
        html = render_memory_facts(facts=[])
        assert "Memory is empty" in html
        # Actionable: must mention the next step (add a purchase, etc.)
        lower = html.lower()
        assert "add" in lower or "log" in lower, (
            "memory empty state should suggest the next action"
        )

    def test_with_facts_renders_cards(self):
        facts = [
            MemoryFact(
                title="Milk",
                fact="You buy it every 3 days.",
                supporting_evidence="Logged 12 purchases.",
            ),
        ]
        html = render_memory_facts(facts=facts)
        assert "intelligence-card" in html
        assert "Milk" in html
        assert "every 3 days" in html


class TestThresholdsDocumented:
    """The threshold constants are pinned to a known value."""

    def test_min_purchases_for_cadence_is_3(self):
        # 3 is the legacy "enough history" floor used in the
        # decision engine for predictive restock.
        assert MEMORY_FACT_THRESHOLDS["min_purchases_for_cadence_fact"] == 3

    def test_max_cards_is_8(self):
        assert MEMORY_FACT_THRESHOLDS["max_cards_in_memory_section"] == 8
