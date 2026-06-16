"""``APIRouter`` instances for the ``/api/v1/*`` surface.

One router per resource group. The :func:`mount_v1_routes` entry
point in :mod:`shopstack.api.v1.mount` aggregates them and
attaches them to the Gradio app's FastAPI instance under
``/api/v1``.

**Why per-resource routers (not one big file):**

* Each resource group can grow to ~5–15 endpoints.
* Per-resource routers keep the surface navigable.
* Routers can be unit-tested in isolation (a ``TestClient`` per
  router is cheap to spin up).
* The pattern matches FastAPI's own conventions and the
  generated OpenAPI doc is naturally grouped.

**To add a new endpoint:**

1. Add the request/response schemas to
   :mod:`shopstack.api.v1.schemas`.
2. Add the endpoint to the appropriate router here.
3. Add a contract test in
   ``tests/test_api_v1_<resource>.py``.
4. Run ``python -c "import shopstack.api.v1; print(shopstack.api.v1.openapi_schema())"``
   to regenerate the schema. The schema is committed to both
   repos and is the source of truth for the mobile client.
"""
from __future__ import annotations

from .meta import router as meta_router
from .auth_router import router as auth_router
from .inventory import router as inventory_router

__all__ = [
    "meta_router",
    "auth_router",
    "inventory_router",
]
