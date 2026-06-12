from __future__ import annotations

import logging
from typing import Any
from datetime import datetime

from shopstack.persistence.database import Database
from shopstack.services.preference import PreferenceService
from shopstack.schemas.models import ReconciliationEvent

logger = logging.getLogger(__name__)

__all__ = [
    "learn_preferences_from_reconciliation",
]


def learn_preferences_from_reconciliation(database: Database, actual_items: list[dict[str, Any]]) -> int:
    """Analyze a batch of actual actions and learn preferences (compatibility wrapper)."""
    service = PreferenceService(database)
    events: list[ReconciliationEvent] = []
    
    for actual in actual_items:
        name = actual.get("canonical_name", "").lower().strip()
        if not name:
            continue
        try:
            ts_val = actual.get("timestamp")
            if isinstance(ts_val, str):
                ts = datetime.fromisoformat(ts_val)
            else:
                ts = ts_val or datetime.utcnow()
                
            event = ReconciliationEvent(
                event_id=actual.get("event_id") or f"compat_{actual.get('canonical_name')}_{int(ts.timestamp())}",
                timestamp=ts,
                canonical_name=name,
                actual_action=actual.get("action", "bought"),
                substituted_with=actual.get("substituted_with"),
                quantity=actual.get("quantity", 1.0),
                unit=actual.get("unit", "unit"),
            )
            events.append(event)
        except Exception as e:
            logger.debug("Failed to map compatibility actual item to ReconciliationEvent: %s", e)
            
    return service.learn_from_reconciliation(events)
