"""ShopStack API v1 package.

This package is the **versioned, mobile- and external-client-facing**
HTTP surface. It lives next to the Gradio UI rather than replacing it;
the Gradio submission is preserved (motto_v3 §0.1 missed-anything, §6
pre-existing is not an excuse).

**Why this exists (decision doc: ``Docs/archive/api_v1_and_mobile_repo_architecture_2026-06-16.md``):**

1. The Gradio app is already a FastAPI app (``gr.Blocks.app.app`` is a
   Starlette/FastAPI instance — see ``app.py:32-40``). 11 HTTP mounts
   are already wired (``shopstack/services/*_mount.py``,
   ``shopstack/ui/pwa_mount.py``), but they are version-untyped, share
   no OpenAPI schema, and have no consistent request/response shape.

2. The mobile repo (``shopstack-mobile/``) consumes **only** this
   surface. No code sharing. The OpenAPI schema generated here is
   checked into both repos; contract tests in both repos assert
   equality.

3. Auth (§3.2 multi-user auth) is load-bearing for the API and the
   mobile app. It is the first thing this package ships.

**Pattern (per motto_v3 §0.15 three-layer rule):**

* HTTP boundary only — no business logic in this package.
* Service-layer functions in ``shopstack/services/`` are the
  source of truth for behavior. Endpoints parse, call services,
  serialize responses.
* Existing ``mount_*`` functions are not removed; they are
  re-mounted under ``/api/v1/*`` and the old paths become
  ``Sunset``-tagged aliases (RFC 8594).

**Public surface:**

  * ``shopstack.api.v1.schemas`` — Pydantic v2 request/response models
  * ``shopstack.api.v1.auth`` — token storage, dependency-injected resolver
  * ``shopstack.api.v1.routers`` — ``APIRouter`` per resource group
  * ``shopstack.api.v1.mount`` — single entry point called by ``app.py``
  * ``shopstack.api.v1.deps`` — FastAPI ``Depends()`` helpers
  * ``shopstack.api.v1.openapi`` — OpenAPI 3.0 schema generation
"""
from __future__ import annotations

__all__ = [
    "mount_v1_routes",
    "openapi_schema",
    "openapi_schema_json",
]


def mount_v1_routes(gradio_app) -> None:  # noqa: ANN001 — gradio.Blocks
    """Mount the ``/api/v1/*`` routers on the Gradio app's FastAPI layer.

    Idempotent: safe to call from inside ``with gr.Blocks() as app:``
    and again from the post-launch hook (Gradio recreates ``app.app``
    on launch, so the mount has to happen twice — see
    ``app.py:_install_post_launch_hooks``).

    Args:
        gradio_app: the ``gr.Blocks`` instance returned by
            ``build_app()``. Used only to access ``gradio_app.app``,
            the underlying FastAPI/Starlette instance.

    Best-effort: any mount failure is logged but does not raise.
    The Gradio UI is the primary surface; the API is a strict
    superset for external clients.
    """
    # Lazy import to avoid a hard dep on FastAPI at module import time
    # (FastAPI is installed via Gradio, but tests and CLI tools may
    # import shopstack without it).
    from .mount import mount_v1_routes as _mount

    _mount(gradio_app)


def openapi_schema() -> dict:
    # docstring redacted — the real one lives in .openapi
    from .openapi import openapi_schema as _os  # type: ignore[import-untyped]  # noqa: F811
    return _os()


def openapi_schema_json() -> str:
    from .openapi import openapi_schema_json as _osj  # type: ignore[import-untyped]  # noqa: F811
    return _osj()
