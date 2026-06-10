"""Post-shopping reconciliation service.

The review (§3.2) identifies this as the loop closer:
Plan basket → user shops → confirm actuals → update inventory →
update price memory → improve next recommendation.

Until this exists, ShopStack is advisory. After this, it becomes
a household memory system.

Flow:
  1. User reports what they actually bought/skipped/substituted
  2. System records ReconciliationEvents
  3. Inventory is updated (new lots added, quantities adjusted)
  4. Price observations are recorded
  5. Future recommendations improve
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from shopstack.schemas.models import (
    ReconciliationAction,
    ReconciliationEvent,
    new_id,
)
from shopstack.repos.inventory import InventoryRepo
from shopstack.tools.spec import DEFAULT_STORAGE_LOCATION

logger = logging.getLogger(__name__)

__all__ = [
    "ReconciliationResult",
    "reconcile_shopping_trip",
    "build_correction_event",
]


@dataclass
class ReconciliationResult:
    """Outcome of reconciling a single shopping trip."""
    trip_id: str
    events: list[ReconciliationEvent] = field(default_factory=list)
    inventory_updates: list[dict[str, Any]] = field(default_factory=list)
    price_observations: list[dict[str, Any]] = field(default_factory=list)
    success: bool = True
    message: str = ""
    errors: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.events)

    @property
    def bought_count(self) -> int:
        return sum(1 for e in self.events if e.actual_action == "bought")

    @property
    def skipped_count(self) -> int:
        return sum(1 for e in self.events if e.actual_action == "skipped")

    @property
    def substituted_count(self) -> int:
        return sum(1 for e in self.events if e.actual_action == "substituted")

    def to_dict(self) -> dict[str, Any]:
        return {
            "trip_id": self.trip_id,
            "events_count": self.count,
            "bought": self.bought_count,
            "skipped": self.skipped_count,
            "substituted": self.substituted_count,
            "success": self.success,
            "message": self.message,
            "errors": self.errors,
        }


def reconcile_shopping_trip(
    planned_items: list[dict[str, Any]],
    actual_items: list[dict[str, Any]],
    tools=None,
    database=None,
) -> ReconciliationResult:
    """Reconcile a planned shopping trip against what actually happened.

    Each actual item should have:
      - canonical_name: str
      - action: "bought" | "skipped" | "substituted" | "price_changed" | "not_found"
      - quantity: float (optional, defaults to planned)
      - price_paid: float (optional)
      - substituted_with: str (optional, canonical name if substituted)
      - notes: str (optional)

    Args:
        planned_items: Items from the decision engine / shopping plan.
        actual_items: What the user actually did after shopping.
        tools: InventoryRepo or ToolRegistry for inventory mutations.
        database: Database for persistence.

    Returns:
        ReconciliationResult with events, inventory updates, and price observations.
    """
    trip_id = new_id()
    result = ReconciliationResult(trip_id=trip_id)

    planned_map: dict[str, dict[str, Any]] = {}
    for item in planned_items:
        name = item.get("canonical_name", "").lower().strip()
        if name:
            planned_map[name] = item

    for actual in actual_items:
        name = actual.get("canonical_name", "").lower().strip()
        if not name:
            continue

        action_str = actual.get("action", "bought")
        planned = planned_map.get(name, {})
        planned_action = planned.get("action", planned.get("smart_decision", "unknown"))

        qty = float(actual.get("quantity", planned.get("requested_quantity", 1.0)) or 1.0)
        unit = actual.get("unit", planned.get("unit", "unit")) or "unit"
        price_paid = actual.get("price_paid")
        planned_price = actual.get("planned_price") or planned.get("market_price")

        event = ReconciliationEvent(
            canonical_name=name,
            planned_action=str(planned_action),
            actual_action=action_str,
            quantity=qty,
            unit=unit,
            price_paid=float(price_paid) if price_paid is not None else None,
            planned_price=float(planned_price) if planned_price is not None else None,
            substituted_with=actual.get("substituted_with"),
            notes=actual.get("notes"),
            source=actual.get("source", "manual"),
        )
        result.events.append(event)

        # ── Update inventory for bought items ──
        if action_str == "bought" and tools is not None:
            try:
                _add = tools.add_item if isinstance(tools, InventoryRepo) else tools.add_inventory_item
                add_result = _add(
                    canonical_name=name,
                    display_name=name.replace("_", " ").title(),
                    quantity=qty,
                    unit=unit,
                    storage_location_id=DEFAULT_STORAGE_LOCATION,
                )
                lot_id = add_result.get("lot_id", "")
                result.inventory_updates.append({
                    "action": "added",
                    "canonical_name": name,
                    "lot_id": lot_id,
                    "quantity": qty,
                    "unit": unit,
                })
            except Exception as exc:
                error_msg = f"Inventory update failed for {name}: {exc}"
                logger.warning(error_msg)
                result.errors.append(error_msg)
                result.inventory_updates.append({
                    "action": "failed",
                    "canonical_name": name,
                    "error": str(exc),
                })

        elif action_str == "substituted" and tools is not None:
            sub_name = actual.get("substituted_with", "").lower().strip()
            if sub_name:
                try:
                    _add = tools.add_item if isinstance(tools, InventoryRepo) else tools.add_inventory_item
                    add_result = _add(
                        canonical_name=sub_name,
                        display_name=sub_name.replace("_", " ").title(),
                        quantity=qty,
                        unit=unit,
                        storage_location_id=DEFAULT_STORAGE_LOCATION,
                    )
                    lot_id = add_result.get("lot_id", "")
                    result.inventory_updates.append({
                        "action": "substituted",
                        "original": name,
                        "substituted_with": sub_name,
                        "lot_id": lot_id,
                        "quantity": qty,
                        "unit": unit,
                    })
                except Exception as exc:
                    error_msg = f"Substitution inventory update failed for {name}→{sub_name}: {exc}"
                    logger.warning(error_msg)
                    result.errors.append(error_msg)

        # ── Record price observation for bought items ──
        if action_str == "bought" and price_paid is not None and database is not None:
            try:
                from shopstack.schemas.models import PriceObservation
                observation = PriceObservation(
                    canonical_name=name,
                    quantity=qty,
                    unit=unit,
                    price=float(price_paid),
                    source_event_id=event.event_id,
                    notes=f"Reconciled from trip {trip_id}",
                )
                result.price_observations.append({
                    "canonical_name": name,
                    "price": observation.price,
                    "quantity": qty,
                    "unit": unit,
                })
            except Exception as exc:
                logger.debug("Price observation record failed for %s: %s", name, exc)

    # ── Build message with error count ──
    error_count = len(result.errors)
    error_suffix = f" ({error_count} error{'s' if error_count != 1 else ''})" if error_count else ""
    result.message = (
        f"Reconciled {result.count} items: "
        f"{result.bought_count} bought, {result.skipped_count} skipped, "
        f"{result.substituted_count} substituted.{error_suffix}"
    )
    result.success = error_count == 0

    # Record trace if database available
    if database is not None:
        try:
            from shopstack.traces.export import create_trace
            create_trace(
                database,
                input_type="reconciliation",
                user_goal="post_shopping_reconciliation",
                redacted_user_request=f"trip {trip_id}: {result.count} items",
                perception={"trip_id": trip_id, "item_count": result.count},
                inventory_context={
                    "bought": [e.canonical_name for e in result.events if e.actual_action == "bought"],
                    "skipped": [e.canonical_name for e in result.events if e.actual_action == "skipped"],
                },
                decision={"action": "reconcile", "bought": result.bought_count},
                proposed_tool_calls=[],
                final_response=result.message,
                human_confirmation="auto-confirmed",
            )
        except Exception as exc:
            logger.debug("Trace record failed for reconciliation: %s", exc)

    return result


def build_correction_event(
    canonical_name: str,
    correction_type: str,
    old_value: str,
    new_value: str,
    source: str = "user_correction",
) -> dict[str, Any]:
    """Build a structured correction event from user feedback.

    The review (§3.6) identifies corrections as the learning loop:
    "This is not tomato, this is hybrid tomato."
    "We don't buy this brand."
    "We call this sambar onion."

    Returns a dict suitable for storage and learning.

    Note: Returns a dict (not a typed model) because the CorrectionEvent
    schema is deferred until the PreferenceService is built. The dict keys
    are documented here for forward compatibility.
    """
    return {
        "event_id": new_id(),
        "canonical_name": canonical_name,
        "correction_type": correction_type,  # alias / brand / pack_size / preference / waste_pattern
        "old_value": old_value,
        "new_value": new_value,
        "source": source,
    }
