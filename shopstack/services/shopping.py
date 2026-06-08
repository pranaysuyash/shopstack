from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from shopstack.services.results import (
    CompletionItem,
    MarkPurchasedResult,
    PurchaseResultItem,
    ShoppingCompletionResult,
)
from shopstack.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

ITEM_ALIASES: dict[str, list[str]] = {
    "tomato": ["tamatar", "tomatoes"],
    "coriander": ["dhania", "cilantro"],
    "curd": ["dahi", "yogurt"],
    "wheat flour": ["atta", "aata"],
    "rice": ["chawal"],
    "lentils": ["dal", "daal"],
    "onion": ["pyaaz", "pyaz"],
    "potato": ["aloo", "alu"],
}


@dataclass
class ShoppingPlan:
    must_buy: list[dict[str, Any]] = field(default_factory=list)
    optional: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    use_soon: list[dict[str, Any]] = field(default_factory=list)

    @property
    def all_items(self) -> list[dict[str, Any]]:
        return self.must_buy + self.optional + self.skipped + self.use_soon


def normalize_item_name(name: str) -> str:
    normal = re.sub(r"[^\w\s]", " ", name.lower()).strip()
    for canonical, aliases in ITEM_ALIASES.items():
        if normal == canonical or normal in aliases:
            return canonical
    return normal


def classify_shopping_items(items: list[dict[str, Any]], tools: ToolRegistry) -> ShoppingPlan:
    """Classify shopping-list items against household memory and market signals.

    Mutates the passed item dictionaries with `reason`, `priority`, and
    `smart_decision` so persistence keeps the same enriched decision contract.
    """
    plan = ShoppingPlan()
    seen: set[str] = set()

    for item in items:
        name = item["canonical_name"]
        normalized = normalize_item_name(name)
        if normalized in seen:
            continue
        seen.add(normalized)

        try:
            qty = float(item.get("requested_quantity", 1.0) or 1.0)
        except (TypeError, ValueError):
            qty = 1.0
        unit = item.get("unit", "unit") or "unit"
        comparison = tools.compare_visible_item_to_inventory(name, qty, unit)
        decision = comparison.get("decision", "maybe")
        total_have = comparison.get("total_quantity_at_home", 0)

        if comparison.get("is_use_soon", False) and decision != "skip":
            decision = "use_soon"

        if decision == "skip":
            conf = min(0.95, 0.82 + (total_have / (qty * 4)) * 0.13) if total_have > 0 else 0.82
        elif decision == "use_soon":
            conf = 0.85
        elif decision == "optional":
            conf = 0.72
        elif total_have > 0:
            conf = 0.62
        else:
            conf = 0.52

        enriched = {
            "canonical_name": normalized.title(),
            "decision": decision,
            "smart_decision": decision,
            "reason": comparison.get("reason", ""),
            "confidence": round(conf, 2),
            "requested_quantity": qty,
            "unit": unit,
        }

        if decision == "skip":
            enriched["priority"] = "avoid_buying"
            plan.skipped.append(enriched)
        elif decision == "use_soon":
            enriched["priority"] = "must_buy"
            plan.use_soon.append(enriched)
        elif decision == "optional":
            enriched["priority"] = "optional"
            plan.optional.append(enriched)
        else:
            enriched["priority"] = "must_buy"
            plan.must_buy.append(enriched)

        item["reason"] = enriched["reason"]
        item["priority"] = enriched["priority"]
        item["smart_decision"] = enriched["smart_decision"]

    enrich_items_with_swiggy(plan.all_items)
    return plan


