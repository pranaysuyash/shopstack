"""``/api/v1/command/*`` — unified command surface preview, execution, and history.

The web Today surface exposes a single input that merges shopping,
inventory, pantry, and Ask ShopStack flows. This router gives the
same canonical behavior to HTTP clients: preview the typed command
without executing it, dispatch through the shared service handlers,
and read back the recent command history from the same trace store.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from shopstack.api.v1.deps import HouseholdContext, require_household
from shopstack.api.v1.schemas import (
    CommandIntentWire,
    CommandHistoryItemWire,
    CommandHistoryResponse,
    CommandRequest,
    CommandPreviewRequest,
    CommandPreviewResponse,
    CommandResponse,
    CommandResultWire,
)
from shopstack.services.command_execution import register_default_handlers, record_command_trace
from shopstack.services.command_surface import dispatch, parse_intent

router = APIRouter(prefix="/command", tags=["command"])

_MUTATING_ACTIONS = {
    "add_to_list",
    "log_purchase",
    "add_stock",
    "mark_consumed",
}


def _preview_for_intent(text: str) -> CommandPreviewResponse:
    intent = parse_intent(text)
    would_mutate = intent.action in _MUTATING_ACTIONS
    route_kind = "ask" if intent.action == "ask" else "mutate" if would_mutate else "unknown"
    if intent.action == "add_to_list":
        summary = f"Would add {intent.canonical_name.replace('_', ' ')} to your shopping list."
    elif intent.action == "log_purchase":
        summary = f"Would log {intent.canonical_name.replace('_', ' ')} as purchased."
    elif intent.action == "add_stock":
        summary = f"Would record {intent.canonical_name.replace('_', ' ')} as already at home."
    elif intent.action == "mark_consumed":
        summary = f"Would mark {intent.canonical_name.replace('_', ' ')} as used."
    elif intent.action == "ask":
        summary = "Would route this as a question to Ask ShopStack."
    elif intent.action == "unknown":
        summary = ""
    else:
        summary = "Would route this to Ask ShopStack."
    return CommandPreviewResponse(
        original_text=text,
        intent=CommandIntentWire(
            action=intent.action,
            canonical_name=intent.canonical_name,
            raw_text=intent.raw,
        ),
        would_mutate=would_mutate,
        route_kind=route_kind,
        summary=summary,
    )


@router.post(
    "/preview",
    response_model=CommandPreviewResponse,
    summary="Parse a command without executing it",
)
def preview_command(body: CommandPreviewRequest) -> CommandPreviewResponse:
    """Parse a command and explain which canonical path it would take.

    This is intentionally public. It gives clients a safe way to show a
    preview or confirmation step before calling the household-scoped
    execute endpoint.
    """
    text = body.text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "empty_command",
                "message": "Enter a shopping command or question.",
            },
        )
    return _preview_for_intent(text)


@router.post(
    "/execute",
    response_model=CommandResponse,
    summary="Parse and execute the unified command surface input",
)
def execute_command(
    body: CommandRequest,
    ctx: HouseholdContext = Depends(require_household),
) -> CommandResponse:
    """Parse a typed command and run the matching canonical action.

    This is the HTTP counterpart to the merged Today-tab command
    surface. It is household-scoped for state-changing commands and
    returns the parsed intent so clients can show a preview or debug
    what the parser understood.
    """
    text = body.text.strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "empty_command",
                "message": "Enter a shopping command or question.",
            },
        )

    register_default_handlers()
    intent = parse_intent(text)
    result = dispatch(intent, user_id=ctx.household_id)
    record_command_trace(
        text=text,
        intent=intent,
        result=result,
        user_id=ctx.household_id,
    )
    return CommandResponse(
        household_id=ctx.household_id,
        original_text=text,
        intent=CommandIntentWire(
            action=intent.action,
            canonical_name=intent.canonical_name,
            raw_text=intent.raw,
        ),
        result=CommandResultWire(
            success=result.success,
            action=result.action,
            canonical_name=result.canonical_name,
            message=result.message,
            toast_html=result.to_toast(),
        ),
    )


@router.get(
    "/recent",
    response_model=CommandHistoryResponse,
    summary="List recent executed commands",
)
def recent_commands(
    limit: int = 10,
    ctx: HouseholdContext = Depends(require_household),
) -> CommandHistoryResponse:
    """Return the most recent command traces for this household."""
    from shopstack.app_context import db

    safe_limit = max(1, min(int(limit or 10), 25))
    traces = db.get_traces(limit=safe_limit, user_id=ctx.household_id) or []
    items = []
    for trace in traces:
        if (trace.input_type or "").lower() != "command":
            continue
        decision = trace.decision if isinstance(trace.decision, dict) else {}
        items.append(
            CommandHistoryItemWire(
                trace_id=trace.trace_id,
                timestamp=trace.timestamp.isoformat() if getattr(trace, "timestamp", None) else "",
                input_type=trace.input_type,
                original_text=trace.redacted_user_request or "",
                action=str(decision.get("action", "")),
                canonical_name=str(decision.get("canonical_name", "")),
                success=bool(decision.get("success", False)),
                summary=str(decision.get("message", ""))[:180],
            )
        )
    return CommandHistoryResponse(items=items, count=len(items))


__all__ = ["router"]
