"""``/api/v1/inventory/*`` — read + write endpoints for the
inventory_lots table.

This is the **first read-side endpoint** shipped under v1. The
pattern here will be replicated for shopping, dashboard, and
intelligence in subsequent passes (per the candidate list in
``Docs/exploration/API_V1_AND_MOBILE_REPO_2026-06-16.md``).

**Why ship inventory first (1st principles):**

* It is the most-touched table (every feature reads or writes
  inventory). Wiring the pattern here means every other
  endpoint can lift the same shape.
* The DB layer is already household-scoped via
  ``user_id`` columns. The endpoint is a thin
  pass-through; no business logic.
* The mobile app's most-frequent offline-cache is the
  inventory snapshot.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import Field

from shopstack.api.v1.deps import HouseholdContext, require_household
from shopstack.api.v1.schemas import (
    AddInventoryLotRequest,
    ApiError,
    ConsumeInventoryRequest,
    InventoryLot,
    ListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inventory", tags=["inventory"])


# ── helpers ──────────────────────────────────────────────────────


def _lot_to_wire(lot: dict[str, Any], location_name: str = "") -> InventoryLot:
    """Translate a DB row to the wire schema.

    Best-effort: missing fields fall back to the schema defaults
    rather than raising. The mobile app should never see a 500
    because the DB had a NULL where the schema expected a
    string.
    """
    return InventoryLot(
        lot_id=lot.get("lot_id", "") or "",
        canonical_name=lot.get("canonical_name", "") or "",
        display_name=lot.get("display_name", "") or "",
        category=lot.get("category", "") or "",
        quantity=float(lot.get("quantity") if lot.get("quantity") is not None else 1.0),
        unit=lot.get("unit", "unit") or "unit",
        storage_location_id=lot.get("storage_location_id", "") or "",
        storage_location_name=location_name,
        purchase_date=lot.get("purchase_date"),
        estimated_use_by_date=lot.get("estimated_use_by_date"),
        label_expiry_date=lot.get("label_expiry_date"),
        opened_date=lot.get("opened_date"),
        price_paid=lot.get("price_paid"),
        currency=lot.get("currency", "INR") or "INR",
        confidence=float(lot.get("confidence") if lot.get("confidence") is not None else 1.0),
        status=lot.get("status", "active") or "active",
    )


def _resolve_location_name(db: Any, location_id: str) -> str:
    """Best-effort location display-name lookup. Empty on miss."""
    if not location_id:
        return ""
    try:
        cur = db.conn.execute(
            "SELECT name FROM household_locations WHERE location_id = ?",
            (location_id,),
        )
        row = cur.fetchone()
        if row is None:
            return ""
        return row["name"] or ""
    except Exception:
        return ""


# ── endpoints ─────────────────────────────────────────────────────


@router.get(
    "/lots",
    response_model=ListResponse[InventoryLot],
    summary="List inventory lots for the caller's household",
)
def list_lots(
    ctx: HouseholdContext = Depends(require_household),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(
        default=None,
        description="Optional status filter: 'active', 'low', 'used', 'expired', 'discarded'.",
    ),
) -> ListResponse[InventoryLot]:
    """Return inventory lots scoped to the caller's household.

    Pagination: ``limit`` (1–1000, default 100) + ``offset``
    (default 0). The response carries ``total`` (total matching
    rows) and ``has_more`` (``offset + len(items) < total``) so
    the mobile app can render "load more" without an extra
    round-trip.
    """
    from shopstack.app_context import db

    # Build the query. user_id is the household scope.
    base_sql = (
        "SELECT lot_id, canonical_name, display_name, category, "
        "quantity, unit, storage_location_id, purchase_date, "
        "estimated_use_by_date, label_expiry_date, opened_date, "
        "price_paid, currency, confidence, status "
        "FROM inventory_lots WHERE user_id = ?"
    )
    params: list[Any] = [ctx.household_id]
    if status_filter:
        base_sql += " AND status = ?"
        params.append(status_filter)

    # Total count (cheap with the user_id index).
    count_sql = f"SELECT COUNT(*) FROM ({base_sql})"
    total = db.conn.execute(count_sql, params).fetchone()[0]

    # Page.
    page_sql = base_sql + " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = db.conn.execute(page_sql, params).fetchall()

    # Denormalise storage_location_name in one pass.
    location_ids = {r["storage_location_id"] for r in rows if r["storage_location_id"]}
    location_names = {lid: _resolve_location_name(db, lid) for lid in location_ids}

    items = [_lot_to_wire(dict(r), location_names.get(r["storage_location_id"], "")) for r in rows]

    return ListResponse[InventoryLot](
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.get(
    "/lots/{lot_id}",
    response_model=InventoryLot,
    summary="Get one inventory lot by id",
)
def get_lot(
    lot_id: str,
    ctx: HouseholdContext = Depends(require_household),
) -> InventoryLot:
    """Fetch a single inventory lot, scoped to the caller's household."""
    from shopstack.app_context import db

    cur = db.conn.execute(
        "SELECT lot_id, canonical_name, display_name, category, "
        "quantity, unit, storage_location_id, purchase_date, "
        "estimated_use_by_date, label_expiry_date, opened_date, "
        "price_paid, currency, confidence, status "
        "FROM inventory_lots WHERE lot_id = ? AND user_id = ?",
        (lot_id, ctx.household_id),
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ApiError(
                code="lot_not_found",
                message=f"No inventory lot with id={lot_id!r} in this household.",
            ).model_dump(),
        )
    location_name = _resolve_location_name(db, row["storage_location_id"])
    return _lot_to_wire(dict(row), location_name)


