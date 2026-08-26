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

from datetime import UTC, datetime
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
        default_factory=lambda: datetime.now(UTC).isoformat(),
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
    nutrition_per_100g: dict | None = Field(
        default=None,
        description="Per-100g nutrition data from barcode lookup (Open Food Facts `nutriments`).",
    )
    status: str = "active"


class AddInventoryLotRequest(ApiModel):
    """``POST /api/v1/inventory/lots`` body."""

    canonical_name: str = Field(
        ..., min_length=1, max_length=200,
        description="Item name (e.g. 'milk', 'basmati rice').",
    )
    display_name: str = Field(default="", max_length=200)
    quantity: float = Field(default=1.0, gt=0, description="How many / how much.")
    unit: str = Field(default="unit", max_length=32)
    storage_location_id: str = Field(default="", max_length=80)
    purchase_date: str | None = Field(
        default=None,
        description="ISO 8601 date (YYYY-MM-DD). Defaults to today.",
    )
    estimated_use_by_date: str | None = Field(
        default=None,
        description="ISO 8601 date (YYYY-MM-DD).",
    )
    label_expiry_date: str | None = Field(
        default=None,
        description="ISO 8601 date (YYYY-MM-DD).",
    )
    opened_date: str | None = Field(
        default=None,
        description="ISO 8601 date (YYYY-MM-DD).",
    )
    price_paid: float | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", max_length=8)
    confidence: float = Field(default=1.0, ge=0, le=1)
    category: str = Field(default="", max_length=100)
    nutrition_per_100g: dict | None = Field(
        default=None,
        description="Per-100g nutrition data from barcode lookup (Open Food Facts `nutriments`). "
        "Keys follow OFF naming: `energy-kcal_100g`, `proteins_100g`, `carbohydrates_100g`, "
        "`fat_100g`, `fiber_100g`, etc.",
    )


class ConsumeInventoryRequest(ApiModel):
    """``POST /api/v1/inventory/lots/{lot_id}/consume`` body."""

    quantity: float = Field(..., gt=0, description="Amount consumed.")
    unit: str = Field(default="unit", description="Unit of the consumed amount.")
    consumed_at: str | None = Field(
        default=None,
        description="ISO 8601. Defaults to server now.",
    )


# ── Household ──────────────────────────────────────────────────────


class CreateHouseholdRequest(ApiModel):
    """``POST /api/v1/household`` body."""

    household_id: str | None = Field(
        default=None,
        max_length=80,
        description="Optional explicit ID. If omitted, the server "
        "derives one from the name.",
    )
    name: str = Field(..., min_length=1, max_length=80)
    notes: str = Field(default="", max_length=500)


class HouseholdListResponse(ApiModel):
    """``GET /api/v1/household`` response."""

    items: list[Household]
    active_household_id: str = Field(..., description="Currently active household.")


# ── Shopping ───────────────────────────────────────────────────────


class ShoppingItemInput(ApiModel):
    """One item to add (input side — no server-assigned id)."""

    canonical_name: str = Field(..., min_length=1, max_length=200)
    requested_quantity: float | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, max_length=32)
    priority: str = Field(default="optional", max_length=32)
    reason: str = Field(default="", max_length=500)


class ShoppingListItemWire(ApiModel):
    """One item on a shopping list, in wire form."""

    item_id: str
    canonical_name: str
    requested_quantity: float | None = None
    unit: str | None = None
    priority: str = "optional"
    reason: str = ""
    status: str = "pending"
    linked_inventory_lots: list[str] = Field(default_factory=list)


class ShoppingListWire(ApiModel):
    """A shopping list, in wire form."""

    list_id: str
    name: str = "Shopping List"
    created_at: str
    updated_at: str
    goal: str = ""
    is_active: bool = True
    items: list[ShoppingListItemWire] = Field(default_factory=list)


class CreateShoppingListRequest(ApiModel):
    """``POST /api/v1/shopping/lists`` body."""

    goal: str = Field(default="", max_length=500)
    items: list[ShoppingItemInput] = Field(default_factory=list)


