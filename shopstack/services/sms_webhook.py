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

import logging
from typing import Any, Callable

import gradio as gr

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

def mount_sms_webhook(app: gr.Blocks) -> None:
    """Mount the SMS / WhatsApp inbound webhook at ``/api/sms/incoming``.

    Best-effort: if the route can't be registered (e.g. the app
    was already started), logs a warning and continues. The
    webhook is an enhancement, not a core feature.

    Args:
        app: The root ``gr.Blocks`` instance. The underlying
            FastAPI app is ``app.app``.

    Why best-effort:
        The webhook depends on the ``sms_quick_add`` service
        being importable. If that import fails for any reason
        (e.g. a missing optional dependency), the rest of the
        app should still start.

    Why POST-only:
        SMS / WhatsApp providers only POST to webhooks. Allowing
        GET would expose the endpoint to accidental browser
        visits and surface a meaningless response.
    """
    from starlette.requests import Request as _SMSRequest
    from starlette.responses import JSONResponse as _SMSResponse
    from shopstack.app_context import current_user_id, db
    from shopstack.services.sms_quick_add import (
        StubAdapter as _SMSStub,
        TwilioAdapter as _SMSTwilio,
        handle_webhook as _sms_handle_webhook,
    )

    dispatcher = _default_intent_dispatcher(db)

    async def _sms_webhook_endpoint(request: _SMSRequest):
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        # Pick adapter by shape: Twilio sends ``From`` + ``Body``,
        # other providers should pre-normalize to ``{from, body}``.
        if "From" in payload and "Body" in payload:
            adapter = _SMSTwilio()
        else:
            adapter = _SMSStub()

        uid = current_user_id() or ""
        result = _sms_handle_webhook(
            payload, adapter=adapter, dispatcher=lambda u, p: dispatcher(u, p),
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
    except Exception as exc:  # noqa: BLE001 — best-effort webhook bootstrap
        logger.warning("SMS webhook mount failed: %s", exc)
