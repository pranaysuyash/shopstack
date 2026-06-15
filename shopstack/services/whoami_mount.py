"""Whoami HTTP endpoint — mounts ``GET /api/whoami``.

**Why this exists (motto_v3 §0.10 Observability Is Delivery):**

Operators hitting the app need a single, read-only endpoint that
answers "where am I" — *which* instance am I talking to, *which*
DB file is it reading, *which* household is currently active. Without
this, debugging a multi-instance deploy or a "user says their data
is missing" ticket requires SSH access to read config files.

**What this returns:**

  - ``app``: name + version (from ``shopstack._version`` + ``pyproject.toml``)
  - ``household``: current active household_id + source of truth
  - ``database``: path, existence flag, size in bytes, table count
  - ``runtime``: Python version, Gradio version
  - ``timestamp``: server-side ISO 8601 timestamp

**What this does NOT do:**

  - It does NOT require auth (per ``motto_v3`` §3.2 multi-user
    auth is a separate deferred item). The endpoint discloses
    non-sensitive metadata (paths, versions, current user_id).
  - It does NOT make write calls. It's a pure read endpoint.
  - It does NOT include secrets, tokens, or env values.

**HTTP semantics:**

  - 200 OK with the JSON payload above.
  - 500 Internal Server Error only if even basic introspection
    (e.g. ``sys.version_info``) fails — should never happen.

**Pattern:**

  Mirrors :mod:`shopstack.services.health_mount` — a thin transport
  adapter that registers a FastAPI route on the Gradio Blocks'
  underlying app. Best-effort: any check that fails reports
  ``null`` for that field rather than aborting the whole payload,
  so a partial response is always more useful than no response.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gradio as gr

logger = logging.getLogger(__name__)


def _safe_call(fn, default: Any = None) -> Any:
    """Run ``fn`` and return its result, or ``default`` on any exception.

    Per the best-effort contract: a whoami probe should never
    crash because one sub-check failed. The operator still gets
    the rest of the payload.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 — best-effort introspection
        logger.debug("whoami sub-check failed: %s", exc)
        return default


def _app_metadata() -> dict[str, Any]:
    """Return app name + version from the canonical ``_version`` module."""
    info: dict[str, Any] = {"name": None, "version": None}
    try:
        from shopstack import _version
        info["name"] = _version.__name__ if hasattr(_version, "__name__") else "shopstack"
        info["version"] = getattr(_version, "__version__", None) or getattr(
            _version, "VERSION", None
        )
    except Exception:
        pass
    return info


def _household_metadata() -> dict[str, Any]:
    """Return the current active household_id and its source.

    ``current_user_id()`` resolves through the ``Settings`` class:
    the active household is whichever the user last selected
    (persisted via ``app_config``) or the default
    (``settings.default_household_user_id``).
    """
    info: dict[str, Any] = {"active_household_id": None, "source": None}
    try:
        from shopstack.app_context import current_user_id
        info["active_household_id"] = current_user_id()
        info["source"] = "current_user_id()"
    except Exception:
        pass
    return info


def _database_metadata() -> dict[str, Any]:
    """Return DB path, existence, size, and table count.

    Best-effort. If the DB isn't initialized, ``table_count``
    is ``None`` rather than a hard error.
    """
    info: dict[str, Any] = {"path": None, "exists": False, "size_bytes": None, "table_count": None}
    try:
        from shopstack.app_context import db
        info["path"] = getattr(db, "db_path", None)
        if info["path"]:
            db_path = Path(info["path"])
            info["exists"] = db_path.is_file()
            if info["exists"]:
                info["size_bytes"] = db_path.stat().st_size
        # Count tables via sqlite3 master (read-only, cheap).
        try:
            cur = db.conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
            )
            info["table_count"] = cur.fetchone()[0]
        except Exception:
            pass
    except Exception:
        pass
    return info


def _runtime_metadata() -> dict[str, Any]:
    """Return Python + Gradio versions + the current thread id."""
    info: dict[str, Any] = {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "gradio_version": getattr(gr, "__version__", None),
        "pid": os.getpid(),
    }
    try:
        import threading
        info["thread"] = threading.current_thread().name
    except Exception:
        pass
    return info


def mount_whoami_endpoint(
    app: gr.Blocks,
    *,
    path: str = "/api/whoami",
) -> None:
    """Mount the ``GET /api/whoami`` route on the Gradio app's FastAPI layer.

    Args:
        app: The ``gr.Blocks`` instance returned by ``build_app()``.
        path: Route path. Defaults to ``/api/whoami``.

    Per ``motto_v3`` §0.10 (Observability Is Delivery), this is
    a Tier-3 (integration) endpoint. It must be reachable
    *post*-launch (per the same `mount_*_endpoint` pattern that
    ``mount_health_endpoint`` uses) because ``app.app`` is
    recreated when the ``with gr.Blocks():`` context exits.

    The endpoint is best-effort: if any sub-check fails, that
    field becomes ``null`` and the rest of the payload is still
    returned. The endpoint never raises 5xx for an internal
    sub-check failure — only for a path-level catastrophic
    failure (which we don't expect).
    """
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    async def _whoami(request: Request) -> JSONResponse:
        payload: dict[str, Any] = {
            "app": _safe_call(_app_metadata, default={}),
            "household": _safe_call(_household_metadata, default={}),
            "database": _safe_call(_database_metadata, default={}),
            "runtime": _safe_call(_runtime_metadata, default={}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return JSONResponse(
            payload,
            status_code=200,
            headers={"Cache-Control": "no-store"},
        )

    try:
        # Use Starlette's ``add_route`` (matches the health/sms pattern)
        # rather than FastAPI's ``add_api_route`` — the latter requires
        # the FastAPI app to be fully constructed, which doesn't hold
        # inside ``with gr.Blocks() as app:``.
        app.app.add_route(path, _whoami, methods=["GET"])
        logger.info("Whoami endpoint mounted at %s", path)
    except Exception as exc:  # noqa: BLE001 — best-effort mount
        logger.warning("Could not mount whoami endpoint at %s: %s", path, exc)


__all__ = ["mount_whoami_endpoint"]
