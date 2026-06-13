"""Service: add a restock prediction to the active shopping list.

The Today dashboard surfaces predictive restock items ("you'll run out of
milk Tuesday"). This service provides the **action** behind the
prediction: a one-click "add to my list" that turns a forecast into a
purchased item.

Distinction from `add_inventory_item`: this adds to the *active shopping
list*, not to the inventory directly. The user reviews, marks as
bought, then reconciles. That is the intended loop.

This is the Phase 2 #2 wire-up — the prediction engine was already
complete; this completes the action side of the loop.
"""

from __future__ import annotations

import logging
from typing import Any

from shopstack.app_context import current_user_id
from shopstack.persistence.database import Database
from shopstack.repos.shopping_list import ShoppingListRepo

logger = logging.getLogger(__name__)


# Default goal text for restock-driven lists. Real users will edit this.
_RESTOCK_GOAL = "Auto-created from restock prediction"


def add_prediction_to_list(
    db: Database,
    prediction: dict[str, Any],
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Append a single restock prediction to the active shopping list.

    If no active list exists, creates one with a sensible default goal.

    Args:
        db: Database instance.
        prediction: One element of ``predict_restock_needs()`` output.
            Must have ``canonical_name``; ``typical_qty`` / ``typical_unit``
            are surfaced from the prediction.
        user_id: Active household. Defaults to ``current_user_id()``.

    Returns:
        Dict with ``added`` (bool), ``list_id`` (str), ``item`` (dict),
        ``reason`` (str). Always succeeds if DB is reachable; the only
        failure mode is invalid input.
    """
    uid = user_id if user_id is not None else current_user_id()
    cname = (prediction.get("canonical_name") or "").strip()
    if not cname:
        return {"added": False, "reason": "missing canonical_name", "list_id": "", "item": {}}

    qty = float(prediction.get("typical_qty") or 1.0)
    unit = (prediction.get("typical_unit") or "unit").strip() or "unit"
    reason = prediction.get("reason") or "Restock prediction"
    urgency = prediction.get("urgency", "due_soon")

    # Map urgency to a priority. The shopping list re-ranks on next refresh
    # anyway, but this gives the user a sensible default.
    priority_map = {
        "overdue": "must_buy",
        "due_today": "must_buy",
        "due_soon": "optional",
    }
    priority = priority_map.get(urgency, "optional")

    repo = ShoppingListRepo(db)
    item = {
        "canonical_name": cname,
        "requested_quantity": qty,
        "unit": unit,
        "priority": priority,
        "reason": f"{reason} (from restock prediction)",
    }
    result = repo.create_or_update(items=[item], goal=_RESTOCK_GOAL, user_id=uid)
    sl = result.get("list") or {}
    return {
        "added": True,
        "list_id": sl.get("list_id", ""),
        "item": item,
        "reason": f"Added {qty:.0f} {unit} of {cname.replace('_', ' ').title()} to your shopping list",
    }


__all__ = ["add_prediction_to_list"]
