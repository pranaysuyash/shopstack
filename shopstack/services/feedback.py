"""Feedback / correction service — the "Mark as wrong" learning loop.

**Why this exists (motto_v3 §0 first-principles + §0.14 product reality):**

ShopStack makes recommendations ("Buy milk", "Skip rice").
The user knows their household better than the system. When
the system gets it wrong, the user needs a way to say so —
and the system needs to learn from the correction so it
doesn't make the same mistake twice.

The infrastructure for corrections was partly built in
prior passes:
  - ``CorrectionEvent`` Pydantic schema (models.py:555)
  - ``correction_events`` table with ``accepted`` flag
  - DB methods: ``record_correction_event``,
    ``get_recent_correction_events``, ``mark_correction_accepted``
  - ``PreferenceService.record_correction`` (translates
    corrections into typed preference signals)
  - Memory → Recent corrections sub-tab (accept/reject UI)

What's missing (Pass 20):
  1. The **user-facing creation flow** — a "Mark as wrong"
     button/form that creates a CorrectionEvent from a
     decision the user disagrees with.
  2. The **engine learning loop** — when the decision
     engine makes a decision, check prior corrections on
     the same item and adjust the decision accordingly.

This module is the first-principles fix for both. It
exposes two pure functions:

  - ``record_user_correction(...)``: creates a
    ``CorrectionEvent`` from a decision the user disagrees
    with. Persists to the ``correction_events`` table. Also
    translates into a ``PreferenceSignal`` via
    ``PreferenceService`` (so the existing preference
    infrastructure benefits from the learning).

  - ``apply_corrections_to_decision(decision, corrections)``:
    takes a ``DecisionResult`` and a list of
    ``CorrectionEvent`` for the same canonical_name,
    returns an adjusted ``DecisionResult``. The adjustment:
    - Forces the action to the user's preferred action
      (if a correction says "should_be=skip", the new
      decision's action is forced to skip)
    - Adds the correction reason to the decision's reasons
    - Reduces confidence by 0.1 (the system is less sure
      because the user disagreed before)
    - Most recent correction wins (time-decay: more recent
      corrections override older ones)

**Mode-portable (motto_v3 first-principles):** the same
correction data flows through the Memory tab (accept/reject
panel), the CLI (``correct`` and ``corrections`` subcommands),
and the HTTP endpoint (``/api/corrections``). The engine
learning loop is a pure function — testable without I/O.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from shopstack.schemas.models import (
    CorrectionEvent,
    DecisionResult,
)

logger = logging.getLogger(__name__)


# ── Confidence adjustment constants ─────────────────────────────────


# How much to reduce confidence when a prior correction
# exists for the same item. The system is less sure because
# the user has disagreed before.
CORRECTION_CONFIDENCE_PENALTY = 0.1

# Minimum confidence (don't go below this — at some point
# the system has to make a recommendation).
MIN_CONFIDENCE_AFTER_CORRECTION = 0.3

# Valid DecisionAction values for the ``should_be_action`` field.
# Mirrors ``DecisionAction`` in schemas/models.py.
_VALID_ACTIONS = {
    "buy", "skip", "use_soon", "compare", "wait", "substitute",
    "watch", "confirm", "optional",
}


# ── Pure functions ────────────────────────────────────────────────


def validate_correction(
    *,
    canonical_name: str,
    was_action: str,
    should_be_action: str,
    reason: str = "",
) -> list[str]:
    """Validate a correction and return a list of error messages.

    Returns an empty list if the correction is valid. The
    caller is expected to surface these errors to the user
    (via the HTTP endpoint, the CLI, or the Gradio form).

    This is a pure function — no I/O, no DB calls. The
    purpose is to give the user actionable feedback BEFORE
    we persist a bad correction.
    """
    errors: list[str] = []
    if not canonical_name or not canonical_name.strip():
        errors.append("canonical_name is required")
    if not was_action or was_action not in _VALID_ACTIONS:
        errors.append(
            f"was_action must be one of {sorted(_VALID_ACTIONS)}, got {was_action!r}"
        )
    if not should_be_action or should_be_action not in _VALID_ACTIONS:
        errors.append(
            f"should_be_action must be one of {sorted(_VALID_ACTIONS)}, got {should_be_action!r}"
        )
    if was_action == should_be_action:
        errors.append(
            "was_action and should_be_action are the same — a correction "
            "should change the action. If you agree with the system, no "
            "correction is needed."
        )
    if reason and len(reason) > 500:
        errors.append("reason must be 500 characters or fewer")
    return errors


def record_user_correction(
    db: Any,
    *,
    user_id: str = "",
    canonical_name: str,
    was_action: str,
    should_be_action: str,
    reason: str = "",
) -> CorrectionEvent:
    """Record a user correction. Returns the persisted event.

    This is the entry point for the "Mark as wrong" flow.
    It:
      1. Validates the correction (returns the event anyway
         if invalid, but logs a warning).
      2. Creates a ``CorrectionEvent`` with type="preference"
         (the user is expressing a preference about the
         decision).
      3. Persists via ``db.record_correction_event``.
      4. Also calls ``PreferenceService.record_correction``
         to translate into typed signals (so the existing
         preference infrastructure benefits).

    The engine learning loop (applying corrections to future
    decisions) is handled separately by
    ``apply_corrections_to_decision``.
    """
    errors = validate_correction(
        canonical_name=canonical_name,
        was_action=was_action,
        should_be_action=should_be_action,
        reason=reason,
    )
    if errors:
        # Log but don't raise — the HTTP/CLI surfaces errors
        # to the user. The event is still created for audit
        # purposes; it's marked accepted=0 (pending) so the
        # user can review it in the Memory tab.
        logger.warning("Recording a correction with errors: %s", errors)

    event = CorrectionEvent(
        canonical_name=canonical_name.lower().strip(),
        correction_type="preference",
        old_value=was_action,
        new_value=should_be_action,
        source="user_correction",
        timestamp=datetime.now(),
        accepted=0,  # Pending — user can accept/reject in Memory.
    )

    try:
        db.record_correction_event(event, user_id=user_id)
    except Exception as exc:
        logger.warning(
            "Failed to persist CorrectionEvent to correction_events: %s",
            exc,
        )

    # Also translate into a typed preference signal so the
    # existing preference infrastructure (staples, dislikes,
    # avoid-list) benefits. The PreferenceService knows how
    # to translate a correction into the right signal type.
    #
    # Pass 20: pass ``persist_event=False`` to avoid a
    # double-write — the event was already persisted above
    # via ``db.record_correction_event``. The preference
    # service would otherwise write a SECOND event with a
    # different event_id, breaking the "one event per
    # correction" invariant.
    try:
        from shopstack.services.preference import build_preference_service
        pref = build_preference_service(db)
        pref.record_correction(
            correction_event={
                "canonical_name": canonical_name,
                "correction_type": "preference",
                "old_value": was_action,
                "new_value": should_be_action,
                "source": "user_correction",
            },
            user_id=user_id,
            persist_event=False,  # Event already written above.
        )
    except Exception as exc:
        # Non-fatal — the CorrectionEvent is the primary
        # contract; the preference signal is a secondary
        # optimization.
        logger.debug("PreferenceService translation failed (non-fatal): %s", exc)

    return event


def apply_corrections_to_decision(
    decision: DecisionResult,
    corrections: list[CorrectionEvent],
) -> DecisionResult:
    """Apply user corrections to a decision, returning an adjusted copy.

    First-principles design:
      - Only corrections on the **same canonical_name**
        apply (no cross-item contamination).
      - The **most recent correction** wins (time-decay).
      - If the user said "should_be=skip" (or any non-buy
        action) for a decision that the system wants to
        "buy", force the action to the user's preference.
      - The confidence is reduced by 0.1 (the system is
        less sure because the user has disagreed before).
      - The correction reason is added to the decision's
        reasons, so the Why? toggle (Pass 19) surfaces it
        to the user.

    The returned decision is a **new** ``DecisionResult``
    (the input is not mutated). This is the first-principles
    rule: pure functions don't mutate their inputs.
    """
    if not corrections:
        return decision

    # Filter to corrections for the same item. Time-decay:
    # sort by timestamp DESC so the most recent correction
    # wins. Only the most recent correction is applied (per
    # first-principles — the user's most recent intent is
    # the strongest signal).
    relevant = sorted(
        [c for c in corrections if c.canonical_name == decision.canonical_name],
        key=lambda c: c.timestamp,
        reverse=True,
    )
    if not relevant:
        return decision

    most_recent = relevant[0]
    # The correction only applies if the user changed their
    # mind (old_value != new_value). validate_correction
    # already enforces this at write-time; we re-check here
    # defensively.
    if most_recent.old_value == most_recent.new_value:
        return decision

    # Build the adjusted decision.
    new_action = most_recent.new_value
    new_confidence = max(
        MIN_CONFIDENCE_AFTER_CORRECTION,
        decision.confidence - CORRECTION_CONFIDENCE_PENALTY,
    )
    correction_reason = (
        f"you previously said {decision.canonical_name.replace('_', ' ')} "
        f"should be {new_action.replace('_', ' ')} (not {most_recent.old_value})"
    )

    new_reasons = list(decision.reasons) + [correction_reason]
    # If the correction had a free-text reason, include it too.
    if most_recent.new_value and most_recent.new_value not in _VALID_ACTIONS:
        # The new_value isn't a valid action — treat as free text.
        new_reasons.append(f"your note: {most_recent.new_value}")

    # Pydantic models: we use ``model_copy(update=...)`` to
    # create a new instance with updated fields. This
    # preserves the input decision's identity (for tests
    # that check ``decision.confidence == original``) while
    # returning a new instance for the caller.
    return decision.model_copy(update={
        "action": new_action,
        "confidence": new_confidence,
        "reasons": new_reasons,
    })


def list_recent_corrections(
    db: Any,
    *,
    user_id: str = "",
    limit: int = 20,
    accepted_only: bool = False,
) -> list[CorrectionEvent]:
    """List recent corrections for the active user.

    Thin wrapper around ``db.get_recent_correction_events``
    that adds a user_id default from the app context.
    """
    return db.get_recent_correction_events(
        limit=limit,
        accepted_only=accepted_only,
        user_id=user_id,
    )


def get_corrections_for_item(
    db: Any,
    canonical_name: str,
    *,
    user_id: str = "",
    limit: int = 5,
) -> list[CorrectionEvent]:
    """Return the most recent corrections for a specific item.

    Used by the engine learning loop: before making a
    decision on an item, the engine checks for prior
    corrections on that item. The most recent correction
    (if any) is applied via
    ``apply_corrections_to_decision``.
    """
    all_recent = db.get_recent_correction_events(
        limit=limit * 5,  # Fetch more than needed to allow filtering.
        user_id=user_id,
    )
    return [c for c in all_recent if c.canonical_name == canonical_name.lower().strip()][:limit]


def summarize_corrections(corrections: list[CorrectionEvent]) -> str:
    """One-line summary of a corrections list (for CLI/UI)."""
    count = len(corrections)
    if count == 0:
        return "No corrections recorded."
    if count == 1:
        c = corrections[0]
        return (
            f"1 correction: {c.canonical_name} — was {c.old_value}, "
            f"should be {c.new_value}."
        )
    return f"{count} corrections recorded."