class AddShoppingItemsRequest(ApiModel):
    """``POST /api/v1/shopping/lists/{list_id}/items`` body.

    Accepts an array so a receipt-scan or import flow sends N items in
    one round-trip (per the mobile-contract note in the exploration doc).
    """

    items: list[ShoppingItemInput] = Field(..., min_length=1)


# ── Dashboard ──────────────────────────────────────────────────────


class DashboardSnapshot(ApiModel):
    """``GET /api/v1/dashboard/today`` response.

    A *data* snapshot of the Today dashboard — counts and item lists,
    not the rendered HTML. This is what a mobile client caches to draw
    the home screen offline. Fields mirror the highest-value panels of
    ``DashboardState`` (``shopstack/services/dashboard.py``).
    """

    household_id: str
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    pantry_count: int = 0
    use_soon_count: int = 0
    low_items_count: int = 0
    recent_purchases_count: int = 0
    use_soon_items: list[dict[str, Any]] = Field(default_factory=list)
    low_items: list[dict[str, Any]] = Field(default_factory=list)
    recent_purchases: list[dict[str, Any]] = Field(default_factory=list)
    has_trip_recommendation: bool = False

# ── Shopping Complete / Mark Purchased ────────────────────────────────


class CompletionItemWire(ApiModel):
    """One item added to inventory during list completion."""

    canonical_name: str
    lot_id: str
    quantity: float
    unit: str


class MarkPurchasedItemWire(ApiModel):
    """One item marked purchased (for response wire)."""

    canonical_name: str
    lot_id: str
    quantity: float
    unit: str


class CompleteShoppingListRequest(ApiModel):
    """``POST /api/v1/shopping/lists/{id}/complete`` body.

    Empty body is accepted; the endpoint completes the list as-is.
    If `purchased_item_ids` is provided, only those items (and items already marked bought)
    are converted to inventory.
    """

    purchased_item_ids: list[str] | None = Field(
        default=None,
        description="Optional list of list_item_id values that were checked/purchased.",
    )


class CompleteShoppingListResponse(ApiModel):
    """Response from completing a shopping list."""

    success: bool
    list_id: str
    items_added: list[CompletionItemWire] = Field(default_factory=list)
    items_skipped: int = 0
    goal: str = ""
    message: str = ""


class MarkPurchasedRequest(ApiModel):
    """``POST /api/v1/shopping/lists/{id}/mark-purchased`` body."""

    item_ids: list[str] = Field(
        ..., min_length=1, description="Shopping list item IDs to mark as purchased."
    )


class MarkPurchasedResponse(ApiModel):
    """Response from marking items as purchased."""

    success: bool
    items_added: list[MarkPurchasedItemWire] = Field(default_factory=list)
    message: str = ""


# ── Search ──────────────────────────────────────────────────────────


class SearchResultWire(ApiModel):
    """One search result in wire form."""

    kind: str
    title: str
    meta: str = ""
    score: float = 0.0
    action_kind: str = "tab"
    action_target: str = ""
    household_id: str = ""


class SearchResponse(ApiModel):
    """``GET /api/v1/search/*`` response."""

    query: str
    search_mode: str = ""
    semantic_active: bool = False
    match_type: str = ""
    expanded_queries: list[str] = Field(default_factory=list)
    results: list[SearchResultWire] = Field(default_factory=list)
    count: int = 0


class VoiceIntentRequest(ApiModel):
    """``POST /api/v1/search/voice-intent`` body."""

    text: str = Field(..., min_length=1, description="Spoken command or typed transcript.")
    language: str = Field(default="en", description="BCP-47-ish language code.")


class VoiceIntentResponse(ApiModel):
    """Parsed voice intent for shopping / shelf workflows."""

    original_text: str = ""
    translated_text: str = ""
    language: str = "en"
    action: str = "observe"
    canonical_items: list[str] = Field(default_factory=list)
    target_scene: str = "auto"
    confidence: float = 0.0
    notes: list[str] = Field(default_factory=list)


