"""Pydantic v2 schemas for the ``/api/v1/*`` request/response surface.

These models are the **wire contract** between ShopStack and its
external clients (the mobile app, future web clients, third-party
integrations). The OpenAPI schema generated from them is checked
into both ShopStack and ``shopstack-mobile/``; contract tests in
both repos assert equality.

**Convention:**

* Request bodies: ``XxxRequest``
* Response bodies: ``XxxResponse``
* List responses: ``XxxListResponse`` with a ``items: list[Xxx]`` and
  pagination metadata (``limit``, ``offset``, ``total``)
* Error responses: ``ApiError`` (single shape, used by every endpoint)
* IDs are always strings (UUIDs or household-scoped slugs)
* Timestamps are always ISO 8601 strings (UTC, ``Z`` suffix)

**Why not reuse ``shopstack.schemas.models``?**

That package holds the **domain** models (Pydantic classes used by
services and the DB layer). The API surface is a **transport**
concern: it may need to expose fewer fields (e.g. never expose
``password_hash``), add pagination metadata, or use wire-friendly
types (``str`` for UUIDs). The two-layer split is intentional.
Domain models are the source of truth for *behavior*; API schemas
are the source of truth for *contract*.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


# ── Common ──────────────────────────────────────────────────────────


class ApiModel(BaseModel):
    """Base for every API schema.

    Pydantic v2 + ``model_config = ConfigDict(...)`` for the
    settings that are common to every wire model.
    """

    model_config = ConfigDict(
        # Accept the legacy ``user_id`` field that some endpoints
        # forward to the DB layer. The API normalises it to
        # ``household_id`` for the response.
        populate_by_name=True,
        # Reject unknown fields at the boundary so the API catches
        # client typos at the door rather than silently ignoring them.
        extra="forbid",
        # Serialize datetimes as ISO 8601 strings.
        ser_json_timedelta="iso8601",
    )


class ApiError(ApiModel):
    """Single error shape used by every endpoint.

    Status code + human-readable message + machine-readable code
    (e.g. ``"household_not_found"``) + optional ``details`` dict
    for context the client can act on.
    """

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error message")
    details: dict[str, Any] | None = Field(
        default=None,
        description="Optional context. Shape is per-error-code.",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Server-side ISO 8601 timestamp (UTC).",
    )


class ListResponse(ApiModel, Generic[T]):
    """Generic list response with pagination metadata.

    Use as ``ListResponse[InventoryLot]`` etc. Pydantic v2
    preserves the generic at runtime; OpenAPI emits the concrete
    item type.
    """

    items: list[T]
    total: int = Field(..., description="Total matching items (before limit/offset).")
    limit: int = Field(..., description="Max items returned.")
    offset: int = Field(..., description="Items skipped before the first returned.")
    has_more: bool = Field(..., description="True iff ``offset + len(items) < total``.")


class Household(ApiModel):
    """A workspace (the unit of multi-tenancy)."""

    household_id: str = Field(..., description="Stable ID; primary key in DB.")
    name: str = Field(..., description="Display name.")
    is_active: bool = Field(
        default=False,
        description="True iff this is the currently active household "
        "for the request's session.",
    )


# ── Auth ────────────────────────────────────────────────────────────


class LoginRequest(ApiModel):
    """v1 auth login request.

    v1 trusts the local-first premise: the mobile app and the
    backend share a device. The login is gated by a device-level
    shared secret (the ``SHOPSTACK_DEVICE_SECRET`` env var, or
    auto-derived on first launch and persisted to the DB).

    A future ``v2/auth/sso`` adds a real identity provider.
    See ``Docs/archive/api_v1_and_mobile_repo_architecture_2026-06-16.md``.
    """

    device_id: str = Field(
        ...,
        description="Stable per-device ID (iOS identifierForVendor, Android ANDROID_ID).",
    )
    device_secret: str = Field(
        ...,
        description="Shared secret. On first launch the mobile app "
        "generates a random secret and registers it via "
        "``POST /api/v1/auth/register``. Subsequent logins reuse it.",
    )
    requested_household_id: str | None = Field(
        default=None,
        description="If set, the response token is scoped to this "
        "household. If the device has access to multiple "
        "households, the caller can list and switch later.",
    )


class TokenResponse(ApiModel):
    """Auth success response."""

    token: str = Field(..., description="Opaque bearer token.")
    expires_at: str = Field(..., description="ISO 8601 timestamp (UTC).")
    household_id: str = Field(..., description="Household the token is scoped to.")
    household_name: str = Field(..., description="Display name of the household.")


class WhoAmI(ApiModel):
    """``GET /api/v1/meta/whoami`` response.

    The endpoint discloses non-sensitive metadata only. No tokens,
    no secrets, no DB contents.
    """

    app_name: str
    app_version: str | None = None
    household_id: str
    household_name: str | None = None
    runtime_mode: str = Field(
        ...,
        description="One of: 'local_mock', 'local_transformers', "
        "'llama_cpp', 'hf_inference', 'production'.",
    )
    timestamp: str


# ── Inventory ───────────────────────────────────────────────────────


class InventoryLot(ApiModel):
    """One row in the inventory_lots table, in wire form."""

    lot_id: str
    canonical_name: str
    display_name: str
    category: str = ""
    quantity: float = 1.0
    unit: str = "unit"
    storage_location_id: str = ""
    storage_location_name: str = Field(
        default="",
        description="Resolved storage location display name (denormalised for mobile).",
    )
    purchase_date: str | None = None
    estimated_use_by_date: str | None = None
    label_expiry_date: str | None = None
    opened_date: str | None = None
    price_paid: float | None = None
    currency: str = "INR"
    confidence: float = 1.0
    status: str = "active"


class ConsumeInventoryRequest(ApiModel):
    """``POST /api/v1/inventory/lots/{lot_id}/consume`` body."""

    quantity: float = Field(..., gt=0, description="Amount consumed.")
    unit: str = Field(default="unit", description="Unit of the consumed amount.")
    consumed_at: str | None = Field(
        default=None,
        description="ISO 8601. Defaults to server now.",
    )


__all__ = [
    "ApiModel",
    "ApiError",
    "ListResponse",
    "Household",
    "LoginRequest",
    "TokenResponse",
    "WhoAmI",
    "InventoryLot",
    "ConsumeInventoryRequest",
]
