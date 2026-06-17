from __future__ import annotations

import os

if os.environ.get("SPACE_ID"):
    os.environ.setdefault("SHOPSTACK_DB_PATH", "shopstack.db")

from shopstack.app_builder import build_app as _build_app
from shopstack.app_context import (
    APP_DESCRIPTION,
    APP_NAME,
    current_user_id,
    db,
    planner,
    providers,
    tools,
)
from shopstack.services.health_mount import mount_health_endpoint
from shopstack.ui.pwa_mount import mount_pwa_static
from shopstack.ui.security_middleware import (
    install_permissions_policy_middleware,
)


def build_app(
    *,
    include_v1_surface: bool = True,
    install_permissions_policy: bool = True,
    install_post_launch_hooks: bool = True,
):
    """Compatibility facade for the ShopStack Gradio UI builder."""
    return _build_app(
        include_v1_surface=include_v1_surface,
        install_permissions_policy=install_permissions_policy,
        install_post_launch_hooks=install_post_launch_hooks,
        mount_pwa_static=mount_pwa_static,
        mount_health_endpoint=mount_health_endpoint,
        install_permissions_policy_middleware=install_permissions_policy_middleware,
    )


if __name__ == "__main__":
    import argparse
    import uvicorn

    from shopstack.server import build_fastapi_app

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    if args.share:
        raise SystemExit("--share is not supported by the FastAPI entrypoint")

    uvicorn.run(
        build_fastapi_app(),
        host="0.0.0.0",
        port=args.port,
        log_level="info",
    )


__all__ = [
    "APP_DESCRIPTION",
    "APP_NAME",
    "build_app",
    "current_user_id",
    "db",
    "planner",
    "providers",
    "tools",
    "mount_health_endpoint",
    "mount_pwa_static",
    "install_permissions_policy_middleware",
]
