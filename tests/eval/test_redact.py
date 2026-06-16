"""Tests for the o/p eval redaction wrapper (EVAL-OP-1).

Mostly a re-export test, but also verifies the wrapper does not
silently break the underlying redaction rules.
"""
from __future__ import annotations

from shopstack.eval.redact import redact_field, redact_text


def test_redact_text_phone():
    out = redact_text("call 9876543210 now")
    assert "[REDACTED_NUMBER]" in out


def test_redact_text_email():
    out = redact_text("email me at foo@bar.com")
    assert "[REDACTED_EMAIL]" in out


def test_redact_text_passes_through_clean_text():
    out = redact_text("add 2 onions to my list")
    assert out == "add 2 onions to my list"


def test_redact_text_empty():
    assert redact_text("") == ""
    assert redact_text(None) is None  # type: ignore[arg-type]


def test_redact_field_dict():
    out = redact_field({"phone": "9876543210", "name": "alice"})
    assert out["phone"] == "[REDACTED]"
    assert out["name"] == "alice"


def test_redact_field_list():
    out = redact_field(["call 9876543210", "no pii here"])
    assert out[0] == "[REDACTED_NUMBER] no pii here" or "[REDACTED_NUMBER]" in out[0]
    assert out[1] == "no pii here"


def test_redact_field_none():
    assert redact_field(None) is None
