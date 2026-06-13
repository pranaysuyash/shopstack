"""SMS / WhatsApp quick-add — Phase 7 #24 (Tier 4 #24).

A webhook receiver that accepts an incoming SMS or WhatsApp
message, runs it through the fine-tuned command parser, and
dispatches the result. The user texts a Twilio / WhatsApp
Business number from their phone, and the message lands in
ShopStack as an inventory addition.

**Why a separate module:**

The webhook surface is its own thing: a different transport
(HTTP POST vs Gradio), a different auth model (signature
verification vs session), and a different error model
(respond 200 OK so the provider doesn't retry, log the
failure internally). Wrapping it in its own module keeps the
dispatcher / parser / provider boundaries clean.

**v1 scope (local-first):**

- The :class:`IncomingMessageAdapter` interface lets any
  SMS / WhatsApp provider plug in. Two adapters ship:
  - :class:`TwilioAdapter` — for Twilio Programmable SMS or
    WhatsApp via Twilio.
  - :class:`StubAdapter` — for tests and local development;
    never makes a real network call.
- The webhook handler :func:`handle_webhook` is a plain
  function that takes a parsed payload and returns a
  response dict. The Gradio / FastAPI wrapper lives in
  :mod:`shopstack.app` and is wired in the deployment step
  (this module only ships the parse + dispatch logic).
- The phone-number → user_id mapping is configurable via
  the :func:`register_phone` helper. By default, only
  registered phones can add items; unregistered numbers
  are rejected with a 200 + "unregistered" response.
- The dispatcher defaults to
  :func:`shopstack.services.fine_tuned_parser.classify_intent`.

**Privacy stance:**

- Messages are processed in-memory and never persisted
  to disk by this module. The trace system may pick them
  up via the normal command path.
- The phone-number registry is stored at
  ``~/.shopstack/inbox/phone_registry.json`` (chmod 0o600).
- No PII fields are returned in the HTTP response (only
  the dispatch status: ok / not_registered / parse_error /
  dispatch_failed).

**Design decision (deferred):**

The deployment step (running the webhook server in
production) is the user's call. This module ships the
"what to do with an incoming message" logic; the "how to
expose it as an HTTP endpoint" lives in the deployment
guide.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─── Storage paths ─────────────────────────────────────────────────


_INBOX_DIR = Path.home() / ".shopstack" / "inbox"
_REGISTRY_FILE = _INBOX_DIR / "phone_registry.json"


# ─── Phone-number helpers ──────────────────────────────────────────


def _normalize_phone(phone: str) -> str:
    """Normalize a phone number to E.164-ish (digits + leading +).

    Strips spaces, dashes, parens. Keeps a leading ``+`` if present.
    """
    if not phone:
        return ""
    p = phone.strip()
    plus = p.startswith("+")
    digits = re.sub(r"\D", "", p)
    if not digits:
        return ""
    return ("+" if plus else "") + digits


# ─── Phone registry ───────────────────────────────────────────────


def register_phone(phone: str, user_id: str) -> dict[str, Any]:
    """Map ``phone`` to ``user_id``.

    Returns ``{"registered": bool, "phone": str, "user_id": str}``.
    Persists to ``~/.shopstack/inbox/phone_registry.json``.
    """
    norm = _normalize_phone(phone)
    if not norm or not user_id:
        return {"registered": False, "reason": "Empty phone or user_id."}
    try:
        _INBOX_DIR.mkdir(parents=True, exist_ok=True)
        prefs: dict[str, str] = {}
        if _REGISTRY_FILE.is_file():
            try:
                prefs = json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                prefs = {}
        prefs[norm] = user_id
        _REGISTRY_FILE.write_text(json.dumps(prefs), encoding="utf-8")
        try:
            os.chmod(_REGISTRY_FILE, 0o600)
        except OSError:
            pass
        return {"registered": True, "phone": norm, "user_id": user_id}
    except OSError as exc:
        logger.debug("register_phone failed: %s", exc)
        return {"registered": False, "reason": str(exc)}


def lookup_phone(phone: str) -> str | None:
    """Return the user_id mapped to ``phone``, or ``None``."""
    norm = _normalize_phone(phone)
    if not norm:
        return None
    try:
        if not _REGISTRY_FILE.is_file():
            return None
        prefs = json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
        return prefs.get(norm)
    except (OSError, json.JSONDecodeError):
        return None


def unregister_phone(phone: str) -> dict[str, Any]:
    """Remove a phone mapping."""
    norm = _normalize_phone(phone)
    if not norm:
        return {"unregistered": False, "reason": "Empty phone."}
    try:
        if not _REGISTRY_FILE.is_file():
            return {"unregistered": True}
        prefs = json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
        if norm in prefs:
            del prefs[norm]
            _REGISTRY_FILE.write_text(json.dumps(prefs), encoding="utf-8")
        return {"unregistered": True, "phone": norm}
    except (OSError, json.JSONDecodeError) as exc:
        return {"unregistered": False, "reason": str(exc)}


# ─── Adapter interface ────────────────────────────────────────────


@dataclass
class IncomingMessage:
    """A parsed message from any SMS / WhatsApp provider."""

    from_phone: str
    body: str
    message_id: str = ""
    received_at: str = ""
    provider: str = "unknown"


class IncomingMessageAdapter:
    """Interface every SMS / WhatsApp provider must implement.

    Two concrete implementations ship in this module:
    :class:`TwilioAdapter` (real) and :class:`StubAdapter`
    (testing / dev). The handler code in
    :func:`handle_webhook` is provider-agnostic.
    """

    name: str = "base"

    def parse_webhook(self, payload: dict[str, Any], headers: dict[str, str] | None = None) -> IncomingMessage:
        raise NotImplementedError


class TwilioAdapter(IncomingMessageAdapter):
    """Adapter for Twilio Programmable SMS + WhatsApp (via Twilio).

    Twilio's webhook payload (for SMS)::

        {
            "From": "+15551234567",
            "Body": "add 2 kg onion",
            "MessageSid": "SM...",
        }

    For WhatsApp the same shape applies (the number is a
    ``whatsapp:`` prefix that we strip).
    """

    name = "twilio"

    def parse_webhook(self, payload: dict[str, Any], headers: dict[str, str] | None = None) -> IncomingMessage:
        from_phone = (payload.get("From") or "").strip()
        if from_phone.startswith("whatsapp:"):
            from_phone = from_phone[len("whatsapp:"):]
        return IncomingMessage(
            from_phone=_normalize_phone(from_phone),
            body=(payload.get("Body") or "").strip(),
            message_id=(payload.get("MessageSid") or "").strip(),
            received_at=datetime.now(timezone.utc).isoformat(),
            provider="twilio",
        )


class StubAdapter(IncomingMessageAdapter):
    """In-memory adapter for tests + dev.

    The webhook payload is expected in the shape already
    normalized by the handler::

        {
            "from": "+15551234567",
            "body": "add 2 kg onion",
            "message_id": "abc123",   # optional
        }
    """

    name = "stub"

    def parse_webhook(self, payload: dict[str, Any], headers: dict[str, str] | None = None) -> IncomingMessage:
        return IncomingMessage(
            from_phone=_normalize_phone(payload.get("from", "")),
            body=(payload.get("body") or "").strip(),
            message_id=(payload.get("message_id") or "").strip(),
            received_at=datetime.now(timezone.utc).isoformat(),
            provider="stub",
        )


# ─── Webhook handler ──────────────────────────────────────────────


@dataclass
class WebhookResult:
    """Structured response from a webhook handler call.

    Always returns ``http_status=200`` (so the provider doesn't
    retry on a soft error). The real status is in ``status``.
    """

    http_status: int = 200
    status: str = "ok"  # "ok" | "unregistered" | "parse_error" | "dispatch_failed" | "ignored"
    user_id: str = ""
    intent: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    parsed_at: str = ""


def handle_webhook(
    payload: dict[str, Any],
    *,
    adapter: IncomingMessageAdapter,
    parser: Callable[[str], dict[str, Any]] | None = None,
    dispatcher: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    require_registration: bool = True,
) -> WebhookResult:
    """Handle an incoming webhook ``payload``.

    The flow:
    1. ``adapter.parse_webhook(payload)`` → :class:`IncomingMessage`.
    2. Look up the phone in the registry. If ``require_registration``
       and the phone is unknown, return ``unregistered``.
    3. Run ``parser(body)`` (default: the fine-tuned parser).
    4. If intent is not ``general_query`` and a dispatcher is set,
       call it with ``(user_id, parsed_intent)``.
    5. Return a :class:`WebhookResult`.

    Args:
        payload: Raw provider payload (Twilio / Stub shape).
        adapter: The provider adapter to parse the payload.
        parser: Intent parser. Defaults to
            :func:`shopstack.services.fine_tuned_parser.classify_intent`.
        dispatcher: ``(user_id, parsed_intent) -> {"ok": bool, "message": str}``.
            When None, intents are recorded but not dispatched.
        require_registration: When True, unknown phone numbers
            are rejected with ``status="unregistered"``.

    Returns:
        :class:`WebhookResult`. Always ``http_status=200`` for
        soft errors so the SMS provider doesn't retry.
    """
    parsed_at = datetime.now(timezone.utc).isoformat()
    try:
        msg = adapter.parse_webhook(payload)
    except Exception as exc:
        logger.debug("adapter.parse_webhook failed: %s", exc)
        return WebhookResult(
            status="parse_error",
            message=f"Adapter failed: {exc}",
            parsed_at=parsed_at,
        )
    if not msg.body:
        return WebhookResult(
            status="ignored",
            message="Empty body.",
            parsed_at=parsed_at,
        )
    user_id = lookup_phone(msg.from_phone) if msg.from_phone else None
    if require_registration and not user_id:
        return WebhookResult(
            status="unregistered",
            user_id="",
            message=f"Phone {msg.from_phone!r} is not registered.",
            parsed_at=parsed_at,
        )
    user_id = user_id or "default"
    if parser is None:
        from shopstack.services.fine_tuned_parser import classify_intent
        parser = classify_intent
    try:
        parsed = parser(msg.body)
    except Exception as exc:
        return WebhookResult(
            status="parse_error",
            user_id=user_id,
            message=f"Parser raised: {exc}",
            parsed_at=parsed_at,
        )
    intent = parsed.get("intent", "general_query")
    args = parsed.get("args", {})
    if intent == "general_query":
        return WebhookResult(
            status="ok",
            user_id=user_id,
            intent=intent,
            args=args,
            message="Parsed as general_query — no action taken.",
            parsed_at=parsed_at,
        )
    if dispatcher is None:
        return WebhookResult(
            status="ok",
            user_id=user_id,
            intent=intent,
            args=args,
            message="Parsed but no dispatcher configured.",
            parsed_at=parsed_at,
        )
    try:
        result = dispatcher(user_id, parsed)
    except Exception as exc:
        return WebhookResult(
            status="dispatch_failed",
            user_id=user_id,
            intent=intent,
            args=args,
            message=f"Dispatcher raised: {exc}",
            parsed_at=parsed_at,
        )
    if not result.get("ok"):
        return WebhookResult(
            status="dispatch_failed",
            user_id=user_id,
            intent=intent,
            args=args,
            message=result.get("message", "Dispatcher returned ok=False."),
            parsed_at=parsed_at,
        )
    return WebhookResult(
        status="ok",
        user_id=user_id,
        intent=intent,
        args=args,
        message=result.get("message", "Dispatched."),
        parsed_at=parsed_at,
    )


# ─── HTML rendering ──────────────────────────────────────────────


def render_inbox_status_html(user_id: str = "") -> str:
    """Render a small status line showing the registered phone + last activity.

    Used in the household settings panel.
    """
    if not _REGISTRY_FILE.is_file():
        return (
            "<div class='ix-empty'>"
            "📱 SMS / WhatsApp quick-add is available. "
            "Register your phone number to enable it."
            "</div>"
        )
    return (
        "<div class='ix-status'>"
        "📱 SMS / WhatsApp quick-add is enabled. "
        "Text a registered number with 'add milk' or 'consume bread'."
        "</div>"
    )


__all__ = [
    "IncomingMessage",
    "IncomingMessageAdapter",
    "StubAdapter",
    "TwilioAdapter",
    "WebhookResult",
    "handle_webhook",
    "lookup_phone",
    "register_phone",
    "render_inbox_status_html",
    "unregister_phone",
]
