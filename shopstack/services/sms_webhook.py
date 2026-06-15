"""SMS / WhatsApp inbound webhook — HTTP endpoint mounting.

This module wires the inbound webhook for SMS and WhatsApp
messages onto the Gradio app's underlying FastAPI app at
``/api/sms/incoming``. The actual parse + dispatch logic lives
in :mod:`shopstack.services.sms_quick_add`; the per-intent DB
handlers live in :mod:`shopstack.services.sms_intent_handlers`.
This module is the **thin transport adapter** (HTTP boundary,
signature verification, dispatcher closure wiring).

**Why a separate module from ``sms_quick_add``:**

``sms_quick_add`` is the parse + dispatch + adapter logic — it's
domain code, transport-agnostic. ``sms_intent_handlers`` is the
per-intent DB layer. This module is the HTTP endpoint that exposes
them over the wire. The three layers let you:

* Unit-test the parse / dispatch logic without a Starlette app.
* Unit-test each per-intent handler against a fake DB.
* Swap the transport (e.g. expose a gRPC endpoint) without
  changing the dispatch or intent logic.

**Adapter selection:**

Twilio sends ``From`` and ``Body`` keys in its webhook payload;
other providers (WhatsApp Business via Meta, MessageBird, etc.)
should pre-normalize to ``{from, body}``. The endpoint picks
the adapter by payload shape — no config needed.

**Failure mode:**

Always responds 200 OK (except for malformed JSON, which
returns 200 with ``status: parse_error``). The provider
(Twilio / Meta) treats 200 as success and won't retry; internal
failures are logged but not propagated. This is the standard
webhook pattern — never let the provider retry on a logic
error.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any, Callable
from urllib.parse import urlencode

import gradio as gr

from shopstack.config import settings

logger = logging.getLogger(__name__)


def _default_intent_dispatcher(db: Any) -> Callable[[str, dict], dict]:
    """Build the default intent dispatcher bound to ``db``.

    Looks up the per-intent handler in
    :data:`shopstack.services.sms_intent_handlers.INTENT_HANDLERS`
    and delegates. Unknown intents return
    ``{"ok": True, "message": ...}`` with a no-action note (the
    provider treats 200 as success; ack-but-do-nothing is the
    right answer for future intents we haven't built yet).
    """
    from shopstack.services.sms_intent_handlers import INTENT_HANDLERS

    def _dispatch(user_id: str, parsed: dict) -> dict:
        intent = parsed.get("intent", "")
        args = parsed.get("args", {}) or {}
        handler = INTENT_HANDLERS.get(intent)
        if handler is not None:
            return handler(user_id, args, db)
        return {"ok": True, "message": f"Parsed {intent} (no action configured)."}

    return _dispatch


# ─── Endpoint mounting ─────────────────────────────────────────────


def verify_twilio_signature(
    url: str,
    params: dict[str, Any],
    signature_header: str,
    auth_token: str,
) -> bool:
    """Verify a Twilio webhook request signature (fail-closed).

    Twilio signs each webhook request with HMAC-SHA1 over the full URL
    (including scheme, host, path, and query string) concatenated with the
    sorted form parameters, keyed by the Twilio auth token. The result is
    Base64-encoded and sent in the ``X-Twilio-Signature`` header.

    Args:
        url: The full URL Twilio called (scheme + host + path + query).
        params: The parsed POST body parameters (Twilio sends form-encoded
            data; the caller should pass the decoded dict).
        signature_header: The raw ``X-Twilio-Signature`` header value.
        auth_token: The Twilio account auth token (the signing secret).

    Returns:
        True only if the signature is valid. Returns False for any missing
        input, empty token, or mismatch — this is deliberately fail-closed
        (motto §0.6: auth boundaries never silently allow on failure).

    This is a pure function so it can be unit-tested without a server.
    """
    if not auth_token or not signature_header:
        return False
    # Twilio concatenates the URL with the sorted, urlencoded form params.
    sorted_params = sorted(params.items())
    param_str = urlencode(sorted_params)
    signer = hmac.new(
        auth_token.encode("utf-8"),
        (url + param_str).encode("utf-8"),
        hashlib.sha1,
    )
    expected = signer.hexdigest()
    # Compare in constant time to avoid timing oracle.
    return hmac.compare_digest(expected, signature_header.strip())


def mount_sms_webhook(app: gr.Blocks) -> None:
    """Mount the SMS / WhatsApp inbound webhook at ``/api/sms/incoming``.

    **Fail-closed by design (motto §0.6 auth boundary).** The webhook only
    mounts when BOTH of these are true:

    1. ``settings.sms_webhook_enabled`` is True.
    2. ``settings.twilio_auth_token`` is non-empty.

    If either is missing, this function is a no-op and logs an info note.
    This guarantees a public deployment without explicitly configured
    credentials exposes no unauthenticated write surface.

    When mounted, every request is authenticated via Twilio HMAC signature
    verification (``verify_twilio_signature``). A request with a missing or
    invalid ``X-Twilio-Signature`` header is rejected with HTTP 403 before
    the dispatcher runs.

    Why best-effort route registration:
        If the route can't be registered (e.g. the app was already
        started), logs a warning and continues. The webhook is an
        enhancement, not a core feature.

    Why POST-only:
        SMS / WhatsApp providers only POST to webhooks. Allowing GET
        would expose the endpoint to accidental browser visits.
    """
    # Fail-closed gate: never mount an unauthenticated write surface.
    if not settings.sms_webhook_enabled:
        logger.info(
            "SMS webhook not mounted: sms_webhook_enabled is False. "
            "Set SHOPSTACK_SMS_WEBHOOK_ENABLED=true to enable."
        )
        return
    if not settings.twilio_auth_token:
        logger.warning(
            "SMS webhook not mounted: twilio_auth_token is empty. "
            "Set SHOPSTACK_TWILIO_AUTH_TOKEN to enable signature verification."
        )
        return

    from starlette.requests import Request as _SMSRequest
    from starlette.responses import JSONResponse as _SMSResponse
    from shopstack.app_context import current_user_id, db
    from shopstack.services.sms_intent_handlers import (
        make_household_scoped_dispatcher,
    )
    from shopstack.services.sms_quick_add import (
        StubAdapter as _SMSStub,
        TwilioAdapter as _SMSTwilio,
        handle_webhook as _sms_handle_webhook,
    )

    auth_token = settings.twilio_auth_token
    dispatcher = make_household_scoped_dispatcher(db, current_user_id() or "")

    async def _sms_webhook_endpoint(request: _SMSRequest):
        # ── Authentication: verify Twilio HMAC signature (fail-closed) ──
        signature_header = request.headers.get("X-Twilio-Signature", "")
        full_url = str(request.url)
        content_type = (request.headers.get("content-type") or "").lower()
        try:
            if "application/x-www-form-urlencoded" in content_type:
                form = await request.form()
                payload = dict(form)
            else:
                payload = await request.json()
        except Exception:
            payload = {}

        if not verify_twilio_signature(full_url, payload, signature_header, auth_token):
            logger.warning(
                "SMS webhook rejected: invalid or missing X-Twilio-Signature"
            )
            return _SMSResponse(
                status_code=403,
                content={"status": "unauthorized", "message": "Invalid signature."},
            )

        # ── Authenticated: pick adapter by payload shape ──
        if "From" in payload and "Body" in payload:
            adapter = _SMSTwilio()
        else:
            adapter = _SMSStub()

        result = _sms_handle_webhook(
            payload, adapter=adapter, dispatcher=dispatcher,
        )
        return _SMSResponse(
            status_code=result.http_status,
            content={
                "status": result.status,
                "intent": result.intent,
                "args": result.args,
                "message": result.message,
            },
        )

    try:
        app.app.add_route(
            "/api/sms/incoming",
            _sms_webhook_endpoint,
            methods=["POST"],
        )
        logger.info("SMS webhook mounted at /api/sms/incoming (signature-verified)")
    except Exception as exc:  # noqa: BLE001 — best-effort webhook bootstrap
        logger.warning("SMS webhook mount failed: %s", exc)

