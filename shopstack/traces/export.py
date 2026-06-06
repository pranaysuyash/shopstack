from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from shopstack.persistence.database import Database
from shopstack.schemas.models import Trace

FIELD_NOTES_CONFIG_KEY = "field_notes_markdown"


def export_traces_to_jsonl(
    db: Database, output_path: str, limit: int = 50, redact: bool = True
) -> int:
    traces = db.get_traces(limit=limit)
    count = 0
    with open(output_path, "w") as f:
        for t in traces:
            dumped = t.model_dump()
            if redact:
                dumped = _redact_trace(dumped)
            f.write(json.dumps(dumped, default=str) + "\n")
            count += 1
    return count


def create_trace(
    db: Database,
    input_type: str = "",
    user_goal: str = "",
    redacted_user_request: str = "",
    perception: dict | None = None,
    inventory_context: dict | None = None,
    decision: dict | None = None,
    proposed_tool_calls: list | None = None,
    final_response: str = "",
    human_confirmation: str | None = None,
) -> Trace:
    trace = Trace(
        input_type=input_type,
        user_goal=user_goal,
        redacted_user_request=redacted_user_request,
        perception=perception or {},
        inventory_context=inventory_context or {},
        decision=decision or {},
        proposed_tool_calls=proposed_tool_calls or [],
        final_response=final_response,
        human_confirmation=human_confirmation,
    )
    db.save_trace(trace)
    return trace


def trace_payload_for_export(trace: Trace, redact: bool = True, db: Database | None = None) -> dict[str, Any]:
    payload = trace.model_dump()
    if db:
        field_notes = db.get_config_value(FIELD_NOTES_CONFIG_KEY, "")
        if field_notes.strip():
            payload["field_notes"] = field_notes
    return _redact_trace(payload) if redact else payload


def export_trace_by_id(
    db: Database, trace_id: str, output_path: str, redact: bool = True
) -> bool:
    target = (trace_id or "").strip()
    if not target:
        return False
    for t in db.get_traces(limit=200):
        if t.trace_id == target:
            with open(output_path, "w") as f:
                f.write(json.dumps(trace_payload_for_export(t, redact=redact, db=db), default=str) + "\n")
            return True
    return False


def create_market_lens_trace(
    db: Database,
    items_detected: list[str] | None = None,
    audio_present: bool = False,
    image_present: bool = False,
    barcode_data: str | None = None,
    analysis_text: str = "",
    analysis_result: str = "",
    decision_items: list[dict] | None = None,
    proposed_tool_calls: list | None = None,
    human_confirmation: str | None = None,
) -> Trace:
    items = items_detected or []
    perception: dict[str, Any] = {
        "items_detected": items,
        "audio": audio_present,
        "image": image_present,
    }
    if barcode_data:
        perception["barcode"] = barcode_data
    return create_trace(
        db,
        input_type="market_lens",
        user_goal="market_lens",
        redacted_user_request=analysis_text,
        perception=perception,
        inventory_context={"decision_count": len(decision_items or [])},
        decision={"items": (decision_items or [])[:6]},
        proposed_tool_calls=proposed_tool_calls or [],
        final_response=analysis_result,
        human_confirmation=human_confirmation,
    )


def create_shopping_list_trace(
    db: Database,
    goal: str = "",
    items: list[dict] | None = None,
    proposed_tool_calls: list | None = None,
    final_response: str = "",
    human_confirmation: str | None = None,
) -> Trace:
    safe_items = items or []
    perception: dict[str, Any] = {
        "goal": goal,
        "item_count": len(safe_items),
        "items": safe_items,
    }
    return create_trace(
        db,
        input_type="shopping_list",
        user_goal=goal or "create_shopping_list",
        redacted_user_request=f"create shopping list: {goal}" if goal else "",
        perception=perception,
        inventory_context={},
        decision={"action": "create_shopping_list"},
        proposed_tool_calls=proposed_tool_calls or [],
        final_response=final_response,
        human_confirmation=human_confirmation,
    )


def create_add_purchase_trace(
    db: Database,
    item_name: str,
    quantity: float = 1.0,
    unit: str = "unit",
    price: float = 0.0,
    store: str = "",
    location: str = "",
    category: str = "",
    proposed_tool_calls: list | None = None,
    final_response: str = "",
    human_confirmation: str | None = None,
) -> Trace:
    return create_trace(
        db,
        input_type="form",
        user_goal="add_purchase",
        redacted_user_request=f"add purchase: {item_name}",
        perception={
            "item": item_name,
            "quantity": quantity,
            "unit": unit,
            "store": store,
        },
        inventory_context={
            "storage_location": location,
            "category": category,
        },
        decision={"action": "add_inventory_item"},
        proposed_tool_calls=proposed_tool_calls or [],
        final_response=final_response,
        human_confirmation=human_confirmation,
    )


def find_trace_by_id(db: Database, trace_id: str) -> Trace | None:
    target = (trace_id or "").strip()
    if not target:
        return None
    for t in db.get_traces(limit=200):
        if t.trace_id == target:
            return t
    return None


def update_trace_confirmation(db: Database, trace_id: str, confirmation: str) -> bool:
    target = (trace_id or "").strip()
    if not target:
        return False
    for t in db.get_traces(limit=200):
        if t.trace_id == target:
            t.human_confirmation = confirmation
            db.save_trace(t)
            return True
    return False


def redact_trace_payload(trace_dict: dict[str, Any]) -> dict[str, Any]:
    return _redact_trace(trace_dict)


def _redact_trace(trace: dict) -> dict:
    text_fields = [
        "redacted_user_request", "user_goal", "final_response",
    ]
    for field in text_fields:
        val = trace.get(field, "")
        if val:
            trace[field] = _redact_text(str(val))

    tool_calls = trace.get("proposed_tool_calls", [])
    if isinstance(tool_calls, list):
        trace["proposed_tool_calls"] = [
            _redact_args_dict(tc) if isinstance(tc, dict) else tc for tc in tool_calls
        ]

    for nested_key in ["perception", "inventory_context", "decision"]:
        if nested_key in trace:
            trace[nested_key] = _redact_obj(trace[nested_key])

    return trace


def _redact_text(value: str) -> str:
    value = re.sub(r"\b\d{10,}\b", "[REDACTED_NUMBER]", value)
    value = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", "[REDACTED_EMAIL]", value)
    value = re.sub(r"\b[A-Z]{5}\d{4}[A-Z]\b", "[REDACTED]", value)
    return value


def _redact_args_dict(args: dict) -> dict:
    redacted: dict = {}
    for key, value in args.items():
        lowered = key.lower()
        if key == "args" and isinstance(value, dict):
            redacted[key] = _redact_args_dict(value)
        elif any(s in lowered for s in ["address", "phone", "email", "aadhar", "pan"]):
            redacted[key] = "[REDACTED]"
        else:
            redacted[key] = _redact_obj(value)
    return redacted


def _redact_obj(value):
    if isinstance(value, dict):
        return {k: _redact_obj(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_obj(v) for v in value]
    if isinstance(value, str):
        return _redact_text(value)
    return value
