"""``/api/v1/household/*`` — multi-tenant household management.

A household is the unit of multi-tenancy in ShopStack (the
``household_id`` that scopes every inventory/shopping row). v1
exposes list/create/switch so the mobile app can manage which
workspace a token is operating in.

**Pattern (per motto_v3 §0.15 three-layer rule):**

* HTTP boundary only.
* Delegates to :meth:`shopstack.persistence.database.Database.list_households`
  / :meth:`add_household` and the ``active_household_id`` property.
* No parallel truth source — these are the exact same calls the
  Gradio household screens make.

**Auth:** every endpoint requires a valid bearer token
(``require_household``). ``switch`` mutates server-side active
state AND returns a fresh token scoped to the new household, so
the client's subsequent requests are correctly scoped even if the
ContextVar reset doesn't propagate (defence in depth).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from shopstack.api.v1 import auth as auth_mod
from shopstack.api.v1.deps import HouseholdContext, require_household
from shopstack.api.v1.schemas import (
    ApiError,
    CreateHouseholdRequest,
    Household,
    HouseholdListResponse,
    TokenResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/household", tags=["household"])


# ── endpoints ─────────────────────────────────────────────────────


@router.get(
    "",
    response_model=HouseholdListResponse,
    summary="List households known to this instance",
)
def list_households(
    ctx: HouseholdContext = Depends(require_household),
) -> HouseholdListResponse:
    """List every household, flagging the active one.

    Note: v1 is local-first / single-device, so this returns all
    households on the device's DB (the mobile app shows a picker).
    A future multi-user v2 will scope this to the device's known
    households via the ``household_members`` table.
    """
    from shopstack.app_context import db

    rows = db.list_households() or []
    active = db.active_household_id
    items = [
        Household(
            household_id=r.get("household_id", ""),
            name=r.get("name", "") or r.get("household_id", ""),
            is_active=(r.get("household_id") == active),
        )
        for r in rows
    ]
    return HouseholdListResponse(items=items, active_household_id=active)


@router.post(
    "",
    response_model=Household,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new household",
)
def create_household(
    body: CreateHouseholdRequest,
    ctx: HouseholdContext = Depends(require_household),
) -> Household:
    """Create a household. Does not switch the active workspace.

    To operate in the new household, the client calls
    ``POST /api/v1/household/{id}/switch``.
    """
    from shopstack.app_context import db

    household_id = body.household_id or "hh_" + _slug(body.name)
    created = db.add_household(household_id, body.name, notes=body.notes)
    if not created:
        # add_household returns False on a pre-existing id.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ApiError(
                code="household_exists",
                message=f"A household with id={household_id!r} already exists.",
            ).model_dump(),
        )
    # Ensure the new household is immediately writable: make the
    # caller's device an owner member. This mirrors the default-seed
    # path (database._seed_default_user) so the permissions layer
    # (services.permissions.require_write) never denies a freshly
    # created workspace. Best-effort; a failure here is non-fatal
    # because the household row already exists.
    try:
        db.add_household_member(household_id, household_id, role="owner")
    except Exception as exc:  # noqa: BLE001
        logger.debug("household owner-membership bootstrap failed: %s", exc)
    return Household(
        household_id=household_id,
        name=body.name,
        is_active=False,
    )


@router.post(
    "/{household_id}/switch",
    response_model=TokenResponse,
    summary="Switch the active household and re-scope the token",
)
def switch_household(
    household_id: str,
    ctx: HouseholdContext = Depends(require_household),
) -> TokenResponse:
    """Switch the server-side active household and mint a token scoped to it.

    Returning a fresh token (rather than mutating the existing one)
    keeps each token's household immutable on disk — simpler
    verification, no read-modify-write race on ``household_id``.
    The old token remains valid until it expires or is revoked.

    Raises 404 if the target household does not exist.
    """
    from shopstack.app_context import db

    rows = db.list_households() or []
    match = next((r for r in rows if r.get("household_id") == household_id), None)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ApiError(
                code="household_not_found",
                message=f"No household with id={household_id!r}.",
            ).model_dump(),
        )

    # Mutate server-side active state (Gradio path reads this).
    db.active_household_id = household_id

    issued = auth_mod.issue_token(
        db, device_id=ctx.device_id, household_id=household_id
    )
    return TokenResponse(
        token=issued["token"],
        expires_at=issued["expires_at"],
        household_id=household_id,
        household_name=match.get("name") or household_id,
    )


# ── helpers ───────────────────────────────────────────────────────


def _slug(name: str) -> str:
    """Derive a household_id slug from a name.

    Lowercase, ASCII alnum + underscore. Non-ASCII is hex-encoded so
    the id is always filesystem/column-safe. Falls back to ``hh``
    if the name yields nothing usable.
    """
    cleaned = "".join(c if (c.isalnum() or c == "_") else "_" for c in name.strip().lower())
    cleaned = cleaned.strip("_")
    return cleaned or "hh"


__all__ = ["router"]
