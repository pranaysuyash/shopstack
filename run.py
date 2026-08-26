"""CLI launcher for the native ShopStack FastAPI web app."""
from __future__ import annotations

import argparse

import uvicorn

from shopstack.server import build_fastapi_app


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "ShopStack — local-first shopping intelligence platform. "
            "Runs the native FastAPI web app on the configured port."
        ),
    )
    parser.add_argument("--port", type=int, default=7860)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    uvicorn.run(build_fastapi_app(), host="0.0.0.0", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
