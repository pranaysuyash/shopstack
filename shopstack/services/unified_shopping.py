"""Unified shopping flow — single-pass plan → classify → market → basket → substitutions.

This service chains the fragmented shopping pipeline into one callable:
    text/goal input → parse items → classify against inventory
    → enrich with market prices → find substitutions for sold-out items
    → build optimized basket → return structured results.

All downstream services (shopping, substitution, basket, price_memory)
are composed here. No UI, no HTML, no Gradio.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

__all__ = [
    "UnifiedShoppingResult",
    "ItemResult",
    "run_unified_shopping_flow",
]


@dataclass
class ItemResult:
    canonical_name: str
    display_name: str
    decision: str  # buy | skip | use_soon | optional | compare
    reason: str
    confidence: float = 0.5
    requested_quantity: float = 1.0
    unit: str = "unit"
    quantity_at_home: float = 0.0

    # Market enrichment
    market_price: float | None = None
    market_price_per_kg: float | None = None
    market_available: bool | None = None
    market_raw_size: str = ""

    # Substitutions (only populated when sold out or overpriced)
    substitutions: list[dict[str, Any]] = field(default_factory=list)

    # Deal scoring
    deal_score: str = ""  # great | good | fair | poor | unknown
    deal_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "display_name": self.display_name,
            "decision": self.decision,
            "reason": self.reason,
            "confidence": self.confidence,
            "requested_quantity": self.requested_quantity,
            "unit": self.unit,
            "quantity_at_home": self.quantity_at_home,
            "market_price": self.market_price,
            "market_price_per_kg": self.market_price_per_kg,
            "market_available": self.market_available,
            "market_raw_size": self.market_raw_size,
            "substitutions": self.substitutions,
            "deal_score": self.deal_score,
            "deal_reason": self.deal_reason,
        }


@dataclass
class UnifiedShoppingResult:
    goal: str
    items: list[ItemResult] = field(default_factory=list)
    graph_projection: dict[str, Any] = field(default_factory=dict)

    @property
    def buy(self) -> list[ItemResult]:
        return [i for i in self.items if i.decision == "buy"]

    @property
    def skip(self) -> list[ItemResult]:
        return [i for i in self.items if i.decision == "skip"]

    @property
    def use_soon(self) -> list[ItemResult]:
        return [i for i in self.items if i.decision == "use_soon"]

    @property
    def optional(self) -> list[ItemResult]:
        return [i for i in self.items if i.decision == "optional"]

    @property
    def compare(self) -> list[ItemResult]:
        return [i for i in self.items if i.decision == "compare"]

    @property
    def sold_out(self) -> list[ItemResult]:
        return [i for i in self.items if i.market_available is False]

    @property
    def estimated_total(self) -> float:
        return round(sum(i.market_price or 0 for i in self.buy), 2)

    @property
    def has_substitutions(self) -> bool:
        return any(i.substitutions for i in self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "items": [i.to_dict() for i in self.items],
            "graph_projection": dict(self.graph_projection),
            "summary": {
                "buy": len(self.buy),
                "skip": len(self.skip),
                "use_soon": len(self.use_soon),
                "optional": len(self.optional),
                "sold_out": len(self.sold_out),
                "estimated_total": self.estimated_total,
            },
        }


def run_unified_shopping_flow(
    goal: str,
    items_text: str,
    db: Any,
    inventory: Any,
    graph: Any | None = None,
) -> UnifiedShoppingResult:
    """Execute the full shopping pipeline in one pass.

    Steps:
      1. Parse free-text items into structured dicts
      2. Classify each against inventory (buy/skip/use_soon/optional)
      3. Enrich with market prices and availability
      4. Find substitutions for sold-out or overpriced items
      5. Score deals against price memory
      6. Return structured UnifiedShoppingResult

    Args:
        goal: User's shopping goal (e.g. "Weekly groceries").
        items_text: Free-text item list (comma/semicolon/newline separated).
        db: Database instance.
        inventory: InventoryRepo or ToolRegistry.

    Returns:
        UnifiedShoppingResult with per-item decisions, market data,
        substitutions, and deal scores.
    """
    from shopstack.market.normalization import normalize_item_name
    from shopstack.services.shopping import (
        classify_shopping_items,
        enrich_items_with_swiggy,
    )

    # Step 1: Parse items from text
    raw_items = _parse_items(items_text)
    if not raw_items:
        return UnifiedShoppingResult(goal=goal)

    # Step 2: Classify against inventory
    plan = classify_shopping_items(raw_items, inventory)

    # Step 3: Enrich with market prices (already done by classify_shopping_items
    # via enrich_items_with_swiggy, but we'll also build ItemResult objects)
    item_results = _build_item_results(plan)

    # Step 4: Find substitutions for sold-out items
    _enrich_substitutions(item_results)

    # Step 5: Score deals against price memory
    _enrich_deal_scores(item_results, db)

    graph_projection: dict[str, Any] = {}
    if graph is not None:
        try:
            from shopstack.services.market_intelligence import project_unified_shopping

            projection = project_unified_shopping(graph, [item.canonical_name for item in item_results])
            graph_projection = projection.to_dict()
        except Exception:
            logger.debug("Failed to project unified shopping against market graph", exc_info=True)
    if not graph_projection:
        graph_projection = {
            "title": "Unified Shopping",
            "matched_names": [item.canonical_name for item in item_results],
            "unmatched_names": [],
            "next_actions": [action for action in (
                "add_to_basket" if any(i.decision == "buy" for i in item_results) else None,
                "review_compare_candidates" if any(i.decision == "compare" for i in item_results) else None,
                "choose_substitute" if any(i.substitutions for i in item_results) else None,
            ) if action],
            "summary": {
                "items": len(item_results),
                "buy": len([i for i in item_results if i.decision == "buy"]),
                "skip": len([i for i in item_results if i.decision == "skip"]),
                "use_soon": len([i for i in item_results if i.decision == "use_soon"]),
                "compare": len([i for i in item_results if i.decision == "compare"]),
                "substitute": len([i for i in item_results if i.substitutions]),
            },
        }

    return UnifiedShoppingResult(goal=goal, items=item_results, graph_projection=graph_projection)


def _parse_items(text: str) -> list[dict[str, Any]]:
    """Parse free-text into list of item dicts."""
    from shopstack.ui.screens._utils import parse_shopping_text
    from shopstack.market.normalization import normalize_item_name

    text = (text or "").strip()
    if not text:
        return []

    parsed = parse_shopping_text(text)
    items = []
    for name in parsed:
        if not name:
            continue
        normalized = normalize_item_name(name) or name.lower().strip()
        items.append({
            "canonical_name": normalized,
            "requested_quantity": 1.0,
            "unit": "unit",
            "priority": "must_buy",
            "reason": "",
        })
    return items


def _build_item_results(plan: Any) -> list[ItemResult]:
    """Convert ShoppingPlan categories into flat ItemResult list."""
    results: list[ItemResult] = []
    for item in plan.must_buy:
        results.append(ItemResult(
            canonical_name=item.get("canonical_name", "").lower(),
            display_name=item.get("canonical_name", "").replace("_", " ").title(),
            decision="buy",
            reason=item.get("reason", ""),
            confidence=item.get("confidence", 0.5),
            requested_quantity=item.get("requested_quantity", 1.0),
            unit=item.get("unit", "unit"),
            market_price=item.get("swiggy_price"),
            market_price_per_kg=item.get("swiggy_price_per_kg"),
            market_available=item.get("swiggy_available"),
            market_raw_size=item.get("swiggy_size", ""),
        ))
    for item in plan.optional:
        results.append(ItemResult(
            canonical_name=item.get("canonical_name", "").lower(),
            display_name=item.get("canonical_name", "").replace("_", " ").title(),
            decision="optional",
            reason=item.get("reason", ""),
            confidence=item.get("confidence", 0.5),
            requested_quantity=item.get("requested_quantity", 1.0),
            unit=item.get("unit", "unit"),
            market_price=item.get("swiggy_price"),
            market_price_per_kg=item.get("swiggy_price_per_kg"),
            market_available=item.get("swiggy_available"),
            market_raw_size=item.get("swiggy_size", ""),
        ))
    for item in plan.use_soon:
        results.append(ItemResult(
            canonical_name=item.get("canonical_name", "").lower(),
            display_name=item.get("canonical_name", "").replace("_", " ").title(),
            decision="use_soon",
            reason=item.get("reason", ""),
            confidence=item.get("confidence", 0.5),
            requested_quantity=item.get("requested_quantity", 1.0),
            unit=item.get("unit", "unit"),
            market_price=item.get("swiggy_price"),
            market_price_per_kg=item.get("swiggy_price_per_kg"),
            market_available=item.get("swiggy_available"),
            market_raw_size=item.get("swiggy_size", ""),
        ))
    for item in plan.skipped:
        results.append(ItemResult(
            canonical_name=item.get("canonical_name", "").lower(),
            display_name=item.get("canonical_name", "").replace("_", " ").title(),
            decision="skip",
            reason=item.get("reason", ""),
            confidence=item.get("confidence", 0.5),
            requested_quantity=item.get("requested_quantity", 1.0),
            unit=item.get("unit", "unit"),
            market_price=item.get("swiggy_price"),
            market_price_per_kg=item.get("swiggy_price_per_kg"),
            market_available=item.get("swiggy_available"),
            market_raw_size=item.get("swiggy_size", ""),
        ))
    return results


def _enrich_substitutions(items: list[ItemResult]) -> None:
    """Find substitutions for sold-out or unavailable items."""
    try:
        from shopstack.market.sources.swiggy import load_snapshot
        snapshot = load_snapshot()
    except Exception:
        logger.debug("No Swiggy snapshot available for substitutions")
        return

    from shopstack.services.substitution import find_substitutions

    for item in items:
        # Only look for substitutions for items that are sold out or have no market data
        needs_sub = item.market_available is False or (
            item.decision == "buy" and item.market_price is None
        )
        if not needs_sub:
            continue

        result = find_substitutions(item.canonical_name, snapshot, include_available=True)
        for suggestion in result.available_suggestions[:3]:
            item.substitutions.append({
                "canonical_name": suggestion.substitute_canonical,
                "display_name": suggestion.substitute_display,
                "type": suggestion.substitution_type,
                "reason": suggestion.reason,
                "price_inr": suggestion.price_inr,
                "price_per_kg": suggestion.price_per_kg,
                "confidence": suggestion.confidence,
            })


def _enrich_deal_scores(items: list[ItemResult], db: Any) -> None:
    """Score deals against historical price memory."""
    try:
        from shopstack.services.price_memory import PriceMemoryService
        pm = PriceMemoryService(db)
    except Exception:
        return

    for item in items:
        if item.market_price is None or item.market_price <= 0:
            continue
        try:
            deal = pm.score_deal(
                item.canonical_name,
                item.market_price,
                per_kg=item.market_price_per_kg,
            )
            item.deal_score = deal.score
            item.deal_reason = deal.reason
        except Exception:
            pass
