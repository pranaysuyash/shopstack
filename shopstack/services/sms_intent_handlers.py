"""SMS / WhatsApp intent handlers — per-intent DB operations.

Extracted from :mod:`shopstack.services.sms_webhook` (Pass 14,
2026-06-14) to keep that module a thin transport adapter (its
docstring claims). Each handler is a small function that:

* validates the parsed intent args against a canonical contract,
* resolves any cross-references (e.g. ``canonical_name`` →
  ``lot_id``) via the DB accessors that already exist,
* calls the canonical DB write path,
* returns a ``{"ok": bool, "message": str}`` result.

All exceptions are caught inside the handler and returned as
``ok=False`` with a user-facing message. The webhook transport
never propagates internal failures to the provider (so it
doesn't retry on a logic error).

Why a separate module:
  Per motto_v3 §11 engineering standards, this file owns the
  per-intent business logic so the webhook stays a thin
  transport. Tests can exercise handlers directly with a fake
  DB without going through the HTTP layer.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable

# (intent_name, args_validator) → handler(user_id, args, db) → result
# A handler receives the validated args dict, the resolved user_id
# (the phone-resolved household id, never the process-global), and
# the db singleton. It returns ``{"ok": bool, "message": str}``.
IntentHandler = Callable[[str, dict, Any], dict]


# ── per-intent handlers ────────────────────────────────────────────


def _handle_add_inventory_item(user_id: str, args: dict, db: Any) -> dict:
    """Build an InventoryLot from the parsed args, write to DB.

    No-op (ok=True) if ``canonical_name`` is missing — the user
    hasn't told us what to add. Matches the legacy inline
    contract: the guard belongs here so each intent is the
    single source of truth for its own required args.
    """
    if not args.get("canonical_name"):
        return {"ok": True, "message": f"Parsed {args.get('intent', '')} (no action configured)."}
    from shopstack.schemas.models import InventoryLot
    try:
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


def _handle_consume_item(user_id: str, args: dict, db: Any) -> dict:
    """Resolve canonical_name → oldest active lot (FIFO), consume quantity.

    No-op (ok=True) if ``canonical_name`` is missing.

    Uses the canonical :func:`Database.get_inventory` accessor with
    household scoping, so the write is correctly authorized against
    the writer's household (per the motto_v3 §0.6 fix to
    ``consume_inventory`` that deduces target_household from the lot).
    """
    if not args.get("canonical_name"):
        return {"ok": True, "message": f"Parsed {args.get('intent', '')} (no action configured)."}
    try:
        canonical = str(args["canonical_name"])
        quantity = float(args.get("quantity", 1.0))
        candidates = db.get_inventory(
            status="active", canonical_name=canonical, user_id=user_id
        )
        if not candidates:
            return {"ok": False, "message": f"No active {canonical} in inventory"}
        # FIFO: oldest lot first so users consume older stock.
        candidates.sort(key=lambda l: l.created_at or datetime.min)
        target = candidates[0]
        db.consume_inventory(target.lot_id, quantity, user_id=user_id)
        return {"ok": True, "message": f"Consumed {canonical}"}
    except Exception as exc:
        return {"ok": False, "message": f"DB error: {exc}"}


# ── registry ──────────────────────────────────────────────────────
#
# A flat table of intent_name → handler. New intents register here.
# motto_v3 §7: a single source of truth for which intents the
# webhook supports. No parallel branches elsewhere.

INTENT_HANDLERS: dict[str, IntentHandler] = {
    "add_inventory_item": _handle_add_inventory_item,
    "consume_item": _handle_consume_item,
}


__all__ = ["INTENT_HANDLERS", "IntentHandler"]
