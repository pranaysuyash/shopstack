"""``/api/v1/traces/*`` - trace inspection and export endpoints.

**Why this exists (motto_v3 first principles):**

The trace system already exists as the canonical audit trail in
``shopstack.traces.export`` and ``shopstack.services.trace``. The
The trace screen can inspect it, and the FastAPI backend exposes the
versioned contract for mobile or the new API-first shell. This router
exposes the same household-scoped trace data through the v1 surface.

**Three endpoints:**

1. ``GET /api/v1/traces`` - list recent traces for the caller's household.
2. ``GET /api/v1/traces/{trace_id}`` - inspect one trace in detail.
3. ``GET /api/v1/traces/{trace_id}/export`` - return a redacted JSONL
   payload for copy/download flows.

**Pattern (per motto_v3 §0.15 three-layer rule):**

* HTTP boundary only.
* Delegates to the shared trace service and DB read helpers.
* Households stay isolated via ``require_household``.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from shopstack.api.v1.deps import HouseholdContext, require_household
from shopstack.api.v1.schemas import (
    ApiError,
    TraceDetailResponse,
    TraceDetailWire,
    TraceExportResponse,
    TraceListResponse,
    TraceSummaryWire,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get(
    "",
    response_model=TraceListResponse,
    summary="List recent household traces",
)
def list_traces(
    ctx: HouseholdContext = Depends(require_household),
    limit: int = Query(default=20, ge=1, le=100, description="Max traces to return"),
    search: str = Query(default="", max_length=120, description="Optional search text"),
    input_type_filter: str = Query(default="", max_length=40, description="Optional input type filter"),
) -> TraceListResponse:
    """Return the most recent traces for the caller's household."""
    from shopstack.app_context import db

    traces = db.get_traces(limit=limit, user_id=ctx.household_id) or []
    traces = _filter_traces(traces, search=search, input_type_filter=input_type_filter)
    return TraceListResponse(
        summary=f"{len(traces)} trace(s) for this household.",
        count=len(traces),
        items=[_trace_to_summary_wire(t) for t in traces],
    )


@router.get(
    "/{trace_id}",
    response_model=TraceDetailResponse,
    summary="Inspect a single trace",
)
def get_trace(
    trace_id: str,
    ctx: HouseholdContext = Depends(require_household),
) -> TraceDetailResponse:
    """Return the full redacted payload for one trace."""
    from shopstack.app_context import db
    from shopstack.services.trace import TraceService

    trace = db.get_trace_by_id(trace_id, user_id=ctx.household_id)
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ApiError(
                code="trace_not_found",
                message=f"No trace with id={trace_id!r} in this household.",
            ).model_dump(),
        )

    service = TraceService(db)
    payload = service.trace_payload(trace, redact=True)
    return TraceDetailResponse(trace=_trace_to_detail_wire(trace, payload))


@router.get(
    "/{trace_id}/export",
    response_model=TraceExportResponse,
    summary="Export a redacted trace as JSONL",
)
def export_trace(
    trace_id: str,
    ctx: HouseholdContext = Depends(require_household),
    redact: bool = Query(default=True, description="Whether to redact sensitive text"),
) -> TraceExportResponse:
    """Return the trace payload as a JSONL line for download/copy flows."""
    from shopstack.app_context import db
    from shopstack.services.trace import TraceService

    trace = db.get_trace_by_id(trace_id, user_id=ctx.household_id)
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ApiError(
                code="trace_not_found",
                message=f"No trace with id={trace_id!r} in this household.",
            ).model_dump(),
        )

    service = TraceService(db)
    payload = service.trace_payload(trace, redact=redact)
    return TraceExportResponse(
        trace_id=trace.trace_id,
        redacted=redact,
        jsonl=json.dumps(payload, default=str, ensure_ascii=False),
    )


def _filter_traces(
    traces: list[Any],
    search: str = "",
    input_type_filter: str = "",
) -> list[Any]:
    needle = search.strip().lower()
    selected = input_type_filter.strip().lower()
    if selected:
        traces = [t for t in traces if (getattr(t, "input_type", "") or "").lower() == selected]
    if needle:
        traces = [
            t for t in traces
            if needle in (getattr(t, "user_goal", "") or "").lower()
            or needle in (getattr(t, "trace_id", "") or "").lower()
            or needle in (getattr(t, "input_type", "") or "").lower()
        ]
    return traces


def _trace_to_summary_wire(trace: Any) -> TraceSummaryWire:
    decision = getattr(trace, "decision", {}) or {}
    action = decision.get("action", "") if isinstance(decision, dict) else ""
    return TraceSummaryWire(
        trace_id=getattr(trace, "trace_id", "") or "",
        input_type=getattr(trace, "input_type", "") or "",
        user_goal=getattr(trace, "user_goal", "") or "",
        timestamp=_iso(getattr(trace, "timestamp", None)),
        human_confirmation=getattr(trace, "human_confirmation", None),
        final_response=getattr(trace, "final_response", "") or "",
        action=str(action or ""),
        tool_call_count=len(getattr(trace, "proposed_tool_calls", []) or []),
    )


def _trace_to_detail_wire(trace: Any, payload: dict[str, Any]) -> TraceDetailWire:
    base = _trace_to_summary_wire(trace).model_dump()
    return TraceDetailWire(
        **base,
        redacted_user_request=str(payload.get("redacted_user_request", "")),
        perception=dict(payload.get("perception", {}) or {}),
        inventory_context=dict(payload.get("inventory_context", {}) or {}),
        decision=dict(payload.get("decision", {}) or {}),
        proposed_tool_calls=list(payload.get("proposed_tool_calls", []) or []),
        actor_id=str(payload.get("actor_id", "") or ""),
    )


def _iso(value: Any) -> str:
    if value is None:
        return ""
    iso = getattr(value, "isoformat", None)
    if callable(iso):
        return iso()
    return str(value)


__all__ = ["router"]
