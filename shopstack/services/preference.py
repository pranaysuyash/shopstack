from __future__ import annotations

import logging
from typing import Any
import re

from shopstack.schemas.models import PreferenceSignal, ReconciliationEvent
from shopstack.persistence.database import Database

logger = logging.getLogger(__name__)


class PreferenceService:
    """Service to handle household preference signals."""

    def __init__(self, db: Database):
        self.db = db

    def record_signal(
        self,
        canonical_name: str,
        signal_type: str,
        value: str,
        source: str = "observed",
        confidence: float = 0.5,
        user_id: str = "",
    ) -> PreferenceSignal:
        """Record a single preference signal."""
        signal = PreferenceSignal(
            canonical_name=canonical_name.lower().strip(),
            signal_type=signal_type,
            value=value,
            confidence=confidence,
            source=source,
        )
        self.db.add_preference_signal(signal, user_id=user_id)
        return signal

    def get_preferences(self, canonical_name: str | None = None, user_id: str = "") -> list[PreferenceSignal]:
        """Fetch preference signals."""
        return self.db.get_preference_signals(canonical_name=canonical_name, user_id=user_id)

    def delete_signal(self, signal_id: str) -> bool:
        """Delete a preference signal by ID."""
        return self.db.delete_preference_signal(signal_id)

    def get_staples(self, user_id: str = "") -> list[str]:
        """Get list of canonical names marked as staple."""
        signals = self.db.get_preference_signals(user_id=user_id)
        return list({s.canonical_name for s in signals if s.signal_type == "staple"})

    def get_disliked(self, user_id: str = "") -> list[str]:
        """Get list of canonical names marked as disliked."""
        signals = self.db.get_preference_signals(user_id=user_id)
        return list({s.canonical_name for s in signals if s.signal_type == "disliked"})

    def get_avoided(self, user_id: str = "") -> list[str]:
        """Get list of canonical names that should be avoided (disliked or often_wasted)."""
        signals = self.db.get_preference_signals(user_id=user_id)
        return list({s.canonical_name for s in signals if s.signal_type in ("often_wasted", "disliked")})

    def is_staple(self, canonical_name: str, user_id: str = "") -> bool:
        """Check if an item is a staple."""
        signals = self.db.get_preference_signals(canonical_name=canonical_name.lower().strip(), user_id=user_id)
        return any(s.signal_type == "staple" for s in signals)

    def learn_from_reconciliation(self, events: list[ReconciliationEvent], user_id: str = "") -> int:
        """Analyze reconciliation events and learn staples, dislikes, and brand preferences."""
        added_signals = 0
        for event in events:
            name = event.canonical_name.lower().strip()
            if not name:
                continue

            action = event.actual_action.lower()

            if action == "bought":
                # Check recent reconciliation history for this item
                recent = self.db.get_reconciliation_events(canonical_name=name, limit=5, user_id=user_id)
                buys = sum(1 for e in recent if e.actual_action.lower() == "bought")
                if buys >= 3:
                    self.record_signal(
                        canonical_name=name,
                        signal_type="staple",
                        value="true",
                        source="reconciliation_learning",
                        confidence=0.8,
                        user_id=user_id,
                    )
                    added_signals += 1
            elif action == "skipped":
                recent = self.db.get_reconciliation_events(canonical_name=name, limit=5, user_id=user_id)
                skips = sum(1 for e in recent if e.actual_action.lower() == "skipped")
                if skips >= 3:
                    self.record_signal(
                        canonical_name=name,
                        signal_type="disliked",
                        value="avoid",
                        source="reconciliation_learning",
                        confidence=0.7,
                        user_id=user_id,
                    )
                    added_signals += 1
            elif action == "substituted" and getattr(event, "substituted_with", None):
                self.record_signal(
                    canonical_name=name,
                    signal_type="brand_preferred",
                    value=event.substituted_with,
                    source="reconciliation_learning",
                    confidence=0.6,
                    user_id=user_id,
                )
                added_signals += 1

        return added_signals

    # --- Legacy Compatibility Methods ---

    def record_correction(self, correction_event: dict[str, Any], user_id: str = "") -> PreferenceSignal | None:
        """Translate a correction event (e.g. from UI / reconciliation) into a PreferenceSignal and persist it.

        Additive (2026-06-15): also persists the raw correction
        event to the new ``correction_events`` table so the
        Memory → Recent corrections panel can show the user what
        the system has learned, and let them accept or reject.
        The preference signal is left intact — accept/reject on
        the panel only updates the ``accepted`` flag on the new
        table. To retract the system-wide effect, the user must
        do that separately from Memory → Preferences.
        """
        try:
            canonical_name = correction_event.get("canonical_name", "").lower().strip()
            correction_type = correction_event.get("correction_type", "")
            old_value = correction_event.get("old_value")
            new_value = correction_event.get("new_value")

            if not canonical_name or not correction_type:
                logger.warning("Invalid correction event: missing canonical_name or correction_type")
                return None

            # Additive: also write the raw event to the new
            # correction_events table so the user can review
            # it from Memory → Recent corrections. Failures here
            # are non-fatal — the preference signal below is the
            # primary contract.
            try:
                from shopstack.schemas.models import CorrectionEvent
                raw_event = CorrectionEvent(
                    canonical_name=canonical_name,
                    correction_type=correction_type,
                    old_value=old_value,
                    new_value=str(new_value) if new_value is not None else "",
                    source=str(correction_event.get("source", "user_correction")),
                )
                self.db.record_correction_event(raw_event, user_id=user_id)
            except Exception as exc:  # noqa: BLE001
                logger.debug("record_correction_event persistence failed (non-fatal): %s", exc)

            signal_type = "brand_preferred"
            value = str(new_value)

            if correction_type == "avoid" or str(new_value).lower() in ("avoid", "skip", "dislike"):
                signal_type = "disliked"
                value = "avoid"
            elif correction_type == "alias":
                signal_type = "brand_preferred"
                value = f"alias:{new_value}"

            return self.record_signal(
                canonical_name=canonical_name,
                signal_type=signal_type,
                value=value,
                source="corrected",
                confidence=1.0,
                user_id=user_id,
            )
        except Exception as exc:
            logger.error("Failed to record preference correction: %s", exc)
            return None

    def get_signals(self, canonical_name: str | None = None, user_id: str = "") -> list[PreferenceSignal]:
        """Fetch list of signals (legacy)."""
        return self.get_preferences(canonical_name=canonical_name, user_id=user_id)

    def get_avoid_list(self, user_id: str = "") -> set[str]:
        """Return canonical_names that should be avoided (legacy)."""
        return set(self.get_avoided(user_id=user_id))

    def get_aliases(self, user_id: str = "") -> dict[str, str]:
        """Return dict of canonical name aliases mappings (legacy)."""
        signals = self.get_preferences(user_id=user_id)
        aliases = {}
        for s in signals:
            if s.signal_type == "brand_preferred" and s.value.startswith("alias:"):
                alias_val = s.value.split("alias:", 1)[1]
                aliases[s.canonical_name.lower().strip()] = alias_val
        return aliases


def build_preference_service(db: Database) -> PreferenceService:
    return PreferenceService(db)
