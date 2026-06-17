"""Contract tests for ``/api/v1/sms/incoming`` — Twilio webhook.

Coverage:
  * Auth-gating: 403 without valid X-Twilio-Signature header.
  * Auth-gating: 403 with invalid X-Twilio-Signature.
  * Auth-gating: 403 when sms_webhook_enabled=False.
  * Auth-gating: 403 when twilio_auth_token is empty.
  * 200 with valid signature and Twilio-shaped payload (form-encoded).
  * 200 with valid signature and Stub-shaped payload (JSON).
  * Response shape (status, intent, args, message keys).
  * Empty body is accepted (ignored result).
  * Malformed JSON still returns 200 with valid signature.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import tempfile
from typing import Iterator
from urllib.parse import urlencode

import pytest


@pytest.fixture
def temp_db(monkeypatch) -> Iterator[str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    from shopstack.persistence.database import Database

    db = Database(path)
    yield path
    db.close()
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture
def db_handle(temp_db: str):
    from shopstack.persistence.database import Database

    db = Database(temp_db)
    yield db
    db.close()


@pytest.fixture
def v1_app(db_handle):
    from fastapi import FastAPI

    from shopstack import app_context
    from shopstack.api.v1.routers.sms import router as sms_router

    monkey = pytest.MonkeyPatch()
    monkey.setattr(app_context, "db", db_handle)

    fastapi_app = FastAPI(title="shopstack-test-sms")
    fastapi_app.include_router(sms_router, prefix="/api/v1")
    yield fastapi_app
    monkey.undo()


@pytest.fixture
def client(v1_app):
    from fastapi.testclient import TestClient

    return TestClient(v1_app)


# ── Helpers ──────────────────────────────────────────────────────

WEBHOOK_URL = "http://testserver/api/v1/sms/incoming"
TWILIO_TOKEN = "test-twilio-secret-token"


def _twilio_signature(url: str, params: dict, auth_token: str) -> str:
    """Compute a valid X-Twilio-Signature header value."""
    sorted_params = sorted(params.items())
    param_str = urlencode(sorted_params)
    return hmac.new(
        auth_token.encode("utf-8"),
        (url + param_str).encode("utf-8"),
        hashlib.sha1,
    ).hexdigest()


# ── Auth gating (fail-closed) ────────────────────────────────────


class TestSmsAuthGate:
    """The endpoint must fail-closed: 403 on any auth issue."""

    def test_missing_signature_header_returns_403(self, client, monkeypatch):
        """No X-Twilio-Signature header -> 403."""
        monkeypatch.setattr(
            "shopstack.api.v1.routers.sms.settings",
            type("obj", (object,), {
                "sms_webhook_enabled": True,
                "twilio_auth_token": TWILIO_TOKEN,
            })(),
        )
        r = client.post(
            "/api/v1/sms/incoming",
            json={"From": "+15551234567", "Body": "add milk"},
        )
        assert r.status_code == 403
        assert r.json()["status"] == "unauthorized"

    def test_invalid_signature_returns_403(self, client, monkeypatch):
        """Wrong signature header value -> 403."""
        monkeypatch.setattr(
            "shopstack.api.v1.routers.sms.settings",
            type("obj", (object,), {
                "sms_webhook_enabled": True,
                "twilio_auth_token": TWILIO_TOKEN,
            })(),
        )
        r = client.post(
            "/api/v1/sms/incoming",
            json={"From": "+15551234567", "Body": "add milk"},
            headers={"X-Twilio-Signature": "garbage-signature"},
        )
        assert r.status_code == 403
        assert r.json()["status"] == "unauthorized"

    def test_disabled_webhook_returns_403(self, client, monkeypatch):
        """sms_webhook_enabled=False -> 403."""
        monkeypatch.setattr(
            "shopstack.api.v1.routers.sms.settings",
            type("obj", (object,), {
                "sms_webhook_enabled": False,
                "twilio_auth_token": TWILIO_TOKEN,
            })(),
        )
        r = client.post("/api/v1/sms/incoming", json={})
        assert r.status_code == 403

    def test_empty_auth_token_returns_403(self, client, monkeypatch):
        """twilio_auth_token is empty -> 403."""
        monkeypatch.setattr(
            "shopstack.api.v1.routers.sms.settings",
            type("obj", (object,), {
                "sms_webhook_enabled": True,
                "twilio_auth_token": "",
            })(),
        )
        r = client.post("/api/v1/sms/incoming", json={})
        assert r.status_code == 403


# ── Happy path ───────────────────────────────────────────────────


class TestSmsHappyPath:
    """With a valid signature, the webhook processes the message.

    The exact ``status`` value depends on downstream service state
    (phone registry, parser quality, DB schema). The endpoint contract
    is: 200 with ``status``, ``intent``, ``args``, ``message`` keys.
    """

    def test_twilio_shaped_payload_returns_200(self, client, monkeypatch):
        """A Twilio-shaped payload (From + Body) with valid sig -> 200."""
        monkeypatch.setattr(
            "shopstack.api.v1.routers.sms.settings",
            type("obj", (object,), {
                "sms_webhook_enabled": True,
                "twilio_auth_token": TWILIO_TOKEN,
            })(),
        )
        payload = {"From": "+15551234567", "Body": "add milk"}
        sig = _twilio_signature(WEBHOOK_URL, payload, TWILIO_TOKEN)
        r = client.post(
            "/api/v1/sms/incoming",
            data=payload,
            headers={
                "X-Twilio-Signature": sig,
                "content-type": "application/x-www-form-urlencoded",
            },
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert "status" in body
        assert isinstance(body["status"], str)
        assert "intent" in body
        assert "args" in body
        assert "message" in body

    def test_stub_shaped_payload_returns_200(self, client, monkeypatch):
        """A generic JSON payload with valid sig -> 200."""
        monkeypatch.setattr(
            "shopstack.api.v1.routers.sms.settings",
            type("obj", (object,), {
                "sms_webhook_enabled": True,
                "twilio_auth_token": TWILIO_TOKEN,
            })(),
        )
        payload = {"from": "+15551234567", "body": "add milk"}
        sig = _twilio_signature(WEBHOOK_URL, payload, TWILIO_TOKEN)
        r = client.post(
            "/api/v1/sms/incoming",
            json=payload,
            headers={"X-Twilio-Signature": sig},
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert "status" in body
        assert isinstance(body["status"], str)
        assert "intent" in body
        assert "args" in body
        assert "message" in body

    def test_response_shape(self, client, monkeypatch):
        """Response contains expected top-level keys."""
        monkeypatch.setattr(
            "shopstack.api.v1.routers.sms.settings",
            type("obj", (object,), {
                "sms_webhook_enabled": True,
                "twilio_auth_token": TWILIO_TOKEN,
            })(),
        )
        payload = {"From": "+15551234567", "Body": "add milk"}
        sig = _twilio_signature(WEBHOOK_URL, payload, TWILIO_TOKEN)
        r = client.post(
            "/api/v1/sms/incoming",
            data=payload,
            headers={
                "X-Twilio-Signature": sig,
                "content-type": "application/x-www-form-urlencoded",
            },
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert "status" in body
        assert "intent" in body
        assert "args" in body
        assert "message" in body


# ── Edge cases ───────────────────────────────────────────────────


class TestSmsEdgeCases:
    def test_empty_body_is_accepted(self, client, monkeypatch):
        """An empty body is still a valid webhook (ignored result)."""
        monkeypatch.setattr(
            "shopstack.api.v1.routers.sms.settings",
            type("obj", (object,), {
                "sms_webhook_enabled": True,
                "twilio_auth_token": TWILIO_TOKEN,
            })(),
        )
        payload = {"From": "+15551234567", "Body": ""}
        sig = _twilio_signature(WEBHOOK_URL, payload, TWILIO_TOKEN)
        r = client.post(
            "/api/v1/sms/incoming",
            data=payload,
            headers={
                "X-Twilio-Signature": sig,
                "content-type": "application/x-www-form-urlencoded",
            },
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert isinstance(body["status"], str)

    def test_malformed_payload_still_returns_200_with_valid_sig(self, client, monkeypatch):
        """Malformed JSON with a valid signature still gets 200."""
        monkeypatch.setattr(
            "shopstack.api.v1.routers.sms.settings",
            type("obj", (object,), {
                "sms_webhook_enabled": True,
                "twilio_auth_token": TWILIO_TOKEN,
            })(),
        )
        sig = _twilio_signature(WEBHOOK_URL, {}, TWILIO_TOKEN)
        r = client.post(
            "/api/v1/sms/incoming",
            content=b"not-json-at-all{{{",
            headers={
                "X-Twilio-Signature": sig,
                "content-type": "application/json",
            },
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert isinstance(body["status"], str)