# ── Command surface ───────────────────────────────────────────────


class CommandRequest(ApiModel):
    """``POST /api/v1/command/execute`` body."""

    text: str = Field(
        ...,
        min_length=1,
        description="Typed command or natural-language question.",
    )


class CommandPreviewRequest(ApiModel):
    """``POST /api/v1/command/preview`` body."""

    text: str = Field(
        ...,
        min_length=1,
        description="Typed command or natural-language question.",
    )


class CommandIntentWire(ApiModel):
    """Parsed intent used by the command surface."""

    action: str = "unknown"
    canonical_name: str = ""
    raw_text: str = ""


class CommandResultWire(ApiModel):
    """Execution result returned by the command surface."""

    success: bool = False
    action: str = ""
    canonical_name: str = ""
    message: str = ""
    toast_html: str = ""


class CommandResponse(ApiModel):
    """Parsed + executed command surface response."""

    household_id: str = ""
    original_text: str = ""
    intent: CommandIntentWire = Field(default_factory=CommandIntentWire)
    result: CommandResultWire = Field(default_factory=CommandResultWire)


class CommandPreviewResponse(ApiModel):
    """Parse-only response for the command surface."""

    original_text: str = ""
    intent: CommandIntentWire = Field(default_factory=CommandIntentWire)
    would_mutate: bool = False
    route_kind: str = "ask"
    summary: str = ""


class CommandHistoryItemWire(ApiModel):
    """One recently executed command."""

    trace_id: str = ""
    timestamp: str = ""
    input_type: str = "command"
    original_text: str = ""
    action: str = ""
    canonical_name: str = ""
    success: bool = False
    summary: str = ""


class CommandHistoryResponse(ApiModel):
    """Recent command execution history."""

    items: list[CommandHistoryItemWire] = Field(default_factory=list)
    count: int = 0


# ── Intelligence ───────────────────────────────────────────────────


class DecisionExplanationWire(ApiModel):
    """Structured explanation of a single decision, in wire form."""

    item_id: str = ""
    canonical_name: str = ""
    action: str = ""
    confidence: float = 0.0
    summary: str = ""
    key_signal: str = ""
    confidence_label: str = ""
    confidence_caveat: str = ""
    warnings: list[dict[str, str]] = Field(default_factory=list)
    override_hint: str = ""
    evidence_summary: list[str] = Field(default_factory=list)
    freshness_status: str = "unknown"
    freshness_label: str = ""


class RecurringPlanItemWire(ApiModel):
    """One item in the recurring shopping plan."""

    canonical_name: str = ""
    display_name: str = ""
    action: str = "buy"
    confidence: float = 0.0
    priority: int = 0
    reasons: list[str] = Field(default_factory=list)
    days_until_next: int | None = None
    typical_interval_days: float | None = None


class RecurringPlanResponse(ApiModel):
    """``GET /api/v1/intelligence/recurring`` response."""

    window_days: int = 3
    summary: str = ""
    count: int = 0
    items: list[RecurringPlanItemWire] = Field(default_factory=list)


class MealPlanDayWire(ApiModel):
    """One day in the meal plan."""

    date: str
    recipe_name: str | None = None
    recipe_id: str | None = None
    cuisine: str | None = None
    cook_minutes: int | None = None
    score: float | None = None
    ingredients_used: list[str] = Field(default_factory=list)
    ingredients_missing: list[str] = Field(default_factory=list)
    confidence: str = "low"
    rationale: str = ""


class RecipeIngredientWire(ApiModel):
    """One ingredient line in a recipe."""

    canonical_name: str
    quantity: float = 1.0
    unit: str = "unit"


class RecipeDetailResponse(ApiModel):
    """``GET /api/v1/intelligence/recipes/{recipe_id}`` response."""

    recipe_id: str
    name: str
    cuisine: str = ""
    dietary: list[str] = Field(default_factory=list)
    prep_minutes: int = 0
    cook_minutes: int = 0
    serves: int = 2
    tags: list[str] = Field(default_factory=list)
    ingredients: list[RecipeIngredientWire] = Field(default_factory=list)
    instructions: list[str] = Field(default_factory=list)
    found: bool = True


