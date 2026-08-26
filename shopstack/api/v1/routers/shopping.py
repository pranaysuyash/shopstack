"""``/api/v1/shopping/*`` — read + write endpoints for shopping lists.

The shopping list is the second-most-touched table after inventory
(the mobile app's "plan groceries" flow). v1 exposes:

* ``GET  /api/v1/shopping/active`` — the caller's active list (mobile
  offline cache target).
* ``POST /api/v1/shopping/lists`` — create a new list (optionally with
  seed items).
* ``POST /api/v1/shopping/lists/{list_id}/items`` — append N items to a
  list (array body for receipt-scan / import flows).

**Pattern (per motto_v3 §0.15 three-layer rule):**

* HTTP boundary only.
* Delegates to :class:`shopstack.repos.shopping_list.ShoppingListRepo`
  and the DB's ``create_shopping_list`` / ``add_list_item`` methods —
  the exact same write path the clients use (motto_v3 §6: the
  pre-existing logic is the source of truth).
* Writes are household-scoped via ``ctx.household_id``.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from shopstack.api.v1.deps import HouseholdContext, require_household
from shopstack.api.v1.schemas import (
    AddShoppingItemsRequest,
    ApiError,
    CompleteShoppingListRequest,
    CompleteShoppingListResponse,
    CompletionItemWire,
    CreateShoppingListRequest,
    MarkPurchasedItemWire,
    MarkPurchasedRequest,
    MarkPurchasedResponse,
    ShoppingListItemWire,
    ShoppingListWire,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shopping", tags=["shopping"])


# ── helpers ──────────────────────────────────────────────────────


def _list_to_wire(sl_dict: dict[str, Any]) -> ShoppingListWire:
    """Translate a shopping-list dict (ShoppingList.model_dump) to wire form."""
    items = [
        ShoppingListItemWire(
            item_id=it.get("list_item_id", "") or "",
            canonical_name=it.get("canonical_name", "") or "",
            requested_quantity=it.get("requested_quantity"),
            unit=it.get("unit"),
            priority=it.get("priority", "optional") or "optional",
            reason=it.get("reason", "") or "",
            status=it.get("status", "pending") or "pending",
            linked_inventory_lots=it.get("linked_inventory_lots") or [],
        )
        for it in (sl_dict.get("items") or [])
    ]
    return ShoppingListWire(
        list_id=sl_dict.get("list_id", "") or "",
        name=sl_dict.get("name", "Shopping List") or "Shopping List",
        created_at=_iso(sl_dict.get("created_at")),
        updated_at=_iso(sl_dict.get("updated_at")),
        goal=sl_dict.get("goal", "") or "",
        is_active=bool(sl_dict.get("is_active", True)),
        items=items,
    )


def _iso(value: Any) -> str:
    """Best-effort ISO 8601 string from a datetime or string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    # datetime → isoformat
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    return str(value)


# ── endpoints ─────────────────────────────────────────────────────


@router.get(
    "/active",
    response_model=ShoppingListWire,
    summary="Get the caller's active shopping list",
)
def get_active_list(
    ctx: HouseholdContext = Depends(require_household),
) -> ShoppingListWire:
    """Return the active shopping list for the caller's household.

    Returns an empty (placeholder) list shape with ``list_id=""`` and
    ``is_active=True`` when no active list exists, so the mobile client
    can render the screen without a separate "no list" code path. The
    caller distinguishes "no list" by ``list_id == ""``.
    """
    from shopstack.app_context import db

    sl = db.get_active_shopping_list(user_id=ctx.household_id)
    if sl is None:
        return ShoppingListWire(
            list_id="",
            name="Shopping List",
            created_at="",
            updated_at="",
            goal="",
            is_active=True,
            items=[],
        )
    return _list_to_wire(sl.model_dump())


@router.post(
    "/lists",
    response_model=ShoppingListWire,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new shopping list (optionally with seed items)",
)
def create_list(
    body: CreateShoppingListRequest,
    ctx: HouseholdContext = Depends(require_household),
) -> ShoppingListWire:
    """Create a new active list scoped to the caller's household.

    If an active list already exists for the household, a new one is
    still created and marked active; the prior list is left in place
    (``get_active_shopping_list`` returns the most-recent). Seed items
    are added in one pass.
    """
    from shopstack.app_context import db

    sl = db.create_shopping_list(goal=body.goal, user_id=ctx.household_id)
    _add_items(db, sl.list_id, ctx.household_id, body.items)
    # Re-read so the response carries the seeded items + server timestamps.
    return _reload(db, sl.list_id)


@router.post(
    "/lists/{list_id}/items",
    response_model=ShoppingListWire,
    summary="Append items to a shopping list",
)
def add_items(
    list_id: str,
    body: AddShoppingItemsRequest,
    ctx: HouseholdContext = Depends(require_household),
) -> ShoppingListWire:
    """Append one or more items to an existing list.

    Household-scoped: if ``list_id`` belongs to a different household
    than the caller's token, the write is refused with 404 (we never
    disclose that the list exists in another household).
    """
    from shopstack.app_context import db

    _assert_list_owned(db, list_id, ctx.household_id)
    _add_items(db, list_id, ctx.household_id, body.items)
    return _reload(db, list_id)