def enrich_items_with_swiggy(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach Swiggy market price + availability data to shopping-list items."""
    try:
        from shopstack.decisions import check_swiggy_availability
        names = [item["canonical_name"].lower() for item in items]
        availability = check_swiggy_availability(names)
    except Exception:
        availability = {}

    for item in items:
        info = availability.get(item["canonical_name"].lower())
        if info:
            item["swiggy_price"] = info["price"]
            item["swiggy_price_per_kg"] = info["price_per_kg"]
            item["swiggy_available"] = info["available"]
            item["swiggy_size"] = info["raw_size"]
        else:
            item["swiggy_price"] = None
            item["swiggy_price_per_kg"] = None
            item["swiggy_available"] = None
            item["swiggy_size"] = ""
    return items


# ─── Shopping Completion Services ───

from shopstack.persistence.database import Database  # noqa: E402 — circular import
from shopstack.traces.export import create_trace  # noqa: E402 — circular import


def complete_shopping_list_service(
    list_id: str,
    tools: ToolRegistry,
    database: Database | None = None,
) -> ShoppingCompletionResult:
    """Complete a shopping list: convert items to inventory and mark list complete.

    Returns a typed ShoppingCompletionResult. Call ``.to_html()`` for display.
    Accepts an optional ``database`` parameter for dependency injection;
    falls back to ``shopstack.app_context.db`` when not provided (legacy path).
    """
    if database is None:
        from shopstack.app_context import db as database

    if not list_id:
        return ShoppingCompletionResult(
            success=False, list_id="", message="No active shopping list to complete."
        )

    sl = database.get_active_shopping_list()
    if not sl or sl.list_id != list_id:
        return ShoppingCompletionResult(
            success=False, list_id=list_id,
            message="Active list not found or already completed."
        )

    items = sl.items or []
    if not items:
        database.mark_list_complete(list_id)
        return ShoppingCompletionResult(
            success=True, list_id=list_id, message="Empty list marked complete."
        )

    added: list[CompletionItem] = []
    for item in items:
        priority = item.priority or "optional"
        if priority == "avoid_buying":
            continue
        qty = item.requested_quantity or 1.0
        if priority == "optional":
            qty = max(qty * 0.5, 0.5)
        result = tools.add_inventory_item(
            canonical_name=item.canonical_name.lower().strip(),
            display_name=item.canonical_name.strip(),
            quantity=qty,
            unit=item.unit or "unit",
            storage_location_id="kitchen",
        )
        lot_id = result.get("lot_id", "")
        added.append(CompletionItem(
            canonical_name=item.canonical_name,
            lot_id=lot_id,
            quantity=qty,
            unit=item.unit or "unit",
        ))

    database.mark_list_complete(list_id)

    skipped = sum(1 for item in items if (item.priority or "") == "avoid_buying")

    try:
        create_trace(
            database,
            input_type="form",
            user_goal="complete_shopping_list",
            redacted_user_request=f"completed list: {sl.goal or ''}",
            perception={"goal": sl.goal or "", "item_count": len(items), "added_count": len(added)},
            inventory_context={"added_items": [i.canonical_name for i in added]},
            decision={"action": "mark_list_complete"},
            proposed_tool_calls=[],
            final_response=f"Completed list with {len(added)} items added to inventory",
            human_confirmation="auto-confirmed",
        )
    except Exception as exc:
        logger.debug("Failed to record complete list trace: %s", exc)

    return ShoppingCompletionResult(
        success=True,
        list_id=list_id,
        items_added=added,
        items_skipped=skipped,
        goal=sl.goal or "",
        message=f"List completed! Added {len(added)} items to inventory.",
    )


def mark_items_purchased_service(
    item_ids_json: str | list[str],
    tools: ToolRegistry,
    database: Database | None = None,
) -> MarkPurchasedResult:
    """Mark selected shopping list items as purchased and add to inventory.

    Returns a typed MarkPurchasedResult. Call ``.to_html()`` for display.
    Accepts an optional ``database`` parameter for dependency injection;
    falls back to ``shopstack.app_context.db`` when not provided (legacy path).
    """
    if database is None:
        from shopstack.app_context import db as database

    if item_ids_json == "[]" or item_ids_json == [] or not item_ids_json:
        return MarkPurchasedResult(success=False, message="No items selected.")

    if isinstance(item_ids_json, list):
        selected = item_ids_json
    else:
        try:
            selected = json.loads(item_ids_json)
        except (json.JSONDecodeError, TypeError):
            return MarkPurchasedResult(success=False, message="Could not parse selection.")

    if not selected:
        return MarkPurchasedResult(success=False, message="No items selected.")

    sl = database.get_active_shopping_list()
    if not sl or not sl.items:
        return MarkPurchasedResult(success=False, message="No active shopping list.")

    added: list[PurchaseResultItem] = []
    matched_ids = set(selected)
    for item in sl.items:
        if item.list_item_id in matched_ids:
            qty = item.requested_quantity or 1.0
            result = tools.add_inventory_item(
                canonical_name=item.canonical_name.lower().strip(),
                display_name=item.canonical_name.strip(),
                quantity=qty,
                unit=item.unit or "unit",
                storage_location_id="kitchen",
            )
            lot_id = result.get("lot_id", "")
            database.update_list_item(item.list_item_id, {"status": "bought"})
            added.append(PurchaseResultItem(
                canonical_name=item.canonical_name,
                lot_id=lot_id,
                quantity=qty,
                unit=item.unit or "unit",
            ))

    if not added:
        return MarkPurchasedResult(success=False, message="No valid items found to mark as purchased.")

    return MarkPurchasedResult(
        success=True,
        items_added=added,
        message=f"Marked {len(added)} item(s) as purchased and added to inventory.",
    )
