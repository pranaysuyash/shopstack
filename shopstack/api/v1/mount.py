"""Single entry point that mounts the ``/api/v1/*`` surface on a
Gradio ``Blocks`` instance.

Called from ``app.py`` once inside ``with gr.Blocks() as app:``
and again from the post-launch hook (Gradio recreates
``app.app`` on launch; see ``app.py:_install_post_launch_hooks``).
The mount is idempotent — duplicate routes are caught and
logged but do not raise.

All legacy HTTP endpoints have been ported to versioned
``/api/v1/*`` routers. The ``_mount_aliases`` function that
provided backward-compat Sunset-tagged aliases was removed
in Pass 26 (2026-06-17).
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
        account_router,
        auth_router,
        dashboard_router,
        command_router,
        household_router,
        intelligence_router,
        inventory_router,
        meta_router,
        corrections_router,
        search_router,
        shopping_router,
        sms_router,
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
        (command_router, "/api/v1"),
        (search_router, "/api/v1"),
        (intelligence_router, "/api/v1"),
        (account_router, "/api/v1"),
        (corrections_router, "/api/v1"),
        (sms_router, "/api/v1"),
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

    # ── 3. Idempotency-Key middleware ─────────────────────────
    try:
        from shopstack.api.v1.idempotency import (
            IdempotencyMiddleware,
            ensure_idempotency_table,
        )

        fastapi_app.add_middleware(IdempotencyMiddleware)
        from shopstack.app_context import db as _idem_db
        ensure_idempotency_table(_idem_db)
        logger.info("idempotency middleware + table ready")
    except Exception as exc:  # noqa: BLE001
        logger.debug("idempotency middleware mount failed: %s", exc)



# ── internal ──────────────────────────────────────────────────


def _get_fastapi_app(gradio_app: gr.Blocks) -> Any:
    """Access the underlying FastAPI/Starlette instance.

    Gradio 6.x exposes it as ``gradio_app.app``. If the
    attribute is missing or the instance is uninitialised,
    we return ``None`` and the caller skips the mount.
    """
    return getattr(gradio_app, "app", None)

__all__ = ["mount_v1_routes"]
