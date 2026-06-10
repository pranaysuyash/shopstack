from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from shopstack.market.normalization import normalize_item_name
from shopstack.decisions.rules import classify_inventory_comparison
from shopstack.repos.inventory import InventoryRepo
from shopstack.services.results import (
    CompletionItem,
    MarkPurchasedResult,
    PurchaseResultItem,
    ShoppingCompletionResult,
)
from shopstack.tools.spec import DEFAULT_STORAGE_LOCATION

if TYPE_CHECKING:
    from shopstack.persistence.database import Database

logger = logging.getLogger(__name__)

# Decision confidence scores — higher = more confident in the classification.
# Skip confidence scales with existing stock (more stock → more confident skip).
_CONF_SKIP_BASE = 0.82
_CONF_SKIP_SCALE = 0.13
_CONF_SKIP_CAP = 0.95
_CONF_USE_SOON = 0.85
_CONF_OPTIONAL = 0.72
_CONF_PARTIAL_STOCK = 0.62
_CONF_NO_STOCK = 0.52

# Optional items get halved quantity to reduce waste on "nice to have" purchases
_OPTIONAL_QTY_FRACTION = 0.5
_OPTIONAL_QTY_FLOOR = 0.5


@dataclass
class ShoppingPlan:
    must_buy: list[dict[str, Any]] = field(default_factory=list)
    optional: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    use_soon: list[dict[str, Any]] = field(default_factory=list)

    @property
    def all_items(self) -> list[dict[str, Any]]:
        return self.must_buy + self.optional + self.skipped + self.use_soon


def classify_shopping_items(items: list[dict[str, Any]], inventory: InventoryRepo) -> ShoppingPlan:
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
        comparison = inventory.compare_visible(name, qty, unit)
        total_have = comparison.get("total_quantity_at_home", 0)
        is_use_soon = comparison.get("is_use_soon", False)

        decision, reason = classify_inventory_comparison(total_have, qty, unit, is_use_soon)

        if is_use_soon and decision != "skip":
            decision = "use_soon"

        if decision == "skip":
            conf = min(_CONF_SKIP_CAP, _CONF_SKIP_BASE + (total_have / (qty * 4)) * _CONF_SKIP_SCALE) if total_have > 0 else _CONF_SKIP_BASE
        elif decision == "use_soon":
            conf = _CONF_USE_SOON
        elif decision == "optional":
            conf = _CONF_OPTIONAL
        elif total_have > 0:
            conf = _CONF_PARTIAL_STOCK
        else:
            conf = _CONF_NO_STOCK

        enriched = {
            "canonical_name": normalized.title(),
            "decision": decision,
            "smart_decision": decision,
            "reason": reason,
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


def enrich_items_with_swiggy(items: list[dict[str, Any]]) -> None:
    """Attach Swiggy market price + availability data to shopping-list items in-place."""
    try:
        from shopstack.decisions import check_swiggy_availability
        names = [item["canonical_name"].lower() for item in items]
        availability = check_swiggy_availability(names)
    except Exception:
        logger.warning("Swiggy enrichment failed, prices will be empty", exc_info=True)
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


# ─── Shopping Completion Services ───

from shopstack.traces.export import create_trace


def complete_shopping_list_service(
    list_id: str,
    inventory: InventoryRepo,
    database: Database,
) -> ShoppingCompletionResult:
    """Complete a shopping list: convert items to inventory and mark list complete.

    Returns a typed ShoppingCompletionResult. Use ``render_shopping_completion()``
    from ``shopstack.ui.renderers`` for Gradio HTML display.
    """
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
            qty = max(qty * _OPTIONAL_QTY_FRACTION, _OPTIONAL_QTY_FLOOR)
        result = inventory.add_item(
            canonical_name=item.canonical_name.lower().strip(),
            display_name=item.canonical_name.strip(),
            quantity=qty,
            unit=item.unit or "unit",
            storage_location_id=DEFAULT_STORAGE_LOCATION,
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
    inventory: InventoryRepo,
    database: Database,
) -> MarkPurchasedResult:
    """Mark selected shopping list items as purchased and add to inventory.

    Returns a typed MarkPurchasedResult. Use ``render_mark_purchased()``
    from ``shopstack.ui.renderers`` for Gradio HTML display.
    """
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
            result = inventory.add_item(
                canonical_name=item.canonical_name.lower().strip(),
                display_name=item.canonical_name.strip(),
                quantity=qty,
                unit=item.unit or "unit",
                storage_location_id=DEFAULT_STORAGE_LOCATION,
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
