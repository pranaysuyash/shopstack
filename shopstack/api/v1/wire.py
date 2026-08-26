"""Sub-builder that wires the ``/api/v1/*`` surface into FastAPI.

Extracted from ``app.py`` (Pass 25, 2026-06-16) to keep the
composition root under the 300-line cap asserted by
``test_app_composition.py::test_app_py_under_300_lines``.

The function does exactly one thing: call
:func:`shopstack.api.v1.mount_v1_routes`. The docstring is
load-bearing — it keeps the transport composition in one native boundary.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI

logger = logging.getLogger(__name__)


def wire_v1_surface(app: FastAPI) -> None:
    """Mount the ``/api/v1/*`` routers on a FastAPI app.

    Called from a composition root when the API surface needs to be
    mounted independently of the full application builder.

    The mount is idempotent: a second call on the same FastAPI
    app logs "router already mounted" and is a no-op. A second
    call on a *different* FastAPI app (post-launch) re-mounts
    cleanly. The old ``/api/whoami`` and ``/health/ui`` paths
    are preserved as Sunset-tagged aliases (RFC 8594).
    """
    from shopstack.api.v1 import mount_v1_routes

    mount_v1_routes(app)


__all__ = ["wire_v1_surface"]
