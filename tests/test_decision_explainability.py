"""Tests for the decision explainability service + renderer (Pass 18).

**Why this exists (motto_v3 §0.14 product reality):**

The decision engine already produces structured reasons and
evidence on every ``DecisionResult`` (see
``shopstack/schemas/models.py``). The product gap is that
this data is buried — neither the Gradio UI nor the CLI
surfaces it to the user.

These tests guard the smallest first-principles fix: the
``explainability`` service + the HTML/text renderers. The
service is a pure function (no I/O) so it's fast to test.

**Coverage:**

  - ``explain_decision`` produces a ``DecisionExplanation``
    with the documented shape, for each ``DecisionAction``.
  - The summary is composed from ``reasons`` (or falls back
    gracefully when reasons is empty).
  - The key_signal is the first non-empty reason.
  - The confidence_label maps 0.0-1.0 to 5 buckets.
  - The confidence_caveat is non-empty when confidence is low
    OR when warnings are present.
  - The HTML renderer is XSS-safe (escapes all dynamic strings).
  - The text renderer produces a non-empty, multi-line output.
  - The HTTP-serializable dict has the right keys.
"""
from __future__ import annotations

import pytest

from shopstack.schemas.models import (
    DecisionEvidence,
    DecisionResult,
    DecisionWarning,
)
from shopstack.services.explainability import (
    DecisionExplanation,
    _confidence_label_for,
    explain_decision,
    explain_decision_set,
    explanation_to_dict,
)
from shopstack.ui.renderers.explainability import (
    render_explanation_html,
    render_explanation_text,
)


# ── Fixtures ────────────────────────────────────────────────────────


def _make_result(
    *,
    canonical_name: str = "milk",
    action: str = "buy",
    confidence: float = 0.7,
    reasons: list[str] | None = None,
    evidence: list[DecisionEvidence] | None = None,
    warnings: list[DecisionWarning] | None = None,
    freshness_status: str = "fresh",
    freshness_label: str = "today",
) -> DecisionResult:
    return DecisionResult(
        canonical_name=canonical_name,
        display_name=canonical_name.title(),
        action=action,
        confidence=confidence,
        reasons=reasons or [],
        evidence=evidence or [],
        warnings=warnings or [],
        data_freshness=freshness_status,
        data_freshness_label=freshness_label,
    )


# ── Confidence label buckets ───────────────────────────────────────


class TestConfidenceLabelFor:
    def test_very_low_below_0_2(self):
        assert _confidence_label_for(0.0) == "very low"
        assert _confidence_label_for(0.1) == "very low"
        assert _confidence_label_for(0.19) == "very low"

    def test_low_0_2_to_0_4(self):
        assert _confidence_label_for(0.2) == "low"
        assert _confidence_label_for(0.3) == "low"
        assert _confidence_label_for(0.39) == "low"

    def test_medium_0_4_to_0_6(self):
        assert _confidence_label_for(0.4) == "medium"
        assert _confidence_label_for(0.5) == "medium"
        assert _confidence_label_for(0.59) == "medium"

    def test_high_0_6_to_0_8(self):
        assert _confidence_label_for(0.6) == "high"
        assert _confidence_label_for(0.7) == "high"
        assert _confidence_label_for(0.79) == "high"

    def test_very_high_0_8_and_above(self):
        assert _confidence_label_for(0.8) == "very high"
        assert _confidence_label_for(0.9) == "very high"
        assert _confidence_label_for(1.0) == "very high"


# ── explain_decision — happy paths for each action ────────────────


