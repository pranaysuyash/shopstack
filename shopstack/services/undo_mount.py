"""Undo HTTP endpoint — mounts ``POST /api/undo``.

The undo toast (rendered by
``shopstack.services.undo_ledger.render_undo_toast_trigger``)
hits ``/api/undo`` with ``{household_id, entry_id}`` when the
user clicks "Undo". This module wires that endpoint onto the
Gradio app's underlying FastAPI router.

**Why a separate module (motto_v3 §0.15 three-layer rule):**

The undo logic lives in ``shopstack.services.undo_ledger``. This
module is purely the HTTP boundary:

1. Parse the JSON body.
2. Look up the household's most recent (or specified) entry.
3. Call ``undo_last`` / ``undo_by_id``.
4. Return the result as JSON.

**Risk (motto_v3 §0.6):**

This endpoint reverses a mutation. The undo ledger already
constrains the entry to a 10s TTL and a per-household ring
buffer; a stale undo is a no-op. The endpoint trusts the ledger's
guards rather than re-implementing them.
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


def mount_undo_endpoint(app: gr.Blocks) -> None:
    """Mount ``POST /api/undo`` on the app's FastAPI router.

    Best-effort: duplicate routes or Gradio-internal errors are
    logged but never raise.
    """
    try:
        app.app.add_route(
            "/api/undo",
            _undo_endpoint,
            methods=["POST"],
        )
        logger.info("undo endpoint mounted at /api/undo")
    except Exception as exc:  # noqa: BLE001
        logger.warning("undo endpoint mount failed: %s", exc)


__all__ = ["mount_undo_endpoint"]
