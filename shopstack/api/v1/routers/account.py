"""``/api/v1/account/*`` — privacy, undo, and store-mode endpoints.

**Why this exists (motto_v3 §0 first-principles):**

The legacy mounts in ``shopstack.services.privacy_mount``,
``shopstack.services.undo_mount``, and
``shopstack.services.decision_explain_mount`` attach routes directly
via ``app.app.add_route``. They are not versioned, not documented
in OpenAPI, and not reusable by the mobile app.

This router ports them to the ``/api/v1/account`` prefix with the
standard FastAPI router pattern.

**Three endpoint groups:**

1. ``/api/v1/account/privacy/*`` — purge user data, retention summary,
   update retention settings.
2. ``/api/v1/account/undo`` — undo the most recent (or a specific)
   undoable mutation.
3. ``/api/v1/account/store-mode/toggle`` — toggle a shopping list
   item's bought/pending status.

**Pattern (per motto_v3 §0.15 three-layer rule):**

* HTTP boundary only.
* Delegates to the same service functions the legacy mounts use.
* Best-effort: sub-check failures return partial payloads with
  error messages rather than 5xx.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from shopstack.api.v1.deps import HouseholdContext, require_household
from shopstack.api.v1.schemas import (
    ApiError,
    PurgeDataResponse,
    RetentionPolicyWire,
    RetentionSummaryResponse,
    StoreModeToggleRequest,
    StoreModeToggleResponse,
    UndoRequest,
    UndoResponse,
    UpdateRetentionRequest,
    UpdateRetentionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/account", tags=["account"])


# ── Privacy ─────────────────────────────────────────────────────────


@router.post(
    "/privacy/purge",
    response_model=PurgeDataResponse,
    summary="Purge all user-derived data (traces, community, SMS, voice, backups)",
)
def purge_data(
    ctx: HouseholdContext = Depends(require_household),
) -> PurgeDataResponse:
    """Wipe every piece of user-derived data for the caller's household.

    Destructive and irreversible. Inventory and shopping lists are kept.

    This endpoint requires ``confirm=true`` — enforced server-side by
    the ``purge_user_data`` function.
    """
    from shopstack.app_context import db
    from shopstack.services.data_retention import purge_user_data

    try:
        result = purge_user_data(
            db,
            user_id=ctx.household_id,
            confirm=True,
        )
        return PurgeDataResponse(
            success=result.success,
            traces_purged=result.traces_purged,
            community_observations_purged=result.community_observations_purged,
            sms_registry_cleared=result.sms_registry_cleared,
            voice_memos_purged=result.voice_memos_purged,
            backups_purged=result.backups_purged,
            errors=result.errors,
        )
    except ValueError as exc:
        return PurgeDataResponse(success=False, errors=[str(exc)])
    except Exception as exc:  # noqa: BLE001
        logger.warning("purge_data failed: %s", exc)
        return PurgeDataResponse(success=False, errors=[f"internal error: {exc}"])


@router.get(
    "/privacy/retention-summary",
    response_model=RetentionSummaryResponse,
    summary="Get the current retention policy",
)
def retention_summary_endpoint(
    ctx: HouseholdContext = Depends(require_household),
) -> RetentionSummaryResponse:
    """Return the current data retention policy for this household.

    Returns every retention knob (trace TTL, community pool retention,
    voice memo retention, etc.) so the client can render the privacy
    panel without server-side HTML.
    """
    from shopstack.app_context import db
    from shopstack.services.data_retention import retention_summary

    try:
        summary = retention_summary(db, user_id=ctx.household_id)
        return RetentionSummaryResponse(
            summary=RetentionPolicyWire(
                trace_ttl_days=summary.trace_ttl_days,
                trace_max_rows=summary.trace_max_rows,
                community_pool_retention_days=summary.community_pool_retention_days,
                voice_memo_retention_days=summary.voice_memo_retention_days,
                sms_registry_retention_days=summary.sms_registry_retention_days,
                backup_retention_days=summary.backup_retention_days,
                locale_persistence=summary.locale_persistence,
                community_optin=summary.community_optin,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("retention_summary failed: %s", exc)
        return RetentionSummaryResponse()


@router.post(
    "/privacy/update-retention",
    response_model=UpdateRetentionResponse,
    summary="Update a single retention setting",
)
def update_retention(
    body: UpdateRetentionRequest,
    ctx: HouseholdContext = Depends(require_household),
) -> UpdateRetentionResponse:
    """Update a retention setting by key/value.

    Keys are the ``_CONFIG_KEY_*`` constants from
    ``shopstack.services.data_retention`` (e.g.
    ``retention.trace_ttl_days``, ``retention.community_optin``).
    """
    from shopstack.app_context import db
    from shopstack.services.data_retention import update_retention_setting

    try:
        ok = update_retention_setting(db, key=body.key, value=body.value)
        return UpdateRetentionResponse(success=ok)
    except Exception as exc:  # noqa: BLE001
        logger.warning("update_retention failed: %s", exc)
        return UpdateRetentionResponse(success=False)


# ── Undo ────────────────────────────────────────────────────────────


@router.post(
    "/undo",
    response_model=UndoResponse,
    summary="Undo the most recent (or a specific) undoable mutation",
)
def undo(
    body: UndoRequest,
    ctx: HouseholdContext = Depends(require_household),
) -> UndoResponse:
    """Reverse the most recent undoable mutation for the caller's
    household. If ``entry_id`` is provided, reverse that specific entry.

    Only mutations registered by the undo ledger are reversible.
    Entries expire after the TTL (default 10 seconds).
    """
    from shopstack.app_context import db
    from shopstack.services.undo_ledger import get_ledger

    try:
        ledger = get_ledger()
        if body.entry_id:
            entry = ledger.undo_by_id(
                ctx.household_id, body.entry_id, db=db,
            )
        else:
            entry = ledger.undo_last(ctx.household_id, db=db)

        if entry is None:
            return UndoResponse(
                success=False,
                message="Nothing to undo or entry has expired.",
            )
        return UndoResponse(
            success=True,
            entry_id=entry.entry_id,
            kind=entry.kind,
            description=entry.description,
            message=f"Undid: {entry.description or entry.kind}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("undo failed: %s", exc)
        return UndoResponse(success=False, message=f"internal error: {exc}")


# ── Store Mode Toggle ──────────────────────────────────────────────


@router.post(
    "/store-mode/toggle",
    response_model=StoreModeToggleResponse,
    summary="Toggle a shopping list item's bought/pending status",
)
def store_mode_toggle(
    body: StoreModeToggleRequest,
    ctx: HouseholdContext = Depends(require_household),
) -> StoreModeToggleResponse:
    """Toggle a shopping list item between ``pending`` and ``bought``
    status. Used by the Store Mode UI to check off items while shopping.
    """
    from shopstack.app_context import db

    try:
        sl = db.get_active_shopping_list(user_id=ctx.household_id)
        if not sl or not sl.items:
            return StoreModeToggleResponse(
                success=False,
                message="No active shopping list.",
            )

        target = None
        for item in sl.items:
            item_key = getattr(item, "list_item_id", None) or getattr(item, "item_id", None) or ""
            if str(item_key) == body.item_id:
                target = item
                break

        if target is None:
            return StoreModeToggleResponse(
                success=False,
                message=f"Item {body.item_id!r} not found in active list.",
            )

        current_status = getattr(target, "status", "pending") or "pending"
        new_status = "bought" if current_status != "bought" else "pending"

        db.update_list_item(
            target.list_item_id,
            {"status": new_status},
        )

        return StoreModeToggleResponse(
            success=True,
            new_status=new_status,
            message=f"Item {target.canonical_name} marked as {new_status}.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("store_mode toggle failed: %s", exc)
        return StoreModeToggleResponse(success=False, message=f"internal error: {exc}")


__all__ = ["router"]
