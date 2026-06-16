"""Sub-builder that mounts every HTTP endpoint on the in-context
Gradio ``Blocks`` instance.

Extracted from ``app.py::build_app`` (Pass 25, 2026-06-16) to keep
the composition root under the 300-line cap asserted by
``test_app_composition.py::test_app_py_under_300_lines``.

**Pattern (same as :mod:`shopstack.api.wire_all_mounts`):**

The in-context mounts are the routes that need to be reachable
during ``with gr.Blocks() as app:`` *and* on the post-launch
FastAPI instance. They are re-mounted by
:func:`wire_post_launch_routes` after Gradio's launch.

The split exists because the in-context mount has comments
explaining the per-route rationale (e.g. which Pass added
which endpoint), while the post-launch re-mount is mechanical.
This module keeps the in-context rationale where it is
discoverable; the post-launch module is the no-comment
mechanical side.
"""
from __future__ import annotations

import logging

import gradio as gr

logger = logging.getLogger(__name__)


def wire_in_context_routes(app: gr.Blocks, db: object) -> None:  # noqa: ANN001
    """Mount every HTTP endpoint on the in-context Gradio Blocks.

    Called from inside ``with gr.Blocks() as app:`` in
    ``app.py::build_app``. Each mount is independent; one
    failure cannot block the others (best-effort pattern from
    every existing ``mount_*`` function).
    """
    # Lazy imports to avoid a hard dep on every mount module at
    # import time. Each mount is independent.
    from shopstack.services.corrections_mount import mount_corrections_endpoint
    from shopstack.services.decision_explain_mount import (
        mount_decision_explain_endpoint,
        mount_mealplan_endpoint,
        mount_recurring_endpoint,
    )
    from shopstack.services.global_search_mount import mount_global_search
    from shopstack.services.privacy_mount import mount_privacy_endpoints
    from shopstack.services.sms_webhook import mount_sms_webhook
    from shopstack.services.undo_mount import mount_undo_endpoint
    from shopstack.services.whoami_mount import mount_whoami_endpoint

    # ``mount_pwa_static`` and ``mount_health_endpoint`` are NOT
    # mounted in the in-context block. The original test contract
    # in test_app.py expects 1 PWA call after build_app() and 1
    # more after launch() — that comes from the post-context
    # block in app.py (the "must be mounted AFTER the
    # ``with gr.Blocks()`` block exits" call) and the
    # post-launch hook. Mounting PWA here would double-count.
    # We import them only to keep the test monkeypatch contract
    # alive (the test patches ``app.mount_pwa_static``; if we
    # don't reference it here, Python may optimize the import
    # away in some interpreters). Lazy no-op reference:
    _app_module = __import__("app")  # noqa: F841
    _ = _app_module.mount_pwa_static
    _ = _app_module.mount_health_endpoint

    # /api/sms/incoming — Twilio webhook (POST). Pre-existing.
    mount_sms_webhook(app)
    # /api/global-search — pre-existing.
    mount_global_search(app)
    # /api/privacy/... — pre-existing.
    mount_privacy_endpoints(app)
    # /api/undo — pre-existing.
    mount_undo_endpoint(app)
    # /api/whoami — pre-existing read-only introspection.
    mount_whoami_endpoint(app)
    # /api/decision/<name>/explain (Pass 18) — decision explainability.
    mount_decision_explain_endpoint(app)
    # /api/recurring (Pass 19) — items due in the user's shopping rhythm.
    mount_recurring_endpoint(app)
    # /api/corrections (Pass 20) — user corrections learning loop.
    mount_corrections_endpoint(app)
    # /api/mealplan (Pass 21) — weekly meal plan.
    mount_mealplan_endpoint(app)
    # 2026-06-16 (Pass 25 — v1 API surface): /api/v1/* routers.
    # See shopstack/api/v1/wire.py for the rationale.
    from shopstack.api.v1.wire import wire_v1_surface
    wire_v1_surface(app)


__all__ = ["wire_in_context_routes"]
