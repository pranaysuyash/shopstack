"""Decision explainability — the answer to "Why did ShopStack say X?".

**Why this exists (motto_v3 §0.14 Product Reality + §0 Observability
+ first-principles):**

The decision engine produces ``DecisionResult`` objects with
``reasons: list[str]`` and ``evidence: list[DecisionEvidence]``.
This is the canonical data; it ALREADY explains why a decision
was made. The product gap is that this data is buried in the
dataclass — neither the Gradio UI nor the CLI surfaces it to
the user.

The user question is real: "Why did ShopStack tell me to BUY
milk when I have 0.3L at home?" The data is there; the
explanation is not.

This module is the smallest first-principles fix:

  1. ``explain_decision(result)`` — pure function that takes a
     ``DecisionResult`` and returns a structured
     ``DecisionExplanation`` with the plain-English narrative,
     key signal, confidence interpretation, and "what would
     change my mind" hint.

  2. ``render_explanation_html(explanation)`` — renders the
     explanation to HTML for the Gradio UI.

  3. The same ``DecisionExplanation`` is JSON-serializable,
     so the CLI can print it and the HTTP endpoint can return
     it (mode-portable, per the §0 first-principles mandate).

**Design choices:**

  - The explanation is a Pydantic model (same style as
    ``DecisionResult``), so the same data flows through the
    service layer, the renderer, the CLI, and the HTTP
    endpoint.
  - The plain-English narrative is constructed from
    ``result.reasons`` (a list of short strings the decision
    engine already produces). The service composes them into
    a sentence. No new LLM call; no extra compute.
  - The "what would change my mind" hint is a static lookup
    table keyed on ``result.action``. This is intentionally
    simple — the user can correct the system (memory tab,
    future pass) and the correction shows up here.
  - This is a **concept-first** feature: "the answer to why"
    is the concept, the renderer is an adapter. The same
    concept holds across Gradio / CLI / API.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from shopstack.schemas.models import DecisionResult


# ── The structured explanation schema ───────────────────────────────


class DecisionExplanation(BaseModel):
    """Structured answer to "Why did ShopStack say X?".

    This is the concept; the renderer / CLI / API are adapters.

    Attributes:
        item_id: Same as ``DecisionResult.item_id`` (round-trip reference).
        canonical_name: Same as ``DecisionResult.canonical_name``.
        action: Same as ``DecisionResult.action`` ("buy" / "skip" / etc.).
        confidence: Same as ``DecisionResult.confidence`` (0.0-1.0).
        summary: One-sentence plain-English summary, e.g.
            "ShopStack suggests buying milk because you have
            0.3 L at home and the freshness snapshot is 3 days
            old." Composed from ``reasons`` + ``evidence``.
        key_signal: The single most important reason (a short
            phrase). Used for the "key driver" UI callout.
        confidence_label: Human-readable confidence:
            "very low" / "low" / "medium" / "high" / "very high".
        confidence_caveat: A short caveat when confidence is
            low or when warnings are present.
        warnings: List of warning codes + messages, mirrored
            from ``DecisionResult.warnings``.
        override_hint: Plain-English hint for what would
            change the decision, e.g. "If you mark it as
            bought, the action will change to use_soon."
        evidence_summary: Short list of the data sources that
            informed this decision, e.g.
            ["inventory: 0.3 L at home",
             "market_snapshot: 3 days old"].
        freshness_status: Same as ``DecisionResult.data_freshness``.
        freshness_label: Same as ``DecisionResult.data_freshness_label``.
    """

    item_id: str
    canonical_name: str
    action: str
    confidence: float
    summary: str
    key_signal: str
    confidence_label: str
    confidence_caveat: str = ""
    warnings: list[dict[str, str]] = Field(default_factory=list)
    override_hint: str = ""
    evidence_summary: list[str] = Field(default_factory=list)
    freshness_status: str = "unknown"
    freshness_label: str = ""


# ── Static lookup tables ────────────────────────────────────────────


_ACTION_VERB = {
    "buy": "buy",
    "skip": "skip",
    "use_soon": "use soon",
    "compare": "compare",
    "wait": "wait on",
    "substitute": "substitute",
    "watch": "watch",
}

_ACTION_OVERRIDE_HINT = {
    "buy": (
        "If you mark this as already in stock, the action "
        "will change to skip or use_soon."
    ),
    "skip": (
        "If you mark this as running low, the action may "
        "change to buy."
    ),
    "use_soon": (
        "If you mark this as consumed, the action may change "
        "to buy. If you confirm it's still good, the action "
        "will become skip."
    ),
    "compare": (
        "If a source becomes unavailable, the action will "
        "update to reflect the next-best option."
    ),
    "wait": (
        "If the price drops further, the action will update. "
        "If you decide to buy now, mark it as bought to move "
        "on."
    ),
    "substitute": (
        "If you mark the suggested substitute as out of stock, "
        "ShopStack will find a new alternative."
    ),
    "watch": (
        "ShopStack is monitoring this. If the situation "
        "changes, the action will update."
    ),
}

_CONFIDENCE_LABELS = [
    (0.0, 0.2, "very low"),
    (0.2, 0.4, "low"),
    (0.4, 0.6, "medium"),
    (0.6, 0.8, "high"),
    (0.8, 1.01, "very high"),
]


def _confidence_label_for(score: float) -> str:
    """Map a 0.0-1.0 confidence score to a 5-bucket label."""
    for low, high, label in _CONFIDENCE_LABELS:
        if low <= score < high:
            return label
    return "very high"


# ── The pure service function ──────────────────────────────────────


def explain_decision(result: DecisionResult) -> DecisionExplanation:
    """Compose a structured explanation of a decision.

    Pure function: takes a ``DecisionResult``, returns a
    ``DecisionExplanation``. No DB / no I/O / no LLM call.
    The same input always produces the same output.

    The summary is composed from ``result.reasons`` (a list of
    short strings the decision engine produces) into a single
    plain-English sentence. If reasons is empty, a fallback
    summary is constructed from the action + the freshness
    label.

    The key_signal is the most important reason — currently
    just the first non-empty reason from ``result.reasons``.

    The confidence_caveat is non-empty when:
      - Confidence is low (< 0.4) — "ShopStack isn't sure."
      - There are warnings — "There are N caveats."
    """
    verb = _ACTION_VERB.get(result.action, result.action)
    canonical = result.canonical_name
    freshness = result.data_freshness_label or result.data_freshness or ""

    # Compose the summary from reasons. Skip whitespace-only
    # reasons so the summary doesn't have stray "; ; ;" segments.
    reasons_text = "; ".join(r.strip() for r in result.reasons if r and r.strip())
    if reasons_text:
        summary = (
            f"ShopStack suggests {verb} {canonical.replace('_', ' ')}: {reasons_text}."
        )
    else:
        # Fallback summary when the engine didn't produce reasons.
        summary = (
            f"ShopStack suggests {verb} {canonical.replace('_', ' ')}"
            + (f" (data: {freshness})." if freshness else ".")
        )

    # Key signal: the first non-empty reason (the most important one).
    # Use `r.strip()` so whitespace-only strings don't count.
    key_signal = ""
    for r in result.reasons:
        if r and r.strip():
            key_signal = r
            break
    if not key_signal:
        key_signal = f"action={result.action}"

    # Confidence label + caveat.
    confidence_label = _confidence_label_for(result.confidence)
    confidence_caveat = ""
    if result.confidence < 0.4:
        confidence_caveat = (
            "ShopStack isn't very confident in this — "
            "the underlying data is thin or stale."
        )
    if result.warnings:
        warning_count = len(result.warnings)
        if confidence_caveat:
            confidence_caveat += " "
        confidence_caveat += (
            f"There {'is' if warning_count == 1 else 'are'} "
            f"{warning_count} caveat{'s' if warning_count != 1 else ''} "
            f"worth knowing about."
        )

    # Warnings: convert to dicts (Pydantic-friendly, JSON-friendly).
    warnings_list = [
        {"code": w.code, "message": w.message, "severity": w.severity}
        for w in result.warnings
    ]

    # Evidence summary: short list of "source: value" strings.
    evidence_summary: list[str] = []
    for ev in result.evidence:
        source = ev.source.replace("_", " ")
        if ev.value is not None:
            evidence_summary.append(f"{source}: {ev.value}")
        else:
            evidence_summary.append(source)
    if not evidence_summary and freshness:
        # At minimum, surface the data freshness so the user
        # knows how recent the data is.
        evidence_summary.append(f"data freshness: {freshness}")

    # Override hint.
    override_hint = _ACTION_OVERRIDE_HINT.get(result.action, "")

    return DecisionExplanation(
        item_id=result.item_id,
        canonical_name=result.canonical_name,
        action=result.action,
        confidence=result.confidence,
        summary=summary,
        key_signal=key_signal,
        confidence_label=confidence_label,
        confidence_caveat=confidence_caveat,
        warnings=warnings_list,
        override_hint=override_hint,
        evidence_summary=evidence_summary,
        freshness_status=result.data_freshness,
        freshness_label=result.data_freshness_label,
    )


# ── Convenience: explain a whole decision set ───────────────────────


def explain_decision_set(
    results: list[DecisionResult],
    *,
    limit: int = 5,
) -> list[DecisionExplanation]:
    """Explain the top N decisions in a set.

    Used by the dashboard / CLI / API to produce a "why these
    decisions" overview. Returns one ``DecisionExplanation``
    per decision, in the same order as the input.
    """
    return [explain_decision(r) for r in results[:limit]]


# ── HTTP-serializable representation ─────────────────────────────────


def explanation_to_dict(explanation: DecisionExplanation) -> dict[str, Any]:
    """Return a plain dict suitable for JSON serialization.

    Mode-portable: the same dict is used by the CLI, the HTTP
    endpoint, and the dashboard's "Why?" button.
    """
    return explanation.model_dump(mode="json")
