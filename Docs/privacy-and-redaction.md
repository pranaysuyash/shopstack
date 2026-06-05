# Privacy and Redaction

ShopStack is designed for local-first privacy. Data stays on device unless explicitly exported.

## Design Principles

1. **No telemetry.** The app does not phone home, send usage data, or require internet access.
2. **Redact before export.** When traces are exported, PII is stripped before writing to disk.
3. **User controls export.** Export is a manual action, not automatic.
4. **No cloud dependencies.** Core functionality works fully offline.

## Redaction Patterns

Applied in `traces/export.py`:

| Pattern | Matches | Replacement |
|---------|---------|-------------|
| 10+ consecutive digits | `9876543210` | `[REDACTED_NUMBER]` |
| Email addresses | `user@example.com` | `[REDACTED_EMAIL]` |
| Tool arg keys: `phone`, `email`, `address`, `name`, `aadhar`, `pan` | Any value under these keys | `[REDACTED]` |

The `_private` key is stripped from all trace dicts before export.

## PII in Traces

Fields that may contain PII:
- `user_goal` (what the user asked)
- `redacted_user_request` (stored for training data pipelines)
- `tool_call.args` (if user provided personal info)

Fields that are always safe:
- `trace_id`, `timestamp` (non-personal identifiers)
- `input_type`, `perception` (object detections, generic sensor data)
- `decision`, `final_response` (agent output)

## Future

- Configurable redaction rules via settings
- On-device model inference (GGUF/llama.cpp) to keep all data local
- Encrypted database option
