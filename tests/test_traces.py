from __future__ import annotations

import json
import tempfile
from pathlib import Path

from shopstack.schemas.models import Trace
from shopstack.traces.export import _redact_trace, create_trace, export_traces_to_jsonl


class TestTraceRedaction:
    def test_redact_phone_number(self):
        trace_dict = {
            "user_goal": "Call me at 9876543210",
            "redacted_user_request": "Call me at 9876543210",
            "final_response": "Sure, I'll call 9876543210",
        }
        redacted = _redact_trace(trace_dict)
        assert "[REDACTED_NUMBER]" in redacted["user_goal"]
        assert "9876543210" not in redacted["user_goal"]

    def test_redact_email(self):
        trace_dict = {
            "user_goal": "Email test@example.com",
            "redacted_user_request": "Email test@example.com",
            "final_response": "ok",
        }
        redacted = _redact_trace(trace_dict)
        assert "[REDACTED_EMAIL]" in redacted["user_goal"]
        assert "test@example.com" not in redacted["user_goal"]

    def test_redact_tool_args(self):
        trace_dict = {
            "user_goal": "add item",
            "redacted_user_request": "add item",
            "final_response": "done",
            "proposed_tool_calls": [
                {"tool_name": "add_inventory", "args": {"name": "milk", "phone": "9876543210", "email": "test@test.com"}}
            ],
        }
        redacted = _redact_trace(trace_dict)
        call = redacted["proposed_tool_calls"][0]
        assert call["args"]["phone"] == "[REDACTED]"
        assert call["args"]["email"] == "[REDACTED]"
        assert call["args"]["name"] == "milk"

    def test_redact_aadhar(self):
        trace_dict = {
            "user_goal": "My aadhar is 123456789012",
            "redacted_user_request": "My aadhar is 123456789012",
            "final_response": "ok",
            "proposed_tool_calls": [],
        }
        redacted = _redact_trace(trace_dict)
        assert "[REDACTED_NUMBER]" in redacted["user_goal"]

    def test_redact_pan(self):
        trace_dict = {
            "proposed_tool_calls": [
                {"tool_name": "verify", "args": {"pan": "ABCDE1234F"}}
            ],
            "user_goal": "verify",
            "redacted_user_request": "verify",
            "final_response": "ok",
        }
        redacted = _redact_trace(trace_dict)
        assert redacted["proposed_tool_calls"][0]["args"]["pan"] == "[REDACTED]"


class TestCreateTrace:
    def test_create_basic(self, db):
        trace = create_trace(
            db,
            input_type="voice",
            user_goal="check milk stock",
            redacted_user_request="check milk stock",
            final_response="You have 2L of milk",
        )
        assert trace.trace_id
        assert trace.input_type == "voice"

    def test_create_with_perception(self, db):
        trace = create_trace(
            db,
            input_type="vision",
            user_goal="what's in the fridge",
            perception={"objects": ["milk", "eggs"]},
            decision={"action": "list_items"},
        )
        assert trace.perception["objects"] == ["milk", "eggs"]


class TestExportTraces:
    def test_export_empty(self, db):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = f.name
        try:
            count = export_traces_to_jsonl(db, path)
            assert count == 0
        finally:
            Path(path).unlink(missing_ok=True)

    def test_export_with_data(self, db):
        create_trace(db, input_type="text", user_goal="test", redacted_user_request="test", final_response="ok")
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = f.name
        try:
            count = export_traces_to_jsonl(db, path, redact=True)
            assert count == 1
            with open(path) as f:
                data = json.loads(f.readline())
            assert "user_goal" in data
            assert "_private" not in data
        finally:
            Path(path).unlink(missing_ok=True)
