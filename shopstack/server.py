"""Native FastAPI web application for ShopStack.

The FastAPI shell and the Expo mobile client are the supported product
surfaces. Both consume the same versioned ``/api/v1`` contract.
"""
from __future__ import annotations

import os

if os.environ.get("SPACE_ID"):
    os.environ.setdefault("SHOPSTACK_DB_PATH", "shopstack.db")

from fastapi import FastAPI

from shopstack.app_context import APP_NAME
from shopstack.api.v1.mount import mount_v1_routes
from shopstack.services.health_mount import mount_health_endpoint
from shopstack.ui.frontend_shell import router as frontend_router
from shopstack.ui.pwa_mount import mount_pwa_static
from shopstack.ui.security_middleware import PermissionsPolicyMiddleware


def build_fastapi_app() -> FastAPI:
    """Build the FastAPI host for the ShopStack backend.

    The FastAPI app owns the canonical web root and ``/api/v1/*`` surface.
    """
    fastapi_app = FastAPI(title=APP_NAME)
    fastapi_app.add_middleware(PermissionsPolicyMiddleware)

    from shopstack import app_context

    mount_v1_routes(fastapi_app)
    fastapi_app.include_router(frontend_router)
    mount_pwa_static(fastapi_app)
    mount_health_endpoint(fastapi_app, app_context.db)

    return fastapi_app


__all__ = ["build_fastapi_app"]
