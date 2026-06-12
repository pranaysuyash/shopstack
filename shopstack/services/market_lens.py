from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from shopstack.scanner import decode_barcode, infer_product_from_code
from shopstack.decisions.rules import classify_inventory_comparison
from shopstack.repos.inventory import InventoryRepo
from shopstack.services.shopping import enrich_items_with_swiggy, normalize_item_name

logger = logging.getLogger(__name__)


@dataclass
class MarketLensResult:
    items_found: list[str] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    barcode_info: list[dict[str, Any]] = field(default_factory=list)
    transcript_text: str = ""
    source_mode: str = "none"
    freshness_label: str = "Market signals are point-in-time snapshots and can change frequently."
    warnings: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    @property
    def analysis_json(self) -> str:
        if self.decisions:
            return json.dumps({"items": self.decisions}, indent=2)
        if self.transcript_text:
            return json.dumps({"audio_query": self.transcript_text}, indent=2)
        return ""

    @property
    def detected_items_json(self) -> str:
        return json.dumps({"items": self.items_found}, ensure_ascii=False)

    @property
    def barcode_json(self) -> str:
        return json.dumps(self.barcode_info) if self.barcode_info else "[]"


def analyze_market_lens(
    image_path: str | None,
    audio_path: str | None,
    providers: Any,
    inventory: InventoryRepo,
) -> MarketLensResult:
    """Analyze Market Lens inputs without rendering UI or writing traces."""
    result = MarketLensResult()

    if not image_path and not audio_path:
        result.source_mode = "none"
        result.warnings.append("No image or audio input provided.")
        return result

    if image_path and audio_path:
        result.source_mode = "vision+audio"
    elif image_path:
        result.source_mode = "vision"
    else:
        result.source_mode = "audio"

    if image_path:
        result.barcode_info = detect_barcodes(image_path)
        result.decisions = analyze_visible_items(image_path, providers, inventory)
        result.items_found = [d["canonical_name"] for d in result.decisions]
        if result.decisions:
            for decision in result.decisions:
                result.tool_calls.append({
                    "tool_name": "compare_visible_item_to_inventory",
                    "args": {
                        "canonical_name": decision.get("canonical_name", ""),
                        "quantity": decision.get("quantity", 1.0),
                        "unit": decision.get("unit", "unit"),
                    },
                })
        if not result.decisions:
            result.warnings.append("Could not detect individual shelf items from image; OCR fallback may still find text.")

    if audio_path:
        result.transcript_text = transcribe_audio(audio_path, providers)
        if image_path:
            result.tool_calls.append({
                "tool_name": "stt.transcribe",
                "args": {"audio_path": audio_path or ""},
            })
        elif result.transcript_text:
            result.tool_calls.append({
                "tool_name": "ask_shopstack",
                "args": {"question": result.transcript_text},
            })
        if not result.transcript_text:
            result.warnings.append("Audio input could not be transcribed.")

    return result


def detect_barcodes(image_path: str) -> list[dict[str, Any]]:
    barcode_info: list[dict[str, Any]] = []
    for code in decode_barcode(image_path):
        info = infer_product_from_code(code["data"])
        barcode_info.append({
            "label": info["label"],
            "code": code["data"],
            "type": code["type"],
        })
    return barcode_info


def analyze_visible_items(image_path: str, providers: Any, inventory: InventoryRepo) -> list[dict[str, Any]]:
    detections = providers.object_detection.detect(image_path)
    ocr_result = providers.ocr.extract(image_path)
    raw_product = ""
    if isinstance(ocr_result, dict):
        raw_product = (
            ocr_result.get("product_name")
            or ocr_result.get("text")
            or ocr_result.get("raw_text")
            or ""
        )
        # If the configured OCR backend cannot read the image path, fall back
        # to the canonical mock OCR surface so the app still produces a visible
        # decision path in local/test mode.
        if not raw_product and (ocr_result.get("error") or ocr_result.get("model")):
            unified = getattr(providers, "unified", None)
            if unified is not None and hasattr(unified, "extract_text"):
                fallback = unified.extract_text(image_path)
                if isinstance(fallback, dict):
                    raw_product = (
                        fallback.get("product_name")
                        or fallback.get("text")
                        or fallback.get("raw_text")
                        or raw_product
                    )

    decisions: list[dict[str, Any]] = []
    if detections:
        for detection in detections[:8]:
            item_name = normalize_item_name(str(detection.get("label", "")))
            quantity = detection.get("quantity", 1.0)
            _compare = inventory.compare_visible if hasattr(inventory, "compare_visible") else inventory.compare_visible_item_to_inventory
            comparison = _compare(item_name, quantity, "unit")
            decision, reason = classify_inventory_comparison(
                comparison.get("total_quantity_at_home", 0),
                quantity,
                "unit",
                comparison.get("is_use_soon", False),
            )
            decisions.append({
                "canonical_name": item_name.title(),
                "decision": decision,
                "reason": reason,
                "confidence": float(detection.get("confidence", 0.0)),
                "unit": "unit",
                "quantity": quantity,
                "suggested_quantity": max(0.0, quantity),
                "source": raw_product,
            })
    elif raw_product:
        normalized = normalize_item_name(raw_product)
        if normalized:
            quantity = 1.0
            _compare = inventory.compare_visible if hasattr(inventory, "compare_visible") else inventory.compare_visible_item_to_inventory
            comparison = _compare(normalized, quantity, "unit")
            decision, reason = classify_inventory_comparison(
                comparison.get("total_quantity_at_home", 0),
                quantity,
                "unit",
                comparison.get("is_use_soon", False),
            )
            decisions.append({
                "canonical_name": normalized.title(),
                "decision": decision,
                "reason": reason,
                "confidence": 0.45,
                "unit": "unit",
                "quantity": quantity,
                "suggested_quantity": max(0.0, quantity),
                "source": raw_product,
            })

    enrich_market_prices(decisions)
    return decisions


def enrich_market_prices(decisions: list[dict[str, Any]]) -> None:
    """Attach market price fields in-place through the canonical shopping service path."""
    enrich_items_with_swiggy(decisions)


def transcribe_audio(audio_path: str, providers: Any) -> str:
    transcript = providers.stt.transcribe(audio_path)
    if isinstance(transcript, dict):
        return str(transcript.get("text", ""))
    return str(transcript)
