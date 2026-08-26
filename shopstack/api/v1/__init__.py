"""ShopStack API v1 package.

This package is the **versioned, mobile- and web-client-facing** HTTP
surface. It is the canonical transport contract for both supported UI
clients.

**Why this exists (decision doc: ``Docs/archive/api_v1_and_mobile_repo_architecture_2026-06-16.md``):**

1. The native FastAPI web app owns the transport boundary. The HTTP
   mounts share one OpenAPI schema and consistent request/response shapes.

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


def mount_v1_routes(fastapi_app) -> None:  # noqa: ANN001
    """Mount the canonical ``/api/v1/*`` routers on FastAPI."""
    # Lazy import keeps lightweight service and CLI imports independent
    # of the HTTP layer while the app entrypoint owns FastAPI directly.
    from .mount import mount_v1_routes as _mount

    _mount(fastapi_app)


def openapi_schema() -> dict:
    # docstring redacted — the real one lives in .openapi
    from .openapi import openapi_schema as _os  # type: ignore[import-untyped]  # noqa: F811
    return _os()


def openapi_schema_json() -> str:
    from .openapi import openapi_schema_json as _osj  # type: ignore[import-untyped]  # noqa: F811
    return _osj()
