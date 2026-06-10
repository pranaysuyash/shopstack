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
    InventoryLot,
    MovementEvent,
    MovementSource,
)
from shopstack.tools.spec import DEFAULT_STORAGE_LOCATION


class InventoryRepo:
    def __init__(self, db: Database, embedding_provider: Any = None):
        self.db = db
        self._embedding_provider = embedding_provider

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
        self.db.add_inventory_lot(lot)
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
        self, lot_id: str, quantity: float = 1.0, reason: str | None = None
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
        updated = self.db.consume_inventory(resolved_id, quantity)
        if not updated:
            return {"success": False, "error": "Consumption failed"}
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
        return {
            "movement": movement.model_dump(),
            "from": lot.storage_location_id,
            "to": to_location_id,
        }

    # --- Search / query ---

    def find(self, query: str) -> dict[str, Any]:
        q = query.lower()
        all_inventory = self.db.get_inventory()
        results = []
        for lot in all_inventory:
            if q in lot.canonical_name.lower() or q in lot.display_name.lower():
                loc = self.db.get_location(lot.storage_location_id)
                results.append({
                    "lot": lot.model_dump(),
                    "location_name": loc.name if loc else "Unknown",
                    "location_id": lot.storage_location_id,
                })
        return {"results": results, "count": len(results)}

    def semantic_find(self, query: str) -> dict[str, Any]:
        q = query.strip()
        if not q:
            return {"results": [], "count": 0, "match_type": "none"}
        from shopstack.services.search import semantic_search
        search_results = semantic_search(
            self.db,
            query,
            threshold=0.6,
            embedding_provider=getattr(self, "_embedding_provider", None),
        )
        all_inventory = self.db.get_inventory()
        lot_results = []
        for sr in search_results:
            matching_lots = [
                lot for lot in all_inventory
                if lot.canonical_name == sr.canonical_name
            ]
            for lot in matching_lots:
                loc = self.db.get_location(lot.storage_location_id)
                lot_results.append({
                    "lot": lot.model_dump(),
                    "location_name": loc.name if loc else "Unknown",
                    "location_id": lot.storage_location_id,
                    "match_type": sr.match_type,
                    "match_score": sr.score,
                })
        match_type = lot_results[0]["match_type"] if lot_results else "none"
        return {"results": lot_results, "count": len(lot_results), "match_type": match_type}

    # --- Inventory comparison (returns raw data, no classification) ---

    def compare_visible(
        self, canonical_name: str, quantity: float = 1.0, unit: str = "unit"
    ) -> dict[str, Any]:
        all_inventory = self.db.get_inventory()
        matching = [lot for lot in all_inventory if lot.canonical_name.lower() == canonical_name.lower()]
        total_have = sum(lot.quantity for lot in matching)
        active_lots = [lot for lot in matching if lot.status == "active"]
        soon = self.get_use_soon(days=3)
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

    def get_use_soon(self, days: int = 3) -> dict[str, Any]:
        all_inventory = self.db.get_inventory(status="active")
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

    def get_buy_suggestions(self) -> dict[str, Any]:
        all_inventory = self.db.get_inventory()
        suggestions = []
        for lot in all_inventory:
            if lot.quantity <= 0 or lot.status == "used" or lot.status == "expired":
                suggestions.append({
                    "canonical_name": lot.canonical_name,
                    "display_name": lot.display_name,
                    "reason": f"All {lot.canonical_name} has been used.",
                    "priority": "must_buy",
                })
            elif lot.quantity < 0.2 * (lot.quantity if lot.quantity > 0 else 1) + 0.1 or lot.status == "low":
                suggestions.append({
                    "canonical_name": lot.canonical_name,
                    "display_name": lot.display_name,
                    "reason": f"Running low: {lot.quantity} {lot.unit} remaining.",
                    "priority": "must_buy",
                    "suggested_quantity": round(lot.quantity * 2, 1),
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
