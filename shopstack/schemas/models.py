from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Currency = Literal["INR", "USD", "EUR"]
ItemStatus = Literal["active", "low", "used", "expired", "discarded"]
Priority = Literal["must_buy", "optional", "avoid_buying"]
ListItemStatus = Literal["pending", "seen", "bought", "skipped"]
LocationType = Literal["fridge", "pantry", "shelf", "cabinet", "room", "drawer", "freezer", "balcony", "other"]
SourceType = Literal["photo", "video", "receipt", "voice", "manual"]
MovementSource = Literal["user_voice", "image_scan", "manual"]
RuntimeMode = Literal["local_transformers", "llama_cpp", "gguf", "mock", "onnx", "diffusers"]

# ── Decision engine types (§7 Priority 4 from review) ──────────────────────


class FreshnessStatus(str, Enum):
    """Data freshness classification for market snapshots and inventory."""
    LIVE = "live"                  # captured today
    RECENT_SNAPSHOT = "recent"     # captured within 24h
    STALE = "stale"                # older than 24h
    UNKNOWN = "unknown"            # cannot determine


class DecisionAction(str, Enum):
    """Every recommendation maps to exactly one action."""
    BUY = "buy"
    SKIP = "skip"
    USE_SOON = "use_soon"
    COMPARE = "compare"
    WAIT = "wait"
    SUBSTITUTE = "substitute"
    CONFIRM = "confirm"
    OPTIONAL = "optional"


class ReconciliationAction(str, Enum):
    """Post-shopping reconciliation outcomes."""
    BOUGHT = "bought"
    SKIPPED = "skipped"
    SUBSTITUTED = "substituted"
    PRICE_CHANGED = "price_changed"
    NOT_FOUND = "not_found"


def new_id() -> str:
    return uuid4().hex[:12]


class ItemCatalog(BaseModel):
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    category: str = ""
    default_unit: str = "unit"
    typical_storage: list[str] = Field(default_factory=list)
    typical_shelf_life_days: dict[str, int] = Field(default_factory=dict)
    is_perishable: bool = False
    nutrition_reference: dict | None = None
    notes: str | None = None


class InventoryLot(BaseModel):
    lot_id: str = Field(default_factory=new_id)
    canonical_name: str
    display_name: str
    category: str = ""
    quantity: float = 1.0
    unit: str = "unit"
    storage_location_id: str = ""
    purchase_date: date | None = None
    estimated_use_by_date: date | None = None
    label_expiry_date: date | None = None
    opened_date: date | None = None
    price_paid: float | None = None
    currency: str = "INR"
    source_event_id: str = ""
    confidence: float = 1.0
    image_crop_path: str | None = None
    status: ItemStatus = "active"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class PurchaseEvent(BaseModel):
    event_id: str = Field(default_factory=new_id)
    timestamp: datetime = Field(default_factory=datetime.now)
    canonical_name: str = ""
    quantity: float = 1.0
    unit: str = "unit"
    total_price: float = 0.0
    currency: str = "INR"
    source_type: SourceType = "manual"
    store_name: str | None = None
    raw_text: str | None = None
    source_file_path: str | None = None
    confirmed: bool = False


class DetectionEvent(BaseModel):
    detection_id: str = Field(default_factory=new_id)
    event_id: str = ""
    frame_id: str | None = None
    bounding_box: tuple[float, float, float, float] | None = None
    mask_path: str | None = None
    crop_path: str | None = None
    predicted_name: str
    confidence: float = 0.0
    user_corrected_name: str | None = None
    final_name: str | None = None


class OcrExtraction(BaseModel):
    ocr_id: str = Field(default_factory=new_id)
    event_id: str = ""
    source_type: Literal["receipt", "packet_label", "expiry", "mrp", "nutrition", "other"] = "other"
    raw_text: str = ""
    brand: str | None = None
    product_name: str | None = None
    weight_volume: str | None = None
    mrp: float | None = None
    price_paid: float | None = None
    expiry_date: date | None = None
    manufacturing_date: date | None = None
    batch_number: str | None = None
    confidence: float = 0.0


class ShoppingListItem(BaseModel):
    list_item_id: str = Field(default_factory=new_id)
    canonical_name: str
    requested_quantity: float | None = None
    unit: str | None = None
    priority: Priority = "optional"
    reason: str = ""
    status: ListItemStatus = "pending"
    linked_inventory_lots: list[str] = Field(default_factory=list)


class ShoppingList(BaseModel):
    list_id: str = Field(default_factory=new_id)
    name: str = "Shopping List"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    items: list[ShoppingListItem] = Field(default_factory=list)
    goal: str = ""
    is_active: bool = True


class VoiceCommand(BaseModel):
    command_id: str = Field(default_factory=new_id)
    raw_text: str
    transcribed_text: str | None = None
    language: str = "en"
    intent: str | None = None
    confidence: float = 0.0
    requires_confirmation: bool = True
    timestamp: datetime = Field(default_factory=datetime.now)