@router.post(
    "/lots/{lot_id}/consume",
    response_model=InventoryLot,
    summary="Consume a quantity from an inventory lot",
)
def consume_lot(
    lot_id: str,
    body: ConsumeInventoryRequest,
    ctx: HouseholdContext = Depends(require_household),
) -> InventoryLot:
    """Consume ``body.quantity`` from a lot.

    Wraps the existing ``consume_inventory`` service so the
    mobile app and the Gradio UI share the same write path
    (motto_v3 §6: pre-existing logic is the source of truth).

    The endpoint refuses to consume more than is available. It
    returns the post-consume lot in the response so the mobile
    app can update its cache without a second round-trip.
    """
    from shopstack.app_context import db

    # 1. Look up the lot (household-scoped).
    cur = db.conn.execute(
        "SELECT * FROM inventory_lots WHERE lot_id = ? AND user_id = ?",
        (lot_id, ctx.household_id),
    )
    row = cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ApiError(
                code="lot_not_found",
                message=f"No inventory lot with id={lot_id!r} in this household.",
            ).model_dump(),
        )

    current_qty = float(row["quantity"] or 0.0)
    if body.quantity > current_qty:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ApiError(
                code="insufficient_quantity",
                message=f"Cannot consume {body.quantity}; only {current_qty} on hand.",
                details={"available": current_qty, "requested": body.quantity},
            ).model_dump(),
        )

    # 2. Delegate to the canonical tool-registry method for the
    #    actual write + trace + decision_engine side effects. The
    #    service accepts the user_id explicitly (the inventory
    #    pre-existing convention: user_id == household_id).
    #
    #    We use the per-request imported ``db`` handle (the same
    #    one the Gradio screens use), and call the existing
    #    ``ToolRegistry.consume_inventory_item`` method. This is
    #    the same write path the Gradio UI uses, so the mobile
    #    app and the Gradio app see identical state changes.
    from shopstack.app_context import tools
    from shopstack.repos.inventory import InventoryRepo

    inv_repo = getattr(tools, "inventory", None)
    if inv_repo is None:
        # ToolRegistry exposes ``consume_inventory_item`` as a
        # delegator; under the hood it calls the InventoryRepo.
        # Build a fresh repo on the same db handle as a fallback
        # so the endpoint never silently no-ops.
        inv_repo = InventoryRepo(db)  # type: ignore[abstract]

    inv_repo.consume_item(
        lot_id=lot_id,
        quantity=body.quantity,
        user_id=ctx.household_id,
    )

    # 3. Re-read the post-consume row.
    cur = db.conn.execute(
        "SELECT lot_id, canonical_name, display_name, category, "
        "quantity, unit, storage_location_id, purchase_date, "
        "estimated_use_by_date, label_expiry_date, opened_date, "
        "price_paid, currency, confidence, status "
        "FROM inventory_lots WHERE lot_id = ? AND user_id = ?",
        (lot_id, ctx.household_id),
    )
    new_row = cur.fetchone()
    location_name = _resolve_location_name(db, new_row["storage_location_id"])
    return _lot_to_wire(dict(new_row), location_name)


