"""``/api/v1/corrections`` — feedback / correction endpoints.

**Why this exists (motto_v3 §0 first-principles):**

The legacy ``corrections_mount`` registered ``/api/corrections``
via ``app.app.add_route`` — not versioned, not documented in
OpenAPI, and not reusable by the mobile app. This router ports
the same endpoints to the standard ``/api/v1/corrections`` path.

**Two endpoints:**

1. ``GET  /api/v1/corrections?limit=20&accepted_only=false``
   — List recent correction events with summary.
2. ``POST /api/v1/corrections``
   — Record a new correction. Body: ``{canonical_name, was_action,
     should_be_action, reason?}``. Returns 201 on success, 400
     on validation error.

**Pattern (per motto_v3 §0.15 three-layer rule):**

* HTTP boundary only.
* Delegates to ``shopstack.services.feedback`` for all business
  logic.
* Validation errors return 400; server errors return 500 (unlike
  the legacy mount which returned 200 with error fields).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from shopstack.api.v1.deps import HouseholdContext, require_household
from shopstack.api.v1.schemas import (
    CorrectionCreateRequest,
    CorrectionCreateResponse,
    CorrectionItemWire,
    CorrectionListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/corrections", tags=["corrections"])


@router.get(
    "",
    response_model=CorrectionListResponse,
    summary="List recent correction events",
)
def list_corrections(
    limit: int = Query(default=20, ge=1, le=100, description="Max items"),
    accepted_only: bool = Query(default=False, description="Only show accepted corrections"),
    ctx: HouseholdContext = Depends(require_household),
) -> CorrectionListResponse:
    """Return the most recent correction events for this household.

    The Memory → Recent corrections panel uses this to surface
    pending corrections so the user can accept or reject them.
    """
    from shopstack.app_context import db
    from shopstack.services.feedback import (
        list_recent_corrections,
        summarize_corrections,
    )

    try:
        corrections = list_recent_corrections(
            db, user_id=ctx.household_id, limit=limit, accepted_only=accepted_only,
        )
        return CorrectionListResponse(
            summary=summarize_corrections(corrections),
            count=len(corrections),
            items=[
                CorrectionItemWire(
                    event_id=c.event_id,
                    canonical_name=c.canonical_name,
                    was_action=c.old_value,
                    should_be_action=c.new_value,
                    source=c.source,
                    timestamp=c.timestamp.isoformat() if hasattr(c.timestamp, "isoformat") else str(c.timestamp),
                    accepted=bool(c.accepted),
                )
                for c in corrections
            ],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not list corrections: %s", exc)
        return CorrectionListResponse(
            summary="Error loading corrections.",
            items=[],
        )


@router.post(
    "",
    response_model=CorrectionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a new correction",
    responses={
        400: {"description": "Validation error"},
        422: {"description": "Validation error"},
    },
)
def create_correction(
    body: CorrectionCreateRequest,
    ctx: HouseholdContext = Depends(require_household),
) -> CorrectionCreateResponse:
    """Record a user correction (mark a decision as wrong).

    The correction is persisted as a ``CorrectionEvent`` and
    also translated into a typed ``PreferenceSignal`` so the
    engine learning loop can use it.
    """
    from shopstack.app_context import db
    from shopstack.services.feedback import (
        record_user_correction,
        validate_correction,
    )

    errors = validate_correction(
        canonical_name=body.canonical_name,
        was_action=body.was_action,
        should_be_action=body.should_be_action,
        reason=body.reason,
    )
    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "validation_failed", "errors": errors},
        )

    try:
        event = record_user_correction(
            db,
            user_id=ctx.household_id,
            canonical_name=body.canonical_name,
            was_action=body.was_action,
            should_be_action=body.should_be_action,
            reason=body.reason,
        )
        return CorrectionCreateResponse(
            event_id=event.event_id,
            canonical_name=event.canonical_name,
            was_action=event.old_value,
            should_be_action=event.new_value,
            source=event.source,
            timestamp=event.timestamp.isoformat() if hasattr(event.timestamp, "isoformat") else str(event.timestamp),
            accepted=bool(event.accepted),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not record correction: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "create_failed", "message": str(exc)},
        )


__all__ = ["router"]
