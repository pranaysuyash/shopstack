"""Tests for the Pass 19 "Why?" toggle on decision cards.

**Why this exists (motto_v3 §0.14 product reality):**

The decision engine produces structured reasons and evidence
on every ``DecisionResult``. The Pass 18 explainability
service surfaces this as a ``DecisionExplanation``. The Pass
19 Why? toggle surfaces it in the Gradio UI: each decision
card now has a native HTML5 ``<details>`` element that the
user can expand to see the full explanation.

These tests guard the integration: the toggle is rendered,
the explanation is embedded, and the markup is XSS-safe.
"""
from __future__ import annotations

import pytest

from shopstack.schemas.models import DecisionEvidence, DecisionResult
from shopstack.ui.components.cards import render_unified_decision_card


def _make_result(
    *,
    canonical_name: str = "milk",
    display_name: str = "Milk",
    action: str = "buy",
    confidence: float = 0.7,
    reason: str = "only 0.3L at home",
    reasons: list[str] | None = None,
    evidence: list[DecisionEvidence] | None = None,
    warnings: list | None = None,
) -> DecisionResult:
    return DecisionResult(
        canonical_name=canonical_name,
        display_name=display_name,
        action=action,
        confidence=confidence,
        reason=reason,
        reasons=reasons or [],
        evidence=evidence or [],
        warnings=warnings or [],
    )


class TestWhyToggle:
    def test_why_toggle_present_when_decision_has_reasons(self):
        d = _make_result(reasons=["only 0.3L at home"])
        html = render_unified_decision_card(d)
        assert "why-toggle" in html
        assert "<details" in html
        assert "Why?" in html

    def test_why_toggle_present_when_decision_has_evidence(self):
        d = _make_result(
            reasons=[],
            evidence=[DecisionEvidence(source="inventory", value="0.3 L at home", confidence=0.9)],
        )
        html = render_unified_decision_card(d)
        assert "why-toggle" in html

    def test_why_toggle_present_when_decision_has_warnings(self):
        from shopstack.schemas.models import DecisionWarning
        d = _make_result(
            reasons=[],
            warnings=[DecisionWarning(code="stale_data", message="data is old", severity="info")],
        )
        html = render_unified_decision_card(d)
        assert "why-toggle" in html

    def test_why_toggle_absent_when_no_explanation_available(self):
        """If a decision has no reasons/evidence/warnings, the Why?
        toggle is omitted (nothing to explain)."""
        d = _make_result(reasons=[], evidence=[])
        html = render_unified_decision_card(d)
        # No reasons/evidence/warnings → no explanation → no toggle.
        assert "why-toggle" not in html

    def test_why_toggle_contains_full_explanation(self):
        d = _make_result(
            reasons=["only 0.3L at home", "last bought 5 days ago"],
            evidence=[DecisionEvidence(source="inventory", value="0.3 L at home", confidence=0.9)],
        )
        html = render_unified_decision_card(d)
        # The toggle wraps the full explanation.
        assert "decision-explanation" in html  # the explanation section class
        # And the summary text from the explainability service.
        assert "ShopStack suggests" in html
        assert "milk" in html

    def test_why_toggle_summary_uses_native_html5_details(self):
        """The toggle is a native <details>/<summary>, not a custom JS widget.

        This is the mode-portable choice: <details> works in
        Gradio's iframe, in any mobile/web UI, and in the
        CLI's HTML export.
        """
        d = _make_result(reasons=["only 0.3L at home"])
        html = render_unified_decision_card(d)
        # Must use <details> and <summary>, not <button onclick="...">.
        assert "<details" in html
        assert "<summary" in html
        # The data-action / onclick JS pattern is NOT used.
        assert "onclick=" not in html.split("why-toggle")[1].split("</details>")[0]

    def test_why_toggle_is_xss_safe(self):
        """An attacker-controlled reason is escaped in the Why? toggle."""
        d = _make_result(
            canonical_name="<script>alert('xss')</script>",
            display_name="<script>alert('xss')</script>",
            reason="<img src=x onerror=alert(1)>",
            reasons=["<img src=x onerror=alert(1)>"],
        )
        html = render_unified_decision_card(d)
        # No raw <script> in the rendered HTML.
        assert "<script>" not in html
        # But the escaped form is there.
        assert "&lt;script&gt;" in html

    def test_why_toggle_per_decision_does_not_pollute_globals(self):
        """Each card's Why? toggle is independent (no shared state)."""
        d1 = _make_result(canonical_name="milk", reasons=["a"])
        d2 = _make_result(canonical_name="rice", reasons=["b"])
        h1 = render_unified_decision_card(d1)
        h2 = render_unified_decision_card(d2)
        # Each card has its own <details> (multiple toggles on the
        # page, each independent).
        assert h1.count("<details") == 1
        assert h2.count("<details") == 1
        # The canonical name is in each card.
        assert "milk" in h1
        assert "rice" in h2
        # The reason "a" is in h1 but not in h2.
        assert "a" in h1
        assert "b" in h2

    def test_why_toggle_does_not_break_existing_action_button(self):
        """The Why? toggle is added alongside the existing action button."""
        d = _make_result(
            action="buy",
            reasons=["only 0.3L at home"],
        )
        html = render_unified_decision_card(d)
        # Both the action button and the Why? toggle are present.
        assert "action-tile" in html
        assert "Buy" in html
        assert "why-toggle" in html
        assert "Why?" in html

    def test_why_toggle_does_not_break_for_non_action_decisions(self):
        """Decisions without an action button (e.g. watch, substitute)
        still get the Why? toggle if they have reasons/evidence."""
        d = _make_result(
            action="watch",
            reasons=["price trending up"],
        )
        html = render_unified_decision_card(d)
        # No action button for "watch".
        assert "action-tile" not in html
        # But the Why? toggle is still there.
        assert "why-toggle" in html

    def test_why_toggle_works_for_every_action(self):
        """The Why? toggle renders for every DecisionAction value."""
        from shopstack.schemas.models import DecisionAction
        for action in DecisionAction:
            d = _make_result(action=action.value, reasons=[f"because of {action.value}"])
            html = render_unified_decision_card(d)
            assert "why-toggle" in html, f"missing why-toggle for action={action.value}"
