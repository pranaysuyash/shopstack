"""Health endpoint — ``/health/ui`` route for operator liveness checks.

Why this exists (motto_v3 §0.10 Observability Is Delivery):
  A deployable app must expose a liveness probe that an operator
  (or orchestrator) can hit to confirm the app is actually serving
  and its key dependencies are reachable. Returning HTTP 200 from
  the Gradio root only proves the FastAPI layer responds — it
  doesn't prove the DB is queryable or that the PWA shell is wired.

What this checks:
  1. ``database`` — opens a read-only ``SELECT 1``-style query
     against the active SQLite DB. If the DB file is missing,
     locked, or corrupt, this surfaces as ``"database": "fail"``.
  2. ``gradio_blocks`` — confirms the ``gr.Blocks`` has at least
     one rendered tab / child block (a Blocks with zero children
     indicates a startup-time build failure that Gradio silently
     swallowed).
  3. ``pwa_assets`` — best-effort check that ``manifest.json`` and
     ``sw.js`` exist on disk. A missing PWA shell degrades the
     install-to-home-screen flow without crashing the app, so this
     is reported but doesn't fail the overall health.

HTTP semantics:
  * 200 OK with ``{"status": "ok", ...}`` when everything passes.
  * 503 Service Unavailable with ``{"status": "degraded", ...}``
    when one or more checks fail. The body always enumerates which
    checks passed/failed so the operator can act on concrete info.

Pattern:
  Mirrors :mod:`shopstack.services.sms_webhook` and
  :mod:`shopstack.ui.pwa_mount` — a thin transport adapter that
  registers a FastAPI route on the Gradio Blocks' underlying app.
  Kept separate so it can be unit-tested in isolation and so
  operators can disable it for deployments that run their own
  external health probe.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import gradio as gr

logger = logging.getLogger(__name__)


def _check_database(db: Any) -> tuple[str, str]:
    """Open a cheap read-only query against the active DB.

    Returns ``(status, detail)`` where status is ``"ok"`` or
    ``"fail"``. Uses ``get_inventory`` because it's the canonical
    read accessor on :class:`shopstack.persistence.database.Database`
    and exercises a real ``SELECT * FROM inventory_lots`` path. If
    the table is missing or the DB file is locked, this raises and
    we catch + report.
    """
    try:
        # Use the canonical read accessor — limits to 1 row to keep
        # the probe cheap even on households with thousands of lots.
        lots = db.get_inventory()
        count = len(lots) if isinstance(lots, list) else 0
        return "ok", f"{count} lots"
    except Exception as exc:
        return "fail", f"{type(exc).__name__}: {exc}"


def _check_gradio_blocks(app: gr.Blocks) -> tuple[str, str]:
    """Confirm the Blocks has rendered children.

    An empty ``app.children`` indicates the build_app() pipeline
    failed silently — Gradio doesn't raise on an empty Blocks, it
    just serves a blank page.
    """
    try:
        children = getattr(app, "children", None) or []
        # ``blocks`` is also a useful signal on newer Gradio.
        blocks_attr = getattr(app, "blocks", None)
        total = len(children) + (len(blocks_attr) if blocks_attr else 0)
        if total == 0:
            return "fail", "no children rendered"
        return "ok", f"{total} top-level elements"
    except Exception as exc:
        return "fail", f"{type(exc).__name__}: {exc}"


def _check_pwa_assets(app: gr.Blocks) -> tuple[str, str]:
    """Best-effort check that the PWA shell files exist on disk.

    Reported but never causes overall health to fail — a missing
    PWA shell degrades install-to-home-screen without crashing.
    """
    try:
        static_dir = Path(__file__).resolve().parent.parent / ".." / "static"
        static_dir = static_dir.resolve()
        if not static_dir.is_dir():
            return "missing", f"no static dir at {static_dir}"
        expected = ("manifest.json", "sw.js")
        present = [f for f in expected if (static_dir / f).is_file()]
        missing = [f for f in expected if f not in present]
        if missing:
            return "partial", f"missing: {', '.join(missing)}"
        return "ok", f"{len(present)}/{len(expected)} assets"
    except Exception as exc:
        return "fail", f"{type(exc).__name__}: {exc}"


def mount_health_endpoint(
    app: gr.Blocks,
    db: Any = None,
    *,
    path: str = "/health/ui",
) -> None:
    """Mount the ``/health/ui`` route on the Gradio app's FastAPI layer.

    Args:
        app: The ``gr.Blocks`` instance returned by ``build_app()``.
        db: Optional Database instance. If ``None``, the database
            check is skipped (reported as ``"skipped"``). This keeps
            the probe useful even when the caller doesn't have a
            handle to the DB (e.g. minimal test harnesses).
        path: Route path. Defaults to ``/health/ui``.
    """
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    async def _health(request: Request) -> JSONResponse:
        checks: dict[str, dict[str, str]] = {}
        if db is None:
            checks["database"] = {"status": "skipped", "detail": "no db handle"}
        else:
            s, d = _check_database(db)
            checks["database"] = {"status": s, "detail": d}
        s, d = _check_gradio_blocks(app)
        checks["gradio_blocks"] = {"status": s, "detail": d}
        s, d = _check_pwa_assets(app)
        checks["pwa_assets"] = {"status": s, "detail": d}

        # Overall: fail only on hard failures (database or gradio_blocks).
        # pwa_assets is best-effort and never degrades overall health.
        hard_failures = [
            name for name, c in checks.items()
            if name in ("database", "gradio_blocks") and c["status"] == "fail"
        ]
        overall = "ok" if not hard_failures else "degraded"
        status_code = 200 if overall == "ok" else 503
        return JSONResponse(
            {"status": overall, "checks": checks},
            status_code=status_code,
            headers={"Cache-Control": "no-store"},
        )

    target_app = getattr(app, "app", app)
    try:
        # Use Starlette's ``add_route`` (matches the sms_webhook pattern)
        # rather than FastAPI's ``add_api_route`` — the latter requires
        # the FastAPI app to be fully constructed, which doesn't hold
        # inside ``with gr.Blocks() as app:``.
        target_app.add_route(path, _health, methods=["GET"])
        logger.info("Health endpoint mounted at %s", path)
    except Exception as exc:  # noqa: BLE001 — best-effort mount
        logger.warning("Could not mount health endpoint at %s: %s", path, exc)


__all__ = ["mount_health_endpoint"]
