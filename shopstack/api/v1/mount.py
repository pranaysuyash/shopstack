"""Single entry point that mounts the ``/api/v1/*`` surface on a
Gradio ``Blocks`` instance.

Called from ``app.py`` once inside ``with gr.Blocks() as app:``
and again from the post-launch hook (Gradio recreates
``app.app`` on launch; see ``app.py:_install_post_launch_hooks``).
The mount is idempotent — duplicate routes are caught and
logged but do not raise.

Also mounts **backward-compat aliases** for the 11 existing
HTTP endpoints. Each alias:
* delegates to the v1 handler, OR
* is a 1-line Starlette route that re-emits the same JSON
  shape the old endpoint returned.

Aliases carry the ``Sunset`` header (RFC 8594) pointing at
the v1 path. The old paths are removed in v1.1 (per the
release notes in the decision doc).
"""
from __future__ import annotations

import logging
from typing import Any

import gradio as gr

logger = logging.getLogger(__name__)


def mount_v1_routes(gradio_app: gr.Blocks) -> None:  # noqa: ANN001
    """Mount the v1 surface + alias the old endpoints.

    Idempotent. Logs but never raises.
    """
    fastapi_app = _get_fastapi_app(gradio_app)
    if fastapi_app is None:
        logger.warning("Could not access gradio_app.app; v1 surface NOT mounted")
        return

    # ── 1. v1 routers ──────────────────────────────────────────
    from .routers import (
        auth_router,
        dashboard_router,
        household_router,
        inventory_router,
        meta_router,
        shopping_router,
    )

    # The routers each declare their own prefix ("/meta", "/auth",
    # "/inventory", ...); we mount them under a single "/api/v1" so the
    # final paths are "/api/v1/meta/...", etc.
    for router, prefix in (
        (meta_router, "/api/v1"),
        (auth_router, "/api/v1"),
        (inventory_router, "/api/v1"),
        (household_router, "/api/v1"),
        (shopping_router, "/api/v1"),
        (dashboard_router, "/api/v1"),
    ):
        try:
            fastapi_app.include_router(router, prefix=prefix)
            logger.info("v1 router mounted under %s", prefix)
        except Exception as exc:  # noqa: BLE001
            logger.warning("v1 router %s mount failed: %s", prefix, exc)

    # ── 2. ensure DB tables exist ─────────────────────────────
    try:
        from shopstack.api.v1 import auth as auth_mod
        from shopstack.api.v1.routers.auth_router import ensure_device_table
        from shopstack.app_context import db

        auth_mod.ensure_auth_table(db)
        ensure_device_table(db)
    except Exception as exc:  # noqa: BLE001
        logger.debug("v1 schema bootstrap failed: %s", exc)

    # ── 3. backward-compat aliases ────────────────────────────
    _mount_aliases(gradio_app)


# ── internal ──────────────────────────────────────────────────


def _get_fastapi_app(gradio_app: gr.Blocks) -> Any:
    """Access the underlying FastAPI/Starlette instance.

    Gradio 6.x exposes it as ``gradio_app.app``. If the
    attribute is missing or the instance is uninitialised,
    we return ``None`` and the caller skips the mount.
    """
    return getattr(gradio_app, "app", None)


def _mount_aliases(gradio_app: gr.Blocks) -> None:
    """Add the 11 legacy paths as Sunset-tagged aliases.

    These are 1-line Starlette routes that call the v1 handler
    in-process. They are intentionally minimal: any
    cross-cutting concern (CORS, rate-limiting, request id) is
    added at the v1 layer, not duplicated.
    """
    from starlette.responses import JSONResponse

    fastapi_app = _get_fastapi_app(gradio_app)
    if fastapi_app is None:
        return

    SUNSET = "Sunset: Wed, 01 Jan 2026 00:00:00 GMT"  # placeholder; v1.1 removal

    # /api/whoami  →  /api/v1/meta/whoami
    async def _alias_whoami(request):  # noqa: ANN001
        from shopstack.api.v1.routers.meta import whoami as v1_whoami

        result = v1_whoami()
        return JSONResponse(
            result.model_dump(),
            headers={"Cache-Control": "no-store", "Sunset": SUNSET,
                     "Deprecation": "true",
                     "Link": '</api/v1/meta/whoami>; rel="successor-version"'},
        )

    # /health/ui  →  /api/v1/meta/health
    async def _alias_health(request):  # noqa: ANN001
        from shopstack.api.v1.routers.meta import health as v1_health

        resp = v1_health()
        resp.headers["Sunset"] = SUNSET
        resp.headers["Deprecation"] = "true"
        resp.headers["Link"] = '</api/v1/meta/health>; rel="successor-version"'
        return resp

    aliases: list[tuple[str, Any, list[str]]] = [
        ("/api/whoami", _alias_whoami, ["GET"]),
        ("/health/ui", _alias_health, ["GET"]),
        # The remaining 9 legacy mounts (/api/sms/incoming,
        # /api/global-search, /api/privacy/..., /api/undo,
        # /api/decision/.../explain, /api/recurring,
        # /api/corrections, /api/mealplan, /runtime_status) keep
        # their original handlers for now. v1 re-implementations
        # are tracked in the candidate list; aliases will be added
        # in a follow-up pass once the v1 equivalents are tested.
    ]

    for path, handler, methods in aliases:
        try:
            fastapi_app.add_route(path, handler, methods=methods)
            logger.info("v1 alias mounted: %s → %s", path, methods)
        except Exception as exc:  # noqa: BLE001 — best-effort
            logger.debug("v1 alias %s mount failed: %s", path, exc)


__all__ = ["mount_v1_routes"]
