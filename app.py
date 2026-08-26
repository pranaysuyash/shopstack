from __future__ import annotations

import os

if os.environ.get("SPACE_ID"):
    os.environ.setdefault("SHOPSTACK_DB_PATH", "shopstack.db")

from shopstack.app_context import (
    APP_DESCRIPTION,
    APP_NAME,
    current_user_id,
    db,
    planner,
    providers,
    tools,
)
from shopstack.server import build_fastapi_app


def build_app():
    """Build the canonical native FastAPI web application."""
    return build_fastapi_app()


if __name__ == "__main__":
    import argparse

    import uvicorn

    from shopstack.server import build_fastapi_app

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()

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
]
