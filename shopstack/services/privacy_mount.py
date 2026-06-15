"""Privacy panel HTTP endpoint — mounts ``POST /api/purge_user_data``.

The privacy panel in the settings tab (rendered by
``shopstack.services.data_retention.render_privacy_panel_html``)
hits ``/api/purge_user_data?confirm=true`` when the user clicks
"Delete my data". This module wires that endpoint onto the
Gradio app's underlying FastAPI router.

**Why POST + confirm query param (motto_v3 §0.6 risk):**

The endpoint is destructive — it wipes traces, community
observations, SMS registry, voice memos, and backups. The
``confirm=true`` query param is a belt-and-suspenders safety
check: the panel's JS already shows a ``window.confirm()``
dialog, and the server-side check ensures the endpoint
can't be hit by a casual GET or a misconfigured client.

**Auth note (motto_v3 §0.6):**

This endpoint currently has no per-user auth check beyond the
DB's per-household scoping. A future PR should add a session
token check that ensures the caller is the household owner.
For now, the endpoint trusts the DB's permission layer (the
same trust model as every other read/write path in the app).

**Failure mode:**

Like the SMS webhook, the endpoint always returns 200 with a
``success`` boolean. A failure in one purge subsystem does not
prevent the others from running (see
``shopstack.services.data_retention.purge_user_data``).
"""
from __future__ import annotations

import logging

import gradio as gr

from shopstack.app_context import current_user_id, db
from shopstack.services.data_retention import (
    purge_user_data,
    retention_summary,
)

logger = logging.getLogger(__name__)


def _purge_endpoint(request):  # noqa: ANN001 — Starlette Request
    """Handle ``POST /api/purge_user_data?confirm=true``.

    Returns ``{"success": bool, "result": {...}}`` as JSON.
    The privacy panel JS reads ``data.success`` and shows the
    appropriate toast.
    """
    try:
        params = dict(request.query_params)
        confirm = str(params.get("confirm", "")).lower() in ("true", "1", "yes")
        user_id = params.get("user_id") or current_user_id() or ""

        if not confirm:
            return {
                "success": False,
                "error": "confirm=true is required for this destructive operation",
            }
        if not user_id:
            return {
                "success": False,
                "error": "no active household",
            }

        result = purge_user_data(
            db,
            user_id=user_id,
            confirm=True,
        )
        return {"success": result.success, "result": result.to_dict()}
    except ValueError as exc:
        # The confirm=True guard in purge_user_data raises this.
        return {"success": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        logger.warning("purge_user_data endpoint failed: %s", exc)
        return {"success": False, "error": "internal error"}


def _retention_endpoint(request):  # noqa: ANN001 — Starlette Request
    """Handle ``GET /api/retention_summary``.

    Returns the current retention policy as JSON. The privacy
    panel reads this on load to show the current values.
    """
    try:
        user_id = current_user_id() or ""
        summary = retention_summary(db, user_id=user_id)
        return {"summary": summary.to_dict()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("retention_summary endpoint failed: %s", exc)
        return {"summary": {}, "error": "internal error"}


def mount_privacy_endpoints(app: gr.Blocks) -> None:
    """Mount the privacy panel's HTTP endpoints.

    Registers two routes:
      * ``POST /api/purge_user_data`` — destructive purge.
      * ``GET  /api/retention_summary`` — current policy read.

    Both are best-effort: duplicate routes or Gradio-internal
    errors are logged but never raise.
    """
    try:
        app.app.add_route(
            "/api/purge_user_data",
            _purge_endpoint,
            methods=["POST"],
        )
        logger.info("privacy purge endpoint mounted at /api/purge_user_data")
    except Exception as exc:  # noqa: BLE001
        logger.warning("privacy purge mount failed: %s", exc)
    try:
        app.app.add_route(
            "/api/retention_summary",
            _retention_endpoint,
            methods=["GET"],
        )
        logger.info("retention summary endpoint mounted at /api/retention_summary")
    except Exception as exc:  # noqa: BLE001
        logger.warning("retention summary mount failed: %s", exc)


__all__ = ["mount_privacy_endpoints"]
