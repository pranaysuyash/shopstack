"""Redaction helpers for the o/p eval layer.

Deliberately thin: reuses the production-grade PII redaction already in
:mod:`shopstack.traces.export` so we don't fork the ruleset. The eval
record never sees raw user PII in the first place because the
recorder redacts at capture time.

The wrapper exists so call sites that only have a model-call record
(no full Trace object) can still redact a single field.
"""
from __future__ import annotations

from typing import Any

from shopstack.traces.export import (
    _redact_args_dict,
    _redact_obj,
    _redact_text,
)


def redact_text(value: str) -> str:
    """Redact a single text value (prompt, output, error message)."""
    if not value:
        return value
    return _redact_text(str(value))


def redact_field(value: Any) -> Any:
    """Redact an arbitrary value (str, dict, list, or scalar)."""
    if value is None:
        return value
    return _redact_obj(value)


__all__ = ["redact_text", "redact_field"]