class MealPlanResponse(ApiModel):
    """``GET /api/v1/intelligence/mealplan`` response."""

    summary: str = ""
    days: int = 7
    start_date: str = ""
    count: int = 0
    items: list[MealPlanDayWire] = Field(default_factory=list)


# ── Account / Privacy / Undo ───────────────────────────────────────


class PurgeDataResponse(ApiModel):
    """Response from purging user data."""

    success: bool
    traces_purged: int = 0
    community_observations_purged: int = 0
    sms_registry_cleared: int = 0
    voice_memos_purged: int = 0
    backups_purged: int = 0
    errors: list[str] = Field(default_factory=list)


class UndoRequest(ApiModel):
    """``POST /api/v1/account/undo`` body."""

    entry_id: str = Field(default="", description="Specific entry to undo. Empty = most recent.")


class UndoResponse(ApiModel):
    """Response from an undo operation."""

    success: bool
    entry_id: str = ""
    kind: str = ""
    description: str = ""
    message: str = ""


class RetentionPolicyWire(ApiModel):
    """Current retention policy snapshot."""

    trace_ttl_days: int = 30
    trace_max_rows: int = 5000
    community_pool_retention_days: int = 90
    voice_memo_retention_days: int = 7
    sms_registry_retention_days: int = 0
    backup_retention_days: int = 0
    locale_persistence: bool = True
    community_optin: bool = False


class RetentionSummaryResponse(ApiModel):
    """``GET /api/v1/account/privacy/retention-summary`` response."""

    summary: RetentionPolicyWire = Field(default_factory=RetentionPolicyWire)


class UpdateRetentionRequest(ApiModel):
    """``POST /api/v1/account/privacy/update-retention`` body."""

    key: str
    value: str


class UpdateRetentionResponse(ApiModel):
    """Response from updating a retention setting."""

    success: bool


class ApplyRetentionProfileRequest(ApiModel):
    """``POST /api/v1/account/privacy/apply-profile`` body."""

    profile: str = Field(
        ...,
        description="Named privacy profile: balanced, strict, or shared.",
    )


class ApplyRetentionProfileResponse(ApiModel):
    """Response from applying a retention profile."""

    success: bool
    profile: str = ""
    updated_keys: list[str] = Field(default_factory=list)
    summary: RetentionPolicyWire = Field(default_factory=RetentionPolicyWire)
    errors: list[str] = Field(default_factory=list)


class RetentionProfileWire(ApiModel):
    """A canonical privacy profile exposed by the backend."""

    profile: str
    label: str
    description: str = ""
    recommended: bool = False
    values: dict[str, str] = Field(default_factory=dict)
    summary: RetentionPolicyWire = Field(default_factory=RetentionPolicyWire)


class RetentionProfileListResponse(ApiModel):
    """``GET /api/v1/account/privacy/profiles`` response."""

    items: list[RetentionProfileWire] = Field(default_factory=list)
    total: int = 0
    limit: int = 0
    offset: int = 0
    has_more: bool = False


class StoreModeToggleRequest(ApiModel):
    """``POST /api/v1/account/store-mode/toggle`` body."""

    item_id: str = Field(..., description="Shopping list item ID to toggle.")


class StoreModeToggleResponse(ApiModel):
    """Response from toggling store mode."""

    success: bool
    new_status: str = ""
    message: str = ""


# ── Corrections ────────────────────────────────────────────────────


class CorrectionItemWire(ApiModel):
    """One correction event in wire form."""

    event_id: str
    canonical_name: str
    was_action: str = ""
    should_be_action: str = ""
    source: str = ""
    timestamp: str = ""
    accepted: bool = False


class CorrectionListResponse(ApiModel):
    """``GET /api/v1/corrections`` response."""

    summary: str = ""
    count: int = 0
    items: list[CorrectionItemWire] = Field(default_factory=list)


