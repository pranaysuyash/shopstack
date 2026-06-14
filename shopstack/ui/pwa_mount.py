"""PWA static mount — serves ``shopstack/static/`` at root paths.

Gradio 6.x's framework auto-serves a generic default manifest at
``/manifest.json`` and intercepts all ``/static/*`` paths with a
JSON error handler. The user's custom PWA shell (branded manifest,
service worker, icons) must be served at ROOT paths (``/manifest.json``,
``/sw.js``, ``/icon-192.svg``, ``/icon-512.svg``) to win over
Gradio's catch-all.

This module:
  1. Adds individual FastAPI routes for each PWA file at root
     paths. FastAPI's ``add_api_route`` appends to the routes
     list, so order matters: the user's PWA routes are added
     AFTER Gradio's. To make the user's manifest win over
     Gradio's default, we replace the Gradio route entry in
     the routes list directly (a small but contained hack).
  2. Mounts the SW + icons at root paths via ``FileResponse``
     handlers.
  3. Updates the manifest content to reference root paths
     (not ``/static/...``) so the icons resolve.

This is intentionally minimal: a full PWA bootstrap would
configure cache strategies, push notifications, and a richer
service worker. The current scope is "installable on mobile +
custom-branded manifest + functional offline shell."
"""
from __future__ import annotations

import json
import logging
import mimetypes
from pathlib import Path
from typing import Any

import gradio as gr

logger = logging.getLogger(__name__)

# Map of PWA filename → media type (used when serving via FileResponse).
# The manifest is JSON; the SW is JS; the icons are SVG.
_PWA_MEDIA_TYPES = {
    "manifest.json": "application/manifest+json",
    "sw.js": "application/javascript",
    "icon-192.svg": "image/svg+xml",
    "icon-512.svg": "image/svg+xml",
}


def mount_pwa_static(app: gr.Blocks) -> None:
    """Serve PWA files at root paths so they win over Gradio's defaults.

    Why root paths:
        Gradio 6.x's framework intercepts ``/static/*`` paths with a
        JSON 404 handler. But it only auto-serves ONE file at root:
        ``/manifest.json`` (with a generic default). So we serve
        the PWA shell at root paths:

            /manifest.json    — overrides Gradio's default with our branded one
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
    from fastapi.responses import FileResponse
    from starlette.requests import Request

    static_dir = Path(__file__).resolve().parent.parent.parent / "static"
    if not static_dir.is_dir():
        logger.debug("PWA static dir not found at %s; skipping mount", static_dir)
        return

    fastapi_app = app.app

    # 1) Add individual routes at root paths. We use ``add_api_route``
    # which appends to the routes list — so our routes are added
    # AFTER Gradio's. Gradio 6.x installs a catch-all ``/{path:path}``
    # route that matches BEFORE any route appended later, so every
    # PWA route added here (not just the manifest) must be moved to
    # the FRONT of ``fastapi_app.routes`` to actually be reached.
    mounted_paths: set[str] = set()
    for filename, media_type in _PWA_MEDIA_TYPES.items():
        filepath = static_dir / filename
        if not filepath.is_file():
            logger.debug("PWA asset %s not found; skipping", filename)
            continue

        # Create a closure that serves this file. The file content
        # is read at request time so updates to the file are picked
        # up without restarting the app.
        def _make_handler(fp: Path, mt: str):
            def _handler():
                return FileResponse(
                    fp,
                    media_type=mt,
                    headers={"Cache-Control": "no-cache"},
                )
            return _handler

        # Use ``add_api_route`` to get FastAPI's normal route
        # handling (path-parameter expansion, methods filter).
        fastapi_app.add_api_route(
            f"/{filename}",
            _make_handler(filepath, media_type),
            methods=["GET"],
        )
        mounted_paths.add(f"/{filename}")

    # 2) The manifest content is the user's branded version
    # (``static/manifest.json``). It's loaded as JSON so the
    # icon paths inside the manifest reference root paths
    # (we rewrite ``/static/...`` → ``/...`` on load).
    # We also REPLACE the Gradio default ``/manifest.json`` route
    # entry with our own (move our entry to the front so it's
    # matched first).
    manifest_path = static_dir / "manifest.json"
    if manifest_path.is_file():
        # Re-write the manifest in-memory so its icon paths point
        # to the root paths we're serving. The on-disk file is
        # left untouched (it's still canonical for other consumers).
        # We expose a route that returns the rewritten JSON.
        original = json.loads(manifest_path.read_text(encoding="utf-8"))
        rewritten = _rewrite_manifest_to_root_paths(original)

        def _manifest_handler():
            from fastapi.responses import JSONResponse
            return JSONResponse(
                rewritten,
                media_type="application/manifest+json",
                headers={"Cache-Control": "no-cache"},
            )

        # Find and REPLACE Gradio's default manifest route with ours
        # so our branded manifest wins. We do this by inserting our
        # handler at the front of the routes list and removing any
        # existing entry that points to ``/manifest.json`` (we keep
        # the LAST one Gradio installed — i.e. the most recent).
        # FastAPI matches routes in order; the first match wins.
        fastapi_app.add_api_route(
            "/manifest.json",
            _manifest_handler,
            methods=["GET"],
        )
        mounted_paths.add("/manifest.json")
        # If Gradio already registered a default ``/manifest.json`` route,
        # drop its (earlier) entry — keep only ours (the one we just added).
        routes = fastapi_app.routes
        manifest_routes = [r for r in routes if getattr(r, "path", None) == "/manifest.json"]
        if len(manifest_routes) > 1:
            ours = manifest_routes[-1]
            others = [r for r in routes if getattr(r, "path", None) != "/manifest.json"]
            routes.clear()
            routes.append(ours)
            routes.extend(others)

    # 3) Move ALL of our PWA routes to the FRONT of the routes list.
    # Gradio 6.x installs a catch-all ``/{path:path}`` route during
    # app construction; anything appended after it (via add_api_route)
    # is unreachable unless moved ahead of that catch-all. This applies
    # to sw.js and the icons just as much as the manifest.
    if mounted_paths:
        routes = fastapi_app.routes
        ours = [r for r in routes if getattr(r, "path", None) in mounted_paths]
        others = [r for r in routes if getattr(r, "path", None) not in mounted_paths]
        routes.clear()
        routes.extend(ours)
        routes.extend(others)

    logger.info("PWA shell mounted: %s (%d routes)", static_dir, len(mounted_paths))


def _rewrite_manifest_to_root_paths(manifest: dict[str, Any]) -> dict[str, Any]:
    """Rewrite manifest icon + shortcut paths to root paths.

    The on-disk manifest references ``/static/icon-192.svg`` etc.
    Since Gradio's framework blocks ``/static/*`` with a JSON 404,
    we rewrite those paths to root paths (``/icon-192.svg``) which
    ARE served by our FileResponse routes.
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
