"""``/api/v1/sms/*`` — Twilio SMS / WhatsApp inbound webhook.

This router ports the legacy Twilio webhook from
``/api/sms/incoming`` (mounted via Starlette ``add_route`` in
:mod:`shopstack.services.sms_webhook`) to a versioned
``/api/v1/sms/incoming`` endpoint served through FastAPI's router
system.

**Why a separate router with HMAC auth (not ``require_household``):**

The SMS webhook is an **external-facing webhook** — Twilio calls
it, not the mobile app. Twilio cannot send bearer tokens; it
authenticates via HMAC-SHA1 signature verification using the
``X-Twilio-Signature`` header. This router uses that same HMAC
verification (the ``verify_twilio_signature`` pure function from
:mod:`shopstack.services.sms_webhook`) instead of the standard
``require_household`` Depends.

**Fail-closed by design (motto_v3 §0.6 auth boundary):**

The endpoint returns 403 for any request with a missing or invalid
``X-Twilio-Signature`` header. It only responds successfully when:

1. ``settings.sms_webhook_enabled`` is True.
2. ``settings.twilio_auth_token`` is non-empty.
3. The HMAC signature is valid.

**Why POST-only:**

SMS / WhatsApp providers only POST to webhooks. Allowing GET would
expose the endpoint to accidental browser visits.

**Architecture (per motto_v3 §0.15 three-layer rule):**

- HTTP boundary only (this module).
- Delegates to :func:`shopstack.services.sms_quick_add.handle_webhook`
  for the parse + dispatch logic (transport-agnostic).
- Delegates to :func:`shopstack.services.sms_intent_handlers.make_household_scoped_dispatcher`
  for per-intent DB operations.
- Reuses :func:`shopstack.services.sms_webhook.verify_twilio_signature`
  for HMAC verification.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from shopstack.app_context import current_user_id, db
from shopstack.config import settings
from shopstack.services.sms_intent_handlers import (
    make_household_scoped_dispatcher,
)
from shopstack.services.sms_quick_add import (
    StubAdapter,
    TwilioAdapter,
    handle_webhook,
)
from shopstack.services.sms_webhook import verify_twilio_signature

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sms", tags=["sms"])


@router.post(
    "/incoming",
    summary="Twilio SMS / WhatsApp inbound webhook",
    description="Accept an incoming SMS or WhatsApp message from Twilio. "
    "Authenticated via X-Twilio-Signature HMAC verification.",
)
async def sms_incoming(request: Request) -> JSONResponse:
    """Handle an incoming Twilio SMS / WhatsApp webhook.

    **Fail-closed gate:** The endpoint returns 403 when:

    * ``settings.sms_webhook_enabled`` is False, or
    * ``settings.twilio_auth_token`` is empty, or
    * The ``X-Twilio-Signature`` header is missing or invalid.

    On success, always returns 200 (even for soft errors like
    unregistered phone or parse failure) so Twilio doesn't retry
    the request.

    Returns:
        JSONResponse with ``status``, ``intent``, ``args``, and
        ``message`` fields.
    """
    # ── Fail-closed gate: never expose an unauthenticated write surface ──
    if not settings.sms_webhook_enabled:
        logger.info(
            "SMS webhook not enabled: sms_webhook_enabled is False. "
            "Set SHOPSTACK_SMS_WEBHOOK_ENABLED=true to enable."
        )
        return JSONResponse(
            status_code=403,
            content={"status": "unauthorized", "message": "SMS webhook not enabled."},
        )

    auth_token = settings.twilio_auth_token
    if not auth_token:
        logger.warning(
            "SMS webhook not enabled: twilio_auth_token is empty. "
            "Set SHOPSTACK_TWILIO_AUTH_TOKEN to enable signature verification."
        )
        return JSONResponse(
            status_code=403,
            content={"status": "unauthorized", "message": "Twilio auth token not configured."},
        )

    # ── Parse the request body ─────────────────────────────────────────
    content_type = (request.headers.get("content-type") or "").lower()
    try:
        if "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            payload: dict = dict(form)
        else:
            payload = await request.json()
    except Exception:
        payload = {}

    # ── Authentication: verify Twilio HMAC signature (fail-closed) ─────
    signature_header = request.headers.get("X-Twilio-Signature", "")
    full_url = str(request.url)

    if not verify_twilio_signature(full_url, payload, signature_header, auth_token):
        logger.warning("SMS webhook rejected: invalid or missing X-Twilio-Signature")
        return JSONResponse(
            status_code=403,
            content={"status": "unauthorized", "message": "Invalid signature."},
        )

    # ── Authenticated: pick adapter by payload shape ────────────────────
    if "From" in payload and "Body" in payload:
        adapter = TwilioAdapter()
    else:
        adapter = StubAdapter()

    dispatcher = make_household_scoped_dispatcher(db, current_user_id() or "")

    result = handle_webhook(
        payload,
        adapter=adapter,
        dispatcher=dispatcher,
    )

    return JSONResponse(
        status_code=result.http_status,
        content={
            "status": result.status,
            "intent": result.intent,
            "args": result.args,
            "message": result.message,
        },
    )


__all__ = ["router"]