class CorrectionCreateRequest(ApiModel):
    """``POST /api/v1/corrections`` body."""

    canonical_name: str = Field(..., min_length=1, max_length=200)
    was_action: str = Field(..., max_length=32)
    should_be_action: str = Field(..., max_length=32)
    reason: str = Field(default="", max_length=500)


class CorrectionCreateResponse(ApiModel):
    """Response from creating a correction."""

    event_id: str
    canonical_name: str
    was_action: str = ""
    should_be_action: str = ""
    source: str = ""
    timestamp: str = ""
    accepted: bool = False


# ── Traces ────────────────────────────────────────────────────────


class TraceSummaryWire(ApiModel):
    """Compact trace metadata for list views."""

    trace_id: str
    input_type: str = ""
    user_goal: str = ""
    timestamp: str = ""
    human_confirmation: str | None = None
    final_response: str = ""
    action: str = ""
    tool_call_count: int = 0


class TraceDetailWire(TraceSummaryWire):
    """Expanded trace payload for detail/export views."""

    redacted_user_request: str = ""
    perception: dict[str, Any] = Field(default_factory=dict)
    inventory_context: dict[str, Any] = Field(default_factory=dict)
    decision: dict[str, Any] = Field(default_factory=dict)
    proposed_tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    actor_id: str = ""


class TraceListResponse(ApiModel):
    """``GET /api/v1/traces`` response."""

    summary: str = ""
    count: int = 0
    items: list[TraceSummaryWire] = Field(default_factory=list)


class TraceDetailResponse(ApiModel):
    """``GET /api/v1/traces/{trace_id}`` response."""

    trace: TraceDetailWire


class TraceExportResponse(ApiModel):
    """``GET /api/v1/traces/{trace_id}/export`` response."""

    trace_id: str
    redacted: bool = True
    jsonl: str = ""


__all__ = [
    "ApiModel",
    "ApiError",
    "ListResponse",
    "Household",
    "LoginRequest",
    "TokenResponse",
    "WhoAmI",
    "InventoryLot",
    "AddInventoryLotRequest",
    "ConsumeInventoryRequest",
    "CreateHouseholdRequest",
    "HouseholdListResponse",
    "ShoppingItemInput",
    "ShoppingListItemWire",
    "ShoppingListWire",
    "CreateShoppingListRequest",
    "AddShoppingItemsRequest",
    "DashboardSnapshot",
    # Shopping complete / mark purchased
    "CompletionItemWire",
    "MarkPurchasedItemWire",
    "CompleteShoppingListRequest",
    "CompleteShoppingListResponse",
    "MarkPurchasedRequest",
    "MarkPurchasedResponse",
    # Search
    "SearchResultWire",
    "SearchResponse",
    "VoiceIntentRequest",
    "VoiceIntentResponse",
    # Command surface
    "CommandRequest",
    "CommandPreviewRequest",
    "CommandIntentWire",
    "CommandResultWire",
    "CommandResponse",
    "CommandPreviewResponse",
    "CommandHistoryItemWire",
    "CommandHistoryResponse",
    # Intelligence
    "DecisionExplanationWire",
    "RecurringPlanItemWire",
    "RecurringPlanResponse",
    "MealPlanDayWire",
    "MealPlanResponse",
    "RecipeIngredientWire",
    "RecipeDetailResponse",
    # Account / Privacy / Undo
    "PurgeDataResponse",
    "UndoRequest",
    "UndoResponse",
    "RetentionPolicyWire",
    "RetentionSummaryResponse",
    "UpdateRetentionRequest",
    "UpdateRetentionResponse",
    "StoreModeToggleRequest",
    "StoreModeToggleResponse",
    # Corrections
    "CorrectionItemWire",
    "CorrectionListResponse",
    "CorrectionCreateRequest",
    "CorrectionCreateResponse",
    # Traces
    "TraceSummaryWire",
    "TraceDetailWire",
    "TraceListResponse",
    "TraceDetailResponse",
    "TraceExportResponse",
]
