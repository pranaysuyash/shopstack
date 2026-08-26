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

from .account import router as account_router
from .auth_router import router as auth_router
from .command import router as command_router
from .corrections import router as corrections_router
from .dashboard import router as dashboard_router
from .household import router as household_router
from .intelligence import router as intelligence_router
from .inventory import router as inventory_router
from .meta import router as meta_router
from .portability import router as portability_router
from .search import router as search_router
from .shopping import router as shopping_router
from .sms import router as sms_router
from .traces import router as traces_router

__all__ = [
    "account_router",
    "auth_router",
    "command_router",
    "corrections_router",
    "dashboard_router",
    "household_router",
    "intelligence_router",
    "inventory_router",
    "meta_router",
    "portability_router",
    "search_router",
    "shopping_router",
    "sms_router",
    "traces_router",
]
