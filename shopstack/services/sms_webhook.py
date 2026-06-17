"""Shared utilities for the SMS / WhatsApp webhook.

**This module is no longer the HTTP endpoint.** The inbound webhook
has been ported to :mod:`shopstack.api.v1.routers.sms` as a versioned
``/api/v1/sms/incoming`` FastAPI router (Pass 27).

This module now provides two shared utilities that the v1 router
and intent-handler layers depend on:

1. :func:`verify_twilio_signature` — pure HMAC-SHA1 verification
   (the fail-closed auth boundary).
2. :func:`_default_intent_dispatcher` — builds the intent-to-handler
   dispatcher for the SMS flow.

The three-layer architecture is preserved (motto_v3 §0.15):

* HTTP boundary → :mod:`shopstack.api.v1.routers.sms`
* Parse + dispatch → :mod:`shopstack.services.sms_quick_add`
* Per-intent DB → :mod:`shopstack.services.sms_intent_handlers`
* Shared utilities → this module
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any, Callable
from urllib.parse import urlencode

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
        (motto_v3 §0.6: auth boundaries never silently allow on failure).

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


__all__ = [
    "_default_intent_dispatcher",
    "verify_twilio_signature",
]
