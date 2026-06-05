from __future__ import annotations

from datetime import date, datetime
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


def new_id() -> str:
    return uuid4().hex[:12]


class ItemCatalog(BaseModel):
    canonical_name: str
    aliases: list[str] = []
    category: str = ""
    default_unit: str = "unit"
    typical_storage: list[str] = []
    typical_shelf_life_days: dict[str, int] = {}
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
    linked_inventory_lots: list[str] = []


class ShoppingList(BaseModel):
    list_id: str = Field(default_factory=new_id)
    name: str = "Shopping List"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    items: list[ShoppingListItem] = []
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
    args: dict = {}
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
    perception: dict = {}
    inventory_context: dict = {}
    decision: dict = {}
    proposed_tool_calls: list[ToolCall] = []
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


class TripWeatherContext(BaseModel):
    context_id: str = Field(default_factory=new_id)
    trip_date: date | None = None
    weather_condition: str | None = None
    temperature_c: float | None = None
    is_rainy: bool | None = None
    travel_mode: str | None = None
    notes: str | None = None
