# Trace Schema

Agent traces capture the full input → perception → decision → tool call → response pipeline for every user interaction.

## Trace Fields

| Field | Type | Description |
|-------|------|-------------|
| `trace_id` | str (UUID) | Unique trace identifier |
| `timestamp` | str (ISO 8601) | When the trace was created |
| `input_type` | str | `voice`, `vision`, `text`, or `scan` |
| `user_goal` | str | The user's stated goal (may be redacted) |
| `redacted_user_request` | str | Original request with PII removed |
| `perception` | dict | Provider outputs (detections, OCR, transcript) |
| `inventory_context` | dict | Relevant inventory state at time of request |
| `decision` | dict | Planner's decision and reasoning |
| `proposed_tool_calls` | list[dict] | Tool calls proposed by the planner |
| `final_response` | str | Response shown to the user |

## Redaction

Before export, the following are redacted:

- **Phone numbers**: 10+ consecutive digits → `[REDACTED_NUMBER]`
- **Email addresses**: standard email pattern → `[REDACTED_EMAIL]`
- **Sensitive tool args**: keys containing `address`, `phone`, `email`, `name`, `aadhar`, `pan` → `[REDACTED]`

## Export Format

Traces are exported as JSONL (one JSON object per line):

```jsonl
{"trace_id": "abc123", "input_type": "voice", "user_goal": "[REDACTED]", ...}
{"trace_id": "def456", "input_type": "vision", "user_goal": "check milk stock", ...}
```

Use `traces/export.py`:

```python
from shopstack.traces.export import export_traces_to_jsonl
count = export_traces_to_jsonl(db, "traces.jsonl", redact=True)
```
