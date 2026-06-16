"""HTTP endpoints for the feedback / correction service (Pass 20).

Mirrors the ``mount_*_endpoint`` pattern from
``shopstack.services.whoami_mount`` and
``shopstack.services.decision_explain_mount``.

Endpoints:
  - ``GET  /api/corrections?limit=20&accepted_only=false``
      List recent corrections.
  - ``POST /api/corrections``
      Record a new correction. Body: JSON with
      ``canonical_name``, ``was_action``, ``should_be_action``,
      optional ``reason``. Returns the created CorrectionEvent
      (or ``400`` with validation errors).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import gradio as gr

logger = logging.getLogger(__name__)


def mount_corrections_endpoint(
    app: gr.Blocks,
    *,
    path: str = "/api/corrections",
) -> None:
    """Mount the corrections list endpoint + correction creation endpoint.

    Per `motto_v3` §0.10 (Observability Is Delivery), the
    endpoints are best-effort: sub-check failures return 200
    with a partial payload (or 400 for validation errors)
    rather than 5xx.

    Args:
        app: The ``gr.Blocks`` instance returned by ``build_app()``.
        path: Route path for GET. The POST endpoint is at
            ``/api/corrections`` (hardcoded — RESTful
            convention is that POST to the collection
            resource creates a new member).
    """
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    async def _list_corrections(request: Request) -> JSONResponse:
        from shopstack.app_context import db as app_db
        from shopstack.services.feedback import (
            list_recent_corrections,
            summarize_corrections,
        )
        try:
            limit = 20
            accepted_only = False
            try:
                limit_raw = request.query_params.get("limit")
                if limit_raw is not None:
                    limit = max(1, min(100, int(limit_raw)))
                if request.query_params.get("accepted_only", "").lower() in ("1", "true", "yes"):
                    accepted_only = True
            except (ValueError, TypeError):
                pass
            corrections = list_recent_corrections(
                app_db, user_id="", limit=limit, accepted_only=accepted_only,
            )
            return JSONResponse(
                {
                    "summary": summarize_corrections(corrections),
                    "count": len(corrections),
                    "items": [
                        {
                            "event_id": c.event_id,
                            "canonical_name": c.canonical_name,
                            "was_action": c.old_value,
                            "should_be_action": c.new_value,
                            "source": c.source,
                            "timestamp": c.timestamp.isoformat(),
                            "accepted": c.accepted,
                        }
                        for c in corrections
                    ],
                },
                status_code=200,
                headers={"Cache-Control": "no-store"},
            )
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning("Could not list corrections: %s", exc)
            return JSONResponse(
                {"error": "list_failed", "message": f"{type(exc).__name__}: {exc}", "items": []},
                status_code=200,
            )

    async def _create_correction(request: Request) -> JSONResponse:
        from shopstack.app_context import db as app_db
        from shopstack.services.feedback import (
            record_user_correction,
            validate_correction,
        )
        try:
            # Parse the JSON body. Starlette's request.json()
            # is a helper that reads the body and parses it.
            body: dict[str, Any] = {}
            try:
                body = await request.json()
            except (json.JSONDecodeError, ValueError) as exc:
                return JSONResponse(
                    {"error": "bad_json", "message": f"Could not parse JSON body: {exc}"},
                    status_code=400,
                )
            canonical_name = str(body.get("canonical_name", "")).strip()
            was_action = str(body.get("was_action", "")).strip()
            should_be_action = str(body.get("should_be_action", "")).strip()
            reason = str(body.get("reason", "")).strip()
            # Validate.
            errors = validate_correction(
                canonical_name=canonical_name,
                was_action=was_action,
                should_be_action=should_be_action,
                reason=reason,
            )
            if errors:
                return JSONResponse(
                    {"error": "validation_failed", "errors": errors},
                    status_code=400,
                )
            event = record_user_correction(
                app_db,
                user_id="",
                canonical_name=canonical_name,
                was_action=was_action,
                should_be_action=should_be_action,
                reason=reason,
            )
            return JSONResponse(
                {
                    "event_id": event.event_id,
                    "canonical_name": event.canonical_name,
                    "was_action": event.old_value,
                    "should_be_action": event.new_value,
                    "source": event.source,
                    "timestamp": event.timestamp.isoformat(),
                    "accepted": event.accepted,
                },
                status_code=201,
                headers={"Cache-Control": "no-store"},
            )
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.warning("Could not record correction: %s", exc)
            return JSONResponse(
                {"error": "create_failed", "message": f"{type(exc).__name__}: {exc}"},
                status_code=500,
            )

    try:
        # GET /api/corrections
        app.app.add_route(path, _list_corrections, methods=["GET"])
        # POST /api/corrections (same path, different method)
        app.app.add_route(path, _create_correction, methods=["POST"])
        logger.info("Corrections endpoints mounted at %s (GET + POST)", path)
    except Exception as exc:  # noqa: BLE001 — best-effort mount
        logger.warning("Could not mount corrections endpoints: %s", exc)


__all__ = ["mount_corrections_endpoint"]