class ToolCall(BaseModel):
    call_id: str = Field(default_factory=new_id)
    tool_name: str
    args: dict = Field(default_factory=dict)
    result: dict | None = None
    success: bool = False
    error: str | None = None
    timestamp: datetime = Field(default_factory=datetime.now)
    requires_confirmation: bool = True
    confirmed: bool = False


class Trace(BaseModel):
    trace_id: str = Field(default_factory=new_id)
    input_type: str = ""
    user_goal: str = ""
    redacted_user_request: str = ""
    perception: dict = Field(default_factory=dict)
    inventory_context: dict = Field(default_factory=dict)
    decision: dict = Field(default_factory=dict)
    proposed_tool_calls: list[ToolCall] = Field(default_factory=list)
    human_confirmation: str | None = None
    final_response: str = ""
    timestamp: datetime = Field(default_factory=datetime.now)


class Store(BaseModel):
    store_id: str = Field(default_factory=new_id)
    name: str
    location: str | None = None
    store_type: str = "kirana"
    notes: str | None = None


class PriceObservation(BaseModel):
    price_id: str = Field(default_factory=new_id)
    canonical_name: str
    quantity: float = 1.0
    unit: str = "unit"
    price: float
    currency: str = "INR"
    store_name: str | None = None
    store_id: str | None = None
    observation_date: date = Field(default_factory=date.today)
    source_event_id: str = ""
    notes: str | None = None


class HouseholdLocation(BaseModel):
    location_id: str = Field(default_factory=new_id)
    name: str
    parent_location_id: str | None = None
    location_type: LocationType = "shelf"
    photo_path: str | None = None
    notes: str | None = None


class MovementEvent(BaseModel):
    movement_id: str = Field(default_factory=new_id)
    lot_id: str
    from_location_id: str | None = None
    to_location_id: str
    timestamp: datetime = Field(default_factory=datetime.now)
    source: MovementSource = "manual"
    confidence: float = 1.0


class DecisionEvidence(BaseModel):
    """A single piece of evidence supporting a decision."""
    source: str  # e.g. "market_snapshot", "inventory", "purchase_history", "price_memory"
    value: str | float | None = None
    confidence: float = 0.0
    captured_at: str | None = None  # ISO date string
    is_stale: bool = False


class DecisionWarning(BaseModel):
    """A warning attached to a decision recommendation."""
    code: str  # e.g. "stale_data", "sold_out", "no_cross_platform", "combo_risk"
    message: str
    severity: str = "info"  # "info" | "warning" | "critical"


_ACTION_COLORS: dict[str, str] = {
    "buy": "#1A9E4A",
    "skip": "#595E66",
    "use_soon": "#C47D0A",
    "optional": "#2A6BC4",
    "compare": "#7345D0",
    "wait": "#7F8C8D",
    "substitute": "#C53030",
    "confirm": "#009688",
}

_ACTION_ICONS: dict[str, str] = {
    "buy": "\U0001f6d2",
    "skip": "\u23f9",
    "use_soon": "\u23f0",
    "optional": "\u2794",
    "compare": "\u2696",
    "wait": "\U0001f441",
    "substitute": "\u2753",
    "confirm": "\u2705",
}


class DecisionResult(BaseModel):
    """Structured output from the decision engine.

    Every recommendation from ShopStack produces one of these.
    This is the canonical representation that powers dashboard, buy, skip,
    use-soon, compare, basket, and trace views.
    """
    item_id: str = Field(default_factory=new_id)
    canonical_name: str
    display_name: str
    action: str  # DecisionAction value: buy/skip/use_soon/compare/wait/substitute
    confidence: float = 0.5  # 0.0–1.0
    priority: int = 0  # higher = more urgent
    reasons: list[str] = Field(default_factory=list)
    evidence: list[DecisionEvidence] = Field(default_factory=list)
    warnings: list[DecisionWarning] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)  # canonical names of substitutes
    data_freshness: str = "unknown"  # FreshnessStatus value
    data_freshness_label: str = ""  # human-readable, e.g. "Snapshot from 6 Jun 2026"
    quantity_at_home: float = 0.0
    unit: str = ""
    market_price: float | None = None
    market_price_per_kg: float | None = None
    market_available: bool = False
    market_raw_size: str = ""
    shopping_list_status: str = ""
    waste_risk: str = "unknown"
    shelf_life_days: int = 0
    last_purchase_date: date | None = None
    location: str = ""
    source_trace: str = ""
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def reason(self) -> str:
        """Convenience accessor for the first reason string."""
        return self.reasons[0] if self.reasons else ""

    def badge_html(self) -> str:
        color = _ACTION_COLORS.get(self.action, "var(--text-dim)")
        icon = _ACTION_ICONS.get(self.action, "")
        return (
            f"<span style='background:{color}20;color:{color};"
            f"padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;'>"
            f"{icon} {self.action.upper()}</span>"
        )

    def to_dict(self) -> dict:
        return {
            "canonical_name": self.canonical_name,
            "display_name": self.display_name,
            "action": self.action,
            "reason": self.reason,
            "confidence": self.confidence,
            "priority": self.priority,
            "reasons": self.reasons,
            "warnings": [w.model_dump() for w in self.warnings],
            "alternatives": self.alternatives,
            "data_freshness": self.data_freshness,
            "data_freshness_label": self.data_freshness_label,
            "quantity_at_home": self.quantity_at_home,
            "unit": self.unit,
            "market_price": self.market_price,
            "market_price_per_kg": self.market_price_per_kg,
            "market_available": self.market_available,
            "market_raw_size": self.market_raw_size,
            "shopping_list_status": self.shopping_list_status,
            "waste_risk": self.waste_risk,
            "shelf_life_days": self.shelf_life_days,
            "location": self.location,
        }


