from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ShelfSceneType(str, Enum):
    AUTO = "auto"
    FRIDGE = "fridge"
    PANTRY = "pantry"
    SHOPPING_BAG = "shopping_bag"
    BATHROOM_CABINET = "bathroom_cabinet"
    MEDICINE_DRAWER = "medicine_drawer"
    CLEANING_CUPBOARD = "cleaning_cupboard"
    BEDROOM = "bedroom"
    DOCUMENTS = "documents"
    UTILITY = "utility"
    OTHER = "other"


class QuantityEstimate(BaseModel):
    value: float = 1.0
    unit: str = "unit"
    confidence: float = 0.5
    method: str = "inferred"


class OCRFinding(BaseModel):
    field_name: str
    raw_text: str = ""
    value: str | float | date | None = None
    confidence: float = 0.0
    source: Literal["ocr", "speech", "vision"] = "ocr"


class SpeechIntent(BaseModel):
    original_text: str = ""
    translated_text: str = ""
    language: str = "en"
    action: str = "observe"
    canonical_items: list[str] = Field(default_factory=list)
    target_scene: ShelfSceneType = ShelfSceneType.AUTO
    confidence: float = 0.0
    notes: list[str] = Field(default_factory=list)


class InventoryMatch(BaseModel):
    canonical_name: str
    matched_lot_ids: list[str] = Field(default_factory=list)
    total_quantity_at_home: float = 0.0
    use_soon_lot_ids: list[str] = Field(default_factory=list)
    matched_location_ids: list[str] = Field(default_factory=list)
    default_location_id: str = ""
    in_home_inventory: bool = False


class VisibleItemInstance(BaseModel):
    instance_id: str
    canonical_name: str
    display_name: str
    source_label: str = ""
    bbox: list[float] = Field(default_factory=list)
    mask_ref: str | None = None
    detection_confidence: float = 0.0
    segmentation_confidence: float = 0.0
    recognition_source: Literal["detection", "ocr", "speech", "barcode", "vision"] = "detection"
    quantity_estimate: QuantityEstimate = Field(default_factory=QuantityEstimate)
    freshness_visual_score: float | None = None
    spoilage_flags: list[str] = Field(default_factory=list)
    label_text: str = ""
    expiry_date: date | None = None
    matched_inventory_lot_id: str | None = None
    zone_guess: str = ""
    notes: list[str] = Field(default_factory=list)


class AggregatedVisibleItem(BaseModel):
    canonical_name: str
    display_name: str
    count: int = 0
    frame_hits: int = 0
    estimated_quantity: float = 0.0
    unit: str = "unit"
    confidence: float = 0.0
    matched_home_quantity: float = 0.0
    delta_from_inventory: float = 0.0
    recommendation: str = "confirm"
    matched_lot_ids: list[str] = Field(default_factory=list)
    instance_ids: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    proposed_actions: list[str] = Field(default_factory=list)
    default_location_id: str = ""


class ProposedInventoryAction(BaseModel):
    action: str
    canonical_name: str
    display_name: str
    quantity: float = 1.0
    unit: str = "unit"
    confidence: float = 0.0
    reason: str = ""
    requires_confirmation: bool = True
    source_instance_ids: list[str] = Field(default_factory=list)
    target_location_id: str = ""
    lot_id: str | None = None
    field_updates: dict[str, Any] = Field(default_factory=dict)


class ConfidenceSummary(BaseModel):
    overall_confidence: float = 0.0
    scene_confidence: float = 0.0
    image_confidence: float = 0.0
    speech_confidence: float = 0.0
    needs_review_count: int = 0
    items_seen: int = 0
    items_grouped: int = 0


class ShelfIntelligenceResult(BaseModel):
    scene_type: ShelfSceneType = ShelfSceneType.AUTO
    scene_label: str = "Auto"
    perception_mode: str = "none"
    image_path: str | None = None
    video_path: str | None = None
    audio_path: str | None = None
    annotated_image_path: str | None = None
    frame_paths: list[str] = Field(default_factory=list)
    frame_count: int = 0
    instances: list[VisibleItemInstance] = Field(default_factory=list)
    aggregates: list[AggregatedVisibleItem] = Field(default_factory=list)
    ocr_findings: list[OCRFinding] = Field(default_factory=list)
    speech_intent: SpeechIntent | None = None
    inventory_matches: list[InventoryMatch] = Field(default_factory=list)
    proposed_actions: list[ProposedInventoryAction] = Field(default_factory=list)
    confidence_summary: ConfidenceSummary = Field(default_factory=ConfidenceSummary)
    warnings: list[str] = Field(default_factory=list)
    corrections_needed: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
