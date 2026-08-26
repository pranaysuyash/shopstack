"""OpenAPI schema generation for the ``/api/v1/*`` surface.

Generates the full OpenAPI 3.0 JSON schema by building a standalone
FastAPI app with all v1 routers mounted. The generated schema is the
source of truth for the mobile client's API contract — it is checked
into both the ShopStack and ``shopstack-mobile/`` repos, and contract
tests in both repos assert equality.

Usage::

    # Print the full schema as JSON
    python -c "from shopstack.api.v1.openapi import openapi_schema_json;\\
               print(openapi_schema_json())"

    # Use programmatically
    from shopstack.api.v1.openapi import openapi_schema
    schema = openapi_schema()  # {"openapi": "3.0.2", "info": ..., "paths": ..., ...}

**Why a standalone schema builder:**

The schema is generated from the native FastAPI contract and does not
depend on application startup state or a UI framework lifecycle.
The standalone app in this module exists *only* for schema generation —
it has no DB, no middleware, no dependencies. FastAPI's ``get_openapi()``
reads route declarations only (it never evaluates dependencies), so the
standalone app produces the exact same schema as the real app would.

**Idempotent per call:** each call to ``openapi_schema()`` or
``openapi_schema_json()`` builds a fresh FastAPI app and generates
the schema from it.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI


# Paths under these prefixes are intentionally public or use a
# non-bearer auth scheme. They should not inherit the BearerAuth
# requirement that applies to the household-scoped endpoints.
PUBLIC_PATH_PREFIXES = (
    "/api/v1/meta",
    "/api/v1/auth",
    "/api/v1/sms",
)

PUBLIC_PATHS = {
    "/api/v1/command/preview",
}

BEARER_SECURITY_REQUIREMENT = [{"BearerAuth": []}]


def _build_openapi_app() -> FastAPI:
    """Build a standalone FastAPI app with all v1 routers mounted.

    This app exists **only** for OpenAPI schema generation. No DB,
    no middleware or UI framework, just the route declarations so FastAPI
    can derive the OpenAPI spec. Dependencies such as
    ``require_household`` are never evaluated by ``get_openapi()``.
    """
    app = FastAPI(
        title="ShopStack API v1",
        version="1.0.0",
        description=(
            "Versioned HTTP surface for the ShopStack mobile app. "
            "This is the canonical API contract between the mobile "
            "client and the backend."
        ),
        contact={
            "name": "ShopStack",
            "url": "https://github.com/shopstack",
        },
        license_info={
            "name": "MIT",
        },
    )

    # Lazy import all routers. Import errors here indicate a broken
    # router declared but not importable — fail fast.
    from .routers import (
        account_router,
        auth_router,
        command_router,
        corrections_router,
        dashboard_router,
        household_router,
        intelligence_router,
        inventory_router,
        meta_router,
        search_router,
        traces_router,
        shopping_router,
        sms_router,
    )

    # Mount each router under /api/v1. The routers each declare their
    # own sub-prefix (/meta, /auth, …), so the final paths are
    # /api/v1/meta/..., /api/v1/auth/..., etc.
    for router in (
        account_router,
        auth_router,
        command_router,
        corrections_router,
        dashboard_router,
        household_router,
        intelligence_router,
        inventory_router,
        meta_router,
        search_router,
        traces_router,
        shopping_router,
        sms_router,
    ):
        app.include_router(router, prefix="/api/v1")

    return app


def openapi_schema() -> dict[str, Any]:
    """Generate the full OpenAPI 3.0 JSON schema for the v1 surface.

    Returns a dict suitable for ``json.dumps()`` or direct inspection.

    The schema includes:

    * **Paths:** every declared endpoint under /api/v1, grouped by
      tag (meta, auth, inventory, household, shopping, dashboard,
      search, intelligence, account, corrections, sms).
    * **Methods:** GET, POST, etc., with parameters, request bodies,
      and response schemas for every status code.
    * **Components.schemas:** all Pydantic models from the schemas
      package, resolved as ``$ref`` targets.
    * **Security:** Bearer-token scheme applied to protected paths.
    * **Tags:** one tag per resource group.

    **Note on security schemes:** The routers use ``Depends(require_household)``
    for household-scoped auth, not ``Security()``. FastAPI only
    auto-generates OpenAPI security info from ``Security()``
    dependencies, so the Bearer scheme is injected post-generation
    into ``components/securitySchemes`` and then attached explicitly
    to every protected path. Public paths such as ``/api/v1/meta/*``,
    ``/api/v1/auth/*``, and ``/api/v1/sms/*`` remain unauthenticated in
    the generated contract.
    """
    app = _build_openapi_app()
    schema = app.openapi()

    # Inject Bearer token security scheme post-generation.
    # The routers use Depends(), not Security(), so FastAPI won't
    # auto-generate the security scheme or apply it to paths.
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "opaque",
        "description": (
            "Device-scoped bearer token. Acquired via POST /api/v1/auth/login "
            "or /api/v1/auth/register. "
            "Pass either as an ``Authorization: Bearer <token>`` header "
            "or as a ``?token=<token>`` query parameter. "
            "The query-string form is the compatibility escape hatch for "
            "clients that cannot set custom HTTP headers on fetch() calls."
        ),
    }
    _apply_security_requirements(schema)

    return schema


def openapi_schema_json() -> str:
    """Return the OpenAPI schema as a pretty-printed JSON string.

    Example::

        python -c "from shopstack.api.v1.openapi import openapi_schema_json;\\
                   print(openapi_schema_json())" > api_v1_openapi.json
    """
    return json.dumps(openapi_schema(), indent=2, default=str, ensure_ascii=False)


def _all_paths() -> set[str]:
    """Return the set of declared path templates (e.g. ``/api/v1/meta/whoami``)."""
    schema = openapi_schema()
    return set(schema.get("paths", {}).keys())


def _apply_security_requirements(schema: dict[str, Any]) -> None:
    """Attach Bearer auth to protected paths only.

    Public routes stay fully unauthenticated so the generated
    contract matches the actual request flow:

    - ``/api/v1/meta/*`` is observability-only.
    - ``/api/v1/auth/*`` bootstraps and refreshes sessions.
    - ``/api/v1/sms/*`` is Twilio-signed, not bearer-signed.
    """
    paths = schema.get("paths", {})
    for path, operations in paths.items():
        if any(path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES) or path in PUBLIC_PATHS:
            for detail in operations.values():
                if isinstance(detail, dict):
                    detail.pop("security", None)
            continue

        for method, detail in operations.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            if isinstance(detail, dict):
                detail["security"] = BEARER_SECURITY_REQUIREMENT


__all__ = [
    "openapi_schema",
    "openapi_schema_json",
    "_all_paths",
]
