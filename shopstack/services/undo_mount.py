"""Undo + Store Mode toggle HTTP endpoints.

This module mounts two endpoints:

1. ``POST /api/undo`` — reverses the most recent undoable mutation
   (or a specific entry by id). See :mod:`shopstack.services.undo_ledger`.

2. ``POST /api/store_mode/toggle`` — marks a shopping list item as
   bought/checked in store mode.

**Why combined (motto_v3 §0.13 scope expansion control):**

Both endpoints are small (one is a 15-line handler) and share the
same HTTP plumbing. Extracting them into separate ``_mount`` modules
would create two nearly-identical files with more boilerplate than
logic. Combining them keeps the total mount surface under 100 lines.
If either handler exceeds 30 lines, extract it into its own module.
"""
from __future__ import annotations

import json
import logging

import gradio as gr

from shopstack.app_context import current_user_id, db
from shopstack.services.undo_ledger import get_ledger

logger = logging.getLogger(__name__)


def _undo_endpoint(request):  # noqa: ANN001 — Starlette Request
    """Handle ``POST /api/undo``.

    Body: ``{"household_id": "...", "entry_id": "..."}``.
    When ``entry_id`` is empty, the most recent entry for the
    household is undone.

    Returns ``{"success": bool, "entry": {...} | null}`` as JSON.
    """
    try:
        body = {}
        try:
            body = json.loads(request.body or b"{}")
        except (ValueError, TypeError):
            body = {}

        household_id = (
            body.get("household_id")
            or dict(request.query_params).get("household_id")
            or current_user_id()
            or ""
        )
        entry_id = (
            body.get("entry_id")
            or dict(request.query_params).get("entry_id")
            or ""
        )

        if not household_id:
            return {"success": False, "error": "no active household"}

        if entry_id:
            entry = get_ledger().undo_by_id(
                household_id, entry_id, db=db,
            )
        else:
            entry = get_ledger().undo_last(household_id, db=db)

        if entry is None:
            return {"success": False, "error": "nothing to undo"}

        return {
            "success": True,
            "entry": {
                "entry_id": entry.entry_id,
                "kind": entry.kind,
                "description": entry.description,
            },
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("undo endpoint failed: %s", exc)
        return {"success": False, "error": "internal error"}



# ── Store Mode toggle endpoint ─────────────────────────────────


def _store_mode_toggle_endpoint(request):  # noqa: ANN001 — Starlette Request
    """Handle ``POST /api/store_mode/toggle``.

    Body: ``{"item_id": "..."}`` where ``item_id`` is the id of a
    shopping list item. The handler toggles the item's status between
    ``"pending"`` and ``"bought"`` (if currently pending, mark as
    bought; if currently bought, mark as pending).

    Returns ``{"success": bool, "error": "..." | null}`` as JSON.

    This endpoint is called from the Store Mode UI's inline
    ``_storeModeToggle()`` JavaScript. No auth — scoped to the
    active household via the app context.
    """
    try:
        body = {}
        try:
            raw = request.body or b"{}"
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="replace")
            body = json.loads(raw)
        except (ValueError, TypeError):
            body = {}

        item_id = body.get("item_id") or ""
        if not item_id:
            return {"success": False, "error": "item_id is required"}

        # Look up the active shopping list and find the item
        from shopstack.app_context import current_user_id as _cuid, db as _db
        uid = _cuid() or ""
        sl = _db.get_active_shopping_list(user_id=uid)
        if not sl or not sl.items:
            return {"success": False, "error": "no active shopping list"}

        # Find the item by item_id or index
        target = None
        target_idx = None
        for idx, item in enumerate(sl.items):
            item_key = getattr(item, "item_id", None) or getattr(item, "id", None) or str(idx)
            if str(item_key) == item_id:
                target = item
                target_idx = idx
                break

        if target is None:
            return {"success": False, "error": f"item {item_id} not found in active list"}

        # Toggle status: pending → bought, bought → pending
        # The database has update_list_item which updates arbitrary fields
        items_list = list(sl.items)
        current_status = getattr(items_list[target_idx], "status", "pending") or "pending"
        new_status = "bought" if current_status != "bought" else "pending"

        # Update the item status via the DB's update_list_item method
        _db.update_list_item(
            items_list[target_idx].item_id,
            {"status": new_status},
        )

        return {"success": True, "new_status": new_status}
    except Exception as exc:  # noqa: BLE001
        logger.warning("store_mode toggle failed: %s", exc)
        return {"success": False, "error": "internal error"}


def mount_undo_endpoint(app: gr.Blocks) -> None:
    """Mount ``POST /api/undo`` and ``POST /api/store_mode/toggle``
    on the app's FastAPI router.

    Best-effort: duplicate routes or Gradio-internal errors are
    logged but never raise.
    """
    endpoints = [
        ("/api/undo", _undo_endpoint, ["POST"]),
        ("/api/store_mode/toggle", _store_mode_toggle_endpoint, ["POST"]),
    ]
    for path, handler, methods in endpoints:
        try:
            app.app.add_route(path, handler, methods=methods)
            logger.info("endpoint mounted at %s", path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("endpoint %s mount failed: %s", path, exc)


__all__ = ["mount_undo_endpoint"]
