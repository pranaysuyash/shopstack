"""``/api/v1/meta/*`` — read-only operator introspection endpoints.

These endpoints are **unauthenticated** in v1 (motto_v3 §0.10
Observability Is Delivery). They disclose non-sensitive metadata
only — app name, version, current household, runtime mode, DB
table count. No tokens, no secrets, no DB contents.

The old path ``/api/whoami`` is preserved as a Sunset alias
(see :mod:`shopstack.api.v1.mount`). The old path ``/health/ui``
is preserved as a Sunset alias too. New clients use
``/api/v1/meta/whoami`` and ``/api/v1/meta/health``.
"""
from __future__ import annotations

import logging
import os
import platform
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gradio as gr
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from shopstack.api.v1.schemas import WhoAmI

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/meta", tags=["meta"])


# ── helpers (moved from the old whoami_mount) ─────────────────────


def _safe(fn, default=None):
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        logger.debug("meta sub-check failed: %s", exc)
        return default


def _app_metadata() -> tuple[str, str | None]:
    name = "shopstack"
    version: str | None = None
    try:
        from shopstack import _version

        version = getattr(_version, "__version__", None) or getattr(
            _version, "VERSION", None
        )
    except Exception:
        pass
    return name, version


def _household_metadata() -> tuple[str, str | None]:
    from shopstack.app_context import current_user_id, db

    hh_id = current_user_id()
    name: str | None = None
    try:
        households = db.list_households()
        for h in households:
            if h.get("household_id") == hh_id:
                name = h.get("name")
                break
    except Exception:
        pass
    return hh_id or "default_household", name


def _runtime_mode() -> str:
    from shopstack.app_context import providers

    try:
        diag = providers.get_runtime_diagnostics()
        loaded_real = [
            r for r in diag.providers
            if getattr(r, "loaded", False) and getattr(r, "backend", "") != "mock"
        ]
        if not loaded_real:
            return "local_mock"
        backends = {getattr(r, "backend", "") for r in loaded_real}
        if "hf_inference" in backends:
            return "hf_inference"
        if "llama_cpp" in backends or "gguf" in backends:
            return "llama_cpp"
        return "local_transformers"
    except Exception:
        return "local_mock"


def _db_metadata() -> dict[str, Any]:
    from shopstack.app_context import db

    info: dict[str, Any] = {"path": None, "exists": False, "size_bytes": None, "table_count": None}
    try:
        info["path"] = getattr(db, "db_path", None)
        if info["path"]:
            p = Path(info["path"])
            info["exists"] = p.is_file()
            if info["exists"]:
                info["size_bytes"] = p.stat().st_size
        try:
            cur = db.conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            )
            info["table_count"] = cur.fetchone()[0]
        except sqlite3.OperationalError:
            pass
    except Exception:
        pass
    return info


def _system_metadata() -> dict[str, Any]:
    return {
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "platform": platform.platform(),
        "pid": os.getpid(),
    }


# ── endpoints ─────────────────────────────────────────────────────


@router.get("/whoami", response_model=WhoAmI, summary="Operator introspection")
def whoami() -> WhoAmI:
    """Return non-sensitive metadata about the running instance.

    No auth required. Returns:
    - app name + version
    - currently active household (id + name)
    - runtime mode (local_mock / local_transformers / llama_cpp / hf_inference)
    - server-side timestamp (UTC, ISO 8601)

    The legacy ``/api/whoami`` path is preserved as a Sunset alias
    and will be removed in v1.1.
    """
    name, version = _safe(_app_metadata, default=("shopstack", None))
    hh_id, hh_name = _safe(_household_metadata, default=("default_household", None))
    runtime = _safe(_runtime_mode, default="local_mock")
    return WhoAmI(
        app_name=name or "shopstack",
        app_version=version,
        household_id=hh_id or "default_household",
        household_name=hh_name,
        runtime_mode=runtime or "local_mock",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get("/health", summary="Liveness probe")
def health() -> JSONResponse:
    """Liveness probe for operators and orchestrators.

    Returns 200 with ``{"status": "ok", ...}`` when DB is queryable
    and Gradio is rendering. Returns 503 with ``{"status":
    "degraded", ...}`` when DB is unreachable.

    The legacy ``/health/ui`` path is preserved as a Sunset alias.
    """
    db_info = _safe(_db_metadata, default={})
    system = _safe(_system_metadata, default={})

    db_ok = bool(db_info and db_info.get("exists", False))
    overall = "ok" if db_ok else "degraded"
    code = 200 if db_ok else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        {
            "status": overall,
            "database": db_info,
            "system": system,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        status_code=code,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/runtime", summary="Provider runtime diagnostics")
def runtime() -> dict[str, Any]:
    """Provider registry runtime diagnostics (unauthenticated).

    Useful for ``mobile-app / model-stack`` screens and operator
    debugging. Discloses the loaded providers and their backend
    kinds. Does NOT disclose API keys, secrets, or env values.
    """
    from shopstack.app_context import providers

    try:
        diag = providers.get_runtime_diagnostics()
        return {
            "mode": _safe(_runtime_mode, default="local_mock"),
            "providers": [
                {
                    "name": getattr(p, "name", None),
                    "backend": getattr(p, "backend", None),
                    "loaded": bool(getattr(p, "loaded", False)),
                    "available": bool(getattr(p, "available", False)),
                    "model_id": getattr(p, "model_id", None),
                    "last_latency_ms": getattr(p, "last_latency_ms", None),
                }
                for p in diag.providers
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("runtime diagnostics failed: %s", exc)
        return {
            "mode": "local_mock",
            "providers": [],
            "error": "diagnostics unavailable",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


__all__ = ["router"]
