from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from shopstack.persistence.database import Database
from shopstack.schemas.models import Trace


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
    )
    db.save_trace(trace)
    return trace


def trace_payload_for_export(trace: Trace, redact: bool = True) -> dict[str, Any]:
    payload = trace.model_dump()
    return _redact_trace(payload) if redact else payload


def export_trace_by_id(
    db: Database, trace_id: str, output_path: str, redact: bool = True
) -> int:
    target = (trace_id or "").strip()
    if not target:
        return 0
    for t in db.get_traces(limit=200):
        if t.trace_id == target:
            with open(output_path, "w") as f:
                f.write(json.dumps(trace_payload_for_export(t, redact=redact), default=str) + "\n")
            return 1
    return 0


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
