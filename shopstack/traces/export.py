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


def _redact_trace(trace: dict) -> dict:
    text_fields = [
        "redacted_user_request", "user_goal", "final_response",
    ]
    for field in text_fields:
        val = trace.get(field, "")
        if val:
            val = re.sub(r"\b\d{10,}\b", "[REDACTED_NUMBER]", str(val))
            val = re.sub(r"\b[\w\.-]+@[\w\.-]+\.\w+\b", "[REDACTED_EMAIL]", val)
            trace[field] = val

    tool_calls = trace.get("proposed_tool_calls", [])
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if isinstance(tc, dict) and "args" in tc:
                for key in list(tc["args"].keys()):
                    if any(s in key.lower() for s in ["address", "phone", "email", "aadhar", "pan"]):
                        tc["args"][key] = "[REDACTED]"
    return trace
