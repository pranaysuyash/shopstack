"""FastAPI host for ShopStack.

This module turns the repo's versioned API surface into the primary
runtime while keeping the existing Gradio UI available as a mounted
surface during the migration.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

if os.environ.get("SPACE_ID"):
    os.environ.setdefault("SHOPSTACK_DB_PATH", "shopstack.db")

import gradio as gr
from fastapi import FastAPI

from shopstack.app_context import APP_NAME
from shopstack.app_builder import build_app
from shopstack.api.v1.mount import mount_v1_routes
from shopstack.services.health_mount import mount_health_endpoint
from shopstack.ui.frontend_shell import router as frontend_router
from shopstack.ui.header import pwa_head_html
from shopstack.ui.pwa_mount import mount_pwa_static
from shopstack.ui.security_middleware import PermissionsPolicyMiddleware
from shopstack.ui.theme import CSS


@dataclass
class _FastAPIShim:
    """Expose ``.app`` so existing mount helpers can target FastAPI."""

    app: FastAPI


def build_fastapi_app() -> FastAPI:
    """Build the FastAPI host for the ShopStack backend.

    The parent FastAPI app owns the canonical ``/api/v1/*`` surface.
    The existing Gradio UI is mounted at ``/`` so the demo still works
    while backend consumers talk to FastAPI directly.
    """
    fastapi_app = FastAPI(title=APP_NAME)
    fastapi_app.add_middleware(PermissionsPolicyMiddleware)

    from shopstack import app_context

    mount_v1_routes(_FastAPIShim(fastapi_app))
    fastapi_app.include_router(frontend_router)
    mount_pwa_static(fastapi_app)
    mount_health_endpoint(fastapi_app, app_context.db)

    gradio_ui = build_app(
        include_v1_surface=False,
        install_permissions_policy=False,
        install_post_launch_hooks=False,
    )
    return gr.mount_gradio_app(
        fastapi_app,
        gradio_ui,
        path="/gradio",
        theme=gr.themes.Base(),
        head=pwa_head_html(),
        css=CSS,
    )


__all__ = ["build_fastapi_app"]