# ── shared write helpers ─────────────────────────────────────────


def _assert_list_owned(db: Any, list_id: str, household_id: str) -> None:
    """Raise 404 if the list does not exist in the caller's household."""
    row = db.conn.execute(
        "SELECT user_id FROM shopping_lists WHERE list_id = ?",
        (list_id,),
    ).fetchone()
    if row is None or (row["user_id"] or "") != household_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ApiError(
                code="list_not_found",
                message=f"No shopping list with id={list_id!r} in this household.",
            ).model_dump(),
        )


def _add_items(db: Any, list_id: str, household_id: str, items: list[Any]) -> None:
    """Append validated items via the canonical ``add_list_item`` write path."""
    from shopstack.schemas.models import ShoppingListItem

    for item_in in items:
        sl_item = ShoppingListItem(
            canonical_name=item_in.canonical_name,
            requested_quantity=item_in.requested_quantity,
            unit=item_in.unit,
            priority=item_in.priority,
            reason=item_in.reason,
        )
        db.add_list_item(list_id, sl_item, user_id=household_id)


def _reload(db: Any, list_id: str) -> ShoppingListWire:
    """Re-read a shopping list by id and return its wire form."""
    row = db.conn.execute(
        "SELECT * FROM shopping_lists WHERE list_id = ?", (list_id,)
    ).fetchone()
    if row is None:
        # Should not happen immediately after a create/add; defend anyway.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=ApiError(
                code="list_vanished",
                message="The shopping list could not be re-read after the write.",
            ).model_dump(),
        )
    from shopstack.persistence.database import _row_to_list

    sl = _row_to_list(row, db.conn)
    return _list_to_wire(sl.model_dump())


# ── Shopping-completion endpoints ──────────────────────────────────


@router.post(
    "/lists/{list_id}/complete",
    response_model=CompleteShoppingListResponse,
    summary="Complete a shopping list: convert items to inventory",
)
def complete_list(
    list_id: str,
    body: CompleteShoppingListRequest = None,
    ctx: HouseholdContext = Depends(require_household),
) -> CompleteShoppingListResponse:
    """Close out a shopping list into inventory.

    Items with priority ``must_buy`` are added at full quantity;
    ``optional`` items are added at 50% quantity; ``avoid_buying``
    items are skipped. The list is marked complete.

    This is the endpoint that closes the only broken loop in the
    shopping API — mobile can now create a list AND convert it to
    inventory.
    """
    from shopstack.app_context import db, tools
    from shopstack.services.shopping import complete_shopping_list_service

    _assert_list_owned(db, list_id, ctx.household_id)

    inventory = getattr(tools, "inventory", None)
    if inventory is None:
        from shopstack.repos.inventory import InventoryRepo
        inventory = InventoryRepo(db)

    result = complete_shopping_list_service(
        list_id=list_id,
        inventory=inventory,
        database=db,
        user_id=ctx.household_id,
        purchased_item_ids=(body.purchased_item_ids if body else None),
    )

    return CompleteShoppingListResponse(
        success=result.success,
        list_id=result.list_id,
        items_added=[
            CompletionItemWire(
                canonical_name=i.canonical_name,
                lot_id=i.lot_id,
                quantity=i.quantity,
                unit=i.unit,
            )
            for i in result.items_added
        ],
        items_skipped=result.items_skipped,
        goal=result.goal,
        message=result.message,
    )


@router.post(
    "/lists/{list_id}/mark-purchased",
    response_model=MarkPurchasedResponse,
    summary="Mark selected items as purchased",
)
def mark_purchased(
    list_id: str,
    body: MarkPurchasedRequest,
    ctx: HouseholdContext = Depends(require_household),
) -> MarkPurchasedResponse:
    """Mark specific shopping list items as purchased and add to inventory.

    ``item_ids`` must be the ``list_item_id`` values of items on the
    list. Items are added to inventory with their full requested
    quantity. The items' status is updated to ``bought``.
    """
    from shopstack.app_context import db, tools
    from shopstack.services.shopping import mark_items_purchased_service

    _assert_list_owned(db, list_id, ctx.household_id)

    inventory = getattr(tools, "inventory", None)
    if inventory is None:
        from shopstack.repos.inventory import InventoryRepo
        inventory = InventoryRepo(db)

    result = mark_items_purchased_service(
        item_ids_json=body.item_ids,
        inventory=inventory,
        database=db,
        user_id=ctx.household_id,
    )

    return MarkPurchasedResponse(
        success=result.success,
        items_added=[
            MarkPurchasedItemWire(
                canonical_name=i.canonical_name,
                lot_id=i.lot_id,
                quantity=i.quantity,
                unit=i.unit,
            )
            for i in result.items_added
        ],
        message=result.message,
    )


__all__ = ["router"]
