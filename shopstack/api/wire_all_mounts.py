"""Sub-builder that re-mounts every HTTP endpoint on the
post-launch FastAPI instance.

Extracted from ``app.py:_install_post_launch_hooks`` (Pass 25,
2026-06-16) to keep the composition root under the 300-line
cap asserted by ``test_app_composition.py``.

**Why every mount is in one place:**

Gradio's ``launch()`` rebuilds ``app.app`` — a fresh FastAPI
instance — so any route added inside ``with gr.Blocks() as app:``
is discarded unless we re-mount it on the post-launch instance.
The pre-existing pattern (9 mounts + the v1 surface) re-mounts
them in ``_install_post_launch_hooks``. This sub-builder is
the single source of truth for "what gets re-mounted after
launch," so future mount additions only touch one file.

**Why this is safe to extract:**

Every function call here is a thin transport adapter that
just calls ``app.app.add_route(...)``. There is no business
logic, no Gradio component construction, no async magic. The
extraction is mechanical; the behavior is byte-identical.
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
    # Lazy imports to avoid a hard dep on every mount module at
    # app import time. Each mount is independent; one failure
    # cannot block the others.
    from shopstack.services.corrections_mount import mount_corrections_endpoint
    from shopstack.services.decision_explain_mount import (
        mount_decision_explain_endpoint,
        mount_mealplan_endpoint,
        mount_recurring_endpoint,
    )
    from shopstack.services.undo_mount import mount_undo_endpoint
    from shopstack.services.whoami_mount import mount_whoami_endpoint
    from shopstack.services.privacy_mount import mount_privacy_endpoints
    from shopstack.services.global_search_mount import mount_global_search

    # ``mount_pwa_static`` and ``mount_health_endpoint`` are
    # looked up via the ``app`` module (rather than imported
    # directly) so the test monkeypatch contract in test_app.py
    # works. The test patches ``app.mount_pwa_static`` and
    # ``app.mount_health_endpoint``; by reading them off the
    # module here, the patch propagates.
    _app_module = __import__("app")  # noqa: F841
    mount_pwa_static = _app_module.mount_pwa_static
    mount_health_endpoint = _app_module.mount_health_endpoint

    mount_pwa_static(app)
    mount_health_endpoint(app, db)
    mount_whoami_endpoint(app)
    mount_undo_endpoint(app)
    mount_privacy_endpoints(app)
    mount_global_search(app)
    mount_decision_explain_endpoint(app)
    mount_recurring_endpoint(app)
    mount_corrections_endpoint(app)
    mount_mealplan_endpoint(app)

    # 2026-06-16 (Pass 25 — v1 API surface): re-mount the
    # /api/v1/* routers + their Sunset aliases. Idempotent.
    from shopstack.api.v1.wire import wire_v1_surface
    wire_v1_surface(app)


__all__ = ["wire_post_launch_routes"]
