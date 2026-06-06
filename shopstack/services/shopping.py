from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from shopstack.tools.registry import ToolRegistry


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