class TestExplainDecision:
    @pytest.mark.parametrize("action", ["buy", "skip", "use_soon", "compare", "wait", "substitute", "watch"])
    def test_every_action_produces_a_valid_explanation(self, action):
        """Every ``DecisionAction`` value produces a valid explanation.

        Guards against the lookup table drifting out of sync
        with the ``DecisionAction`` enum.
        """
        result = _make_result(action=action, reasons=[f"because of {action}"])
        exp = explain_decision(result)
        assert isinstance(exp, DecisionExplanation)
        assert exp.action == action
        assert exp.canonical_name == "milk"
        # Each action has a non-empty override hint.
        assert exp.override_hint, f"missing override_hint for action={action!r}"
        # The summary mentions the action verb.
        assert action in exp.summary or action.replace("_", " ") in exp.summary

    def test_summary_composed_from_reasons(self):
        """The summary uses the reasons from the DecisionResult."""
        result = _make_result(
            action="buy",
            reasons=["only 0.3L at home", "last bought 5 days ago"],
        )
        exp = explain_decision(result)
        assert "0.3L at home" in exp.summary
        assert "last bought 5 days ago" in exp.summary
        # And the action verb.
        assert "buy" in exp.summary

    def test_summary_falls_back_when_no_reasons(self):
        """When reasons is empty, the summary uses the action + freshness."""
        result = _make_result(action="skip", reasons=[], freshness_label="3 days old")
        exp = explain_decision(result)
        assert "skip" in exp.summary
        assert "3 days old" in exp.summary
        # No crash, no empty summary.
        assert exp.summary

    def test_key_signal_is_first_nonempty_reason(self):
        result = _make_result(
            reasons=["", "  ", "the actual signal", "second reason"],
        )
        exp = explain_decision(result)
        assert exp.key_signal == "the actual signal"

    def test_key_signal_falls_back_to_action(self):
        """When all reasons are empty, key_signal is ``action=<action>``."""
        result = _make_result(reasons=["", ""], action="skip")
        exp = explain_decision(result)
        assert exp.key_signal == "action=skip"

    def test_low_confidence_adds_caveat(self):
        """Confidence < 0.4 adds a caveat about the system not being sure."""
        result = _make_result(confidence=0.2)
        exp = explain_decision(result)
        assert "isn't very confident" in exp.confidence_caveat
        assert exp.confidence_label == "low"

    def test_warnings_add_caveat(self):
        """Warnings add a caveat about caveats."""
        result = _make_result(
            warnings=[DecisionWarning(code="x", message="y", severity="info")],
        )
        exp = explain_decision(result)
        assert "caveat" in exp.confidence_caveat

    def test_warnings_count_caveat_uses_correct_pluralization(self):
        """The caveat uses the right singular/plural form."""
        r1 = _make_result(warnings=[
            DecisionWarning(code="a", message="x", severity="info"),
        ])
        r2 = _make_result(warnings=[
            DecisionWarning(code="a", message="x", severity="info"),
            DecisionWarning(code="b", message="y", severity="warning"),
        ])
        e1 = explain_decision(r1)
        e2 = explain_decision(r2)
        assert "1 caveat worth" in e1.confidence_caveat
        assert "2 caveats worth" in e2.confidence_caveat

    def test_high_confidence_no_warnings_no_caveat(self):
        """High confidence + no warnings = empty caveat."""
        result = _make_result(confidence=0.9, warnings=[])
        exp = explain_decision(result)
        assert exp.confidence_caveat == ""

    def test_evidence_summary_renders_source_value(self):
        """Each evidence entry becomes ``source: value``."""
        result = _make_result(evidence=[
            DecisionEvidence(source="inventory", value="0.3 L at home", confidence=0.9),
            DecisionEvidence(source="purchase_history", value="avg interval 3 days", confidence=0.6),
        ])
        exp = explain_decision(result)
        assert "inventory: 0.3 L at home" in exp.evidence_summary
        assert "purchase history: avg interval 3 days" in exp.evidence_summary

    def test_evidence_summary_falls_back_to_freshness(self):
        """When evidence is empty, surface data freshness instead."""
        result = _make_result(evidence=[], freshness_label="3 days old")
        exp = explain_decision(result)
        assert "data freshness: 3 days old" in exp.evidence_summary

    def test_warnings_serialized_to_dicts(self):
        """Warnings become JSON-serializable dicts."""
        result = _make_result(warnings=[
            DecisionWarning(code="stale_data", message="x", severity="info"),
        ])
        exp = explain_decision(result)
        assert exp.warnings == [{"code": "stale_data", "message": "x", "severity": "info"}]

    def test_round_trip_canonical_name(self):
        """The explanation preserves the canonical name verbatim."""
        result = _make_result(canonical_name="toilet_paper")
        exp = explain_decision(result)
        assert exp.canonical_name == "toilet_paper"

    def test_canonical_name_underscores_replaced_in_summary(self):
        """The summary uses spaces instead of underscores for readability."""
        result = _make_result(canonical_name="toilet_paper", reasons=["low stock"])
        exp = explain_decision(result)
        assert "toilet paper" in exp.summary
        assert "toilet_paper" not in exp.summary


# ── explain_decision_set — bulk operation ──────────────────────────


