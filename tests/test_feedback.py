"""Tests for the feedback / correction service (Pass 20).

**Why this exists (motto_v3 §0.14 product reality):**

The user needs a way to say "ShopStack was wrong about X"
and have the system learn. This module tests the full
learning loop:
  1. ``validate_correction`` — rejects malformed input.
  2. ``record_user_correction`` — persists to
     ``correction_events`` + translates to a preference signal.
  3. ``apply_corrections_to_decision`` — the engine learning
     loop: prior corrections adjust future decisions.
  4. ``list_recent_corrections`` / ``get_corrections_for_item``
     — query helpers for the UI and engine.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from shopstack.schemas.models import (
    CorrectionEvent,
    DecisionResult,
)
from shopstack.services.feedback import (
    CORRECTION_CONFIDENCE_PENALTY,
    MIN_CONFIDENCE_AFTER_CORRECTION,
    apply_corrections_to_decision,
    get_corrections_for_item,
    list_recent_corrections,
    record_user_correction,
    summarize_corrections,
    validate_correction,
)

# ── Fake DB ────────────────────────────────────────────────────────


class _FakeDB:
    """Minimal DB stand-in for testing the feedback service.

    Implements only the methods that
    ``record_user_correction`` / ``list_recent_corrections``
    call: ``record_correction_event`` and
    ``get_recent_correction_events``.
    """

    def __init__(self):
        self.events: list[CorrectionEvent] = []
        self._next_id = 0

    def record_correction_event(self, event: CorrectionEvent, user_id: str = "") -> CorrectionEvent:
        self._next_id += 1
        event.user_id = user_id or event.user_id
        event.event_id = event.event_id or f"evt_{self._next_id}"
        # Replace any existing event with the same event_id.
        self.events = [e for e in self.events if e.event_id != event.event_id]
        self.events.append(event)
        return event

    def get_recent_correction_events(
        self,
        limit: int = 20,
        accepted_only: bool = False,
        user_id: str = "",
    ) -> list[CorrectionEvent]:
        result = list(self.events)
        if accepted_only:
            result = [e for e in result if e.accepted == 1]
        if user_id:
            result = [e for e in result if e.user_id == user_id]
        # Sort by timestamp DESC (newest first).
        result.sort(key=lambda e: e.timestamp, reverse=True)
        return result[:limit]

    def add_preference_signal(self, signal, user_id: str = ""):
        # No-op for tests — we just verify the call doesn't crash.
        pass

    def get_preference_signals(self, *args, **kwargs):
        return []


# ── validate_correction ──────────────────────────────────────────


class TestValidateCorrection:
    def test_valid_correction_returns_no_errors(self):
        errors = validate_correction(
            canonical_name="milk",
            was_action="buy",
            should_be_action="skip",
            reason="I have plenty",
        )
        assert errors == []

    def test_missing_canonical_name_returns_error(self):
        errors = validate_correction(
            canonical_name="",
            was_action="buy",
            should_be_action="skip",
        )
        assert any("canonical_name" in e for e in errors)

    def test_invalid_was_action_returns_error(self):
        errors = validate_correction(
            canonical_name="milk",
            was_action="invalid_action",
            should_be_action="skip",
        )
        assert any("was_action" in e for e in errors)

    def test_invalid_should_be_action_returns_error(self):
        errors = validate_correction(
            canonical_name="milk",
            was_action="buy",
            should_be_action="",
        )
        assert any("should_be_action" in e for e in errors)

    def test_same_action_returns_error(self):
        """A correction should change the action — same action is a no-op."""
        errors = validate_correction(
            canonical_name="milk",
            was_action="buy",
            should_be_action="buy",
        )
        assert any("the same" in e for e in errors)

    def test_long_reason_returns_error(self):
        errors = validate_correction(
            canonical_name="milk",
            was_action="buy",
            should_be_action="skip",
            reason="x" * 501,
        )
        assert any("reason" in e.lower() for e in errors)


# ── record_user_correction ────────────────────────────────────────


class TestRecordUserCorrection:
    def test_records_event_with_correct_fields(self):
        db = _FakeDB()
        event = record_user_correction(
            db,
            user_id="",
            canonical_name="milk",
            was_action="buy",
            should_be_action="skip",
            reason="I have plenty",
        )
        assert event.canonical_name == "milk"
        assert event.old_value == "buy"
        assert event.new_value == "skip"
        assert event.source == "user_correction"
        assert event.accepted == 0
        assert event.event_id
        assert event in db.events

    def test_canonical_name_is_lowercased(self):
        db = _FakeDB()
        event = record_user_correction(
            db,
            canonical_name="MILK",
            was_action="buy",
            should_be_action="skip",
        )
        assert event.canonical_name == "milk"

    def test_validation_errors_do_not_block_persistence(self):
        """Invalid corrections are still persisted (for audit) but
        a warning is logged. This is the best-effort contract:
        the user can review the event in the Memory tab."""
        db = _FakeDB()
        # Same action = validation error but the event is still created.
        record_user_correction(
            db,
            canonical_name="milk",
            was_action="buy",
            should_be_action="buy",  # same as was_action
        )
        # The event IS persisted (for audit).
        assert len(db.events) == 1


# ── apply_corrections_to_decision (the engine learning loop) ────


class TestApplyCorrectionsToDecision:
    def _make_decision(self, **kwargs) -> DecisionResult:
        defaults = {
            "canonical_name": "milk",
            "display_name": "Milk",
            "action": "buy",
            "confidence": 0.7,
            "reasons": ["only 0.3L at home"],
        }
        defaults.update(kwargs)
        return DecisionResult(**defaults)

    def _make_correction(self, **kwargs) -> CorrectionEvent:
        defaults = {
            "canonical_name": "milk",
            "old_value": "buy",
            "new_value": "skip",
            "source": "user_correction",
            "timestamp": datetime.now(),
        }
        defaults.update(kwargs)
        return CorrectionEvent(correction_type="preference", **defaults)

    def test_no_corrections_returns_original(self):
        d = self._make_decision()
        result = apply_corrections_to_decision(d, [])
        assert result.action == "buy"
        assert result.confidence == 0.7

    def test_correction_for_different_item_is_ignored(self):
        """Corrections only apply to the same canonical_name."""
        d = self._make_decision(canonical_name="milk")
        c = self._make_correction(canonical_name="rice")
        result = apply_corrections_to_decision(d, [c])
        assert result.action == "buy"
        assert result.confidence == 0.7

    def test_correction_with_same_was_and_new_value_is_ignored(self):
        """Defensive check: a correction with old==new is a no-op."""
        d = self._make_decision()
        c = self._make_correction(old_value="buy", new_value="buy")
        result = apply_corrections_to_decision(d, [c])
        assert result.action == "buy"

    def test_correction_forces_action_to_user_preference(self):
        d = self._make_decision(action="buy", confidence=0.7)
        c = self._make_correction(old_value="buy", new_value="skip")
        result = apply_corrections_to_decision(d, [c])
        assert result.action == "skip"

    def test_correction_reduces_confidence(self):
        d = self._make_decision(action="buy", confidence=0.7)
        c = self._make_correction(old_value="buy", new_value="skip")
        result = apply_corrections_to_decision(d, [c])
        assert result.confidence == pytest.approx(
            0.7 - CORRECTION_CONFIDENCE_PENALTY, abs=0.001,
        )

    def test_correction_does_not_reduce_confidence_below_minimum(self):
        d = self._make_decision(action="buy", confidence=0.3)
        c = self._make_correction(old_value="buy", new_value="skip")
        result = apply_corrections_to_decision(d, [c])
        assert result.confidence >= MIN_CONFIDENCE_AFTER_CORRECTION

    def test_correction_adds_reason_to_decision(self):
        d = self._make_decision()
        c = self._make_correction(old_value="buy", new_value="skip")
        result = apply_corrections_to_decision(d, [c])
        # The new reason mentions the correction.
        assert any("previously said" in r for r in result.reasons)
        assert any("skip" in r for r in result.reasons)

    def test_most_recent_correction_wins(self):
        """When multiple corrections exist, the most recent one wins."""
        d = self._make_decision(action="buy", confidence=0.7)
        old = self._make_correction(
            old_value="buy",
            new_value="skip",
            timestamp=datetime.now() - timedelta(days=5),
        )
        recent = self._make_correction(
            old_value="buy",
            new_value="use_soon",
            timestamp=datetime.now(),
        )
        result = apply_corrections_to_decision(d, [old, recent])
        # Recent correction (use_soon) wins over old correction (skip).
        assert result.action == "use_soon"

    def test_input_decision_is_not_mutated(self):
        """The input decision is not mutated — a new instance is returned."""
        d = self._make_decision(action="buy", confidence=0.7)
        original_action = d.action
        original_confidence = d.confidence
        original_reasons = list(d.reasons)
        c = self._make_correction()
        apply_corrections_to_decision(d, [c])
        assert d.action == original_action
        assert d.confidence == original_confidence
        assert d.reasons == original_reasons


# ── list_recent_corrections / get_corrections_for_item ────────────


class TestListRecentCorrections:
    def test_returns_events_newest_first(self):
        db = _FakeDB()
        for i in range(3):
            db.events.append(CorrectionEvent(correction_type="preference", 
                canonical_name=f"item_{i}",
                old_value="buy",
                new_value="skip",
                timestamp=datetime.now() - timedelta(hours=i),
            ))
        result = list_recent_corrections(db, user_id="", limit=10)
        assert len(result) == 3
        # Newest first.
        assert result[0].canonical_name == "item_0"
        assert result[2].canonical_name == "item_2"

    def test_respects_limit(self):
        db = _FakeDB()
        for i in range(5):
            db.events.append(CorrectionEvent(correction_type="preference", 
                canonical_name=f"item_{i}",
                old_value="buy",
                new_value="skip",
                timestamp=datetime.now() - timedelta(hours=i),
            ))
        result = list_recent_corrections(db, user_id="", limit=3)
        assert len(result) == 3

    def test_accepted_only_filter(self):
        db = _FakeDB()
        pending = CorrectionEvent(correction_type="preference", 
            canonical_name="a", old_value="buy", new_value="skip",
            accepted=0,
        )
        accepted = CorrectionEvent(correction_type="preference", 
            canonical_name="b", old_value="buy", new_value="skip",
            accepted=1,
        )
        db.events.extend([pending, accepted])
        result = list_recent_corrections(
            db, user_id="", limit=10, accepted_only=True,
        )
        assert len(result) == 1
        assert result[0].canonical_name == "b"


class TestGetCorrectionsForItem:
    def test_returns_corrections_for_specific_item(self):
        db = _FakeDB()
        for cn in ("milk", "rice", "milk", "milk"):
            db.events.append(CorrectionEvent(correction_type="preference", 
                canonical_name=cn,
                old_value="buy",
                new_value="skip",
                timestamp=datetime.now(),
            ))
        result = get_corrections_for_item(db, "milk", limit=10)
        assert len(result) == 3
        for c in result:
            assert c.canonical_name == "milk"

    def test_case_insensitive_match(self):
        db = _FakeDB()
        db.events.append(CorrectionEvent(correction_type="preference", 
            canonical_name="milk", old_value="buy", new_value="skip",
        ))
        result = get_corrections_for_item(db, "MILK", limit=10)
        assert len(result) == 1


# ── summarize_corrections ─────────────────────────────────────────


class TestSummarizeCorrections:
    def test_empty_corrections(self):
        assert summarize_corrections([]) == "No corrections recorded. Try reconciling an item to generate one."

    def test_one_correction(self):
        c = CorrectionEvent(correction_type="preference", 
            canonical_name="milk", old_value="buy", new_value="skip",
        )
        s = summarize_corrections([c])
        assert "1 correction" in s
        assert "milk" in s
        assert "buy" in s
        assert "skip" in s

    def test_multiple_corrections(self):
        cs = [
            CorrectionEvent(correction_type="preference", canonical_name="a", old_value="buy", new_value="skip"),
            CorrectionEvent(correction_type="preference", canonical_name="b", old_value="buy", new_value="skip"),
        ]
        s = summarize_corrections(cs)
        assert "2 corrections" in s
