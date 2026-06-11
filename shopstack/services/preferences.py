from __future__ import annotations

import logging
from typing import Any

from shopstack.schemas.models import PreferenceSignal
from shopstack.persistence.database import Database

logger = logging.getLogger(__name__)

__all__ = [
    "learn_preferences_from_reconciliation",
]


def learn_preferences_from_reconciliation(database: Database, actual_items: list[dict[str, Any]]):
    """Analyze a batch of actual actions and learn preferences."""
    added_signals = 0
    
    for actual in actual_items:
        name = actual.get("canonical_name", "").lower().strip()
        if not name:
            continue
            
        action = actual.get("action", "bought").lower()
        sub_with = actual.get("substituted_with", "").strip()
        
        # Rule 1: Substitution
        # If an item is substituted, record it as a potential brand or alternative preference.
        if action == "substituted" and sub_with:
            signal = PreferenceSignal(
                canonical_name=name,
                signal_type="brand_preferred",
                value=sub_with,
                confidence=0.5, # Initial confidence
                source="reconciliation_substitution"
            )
            try:
                database.add_preference_signal(signal)
                added_signals += 1
            except Exception as e:
                logger.warning("Failed to record preference signal for %s: %s", name, e)
                
        # Rule 2: Repeated Skipping
        # We could check how many times it was skipped recently
        if action == "skipped":
            # fetch recent reconciliations for this item
            try:
                events = database.get_reconciliation_events(canonical_name=name, limit=5)
                skips = sum(1 for e in events if e.actual_action == "skipped")
                if skips >= 3:
                    # 3 times skipped in recent trips
                    signal = PreferenceSignal(
                        canonical_name=name,
                        signal_type="often_skipped",
                        value="true",
                        confidence=0.7,
                        source="reconciliation_skips"
                    )
                    database.add_preference_signal(signal)
                    added_signals += 1
            except Exception as e:
                logger.warning("Failed to evaluate skips for %s: %s", name, e)

    return added_signals
