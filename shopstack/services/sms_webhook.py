"""SMS / WhatsApp inbound webhook — HTTP endpoint mounting.

This module wires the inbound webhook for SMS and WhatsApp
messages onto the Gradio app's underlying FastAPI app at
``/api/sms/incoming``. The actual parse + dispatch logic lives
in :mod:`shopstack.services.sms_quick_add`; this module is
the thin transport adapter.

**Why a separate module from ``sms_quick_add``:**

``sms_quick_add`` is the parse + dispatch + adapter logic — it's
domain code, transport-agnostic. This module is the HTTP
endpoint that exposes ``sms_quick_add`` over the wire. Splitting
them lets you:

* Unit-test the parse / dispatch logic without a Starlette app.
* Swap the transport (e.g. expose a gRPC endpoint) without
  changing the dispatch logic.
* Mount the endpoint conditionally (only in deployments that
  enable SMS / WhatsApp).

**Adapter selection:**

Twilio sends ``From`` and ``Body`` keys in its webhook payload;
other providers (WhatsApp Business via Meta, MessageBird, etc.)
should pre-normalize to ``{from, body}``. The endpoint picks
the adapter by payload shape — no config needed.

**Dispatcher shape:**

The dispatcher maps a parsed ``(intent, args)`` to a database
operation. Today it handles two intents:

* ``add_inventory_item`` → :func:`db.add_inventory_lot`
* ``consume_item`` → :func:`db.consume_inventory`

Other intents are acknowledged with ``ok=True`` but no action.
Future work: a registry of intent handlers that any tab can
register, so the dispatcher becomes plug-and-play.

**Failure mode:**

Always responds 200 OK (except for malformed JSON, which
returns 200 with ``status: parse_error``). The provider
(Twilio / Meta) treats 200 as success and won't retry; internal
failures are logged but not propagated. This is the standard
webhook pattern — never let the provider retry on a logic
error.

Extracted from ``app.py`` in Pass 7 to keep ``build_app()`` as
a true composition root.
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


# ─── Default intent dispatcher ─────────────────────────────────────
#
# Maps a parsed (intent, args) pair to a database operation. Returns
# a small result dict with ``ok`` and a user-facing ``message``.
#
# Why a closure and not a service:
#   The dispatcher needs the ``db`` singleton from ``app_context``,
#   which is only available after the app boots. The default
#   implementation closes over ``db`` at mount time; tests can
#   substitute a fake dispatcher that doesn't touch the DB.

def _default_intent_dispatcher(db: Any) -> Callable[[str, dict], dict]:
    """Build the default intent dispatcher bound to ``db``.

    Handles two intents:

    * ``add_inventory_item`` → ``db.add_inventory_lot``
    * ``consume_item`` → ``db.consume_inventory``

    Other intents return ``{"ok": True, "message": ...}`` with a
    no-action note.
    """

    def _dispatch(user_id: str, parsed: dict) -> dict:
        intent = parsed.get("intent", "")
        args = parsed.get("args", {})
        # Map to the inventory API
        if intent == "add_inventory_item" and args.get("canonical_name"):
            try:
                from shopstack.schemas.models import InventoryLot
                canonical = str(args["canonical_name"])
                lot = InventoryLot(
                    canonical_name=canonical,
                    display_name=str(args.get("display_name", canonical)),
                    quantity=float(args.get("quantity", 1.0)),
                    unit=str(args.get("unit", "unit")),
                )
                db.add_inventory_lot(lot, user_id=user_id)
                return {"ok": True, "message": f"Added {canonical}"}
            except Exception as exc:
                return {"ok": False, "message": f"DB error: {exc}"}
        if intent == "consume_item" and args.get("canonical_name"):
            try:
                canonical = str(args["canonical_name"])
                quantity = float(args.get("quantity", 1.0))
                # Resolve canonical_name → active lot (FIFO: oldest first).
                # The DB layer's get_inventory is the canonical accessor and
                # already supports household scoping via user_id.
                candidates = db.get_inventory(
                    status="active", canonical_name=canonical, user_id=user_id
                )
                if not candidates:
                    return {"ok": False, "message": f"No active {canonical} in inventory"}
                candidates.sort(key=lambda l: l.created_at)
                target = candidates[0]
                db.consume_inventory(target.lot_id, quantity, user_id=user_id)
                return {"ok": True, "message": f"Consumed {canonical}"}
            except Exception as exc:
                return {"ok": False, "message": f"DB error: {exc}"}
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


def _household_scoped_dispatcher(
    db: Any,
    fallback_user_id: str,
) -> Callable[[str, dict], dict]:
    """Build a dispatcher that uses the phone-resolved household.

    The SMS flow resolves the sender's household from the phone registry
    (``sms_quick_add.handle_webhook`` → ``lookup_phone``). That resolved
    ``user_id`` is what the dispatcher must scope DB writes to — NOT the
    process-global ``current_user_id()`` (which reflects whichever
    household is active in the UI at request time, and would corrupt
    cross-household data).

    ``handle_webhook`` calls ``dispatcher(user_id, parsed)`` where
    ``user_id`` is the phone-resolved id (falling back to "default" when
    unregistered). We honor that id and only fall back to
    ``fallback_user_id`` (the process default) when the resolved id is
    empty — preserving the previous behavior for the local-dev Stub path
    where no phone registry exists.
    """
    base = _default_intent_dispatcher(db)

    def _dispatch(user_id: str, parsed: dict) -> dict:
        uid = user_id or fallback_user_id or ""
        return base(uid, parsed)

    return _dispatch


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

    Args:
        app: The root ``gr.Blocks`` instance. The underlying FastAPI app
            is ``app.app``.

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
    from shopstack.services.sms_quick_add import (
        StubAdapter as _SMSStub,
        TwilioAdapter as _SMSTwilio,
        handle_webhook as _sms_handle_webhook,
    )

    auth_token = settings.twilio_auth_token
    dispatcher = _household_scoped_dispatcher(db, current_user_id() or "")

    async def _sms_webhook_endpoint(request: _SMSRequest):
        # ── Authentication: verify Twilio HMAC signature (fail-closed) ──
        signature_header = request.headers.get("X-Twilio-Signature", "")
        # Reconstruct the full URL Twilio called (scheme + host + path + query).
        # Starlette's request.url gives the full URL; for proxy/forwarded setups
        # the X-Forwarded-* headers are respected by Gradio/FastAPI's config.
        full_url = str(request.url)
        # Parse the POST body. Twilio sends form-encoded data; accept JSON too
        # for flexibility, but signature verification always uses the raw params.
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
