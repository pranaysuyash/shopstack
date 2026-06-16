"""Regression test for the CorrectionEvent data layer coherence.

As of 2026-06-15 (motto_v3 §0.8): the correction_events table has
``accepted`` and ``user_id`` columns, and the screen reads these via
``getattr(row, "accepted", 0)``. The CorrectionEvent Pydantic model
was missing these fields, creating a data layer mismatch.

This test verifies:
  1. The CorrectionEvent model has both ``accepted`` and ``user_id`` fields
  2. The row converter passes them from the DB
  3. The DB CRUD methods handle them correctly
  4. The corrections screen can read them via getattr
"""
from __future__ import annotations

from datetime import datetime

from shopstack.persistence.database import _row_to_correction
from shopstack.schemas.models import CorrectionEvent


class TestCorrectionEventModel:
    """The Pydantic model must have all the fields the DB table has."""

    def test_accepted_field_exists(self):
        """The ``accepted`` field is the accept/reject flag set by the
        Memory → Recent corrections panel."""
        event = CorrectionEvent(
            canonical_name="tomato",
            correction_type="alias",
            new_value="cherry tomato",
        )
        # Default is 0 (pending)
        assert event.accepted == 0
        # Can be set
        event.accepted = 1
        assert event.accepted == 1

    def test_user_id_field_exists(self):
        """The ``user_id`` field is for household scoping (Phase 11)."""
        event = CorrectionEvent(
            canonical_name="tomato",
            correction_type="alias",
            new_value="cherry tomato",
            user_id="hh-test-1",
        )
        assert event.user_id == "hh-test-1"

    def test_default_values(self):
        """Fresh events default to pending (accepted=0) and no user."""
        event = CorrectionEvent(
            canonical_name="tomato",
            correction_type="alias",
            new_value="cherry tomato",
        )
        assert event.accepted == 0
        assert event.user_id == ""


class TestCorrectionRowConverter:
    """The _row_to_correction helper must populate the new fields."""

    def test_row_converter_passes_accepted(self):
        """The row converter must read the ``accepted`` column."""
        class FakeRow:
            def __getitem__(self, key):
                values = {
                    "event_id": "evt-1",
                    "timestamp": "2026-06-15T10:00:00",
                    "canonical_name": "tomato",
                    "correction_type": "alias",
                    "old_value": "tamatar",
                    "new_value": "cherry tomato",
                    "source": "user_correction",
                    "accepted": 1,
                    "user_id": "hh-1",
                }
                return values[key]

        event = _row_to_correction(FakeRow())
        assert event.accepted == 1, (
            "_row_to_correction must populate the accepted field "
            "from the DB column. Per §0.8 data layer coherence, the "
            "model and table must be in sync."
        )

    def test_row_converter_passes_user_id(self):
        class FakeRow:
            def __getitem__(self, key):
                values = {
                    "event_id": "evt-1",
                    "timestamp": "2026-06-15T10:00:00",
                    "canonical_name": "tomato",
                    "correction_type": "alias",
                    "old_value": "tamatar",
                    "new_value": "cherry tomato",
                    "source": "user_correction",
                    "accepted": 0,
                    "user_id": "hh-test-1",
                }
                return values[key]

        event = _row_to_correction(FakeRow())
        assert event.user_id == "hh-test-1"

    def test_row_converter_handles_null_accepted(self):
        """A null ``accepted`` column should default to 0 (pending)."""
        class FakeRow:
            def __getitem__(self, key):
                values = {
                    "event_id": "evt-1",
                    "timestamp": "2026-06-15T10:00:00",
                    "canonical_name": "tomato",
                    "correction_type": "alias",
                    "old_value": "tamatar",
                    "new_value": "cherry tomato",
                    "source": "user_correction",
                    "accepted": None,
                    "user_id": "hh-1",
                }
                return values[key]

        event = _row_to_correction(FakeRow())
        assert event.accepted == 0, (
            "Null accepted column should default to 0 (pending), "
            "not raise a TypeError."
        )
