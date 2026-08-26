"""Single entry point that mounts the ``/api/v1/*`` surface on a
Gradio ``Blocks`` instance.

Called from ``app.py`` once inside ``with gr.Blocks() as app:``
and again from the post-launch hook (Gradio recreates
``app.app`` on launch; see ``app.py:_install_post_launch_hooks``).
The mount is idempotent — duplicate routes are caught and
logged but do not raise.

The versioned routers are canonical. A small set of compatibility aliases
remains for the existing Gradio shell and external local tooling; aliases
must preserve FastAPI dependency resolution and are excluded from OpenAPI.
"""
from __future__ import annotations

import logging
from typing import Any

import gradio as gr

logger = logging.getLogger(__name__)


def mount_v1_routes(gradio_app: gr.Blocks) -> None:
    """Mount the v1 surface plus its compatibility aliases.

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
        command_router,
        corrections_router,
        dashboard_router,
        household_router,
        intelligence_router,
        inventory_router,
        meta_router,
        portability_router,
        search_router,
        shopping_router,
        sms_router,
        traces_router,
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
        (traces_router, "/api/v1"),
        (intelligence_router, "/api/v1"),
        (account_router, "/api/v1"),
        (corrections_router, "/api/v1"),
        (portability_router, "/api/v1"),
        (sms_router, "/api/v1"),
    ):
        try:
            from fastapi import Depends

            from shopstack.api.v1.deps import db_transaction_cleanup
            fastapi_app.include_router(
                router,
                prefix=prefix,
                dependencies=[Depends(db_transaction_cleanup)],
            )
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

    # ── 4. legacy /api/* aliases (Sunset-tagged) ───────────
    # These flat paths exist for backward-compat with external
    # orchestrators.  They are thin clones of the versioned
    # endpoints and are NOT documented in OpenAPI.
    try:
        from fastapi import Depends
        from fastapi.routing import APIRoute

        from shopstack.api.v1.deps import db_transaction_cleanup
        from shopstack.api.v1.routers.search import legacy_search_global

        def _clone_route(
            src_route: APIRoute,
            new_path: str,
            *,
            endpoint: Any | None = None,
        ) -> APIRoute:
            """Clone an API route without dropping FastAPI semantics.

            A plain Starlette ``Route`` bypasses dependency injection. That
            is unsafe for aliases whose endpoint declares authentication or
            request parsing dependencies, so preserve the complete API route
            contract and bind overrides to the mounted FastAPI app.
            """
            return APIRoute(
                new_path,
                endpoint or src_route.endpoint,
                response_model=src_route.response_model,
                status_code=src_route.status_code,
                tags=src_route.tags,
                dependencies=[Depends(db_transaction_cleanup), *src_route.dependencies],
                summary=src_route.summary,
                description=src_route.description,
                response_description=src_route.response_description,
                responses=src_route.responses,
                deprecated=src_route.deprecated,
                name=f"legacy_{src_route.name or 'route'}",
                methods=list(src_route.methods or []),
                operation_id=None,
                response_model_include=src_route.response_model_include,
                response_model_exclude=src_route.response_model_exclude,
                response_model_by_alias=src_route.response_model_by_alias,
                response_model_exclude_unset=src_route.response_model_exclude_unset,
                response_model_exclude_defaults=src_route.response_model_exclude_defaults,
                response_model_exclude_none=src_route.response_model_exclude_none,
                include_in_schema=False,
                response_class=src_route.response_class,
                dependency_overrides_provider=fastapi_app,
                callbacks=src_route.callbacks,
                openapi_extra=src_route.openapi_extra,
                generate_unique_id_function=src_route.generate_unique_id_function,
                strict_content_type=src_route.strict_content_type,
            )

        _legacy_aliases = [
            (meta_router,        "/meta/whoami",              "/api/whoami"),
            (account_router,     "/account/undo",             "/api/undo"),
            (account_router,     "/account/privacy/retention-summary", "/api/retention_summary"),
            (account_router,     "/account/privacy/purge",    "/api/purge_user_data"),
            (corrections_router, "/corrections",              "/api/corrections"),
            (intelligence_router, "/intelligence/recurring",  "/api/recurring"),
            (intelligence_router, "/intelligence/mealplan",   "/api/mealplan"),
            (search_router,      "/search/global",            "/api/global_search", legacy_search_global),
        ]
        for alias_spec in _legacy_aliases:
            src_router, internal_path, alias_path, *endpoint_override = alias_spec
            target = next(
                (r for r in src_router.routes
                 if isinstance(r, APIRoute) and r.path == internal_path),
                None,
            )
            if target is not None:
                fastapi_app.routes.append(
                    _clone_route(
                        target,
                        alias_path,
                        endpoint=endpoint_override[0] if endpoint_override else None,
                    )
                )
                logger.debug("legacy alias %s → %s", alias_path, internal_path)
    except Exception as exc:  # noqa: BLE001
        logger.debug("legacy alias block failed: %s", exc)


# ── internal ──────────────────────────────────────────────────


def _get_fastapi_app(gradio_app: gr.Blocks) -> Any:
    """Access the underlying FastAPI/Starlette instance.

    Gradio 6.x exposes it as ``gradio_app.app``. If the
    attribute is missing or the instance is uninitialised,
    we return ``None`` and the caller skips the mount.
    """
    return getattr(gradio_app, "app", None)


__all__ = ["mount_v1_routes"]
