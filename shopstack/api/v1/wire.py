"""Sub-builder that wires the ``/api/v1/*`` surface into ``app.py``.

Extracted from ``app.py`` (Pass 25, 2026-06-16) to keep the
composition root under the 300-line cap asserted by
``test_app_composition.py::test_app_py_under_300_lines``.

The function does exactly one thing: call
:func:`shopstack.api.v1.mount_v1_routes`. The docstring is
load-bearing — it explains why the mount happens inside the
``with gr.Blocks()`` context AND inside the post-launch hook.
"""
from __future__ import annotations

import logging

import gradio as gr

logger = logging.getLogger(__name__)


def wire_v1_surface(app: gr.Blocks) -> None:  # noqa: ANN001
    """Mount the ``/api/v1/*`` routers on the Gradio app's FastAPI layer.

    Called from two places in ``app.py`` (matches every other
    mount's pattern):
    1. Inside ``with gr.Blocks() as app:`` — the in-context
       FastAPI instance.
    2. From ``_install_post_launch_hooks`` — the post-launch
       FastAPI instance (Gradio rebuilds ``app.app`` on launch).

    The mount is idempotent: a second call on the same FastAPI
    app logs "router already mounted" and is a no-op. A second
    call on a *different* FastAPI app (post-launch) re-mounts
    cleanly. The old ``/api/whoami`` and ``/health/ui`` paths
    are preserved as Sunset-tagged aliases (RFC 8594).
    """
    from shopstack.api.v1 import mount_v1_routes

    mount_v1_routes(app)


__all__ = ["wire_v1_surface"]
