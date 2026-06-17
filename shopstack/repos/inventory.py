"""Domain operations for inventory management.

This repo encapsulates all inventory-related business logic: adding, updating,
consuming, moving, finding, and analyzing inventory items. Services and the
decision engine depend on this instead of the full ToolRegistry.
"""

from __future__ import annotations

from datetime import date
from typing import Any, cast

from shopstack.persistence.database import Database
from shopstack.schemas.models import (
    InventoryEvent,
    InventoryLot,
    MovementEvent,
    MovementSource,
)
from shopstack.tools.spec import DEFAULT_STORAGE_LOCATION


class InventoryRepo:
    def __init__(self, db: Database, embedding_provider: Any = None):
        self.db = db
        self._embedding_provider = embedding_provider
        self._find_service = None

    # --- Lot ID resolution ---

    def resolve_lot_id(self, lot_id: str) -> tuple[str | None, str | None]:
        if not lot_id:
            return None, "Lot id cannot be empty"
        candidates = self.db.get_inventory_lot_ids(lot_id)
        if not candidates:
            return None, f"Lot {lot_id} not found"
        if len(candidates) > 1:
            return None, f"Lot id '{lot_id}' is ambiguous, use more characters"
        return candidates[0], None

    # --- CRUD ---

    def add_item(
        self,
        canonical_name: str,
        display_name: str = "",
        quantity: float = 1.0,
        unit: str = "unit",
        storage_location_id: str = DEFAULT_STORAGE_LOCATION,
        purchase_date: str | None = None,
        estimated_use_by_date: str | None = None,
        label_expiry_date: str | None = None,
        price_paid: float | None = None,
        source_event_id: str = "",
        confidence: float = 1.0,
        category: str = "",
        user_id: str = "",
    ) -> dict[str, Any]:
        lot = InventoryLot(
            canonical_name=canonical_name,
            display_name=display_name or canonical_name,
            quantity=quantity,
            unit=unit,
            storage_location_id=storage_location_id,
            purchase_date=date.fromisoformat(purchase_date) if purchase_date else date.today(),
            estimated_use_by_date=date.fromisoformat(estimated_use_by_date) if estimated_use_by_date else None,
            label_expiry_date=date.fromisoformat(label_expiry_date) if label_expiry_date else None,
            price_paid=price_paid,
            source_event_id=source_event_id,
            confidence=confidence,
            category=category,
        )
        self.db.add_inventory_lot(lot, user_id=user_id)
        self.db.record_inventory_event(InventoryEvent(
            lot_id=lot.lot_id,
            canonical_name=canonical_name,
            action="added",
            quantity_before=0,
            quantity_after=quantity,
            quantity_delta=quantity,
            unit=unit,
            location_to=storage_location_id,
            source=source_event_id or "manual",
        ), user_id=user_id)
        return {"lot": lot.model_dump(), "lot_id": lot.lot_id}

    def update_item(self, lot_id: str, updates: dict) -> dict[str, Any]:
        resolved_id, resolve_error = self.resolve_lot_id(lot_id)
        if resolve_error:
            return {"success": False, "error": resolve_error}
        assert resolved_id is not None
        lot = self.db.update_inventory_lot(resolved_id, updates)
        if not lot:
            return {"success": False, "error": f"Lot {lot_id} not found"}
        return {"lot": lot.model_dump()}

    def consume_item(
        self, lot_id: str, quantity: float = 1.0, reason: str | None = None, user_id: str = ""
    ) -> dict[str, Any]:
        resolved_id, resolve_error = self.resolve_lot_id(lot_id)
        if resolve_error:
            return {"success": False, "error": resolve_error}
        assert resolved_id is not None
        lot = self.db.get_inventory_lot(resolved_id)
        if not lot:
            return {"success": False, "error": f"Lot {lot_id} not found"}
        if quantity <= 0:
            return {"success": False, "error": "Quantity to consume must be a positive number"}
        if lot.quantity < quantity:
            quantity = lot.quantity
        qty_before = lot.quantity
        updated = self.db.consume_inventory(resolved_id, quantity, user_id=user_id)
        if not updated:
            return {"success": False, "error": "Consumption failed"}
        self.db.record_inventory_event(InventoryEvent(
            lot_id=resolved_id,
            canonical_name=lot.canonical_name,
            action="consumed",
            quantity_before=qty_before,
            quantity_after=updated.quantity,
            quantity_delta=-quantity,
            unit=lot.unit,
            source="manual",
            notes=reason,
        ))
        return {
            "lot": updated.model_dump(),
            "consumed_quantity": quantity,
            "remaining": updated.quantity,
            "status": updated.status,
        }

    def move_item(
        self, lot_id: str, to_location_id: str, source: str = "manual"
    ) -> dict[str, Any]:
        resolved_id, resolve_error = self.resolve_lot_id(lot_id)
        if resolve_error:
            return {"success": False, "error": resolve_error}
        assert resolved_id is not None
        lot = self.db.get_inventory_lot(resolved_id)
        if not lot:
            return {"success": False, "error": f"Lot {lot_id} not found"}
        location = self.db.get_location(to_location_id)
        if not location:
            return {"success": False, "error": f"Location {to_location_id} not found"}
        movement = MovementEvent(
            lot_id=resolved_id,
            from_location_id=lot.storage_location_id or None,
            to_location_id=to_location_id,
            source=cast(MovementSource, source),
        )
        self.db.record_movement(movement)
        self.db.record_inventory_event(InventoryEvent(
            lot_id=resolved_id,
            canonical_name=lot.canonical_name,
            action="moved",
            unit=lot.unit,
            location_from=lot.storage_location_id,
            location_to=to_location_id,
            source=source,
        ))
        return {
            "movement": movement.model_dump(),
            "from": lot.storage_location_id,
            "to": to_location_id,
        }

    # --- Undo ---

    def undo_last_change(self, lot_id: str, user_id: str = "") -> dict[str, Any]:
        """Reverse the most recent inventory event for a lot.

        Looks up the latest ``inventory_events`` row for the resolved lot,
        computes its inverse via :meth:`InventoryEvent.get_undo_event`,
        applies that inverse to the lot, and records the inverse itself as
        a new ``action="undo"`` event so the reversal stays in the audit
        trail rather than rewriting history.
        """
        resolved_id, resolve_error = self.resolve_lot_id(lot_id)
        if resolve_error:
            return {"success": False, "error": resolve_error}
        assert resolved_id is not None
        lot = self.db.get_inventory_lot(resolved_id)
        if not lot:
            return {"success": False, "error": f"Lot {lot_id} not found"}

        events = self.db.get_inventory_events(lot_id=resolved_id, limit=1)
        if not events:
            return {
                "success": False,
                "error": "No history to undo for this lot — make a change first, then try again.",
            }
        last_event = events[0]

        undo_event = last_event.get_undo_event()
        if undo_event is None:
            return {
                "success": False,
                "error": f"Cannot undo a '{last_event.action}' event",
            }

        if undo_event.action == "moved":
            if not undo_event.location_to:
                return {"success": False, "error": "Original location is unknown, cannot undo move"}
            movement = MovementEvent(
                lot_id=resolved_id,
                from_location_id=undo_event.location_from,
                to_location_id=undo_event.location_to,
                source="manual",
            )
            self.db.record_movement(movement, user_id=user_id)
        else:
            new_qty = undo_event.quantity_after if undo_event.quantity_after is not None else lot.quantity
            new_status = "used" if new_qty <= 0 else "active"
            self.db.update_inventory_lot(resolved_id, {"quantity": new_qty, "status": new_status}, user_id=user_id)

        self.db.record_inventory_event(undo_event, user_id=user_id)

        updated = self.db.get_inventory_lot(resolved_id)
        return {
            "success": True,
            "undone_action": last_event.action,
            "lot": updated.model_dump() if updated else None,
        }

    # --- Search / query ---

    def find(self, query: str, user_id: str = "") -> dict[str, Any]:
        return self._shopfind().find_inventory_compatible(query, user_id=user_id)

    def semantic_find(self, query: str, user_id: str = "") -> dict[str, Any]:
        return self._shopfind().semantic_find_inventory_compatible(query, user_id=user_id)

    def _shopfind(self):
        if self._find_service is None:
            from shopstack.services.find import ShopFindService

            self._find_service = ShopFindService(self.db, self._embedding_provider)
        return self._find_service

    # --- Inventory comparison (returns raw data, no classification) ---

    def compare_visible(
        self, canonical_name: str, quantity: float = 1.0, unit: str = "unit", user_id: str = ""
    ) -> dict[str, Any]:
        all_inventory = self.db.get_inventory(user_id=user_id)
        matching = [lot for lot in all_inventory if lot.canonical_name.lower() == canonical_name.lower()]
        total_have = sum(lot.quantity for lot in matching)
        active_lots = [lot for lot in matching if lot.status == "active"]
        soon = self.get_use_soon(days=3, user_id=user_id)
        is_use_soon = any(
            canonical_name.lower() in s.get("canonical_name", "").lower()
            for s in soon.get("items", [])
        )
        return {
            "canonical_name": canonical_name,
            "in_home_inventory": total_have > 0,
            "total_quantity_at_home": total_have,
            "active_lots": len(active_lots),
            "is_use_soon": is_use_soon,
            "shortfall": max(quantity - total_have, 0),
            "surplus_ratio": total_have / quantity if quantity > 0 else float("inf"),
        }

    # --- Use-soon / buy suggestions ---

    def get_use_soon(self, days: int = 3, user_id: str = "") -> dict[str, Any]:
        all_inventory = self.db.get_inventory(status="active", user_id=user_id)
        soon = []
        today = date.today()
        for lot in all_inventory:
            ref_date = lot.label_expiry_date or lot.estimated_use_by_date
            if ref_date and 0 <= (ref_date - today).days <= days:
                soon.append({
                    "lot_id": lot.lot_id,
                    "canonical_name": lot.canonical_name,
                    "display_name": lot.display_name,
                    "quantity": lot.quantity,
                    "unit": lot.unit,
                    "expiry_date": ref_date.isoformat(),
                    "expiry_type": "label" if lot.label_expiry_date else "estimated",
                    "days_remaining": (ref_date - today).days,
                })
            elif lot.purchase_date and (today - lot.purchase_date).days >= 7:
                soon.append({
                    "lot_id": lot.lot_id,
                    "canonical_name": lot.canonical_name,
                    "display_name": lot.display_name,
                    "quantity": lot.quantity,
                    "unit": lot.unit,
                    "purchase_date": lot.purchase_date.isoformat(),
                    "days_since_purchase": (today - lot.purchase_date).days,
                    "reason": "purchased over a week ago",
                })
        soon.sort(key=lambda x: x.get("days_remaining", 999))
        return {"items": soon[:20], "count": len(soon)}

    def get_buy_suggestions(self, user_id: str = "") -> dict[str, Any]:
        all_inventory = self.db.get_inventory(user_id=user_id)
        suggestions = []
        for lot in all_inventory:
            if lot.quantity <= 0 or lot.status == "used" or lot.status == "expired":
                suggestions.append({
                    "canonical_name": lot.canonical_name,
                    "display_name": lot.display_name,
                    "reason": f"All {lot.canonical_name} has been used.",
                    "priority": "must_buy",
                })
            elif lot.status == "low" or lot.quantity <= 0.5:
                suggestions.append({
                    "canonical_name": lot.canonical_name,
                    "display_name": lot.display_name,
                    "reason": f"Running low: {lot.quantity} {lot.unit} remaining.",
                    "priority": "must_buy",
                    "suggested_quantity": max(round(lot.quantity * 2, 1), 1.0),
                })
            elif lot.label_expiry_date and (lot.label_expiry_date - date.today()).days <= 3:
                suggestions.append({
                    "canonical_name": lot.canonical_name,
                    "display_name": lot.display_name,
                    "reason": f"Expiring in {(lot.label_expiry_date - date.today()).days} days.",
                    "priority": "optional",
                    "suggested_quantity": round(lot.quantity, 1),
                })
        return {"suggestions": suggestions[:10], "count": len(suggestions)}
