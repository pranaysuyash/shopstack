"""Tests for the waste reduction coach.

The coach upgrades ``detect_waste_patterns`` observations ("you waste
30% of tomatoes") into recommendations ("buy 500g instead of 1kg, or
freeze"). Tests cover:

- Each pattern (high+overstocked, high+frequent, medium, low) maps to
  the right action kind.
- The renderer surfaces the recommendation with severity color coding.
- XSS-safe HTML output.
- Empty / no-signal inputs return empty strings.
"""

from __future__ import annotations

import pytest

from shopstack.services.waste_coach import (
    coach_waste_signal,
    coach_waste_signals,
    render_waste_coach_html,
)


def _signal(
    cname: str = "tomato",
    *,
    display_name: str | None = None,
    current_qty: float = 0,
    unit: str = "kg",
    waste_risk: str = "high",
    avg_interval_days: float | None = 5.0,
    reason: str = "high waste risk",
) -> dict:
    return {
        "canonical_name": cname,
        "display_name": display_name or cname.replace("_", " ").title(),
        "current_quantity": current_qty,
        "unit": unit,
        "waste_risk": waste_risk,
        "avg_interval_days": avg_interval_days,
        "reason": reason,
    }


class TestCoachWasteSignal:
    def test_high_overstocked_and_frequent_recommends_tinned_swap(self):
        sig = _signal(current_qty=2.0, avg_interval_days=1.0)
        rec = coach_waste_signal(sig)
        assert rec.action_kind == "tinned_swap"
        assert "tinned" in rec.action.lower() or "frozen" in rec.action.lower()
        assert rec.severity == "high"

    def test_high_overstocked_only_recommends_smaller_pack(self):
        sig = _signal(current_qty=2.5, avg_interval_days=5.0)
        rec = coach_waste_signal(sig)
        assert rec.action_kind == "smaller_pack"
        assert "smaller pack" in rec.action.lower() or "smaller" in rec.action.lower()

    def test_high_frequent_only_recommends_tinned_swap(self):
        sig = _signal(current_qty=0.5, avg_interval_days=1.0)
        rec = coach_waste_signal(sig)
        # 0.5 is not > 1.0, so not overstocked; 1.0 day interval = frequent
        assert rec.action_kind == "tinned_swap"

    def test_high_no_overstocked_no_frequent_recommends_freeze(self):
        sig = _signal(current_qty=0.5, avg_interval_days=5.0)
        rec = coach_waste_signal(sig)
        assert rec.action_kind == "freeze"

    def test_medium_overstocked_recommends_smaller_pack(self):
        sig = _signal(waste_risk="medium", current_qty=2.0, avg_interval_days=5.0)
        rec = coach_waste_signal(sig)
        assert rec.action_kind == "smaller_pack"
        assert rec.severity == "medium"

    def test_medium_no_overstocked_recommends_plan(self):
        sig = _signal(waste_risk="medium", current_qty=0.5, avg_interval_days=5.0)
        rec = coach_waste_signal(sig)
        assert rec.action_kind == "plan_around_use"

    def test_low_risk_falls_through_to_plan(self):
        sig = _signal(waste_risk="low", current_qty=0.5, avg_interval_days=5.0)
        rec = coach_waste_signal(sig)
        assert rec.action_kind == "plan_around_use"
        assert rec.severity == "low"

    def test_missing_avg_interval_treated_as_not_frequent(self):
        sig = _signal(current_qty=2.0, avg_interval_days=None)
        rec = coach_waste_signal(sig)
        # overstocked but not frequent → smaller_pack
        assert rec.action_kind == "smaller_pack"

    def test_metadata_preserved(self):
        sig = _signal(current_qty=3.0, unit="kg", avg_interval_days=2.0)
        rec = coach_waste_signal(sig)
        assert rec.metadata["current_quantity"] == 3.0
        assert rec.metadata["unit"] == "kg"
        assert rec.metadata["overstocked"] is True


class TestCoachWasteSignals:
    def test_empty_returns_empty(self):
        assert coach_waste_signals([]) == []

    def test_batch(self):
        sigs = [_signal("tomato"), _signal("onion")]
        recs = coach_waste_signals(sigs)
        assert len(recs) == 2


class TestRenderWasteCoachHtml:
    def test_no_signals_returns_empty(self):
        assert render_waste_coach_html([]) == ""

    def test_renders_recommendations(self):
        sigs = [_signal(current_qty=2.0, avg_interval_days=1.0)]
        html = render_waste_coach_html(sigs)
        assert "Waste Coach" in html
        assert "Tomato" in html
        assert "→" in html  # arrow before action

    def test_high_severity_red_icon(self):
        sigs = [_signal(waste_risk="high", current_qty=2.0, avg_interval_days=1.0)]
        html = render_waste_coach_html(sigs)
        assert "var(--red)" in html
        assert "⚠️" in html

    def test_medium_severity_amber_icon(self):
        sigs = [_signal(waste_risk="medium", current_qty=2.0, avg_interval_days=5.0)]
        html = render_waste_coach_html(sigs)
        assert "var(--amber)" in html
        assert "💡" in html

    def test_html_escapes_xss(self):
        sigs = [
            {
                "canonical_name": "weird<script>",
                "display_name": "Weird<script>",
                "current_quantity": 1.0,
                "unit": "kg",
                "waste_risk": "high",
                "avg_interval_days": 1.0,
                "reason": "<script>alert(1)</script>",
            }
        ]
        html = render_waste_coach_html(sigs)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html

    def test_caps_to_4_signals(self):
        """Top 4 recommendations only."""
        sigs = [_signal(f"item_{i}", current_qty=2.0) for i in range(10)]
        html = render_waste_coach_html(sigs)
        # The observation line is per-recommendation; count the arrows
        arrow_count = html.count("→")
        assert arrow_count == 4
