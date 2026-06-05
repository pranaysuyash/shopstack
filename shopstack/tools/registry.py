from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable

from shopstack.persistence.database import Database
from shopstack.schemas.models import (
    InventoryLot,
    MovementEvent,
    PriceObservation,
    PurchaseEvent,
    ShoppingListItem,
    Trace,
)

ToolFunc = Callable[..., dict[str, Any]]


class ToolRegistry:
    def __init__(self, db: Database):
        self.db = db
        self._tools: dict[str, tuple[ToolFunc, str, list[str]]] = {}
        self._register_all()

    def _register(
        self, name: str, fn: ToolFunc, description: str, arg_names: list[str]
    ) -> None:
        self._tools[name] = (fn, description, arg_names)

    def _register_all(self) -> None:
        self._register(
            "add_inventory_item",
            self.add_inventory_item,
            "Add a new item to household inventory",
            ["canonical_name", "display_name", "quantity", "unit", "storage_location_id"],
        )
        self._register(
            "update_inventory_item",
            self.update_inventory_item,
            "Update details of an existing inventory item",
            ["lot_id", "updates"],
        )
        self._register(
            "consume_inventory_item",
            self.consume_inventory_item,
            "Record consumption of an inventory item",
            ["lot_id", "quantity"],
        )
        self._register(
            "move_inventory_item",
            self.move_inventory_item,
            "Move an item to a different storage location",
            ["lot_id", "to_location_id"],
        )
        self._register(
            "find_item",
            self.find_item,
            "Search for an item across inventory and locations",
            ["query"],
        )
        self._register(
            "create_or_update_shopping_list",
            self.create_or_update_shopping_list,
            "Create or update the active shopping list",
            ["items", "goal"],
        )
        self._register(
            "compare_visible_item_to_inventory",
            self.compare_visible_item_to_inventory,
            "Compare a detected visible item against current inventory",
            ["canonical_name", "quantity", "unit"],
        )
        self._register(
            "record_price_observation",
            self.record_price_observation,
            "Record a price observation for an item",
            ["canonical_name", "price", "quantity", "unit", "store_name"],
        )
        self._register(
            "get_use_soon_items",
            self.get_use_soon_items,
            "Get items that need to be used soon (expiring or old)",
            ["days"],
        )
        self._register(
            "get_next_buy_suggestions",
            self.get_next_buy_suggestions,
            "Get suggestions for what to buy next",
            [],
        )
        self._register(
            "export_anonymized_trace",
            self.export_anonymized_trace,
            "Export an anonymized agent trace",
            ["trace_id"],
        )

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": name, "description": desc, "arg_names": args}
            for name, (_, desc, args) in self._tools.items()
        ]

    def execute(self, tool_name: str, **kwargs) -> dict[str, Any]:
        entry = self._tools.get(tool_name)
        if not entry:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        fn, _, _ = entry
        try:
            result = fn(**kwargs)
            return {"success": True, "result": result, "tool": tool_name}
        except Exception as e:
            return {"success": False, "error": str(e), "tool": tool_name}

    # --- Tool implementations ---

    def _resolve_lot_id(self, lot_id: str) -> tuple[str | None, str | None]:
        if not lot_id:
            return None, "Lot id cannot be empty"
        candidates = self.db.get_inventory_lot_ids(lot_id)
        if not candidates:
            return None, f"Lot {lot_id} not found"
        if len(candidates) > 1:
            return None, f"Lot id '{lot_id}' is ambiguous, use more characters"
        return candidates[0], None

    def add_inventory_item(
        self,
        canonical_name: str,
        display_name: str = "",
        quantity: float = 1.0,
        unit: str = "unit",
        storage_location_id: str = "kitchen",
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

    def update_inventory_item(self, lot_id: str, updates: dict) -> dict[str, Any]:
        resolved_id, resolve_error = self._resolve_lot_id(lot_id)
        if resolve_error:
            return {"error": resolve_error}
        lot = self.db.update_inventory_lot(resolved_id, updates)
        if not lot:
            return {"error": f"Lot {lot_id} not found"}
        return {"lot": lot.model_dump()}

    def consume_inventory_item(
        self, lot_id: str, quantity: float = 1.0, reason: str | None = None
    ) -> dict[str, Any]:
        resolved_id, resolve_error = self._resolve_lot_id(lot_id)
        if resolve_error:
            return {"error": resolve_error}
        lot = self.db.get_inventory_lot(resolved_id) if resolved_id else None
        if not lot:
            return {"error": f"Lot {lot_id} not found"}
        if quantity <= 0:
            return {"error": "Quantity to consume must be a positive number"}
        if lot.quantity < quantity:
            quantity = lot.quantity
        updated = self.db.consume_inventory(resolved_id, quantity)
        if not updated:
            return {"error": "Consumption failed"}
        return {
            "lot": updated.model_dump(),
            "consumed_quantity": quantity,
            "remaining": updated.quantity,
            "status": updated.status,
        }

    def move_inventory_item(
        self, lot_id: str, to_location_id: str, source: str = "manual"
    ) -> dict[str, Any]:
        resolved_id, resolve_error = self._resolve_lot_id(lot_id)
        if resolve_error:
            return {"error": resolve_error}
        lot = self.db.get_inventory_lot(resolved_id)
        if not lot:
            return {"error": f"Lot {lot_id} not found"}
        location = self.db.get_location(to_location_id)
        if not location:
            return {"error": f"Location {to_location_id} not found"}
        movement = MovementEvent(
            lot_id=resolved_id,
            from_location_id=lot.storage_location_id or None,
            to_location_id=to_location_id,
            source=source,
        )
        self.db.record_movement(movement)
        return {
            "movement": movement.model_dump(),
            "from": lot.storage_location_id,
            "to": to_location_id,
        }

    def find_item(self, query: str) -> dict[str, Any]:
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

    def create_or_update_shopping_list(
        self,
        items: list[dict[str, Any]] | None = None,
        goal: str = "",
    ) -> dict[str, Any]:
        existing = self.db.get_active_shopping_list()
        if existing:
            sl = existing
            sl.goal = goal or sl.goal
        else:
            sl = self.db.create_shopping_list(goal=goal)

        if items:
            for item_data in items:
                sl_item = ShoppingListItem(
                    canonical_name=item_data.get("canonical_name", ""),
                    requested_quantity=item_data.get("requested_quantity"),
                    unit=item_data.get("unit"),
                    priority=item_data.get("priority", "optional"),
                    reason=item_data.get("reason", ""),
                )
                self.db.add_list_item(sl.list_id, sl_item)

        return {"list": self._load_list(sl.list_id)}

    def _load_list(self, list_id: str) -> dict[str, Any]:
        row = self.db.conn.execute(
            "SELECT * FROM shopping_lists WHERE list_id = ?", (list_id,)
        ).fetchone()
        if not row:
            return {}
        from shopstack.persistence.database import _row_to_list
        sl = _row_to_list(row, self.db.conn)
        return sl.model_dump()

    def compare_visible_item_to_inventory(
        self, canonical_name: str, quantity: float = 1.0, unit: str = "unit"
    ) -> dict[str, Any]:
        all_inventory = self.db.get_inventory()
        matching = [lot for lot in all_inventory if lot.canonical_name.lower() == canonical_name.lower()]
        total_have = sum(lot.quantity for lot in matching)
        active_lots = [lot for lot in matching if lot.status == "active"]
        soon = self.get_use_soon_items(days=3)
        is_use_soon = any(
            canonical_name.lower() in s.get("canonical_name", "").lower()
            for s in soon.get("items", [])
        )

        decision = "buy"
        reason = f"No {canonical_name} found in inventory."
        if total_have > 0:
            if total_have >= quantity * 2:
                decision = "skip"
                reason = f"You already have {total_have} {unit} of {canonical_name} at home."
            elif total_have >= quantity:
                decision = "optional"
                reason = f"You have {total_have} {unit}. Only buy if needed."
            else:
                decision = "buy"
                reason = f"You have only {total_have} {unit}. Buy {max(quantity - total_have, 0)} {unit}."

        return {
            "canonical_name": canonical_name,
            "in_home_inventory": total_have > 0,
            "total_quantity_at_home": total_have,
            "active_lots": len(active_lots),
            "is_use_soon": is_use_soon,
            "decision": decision,
            "reason": reason,
        }

    def record_price_observation(
        self,
        canonical_name: str,
        price: float,
        quantity: float = 1.0,
        unit: str = "unit",
        store_name: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        obs = PriceObservation(
            canonical_name=canonical_name,
            price=price,
            quantity=quantity,
            unit=unit,
            store_name=store_name,
            observation_date=date.today(),
            notes=notes,
        )
        self.db.record_price(obs)
        history = self.db.get_price_history(canonical_name)
        last_price = history[1].price if len(history) > 1 else None
        return {
            "observation": obs.model_dump(),
            "last_price": last_price,
            "change": round(price - last_price, 2) if last_price else None,
        }

    def get_use_soon_items(self, days: int = 3) -> dict[str, Any]:
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

    def get_next_buy_suggestions(self) -> dict[str, Any]:
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

    def export_anonymized_trace(self, trace_id: str) -> dict[str, Any]:
        traces = self.db.get_traces(limit=100)
        for t in traces:
            if t.trace_id == trace_id:
                return {"trace": _redact_trace(t.model_dump())}
        return {"error": f"Trace {trace_id} not found"}


def _redact_trace(t: dict) -> dict:
    if "redacted_user_request" in t:
        t["user_goal"] = "[REDACTED]"
    tool_calls = t.get("proposed_tool_calls", [])
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if isinstance(tc, dict):
                args = tc.get("args", {})
                for sensitive_key in ["address", "phone", "email", "name"]:
                    if sensitive_key in args:
                        args[sensitive_key] = "[REDACTED]"
    t.pop("_private", None)
    return t
