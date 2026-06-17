"""Sub-builder that mounts every HTTP endpoint on the in-context
Gradio ``Blocks`` instance.

All legacy HTTP endpoints have been ported to versioned
``/api/v1/*`` routers. The v1 surface is mounted via
:func:`wire_v1_surface` below.

For the full list of v1 routers see :mod:`shopstack.api.v1.routers`.
The SMS webhook (``/api/v1/sms/incoming``) is now part of the v1
surface, completing the legacy mount migration started in Pass 26.
"""
from __future__ import annotations

import logging

import gradio as gr

logger = logging.getLogger(__name__)


def wire_in_context_routes(app: gr.Blocks, db: object) -> None:  # noqa: ANN001
    """Mount every HTTP endpoint on the in-context Gradio Blocks.

    Called from inside ``with gr.Blocks() as app:`` in
    ``app.py::build_app``.

    All legacy HTTP mounts have been ported to versioned
    ``/api/v1/*`` routers (Pass 26–27). The v1 surface is
    mounted via :func:`wire_v1_surface`, which delegates to
    :func:`shopstack.api.v1.mount_v1_routes`.
    """
    from shopstack.api.v1.wire import wire_v1_surface
    wire_v1_surface(app)


__all__ = ["wire_in_context_routes"]
