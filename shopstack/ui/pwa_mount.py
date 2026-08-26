"""PWA static mount for the native web app.

The user's custom PWA shell (branded manifest, service worker, icons)
is served at root paths (``/manifest.json``, ``/sw.js``,
``/icon-192.svg``, ``/icon-512.svg``), independent of a UI framework.

The middleware intercepts PWA requests before FastAPI route matching;
explicit routes remain as a direct fallback.

The PWA manifest's icon paths reference root paths (not ``/static/...``)
so the icons resolve. The service worker is registered at ``/sw.js``
in ``shopstack/ui/header.py:_pwa_block``.

This is intentionally minimal: a full PWA bootstrap would
configure cache strategies, push notifications, and a richer
service worker. The current scope is "installable on mobile +
custom-branded manifest + functional offline shell."
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Map of PWA filename → media type (used when serving via FileResponse).
# The manifest is JSON; the SW is JS; the icons are SVG.
_PWA_MEDIA_TYPES = {
    "manifest.json": "application/manifest+json",
    "sw.js": "application/javascript",
    "icon-192.svg": "image/svg+xml",
    "icon-512.svg": "image/svg+xml",
}

# Pre-load the manifest content at module level so the middleware
# doesn't need to do I/O on every request. The manifest is small
# and rarely changes; restart the app to pick up changes.
_MANIFEST_CACHE: dict[str, Any] | None = None
_MANIFEST_PATH: Path | None = None


def _get_manifest(static_dir: Path) -> dict[str, Any] | None:
    """Load the user's branded manifest (with /static → / rewrite).

    Cached at module level. Returns ``None`` if the manifest doesn't
    exist on disk.
    """
    global _MANIFEST_CACHE, _MANIFEST_PATH
    manifest_path = static_dir / "manifest.json"
    if not manifest_path.is_file():
        return None
    if _MANIFEST_PATH == manifest_path and _MANIFEST_CACHE is not None:
        return _MANIFEST_CACHE
    try:
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        _MANIFEST_CACHE = _rewrite_manifest_to_root_paths(original)
        _MANIFEST_PATH = manifest_path
        return _MANIFEST_CACHE
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("Failed to load PWA manifest: %s", exc)
        return None


def _is_pwa_path(path: str) -> bool:
    """Return True if the request path is one of our PWA files."""
    # Strip query string if present
    clean = path.split("?", 1)[0].split("#", 1)[0]
    return clean.lstrip("/") in _PWA_MEDIA_TYPES


def mount_pwa_static(app: Any) -> None:
    """Serve PWA files at root paths on the native web app.

    Why root paths:
        The PWA shell is served at root paths:

            /manifest.json    — branded application manifest
            /sw.js            — service worker
            /icon-192.svg     — PWA icon (192x192)
            /icon-512.svg     — PWA icon (512x512, maskable)

        The PWA manifest's icon paths reference these root paths.
        The service worker is registered at ``/sw.js`` in
        ``shopstack/ui/header.py:_pwa_block``.

    Best-effort:
        Missing files are silently skipped. The app still works as
        a regular web app. The PWA install prompt is gated by the
        presence of a valid manifest + service worker, so a
        partial shell just means "no install prompt" — no crash.
    """
    static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    if not static_dir.is_dir():
        logger.debug("PWA static dir not found at %s; skipping mount", static_dir)
        return

    fastapi_app = app

    # ─── Layer 1: Middleware (preferred) ─────────────────────────
    # Add a BaseHTTPMiddleware that intercepts PWA paths before any
    # route matching. This is the strongest layer because middleware
    # runs in the request stack BEFORE FastAPI's router.
    try:
        from fastapi.responses import FileResponse, JSONResponse
        from starlette.middleware.base import BaseHTTPMiddleware

        class _PwaStaticMiddleware(BaseHTTPMiddleware):
            """Serve PWA files before application route matching.

            """

            async def dispatch(self, request, call_next):
                path = request.url.path
                if not _is_pwa_path(path):
                    return await call_next(request)
                filename = path.lstrip("/")
                # Manifest: serve the rewritten JSON
                if filename == "manifest.json":
                    manifest = _get_manifest(static_dir)
                    if manifest is None:
                        return await call_next(request)
                    return JSONResponse(
                        manifest,
                        media_type="application/manifest+json",
                        headers={"Cache-Control": "no-cache"},
                    )
                # Other PWA files: serve from disk
                filepath = static_dir / filename
                if not filepath.is_file():
                    return await call_next(request)
                media_type = _PWA_MEDIA_TYPES.get(filename)
                return FileResponse(
                    filepath,
                    media_type=media_type,
                    headers={"Cache-Control": "no-cache"},
                )

        # Insert the middleware. add_middleware puts it on top of
        # the stack, so it's the OUTERMOST middleware (runs first
        # for incoming requests, last for outgoing responses).
        # This is exactly what we want.
        fastapi_app.add_middleware(_PwaStaticMiddleware)
        logger.info(
            "PWA shell mounted via middleware: %s (%d files)",
            static_dir,
            len(_PWA_MEDIA_TYPES),
        )
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(
            "Failed to install PWA middleware (falling back to routes): %s",
            exc,
        )

    # ─── Layer 2: add_api_route (fallback) ──────────────────────
    # Also add the routes (in case the middleware is bypassed in
    # some edge case). The middleware will short-circuit before
    # these are reached in the normal case, but they exist as a
    # safety net.
    mounted_paths: set[str] = set()
    for filename, media_type in _PWA_MEDIA_TYPES.items():
        filepath = static_dir / filename
        if not filepath.is_file():
            logger.debug("PWA asset %s not found; skipping", filename)
            continue

        def _make_handler(fp: Path, mt: str):
            def _handler():
                from fastapi.responses import FileResponse
                return FileResponse(
                    fp,
                    media_type=mt,
                    headers={"Cache-Control": "no-cache"},
                )
            return _handler

        fastapi_app.add_api_route(
            f"/{filename}",
            _make_handler(filepath, media_type),
            methods=["GET"],
        )
        mounted_paths.add(f"/{filename}")

    # Reorder routes so explicit PWA handlers stay ahead of broad routes.
    if mounted_paths:
        routes = fastapi_app.routes
        ours = [r for r in routes if getattr(r, "path", None) in mounted_paths]
        others = [r for r in routes if getattr(r, "path", None) not in mounted_paths]
        routes.clear()
        routes.extend(ours)
        routes.extend(others)


def _rewrite_manifest_to_root_paths(manifest: dict[str, Any]) -> dict[str, Any]:
    """Rewrite manifest icon + shortcut paths to root paths.

    The on-disk manifest may reference ``/static/icon-192.svg``.
    Rewrite those paths to root paths (``/icon-192.svg``), which are
    served by the explicit PWA handlers above.
    """
    out = dict(manifest)
    if "icons" in out:
        out["icons"] = [
            {**icon, "src": icon.get("src", "").replace("/static/", "/")}
            for icon in out["icons"]
        ]
    if "shortcuts" in out:
        out["shortcuts"] = [
            {**sc, "url": sc.get("url", "").replace("/static/", "/")}
            for sc in out["shortcuts"]
        ]
    return out
