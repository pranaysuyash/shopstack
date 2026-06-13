"""Tests for shopstack.services.sms_quick_add (Phase 7 #24)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from shopstack.services.sms_quick_add import (
    IncomingMessage,
    StubAdapter,
    TwilioAdapter,
    WebhookResult,
    handle_webhook,
    lookup_phone,
    register_phone,
    render_inbox_status_html,
    unregister_phone,
)


# ── register_phone / lookup_phone / unregister_phone ─────────────


def test_register_and_lookup(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone_registry.json",
    )
    r = register_phone("+15551234567", "hh-1")
    assert r["registered"] is True
    assert r["phone"] == "+15551234567"
    assert lookup_phone("+15551234567") == "hh-1"


def test_register_phone_normalizes_format(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone_registry.json",
    )
    register_phone("(555) 123-4567", "hh-2")  # no leading +
    n = lookup_phone("5551234567")
    assert n == "hh-2"


def test_register_phone_strips_dashes_and_parens(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone_registry.json",
    )
    register_phone("+1 (555) 123-4567", "hh-3")
    n = lookup_phone("+15551234567")
    assert n == "hh-3"


def test_register_phone_empty_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone_registry.json",
    )
    r = register_phone("", "hh-1")
    assert r["registered"] is False


def test_register_phone_no_user_id_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone_registry.json",
    )
    r = register_phone("+15551234567", "")
    assert r["registered"] is False


def test_register_phone_creates_parent_dir(tmp_path, monkeypatch):
    fake_inbox = tmp_path / "inbox"
    target = fake_inbox / "phone.json"
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._INBOX_DIR", fake_inbox
    )
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE", target
    )
    r = register_phone("+15551234567", "hh-1")
    assert r["registered"] is True
    assert target.is_file()


def test_lookup_phone_unknown_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "nope.json",
    )
    assert lookup_phone("+15551234567") is None


def test_lookup_phone_corrupt_file_returns_none(tmp_path, monkeypatch):
    target = tmp_path / "phone.json"
    target.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE", target,
    )
    assert lookup_phone("+15551234567") is None


def test_unregister_phone_removes_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone.json",
    )
    register_phone("+15551234567", "hh-1")
    assert lookup_phone("+15551234567") == "hh-1"
    unregister_phone("+15551234567")
    assert lookup_phone("+15551234567") is None


# ── TwilioAdapter ───────────────────────────────────────────


def test_twilio_adapter_parse_sms():
    a = TwilioAdapter()
    msg = a.parse_webhook({
        "From": "+15551234567",
        "Body": "add milk",
        "MessageSid": "SM123",
    })
    assert isinstance(msg, IncomingMessage)
    assert msg.from_phone == "+15551234567"
    assert msg.body == "add milk"
    assert msg.message_id == "SM123"
    assert msg.provider == "twilio"


def test_twilio_adapter_parse_whatsapp_strips_prefix():
    a = TwilioAdapter()
    msg = a.parse_webhook({
        "From": "whatsapp:+15551234567",
        "Body": "add 2 kg onion",
    })
    assert msg.from_phone == "+15551234567"


def test_twilio_adapter_handles_empty_payload():
    a = TwilioAdapter()
    msg = a.parse_webhook({})
    assert msg.from_phone == ""
    assert msg.body == ""


# ── StubAdapter ──────────────────────────────────────────────


def test_stub_adapter_parse():
    a = StubAdapter()
    msg = a.parse_webhook({"from": "+15551234567", "body": "hello"})
    assert msg.from_phone == "+15551234567"
    assert msg.body == "hello"
    assert msg.provider == "stub"


# ─- handle_webhook ──────────────────────────────────────────


def test_handle_webhook_stub_unregistered_phone():
    a = StubAdapter()
    r = handle_webhook(
        {"from": "+15550000000", "body": "add milk"},
        adapter=a,
    )
    assert r.status == "unregistered"


def test_handle_webhook_stub_registered_parses(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone.json",
    )
    register_phone("+15551234567", "hh-1")
    a = StubAdapter()
    r = handle_webhook(
        {"from": "+15551234567", "body": "add 2 kg tomato"},
        adapter=a,
    )
    assert r.status == "ok"
    assert r.user_id == "hh-1"
    assert r.intent == "add_inventory_item"
    assert r.args.get("canonical_name") == "tomato"


def test_handle_webhook_empty_body_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone.json",
    )
    register_phone("+15551234567", "hh-1")
    a = StubAdapter()
    r = handle_webhook(
        {"from": "+15551234567", "body": "  "},
        adapter=a,
    )
    assert r.status == "ignored"


def test_handle_webhook_general_query_no_action(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone.json",
    )
    register_phone("+15551234567", "hh-1")
    a = StubAdapter()
    r = handle_webhook(
        {"from": "+15551234567", "body": "hello world"},
        adapter=a,
    )
    assert r.status == "ok"
    assert r.intent == "general_query"


def test_handle_webhook_dispatches_to_user(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone.json",
    )
    register_phone("+15551234567", "hh-1")
    a = StubAdapter()
    dispatched = []

    def dispatcher(user_id, parsed):
        dispatched.append((user_id, parsed["intent"]))
        return {"ok": True, "message": "ok"}

    r = handle_webhook(
        {"from": "+15551234567", "body": "add milk"},
        adapter=a,
        dispatcher=dispatcher,
    )
    assert r.status == "ok"
    assert dispatched == [("hh-1", "add_inventory_item")]


def test_handle_webhook_dispatcher_failed_status(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone.json",
    )
    register_phone("+15551234567", "hh-1")
    a = StubAdapter()

    def failing_dispatcher(user_id, parsed):
        return {"ok": False, "message": "DB error."}

    r = handle_webhook(
        {"from": "+15551234567", "body": "add milk"},
        adapter=a,
        dispatcher=failing_dispatcher,
    )
    assert r.status == "dispatch_failed"
    assert "DB error" in r.message


def test_handle_webhook_dispatcher_raises_caught(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone.json",
    )
    register_phone("+15551234567", "hh-1")
    a = StubAdapter()

    def raising_dispatcher(user_id, parsed):
        raise RuntimeError("kaboom")

    r = handle_webhook(
        {"from": "+15551234567", "body": "add milk"},
        adapter=a,
        dispatcher=raising_dispatcher,
    )
    assert r.status == "dispatch_failed"
    assert "kaboom" in r.message


def test_handle_webhook_registration_not_required(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "nope.json",
    )
    a = StubAdapter()
    r = handle_webhook(
        {"from": "+15550000000", "body": "add milk"},
        adapter=a,
        require_registration=False,
    )
    # No registration → falls through to "default" user
    assert r.user_id == "default"
    assert r.status == "ok"


def test_handle_webhook_twilio_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone.json",
    )
    register_phone("+15551234567", "hh-1")
    r = handle_webhook(
        {
            "From": "+15551234567",
            "Body": "consume bread",
            "MessageSid": "SM_xyz",
        },
        adapter=TwilioAdapter(),
    )
    assert r.user_id == "hh-1"
    assert r.intent == "consume_item"


def test_handle_webhook_always_200():
    """Soft errors return http_status=200 so the SMS provider doesn't retry."""
    a = StubAdapter()
    r = handle_webhook({"from": "+15550000000", "body": "hi"}, adapter=a)
    assert r.http_status == 200
    r2 = handle_webhook({}, adapter=a)
    assert r2.http_status == 200


# ─- HTML rendering ──────────────────────────────────────────


def test_render_inbox_status_html_no_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "nope.json",
    )
    html = render_inbox_status_html()
    assert "available" in html.lower() or "ix-empty" in html


def test_render_inbox_status_html_with_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "shopstack.services.sms_quick_add._REGISTRY_FILE",
        tmp_path / "phone.json",
    )
    register_phone("+15551234567", "hh-1")
    html = render_inbox_status_html()
    assert "enabled" in html.lower() or "ix-status" in html