class DecisionSet(BaseModel):
    """A complete set of decisions for a household shopping session."""
    decisions: list[DecisionResult] = Field(default_factory=list)
    snapshot_source: str = ""
    snapshot_captured_at: str = ""
    snapshot_freshness: str = "unknown"
    generated_at: datetime = Field(default_factory=datetime.now)

    @property
    def buy(self) -> list[DecisionResult]:
        return [d for d in self.decisions if d.action == "buy"]

    @property
    def skip(self) -> list[DecisionResult]:
        return [d for d in self.decisions if d.action == "skip"]

    @property
    def use_soon(self) -> list[DecisionResult]:
        return [d for d in self.decisions if d.action == "use_soon"]

    @property
    def optional(self) -> list[DecisionResult]:
        return [d for d in self.decisions if d.action == "optional"]

    @property
    def compare(self) -> list[DecisionResult]:
        return [d for d in self.decisions if d.action == "compare"]

    @property
    def wait(self) -> list[DecisionResult]:
        return [d for d in self.decisions if d.action == "wait"]

    @property
    def substitute(self) -> list[DecisionResult]:
        return [d for d in self.decisions if d.action == "substitute"]

    @property
    def confirm(self) -> list[DecisionResult]:
        return [d for d in self.decisions if d.action == "confirm"]

    @property
    def estimated_basket_total(self) -> float:
        return round(sum(d.market_price or 0 for d in self.buy), 2)

    @property
    def stale_warning_count(self) -> int:
        return sum(1 for d in self.decisions if d.data_freshness == "stale")


class ReconciliationEvent(BaseModel):
    """Records what actually happened after a shopping trip.

    This closes the loop: plan → shop → reconcile → update memory.
    """
    event_id: str = Field(default_factory=new_id)
    timestamp: datetime = Field(default_factory=datetime.now)
    canonical_name: str
    planned_action: str  # what the decision engine recommended
    actual_action: str  # ReconciliationAction value
    quantity: float = 0.0
    unit: str = "unit"
    price_paid: float | None = None  # actual price, may differ from planned
    planned_price: float | None = None
    substituted_with: str | None = None  # canonical name if substituted
    notes: str | None = None
    source: str = "manual"  # manual / receipt / scan / voice


class PreferenceSignal(BaseModel):
    """A household preference learned from user corrections or behavior."""
    signal_id: str = Field(default_factory=new_id)
    canonical_name: str
    signal_type: str  # "staple" | "disliked" | "often_wasted" | "brand_preferred" | "pack_size" | "discount_only"
    value: str  # the preference value
    confidence: float = 0.5
    source: str = "observed"  # observed / corrected / explicit
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class MarketSnapshotModel(BaseModel):
    snapshot_id: str = Field(default_factory=new_id)
    source: str
    source_category: str
    captured_at: str
    freshness_context: str = "unknown"

class MarketRecordModel(BaseModel):
    record_id: str = Field(default_factory=new_id)
    snapshot_id: str
    raw_name: str
    canonical_name: str
    description: str = ""
    raw_size: str = ""
    normalized_quantity: float | None = None
    normalized_unit: str | None = None
    package_count: int = 1
    is_combo: bool = False
    is_weight_based: bool = False
    is_piece_based: bool = False
    is_size_class: bool = False
    size_class: str = ""
    price_inr: float = 0.0
    mrp_inr: float = 0.0
    discount_percent_displayed: float = 0.0
    discount_amount_inr: float = 0.0
    computed_discount_percent: float = 0.0
    availability: str = ""
    is_available: bool = True
    tag: str = ""
    is_ad: bool = False
    is_upgrade: bool = False
    card_index: int = 0
    delivery_time: str = ""
    price_per_kg: float | None = None
    price_per_100g: float | None = None
    price_per_piece: float | None = None
    normalization_warnings: str = ""  # Can store as JSON list of strings
    variety: str = ""
    brand: str = ""

class MarketRecordComponentModel(BaseModel):
    component_id: str = Field(default_factory=new_id)
    record_id: str
    component_name: str