class TestExplainDecisionSet:
    def test_bulk_explanation_preserves_order(self):
        results = [
            _make_result(canonical_name="a", action="buy", reasons=["low"]),
            _make_result(canonical_name="b", action="skip", reasons=["fresh"]),
            _make_result(canonical_name="c", action="use_soon", reasons=["expiring"]),
        ]
        explanations = explain_decision_set(results)
        assert len(explanations) == 3
        assert [e.canonical_name for e in explanations] == ["a", "b", "c"]

    def test_bulk_respects_limit(self):
        results = [_make_result(canonical_name=f"x{i}") for i in range(10)]
        explanations = explain_decision_set(results, limit=3)
        assert len(explanations) == 3


# ── explanation_to_dict — JSON serialization ────────────────────────


class TestExplanationToDict:
    def test_to_dict_has_all_keys(self):
        result = _make_result()
        exp = explain_decision(result)
        d = explanation_to_dict(exp)
        assert set(d.keys()) == {
            "item_id", "canonical_name", "action", "confidence",
            "summary", "key_signal", "confidence_label", "confidence_caveat",
            "warnings", "override_hint", "evidence_summary",
            "freshness_status", "freshness_label",
        }

    def test_to_dict_is_json_serializable(self):
        """The dict can round-trip through ``json.dumps``."""
        import json
        result = _make_result()
        exp = explain_decision(result)
        d = explanation_to_dict(exp)
        # No crash.
        json.dumps(d, default=str)


# ── HTML renderer ───────────────────────────────────────────────────


class TestRenderExplanationHtml:
    def test_html_contains_section_wrapper(self):
        result = _make_result()
        exp = explain_decision(result)
        html = render_explanation_html(exp)
        assert html.startswith("<section class='decision-explanation'")
        assert html.endswith("</section>")

    def test_html_includes_canonical_name_as_attribute(self):
        result = _make_result(canonical_name="milk")
        exp = explain_decision(result)
        html = render_explanation_html(exp)
        assert "data-canonical-name='milk'" in html

    def test_html_includes_action_verb(self):
        result = _make_result(action="buy")
        exp = explain_decision(result)
        html = render_explanation_html(exp)
        assert "buy" in html.lower()

    def test_html_includes_confidence_label(self):
        result = _make_result(confidence=0.85)
        exp = explain_decision(result)
        html = render_explanation_html(exp)
        assert "very high" in html
        assert "85%" in html

    def test_html_includes_warnings_when_present(self):
        result = _make_result(warnings=[
            DecisionWarning(code="stale_data", message="snapshot is 3 days old", severity="warning"),
        ])
        exp = explain_decision(result)
        html = render_explanation_html(exp)
        assert "stale_data" in html
        assert "Caveats" in html

    def test_html_omits_warnings_section_when_no_warnings(self):
        result = _make_result(warnings=[])
        exp = explain_decision(result)
        html = render_explanation_html(exp)
        assert "Caveats" not in html

    def test_html_includes_override_hint(self):
        result = _make_result(action="buy")
        exp = explain_decision(result)
        html = render_explanation_html(exp)
        assert "Override:" in html

    def test_html_escapes_xss_attempt_in_canonical_name(self):
        """XSS-safe: an attacker-controlled canonical name is escaped."""
        result = _make_result(canonical_name="<script>alert('xss')</script>")
        exp = explain_decision(result)
        html = render_explanation_html(exp)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_html_escapes_xss_attempt_in_reasons(self):
        """XSS-safe: a malicious reason string is escaped."""
        result = _make_result(reasons=['<img src=x onerror="alert(1)">'])
        exp = explain_decision(result)
        html = render_explanation_html(exp)
        assert "<img" not in html
        assert "&lt;img" in html


# ── Text renderer ───────────────────────────────────────────────────


class TestRenderExplanationText:
    def test_text_output_is_multiline(self):
        result = _make_result()
        exp = explain_decision(result)
        text = render_explanation_text(exp)
        assert "\n" in text
        assert len(text.split("\n")) >= 5

    def test_text_includes_canonical_name(self):
        result = _make_result(canonical_name="milk")
        exp = explain_decision(result)
        text = render_explanation_text(exp)
        assert "milk" in text

    def test_text_includes_action_verb(self):
        result = _make_result(action="skip")
        exp = explain_decision(result)
        text = render_explanation_text(exp)
        assert "skip" in text

    def test_text_includes_confidence_label(self):
        result = _make_result(confidence=0.7)
        exp = explain_decision(result)
        text = render_explanation_text(exp)
        assert "high" in text
        assert "70%" in text

    def test_text_includes_warnings_when_present(self):
        result = _make_result(warnings=[
            DecisionWarning(code="x", message="y", severity="info"),
        ])
        exp = explain_decision(result)
        text = render_explanation_text(exp)
        assert "Caveats:" in text
        assert "[x]" in text