@router.post(
    "/lots",
    response_model=InventoryLot,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new inventory lot (record a purchase)",
)
def add_lot(
    body: AddInventoryLotRequest,
    ctx: HouseholdContext = Depends(require_household),
) -> InventoryLot:
    """Record a new purchase as an inventory lot.

    This is the **most-used write endpoint** — the mobile app's primary
    way to add items to the household inventory. The endpoint accepts
    optional metadata (dates, price, location, category) alongside the
    required item name.

    The lot is created with an auto-generated ``lot_id``. The response
    returns the full ``InventoryLot`` wire shape so the mobile app can
    update its local cache without a second round-trip.

    Validation:
    - ``canonical_name`` is required (min 1 char, max 200).
    - ``quantity`` must be > 0 (default 1.0).
    - ``price_paid`` must be >= 0 if provided.
    - ``confidence`` must be in [0, 1].
    """
    from datetime import date

    from shopstack.schemas.models import InventoryLot as DomainLot

    from shopstack.app_context import db

    lot = DomainLot(
        canonical_name=body.canonical_name,
        display_name=body.display_name or body.canonical_name,
        quantity=body.quantity,
        unit=body.unit,
        storage_location_id=body.storage_location_id,
        purchase_date=(
            date.fromisoformat(body.purchase_date) if body.purchase_date else date.today()
        ),
        estimated_use_by_date=(
            date.fromisoformat(body.estimated_use_by_date) if body.estimated_use_by_date else None
        ),
        label_expiry_date=(
            date.fromisoformat(body.label_expiry_date) if body.label_expiry_date else None
        ),
        opened_date=(
            date.fromisoformat(body.opened_date) if body.opened_date else None
        ),
        price_paid=body.price_paid,
        currency=body.currency,
        confidence=body.confidence,
        category=body.category,
    )
    db.add_inventory_lot(lot, user_id=ctx.household_id)

    # Record an inventory event so the audit trail is complete.
    from shopstack.schemas.models import InventoryEvent

    db.record_inventory_event(
        InventoryEvent(
            lot_id=lot.lot_id,
            canonical_name=lot.canonical_name,
            action="added",
            quantity_before=0,
            quantity_after=body.quantity,
            quantity_delta=body.quantity,
            unit=body.unit,
            location_to=body.storage_location_id,
            source="api",
        ),
        user_id=ctx.household_id,
    )

    # Re-read the row so we return server-set timestamps.
    cur = db.conn.execute(
        "SELECT lot_id, canonical_name, display_name, category, "
        "quantity, unit, storage_location_id, purchase_date, "
        "estimated_use_by_date, label_expiry_date, opened_date, "
        "price_paid, currency, confidence, status "
        "FROM inventory_lots WHERE lot_id = ? AND user_id = ?",
        (lot.lot_id, ctx.household_id),
    )
    row = cur.fetchone()
    location_name = _resolve_location_name(db, row["storage_location_id"])
    return _lot_to_wire(dict(row), location_name)


__all__ = ["router"]
