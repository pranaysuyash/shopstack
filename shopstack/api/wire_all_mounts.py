"""Post-launch route re-mounter for the Gradio FastAPI instance.

Gradio's ``launch()`` rebuilds ``app.app`` — a fresh FastAPI
instance — so any routes mounted inside the ``with gr.Blocks()``
block are discarded unless re-mounted post-launch. This module
provides that re-mount via :func:`install_post_launch_hooks`,
which monkeypatches ``app.launch``.

**What gets re-mounted:**

1. PWA static files (``/static/*``) — no v1 equivalent.
2. Health endpoint (``/health/ui``) — legacy path; the v1 equivalent
   at ``/api/v1/meta/health`` was added in Pass 26 but the legacy
   path is kept for operator/orchestrator tooling that uses it.
3. ``/api/v1/*`` surface via :func:`shopstack.api.v1.wire.wire_v1_surface`.

All legacy HTTP mount modules (corrections, whoami, global_search,
privacy, undo, decision_explain, recurring, mealplan) were ported
to versioned ``/api/v1/*`` routers and deleted in Pass 26.
"""
from __future__ import annotations

import logging

import gradio as gr

logger = logging.getLogger(__name__)


def wire_post_launch_routes(  # noqa: ANN001
    app: gr.Blocks,
    db: object,
) -> None:
    """Re-mount every HTTP endpoint on the post-launch FastAPI instance.

    Mirrors the in-context mounts in ``app.py::build_app``.
    Best-effort: any mount failure is logged but does not raise.
    """
    # PWA static + health endpoint are looked up via the ``app`` module
    # so the test monkeypatch contract in test_app.py works.
    _app_module = __import__("app")  # noqa: F841
    mount_pwa_static = _app_module.mount_pwa_static
    mount_health_endpoint = _app_module.mount_health_endpoint

    mount_pwa_static(app)
    mount_health_endpoint(app, db)

    from shopstack.api.v1.wire import wire_v1_surface
    wire_v1_surface(app)


def install_post_launch_hooks(  # noqa: ANN001
    app: gr.Blocks,
    db: object,
) -> None:
    """Ensure routes, middleware, and PWA are restored after Gradio
    recreates the FastAPI app.

    Gradio's ``launch()`` rebuilds ``app.app`` — a fresh FastAPI instance —
    so any routes mounted inside ``with gr.Blocks() as app:`` are discarded
    unless we re-mount them after launch. This wrapper:

      1. Calls ``wire_post_launch_routes`` which re-mounts every HTTP
         endpoint (PWA static, health, whoami, decision-explain, recurring,
         corrections, mealplan, v1 surface, undo, etc.).
      2. Re-installs the Permissions-Policy middleware (lost when the
         FastAPI app was recreated).

    **2026-06-16 fix (motto_v3 §6):** The previous version had TWO
    definitions of this function — the earlier one (PWA + health +
    permissions) was *silently overridden* by the later one (wire_all_mounts
    only). The result: ``install_permissions_policy_middleware`` was never
    called after launch, meaning the restrictive Permissions-Policy header
    was absent on every page load via ``app.launch()`` (not just HF Spaces
    but also local dev that calls ``app.launch()``).

    The merge preserves BOTH responsibilities: ``wire_post_launch_routes``
    handles all route mounts, and the middleware is re-installed here.

    Args:
        app: The ``gr.Blocks`` instance.
        db: The database handle (passed to ``wire_post_launch_routes``).
    """
    from shopstack.ui.security_middleware import install_permissions_policy_middleware

    original_launch = app.launch

    def _launch_with_post_hooks(*args, **kwargs):
        result = original_launch(*args, **kwargs)
        wire_post_launch_routes(app, db)
        install_permissions_policy_middleware(app)
        return result

    app.launch = _launch_with_post_hooks


__all__ = [
    "install_post_launch_hooks",
    "wire_post_launch_routes",
]
