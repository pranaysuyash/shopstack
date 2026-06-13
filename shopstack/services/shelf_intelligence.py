from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any
from uuid import uuid4

from shopstack.market.normalization import normalize_item_name, parse_size
from shopstack.repos.inventory import InventoryRepo
from shopstack.schemas.shelf import (
    AggregatedVisibleItem,
    ConfidenceSummary,
    InventoryMatch,
    OCRFinding,
    ProposedInventoryAction,
    QuantityEstimate,
    ShelfIntelligenceResult,
    ShelfSceneType,
    SpeechIntent,
    VisibleItemInstance,
)
from shopstack.services.expiry_parser import expiry_risk_label, parse_expiry_value
from shopstack.services.speech_intent import parse_speech_intent

_SCENE_LABELS: dict[ShelfSceneType, str] = {
    ShelfSceneType.AUTO: "Auto",
    ShelfSceneType.FRIDGE: "Fridge",
    ShelfSceneType.PANTRY: "Pantry",
    ShelfSceneType.SHOPPING_BAG: "Shopping Bag",
    ShelfSceneType.BATHROOM_CABINET: "Bathroom Cabinet",
    ShelfSceneType.MEDICINE_DRAWER: "Medicine Drawer",
    ShelfSceneType.CLEANING_CUPBOARD: "Cleaning Cupboard",
    ShelfSceneType.BEDROOM: "Bedroom",
    ShelfSceneType.DOCUMENTS: "Documents",
    ShelfSceneType.UTILITY: "Utility",
    ShelfSceneType.OTHER: "Other",
}

_SCENE_DEFAULT_LOCATION: dict[ShelfSceneType, str] = {
    ShelfSceneType.AUTO: "kitchen",
    ShelfSceneType.FRIDGE: "fridge",
    ShelfSceneType.PANTRY: "pantry",
    ShelfSceneType.SHOPPING_BAG: "pantry",
    ShelfSceneType.BATHROOM_CABINET: "bathroom_cabinet",
    ShelfSceneType.MEDICINE_DRAWER: "medicine_drawer",
    ShelfSceneType.CLEANING_CUPBOARD: "cleaning_shelf",
    ShelfSceneType.BEDROOM: "bedroom",
    ShelfSceneType.DOCUMENTS: "bedroom",
    ShelfSceneType.UTILITY: "room",
    ShelfSceneType.OTHER: "room",
}

_MEDICINE_HINTS = (
    "tablet",
    "tabs",
    "syrup",
    "ointment",
    "bandage",
    "crocin",
    "paracetamol",
    "ors",
    "inhaler",
    "strip",
)
_BATHROOM_HINTS = (
    "toothpaste",
    "soap",
    "shampoo",
    "conditioner",
    "razor",
    "deodorant",
    "face wash",
    "wash",
)
_CLEANING_HINTS = (
    "detergent",
    "dishwash",
    "floor cleaner",
    "cleaner",
    "phenyl",
    "garbage",
    "sponge",
)


def analyze_shelf_scene(
    image_path: str | None,
    audio_path: str | None,
    scene_type: str | ShelfSceneType | None,
    providers: Any,
    inventory: InventoryRepo,
    user_id: str = "",
) -> ShelfIntelligenceResult:
    scene = _normalize_scene_type(scene_type)
    result = ShelfIntelligenceResult(
        scene_type=scene,
        scene_label=_SCENE_LABELS.get(scene, "Other"),
        image_path=image_path,
        audio_path=audio_path,
    )

    if not image_path and not audio_path:
        result.warnings.append("No image or audio input provided.")
        return result

    detections: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    ocr_payload: dict[str, Any] = {}
    transcript: dict[str, Any] | None = None

    if image_path:
        detections = _safe_detection(providers, image_path)
        segments = _safe_segmentation(providers, image_path)
        ocr_payload = _safe_ocr(providers, image_path)
        if detections and hasattr(providers, "image_edit"):
            try:
                annotated = providers.image_edit.annotate_image(image_path, detections)
                if annotated:
                    result.annotated_image_path = str(annotated)
            except Exception:
                result.warnings.append("Could not render annotated image.")
        if detections and not result.annotated_image_path:
            # Keep a visible artifact in mock/test mode even if the annotator
            # provider is unavailable in the current runtime.
            result.annotated_image_path = image_path

    if audio_path and hasattr(providers, "stt"):
        try:
            transcript = providers.stt.transcribe(audio_path)
        except Exception:
            transcript = None

    if image_path and audio_path:
        result.perception_mode = "multimodal"
    elif image_path:
        result.perception_mode = "vision"
    else:
        result.perception_mode = "speech"

    if detections and segments:
        result.perception_mode = "detection_segmentation"
    elif detections:
        result.perception_mode = "detection_only"
    elif image_path and ocr_payload:
        result.perception_mode = "ocr_only"

    speech_intent = _build_speech_intent(transcript, scene)
    scene = _infer_scene_type(scene, speech_intent, detections, ocr_payload)
    result.scene_type = scene
    result.scene_label = _SCENE_LABELS.get(scene, "Other")
    result.speech_intent = speech_intent

    if transcript:
        confidence = float(transcript.get("confidence", 0.0) or 0.0)
        result.confidence_summary.speech_confidence = confidence
        if transcript.get("text"):
            result.ocr_findings.append(
                OCRFinding(
                    field_name="speech",
                    raw_text=str(transcript.get("text", "")),
                    value=speech_intent.translated_text,
                    confidence=confidence,
                    source="speech",
                )
            )
    if ocr_payload:
        _populate_ocr_findings(result, ocr_payload)

    instances = _build_instances(
        detections=detections,
        segments=segments,
        ocr_payload=ocr_payload,
        speech_intent=speech_intent,
        scene=scene,
    )
    result.instances = instances
    if not instances and speech_intent.canonical_items:
        result.instances = [
            VisibleItemInstance(
                instance_id=uuid4().hex[:12],
                canonical_name=item,
                display_name=item.replace("_", " ").title(),
                recognition_source="speech",
                detection_confidence=speech_intent.confidence,
                quantity_estimate=QuantityEstimate(value=1.0, unit="unit", confidence=speech_intent.confidence, method="speech"),
                zone_guess=result.scene_label,
                notes=["speech_only_instance"],
            )
            for item in speech_intent.canonical_items
        ]

    aggregates = _aggregate_instances(result.instances)
    _attach_inventory_context(aggregates, result, inventory, scene, user_id)
    result.aggregates = aggregates
    result.inventory_matches = [InventoryMatch.model_validate(match) for match in _build_inventory_matches(aggregates, inventory, scene, user_id)]
    result.proposed_actions = _build_actions(result, inventory, scene, user_id)
    result.confidence_summary = _build_confidence_summary(result, detections, ocr_payload, transcript)
    result.warnings.extend(_scene_warnings(scene, result))
    result.corrections_needed = _build_corrections(result)
    return result


def _normalize_scene_type(scene_type: str | ShelfSceneType | None) -> ShelfSceneType:
    if isinstance(scene_type, ShelfSceneType):
        return scene_type
    raw = (scene_type or "auto").strip().lower().replace(" ", "_")
    mapping = {
        "auto": ShelfSceneType.AUTO,
        "fridge": ShelfSceneType.FRIDGE,
        "pantry": ShelfSceneType.PANTRY,
        "shopping_bag": ShelfSceneType.SHOPPING_BAG,
        "bag": ShelfSceneType.SHOPPING_BAG,
        "grocery_bag": ShelfSceneType.SHOPPING_BAG,
        "bathroom": ShelfSceneType.BATHROOM_CABINET,
        "bathroom_cabinet": ShelfSceneType.BATHROOM_CABINET,
        "medicine": ShelfSceneType.MEDICINE_DRAWER,
        "medicine_drawer": ShelfSceneType.MEDICINE_DRAWER,
        "first_aid": ShelfSceneType.MEDICINE_DRAWER,
        "cleaning": ShelfSceneType.CLEANING_CUPBOARD,
        "cleaning_cupboard": ShelfSceneType.CLEANING_CUPBOARD,
        "bedroom": ShelfSceneType.BEDROOM,
        "documents": ShelfSceneType.DOCUMENTS,
        "document": ShelfSceneType.DOCUMENTS,
        "utility": ShelfSceneType.UTILITY,
    }
    return mapping.get(raw, ShelfSceneType.OTHER if raw not in mapping else mapping[raw])


def _infer_scene_type(
    scene: ShelfSceneType,
    speech_intent: SpeechIntent,
    detections: list[dict[str, Any]],
    ocr_payload: dict[str, Any],
) -> ShelfSceneType:
    if scene != ShelfSceneType.AUTO:
        return scene
    if speech_intent.target_scene != ShelfSceneType.AUTO:
        return speech_intent.target_scene

    haystack = " ".join(
        [
            str(ocr_payload.get("product_name", "")),
            str(ocr_payload.get("brand", "")),
            str(ocr_payload.get("raw_text", "")),
            " ".join(str(d.get("label", "")) for d in detections),
            speech_intent.translated_text,
        ]
    ).lower()

    if any(token in haystack for token in _MEDICINE_HINTS):
        return ShelfSceneType.MEDICINE_DRAWER
    if any(token in haystack for token in _BATHROOM_HINTS):
        return ShelfSceneType.BATHROOM_CABINET
    if any(token in haystack for token in _CLEANING_HINTS):
        return ShelfSceneType.CLEANING_CUPBOARD
    if any(token in haystack for token in ("milk", "curd", "butter", "cheese", "yogurt", "paneer", "eggs", "tomato", "coriander", "leaf", "fruit")):
        return ShelfSceneType.FRIDGE
    if any(token in haystack for token in ("rice", "dal", "flour", "atta", "oil", "spice", "salt", "sugar", "tea", "coffee")):
        return ShelfSceneType.PANTRY
    return ShelfSceneType.AUTO


def _safe_detection(providers: Any, image_path: str) -> list[dict[str, Any]]:
    try:
        detection_provider = getattr(providers, "object_detection", None)
        if detection_provider is None:
            return []
        detections = detection_provider.detect(image_path)
        return [d for d in detections if isinstance(d, dict) and d.get("label")]
    except Exception:
        return []


def _safe_segmentation(providers: Any, image_path: str) -> list[dict[str, Any]]:
    try:
        segmentation_provider = getattr(providers, "segmentation", None)
        if segmentation_provider is None:
            return []
        segments = segmentation_provider.segment(image_path)
        return [s for s in segments if isinstance(s, dict)]
    except Exception:
        return []


def _safe_ocr(providers: Any, image_path: str) -> dict[str, Any]:
    try:
        ocr_provider = getattr(providers, "ocr", None)
        if ocr_provider is None:
            return {}
        payload = ocr_provider.extract(image_path)
        if not isinstance(payload, dict):
            return {}
        raw_product = (
            payload.get("product_name")
            or payload.get("text")
            or payload.get("raw_text")
            or ""
        )
        if not raw_product and (payload.get("error") or payload.get("model")):
            unified = getattr(providers, "unified", None)
            if unified is not None and hasattr(unified, "extract_text"):
                fallback = unified.extract_text(image_path)
                if isinstance(fallback, dict):
                    payload = fallback
        return payload
    except Exception:
        return {}


def _build_speech_intent(transcript: dict[str, Any] | None, scene: ShelfSceneType) -> SpeechIntent:
    if not transcript:
        return SpeechIntent(target_scene=scene)
    return parse_speech_intent(
        str(transcript.get("text", "")),
        language=str(transcript.get("language", "en")),
    ).model_copy(update={"target_scene": scene if scene != ShelfSceneType.AUTO else parse_speech_intent(str(transcript.get("text", ""))).target_scene})


def _populate_ocr_findings(result: ShelfIntelligenceResult, payload: dict[str, Any]) -> None:
    confidence = float(payload.get("confidence", 0.0) or 0.0)
    raw_text = str(payload.get("raw_text", "") or "")
    for field in ("brand", "product_name", "weight", "mrp", "price_paid"):
        value = payload.get(field)
        if value in (None, "", []):
            continue
        result.ocr_findings.append(
            OCRFinding(
                field_name=field,
                raw_text=raw_text,
                value=value,
                confidence=confidence,
                source="ocr",
            )
        )
    expiry_value = payload.get("expiry_date") or payload.get("best_before") or payload.get("use_by")
    expiry = parse_expiry_value(expiry_value)
    if expiry is None and raw_text:
        expiry = parse_expiry_value(raw_text)
    if expiry is not None:
        result.ocr_findings.append(
            OCRFinding(
                field_name="expiry_date",
                raw_text=raw_text,
                value=expiry,
                confidence=confidence,
                source="ocr",
            )
        )


def _build_instances(
    detections: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    ocr_payload: dict[str, Any],
    speech_intent: SpeechIntent,
    scene: ShelfSceneType,
) -> list[VisibleItemInstance]:
    instances: list[VisibleItemInstance] = []
    ocr_name = normalize_item_name(
        str(
            ocr_payload.get("product_name")
            or ocr_payload.get("brand")
            or ocr_payload.get("text")
            or ocr_payload.get("raw_text")
            or ""
        )
    )
    ocr_expiry = parse_expiry_value(
        ocr_payload.get("expiry_date")
        or ocr_payload.get("best_before")
        or ocr_payload.get("use_by")
    )
    ocr_weight = str(ocr_payload.get("weight", "") or "")
    size_result = parse_size(ocr_weight) if ocr_weight else None
    ocr_quantity = float(size_result.normalized_quantity) if size_result and size_result.normalized_quantity is not None else None
    ocr_unit = size_result.normalized_unit if size_result and size_result.normalized_unit else "unit"
    ocr_confidence = float(ocr_payload.get("confidence", 0.0) or 0.0)

    for index, detection in enumerate(detections):
        canonical_name = normalize_item_name(str(detection.get("label", "")))
        if not canonical_name:
            continue
        seg = segments[index] if index < len(segments) else {}
        label_text = str(detection.get("label", ""))
        quantity_value = float(detection.get("quantity", 1.0) or 1.0)
        quantity_unit = "unit"
        quantity_confidence = float(detection.get("confidence", 0.0) or 0.0)
        if ocr_name and ocr_name == canonical_name and ocr_quantity:
            quantity_value = float(ocr_quantity)
            quantity_unit = ocr_unit
            quantity_confidence = max(quantity_confidence, ocr_confidence)
        freshness = _visual_freshness(canonical_name, ocr_expiry, scene)
        instance = VisibleItemInstance(
            instance_id=uuid4().hex[:12],
            canonical_name=canonical_name,
            display_name=canonical_name.replace("_", " ").title(),
            bbox=list(detection.get("bbox") or []),
            mask_ref=str(seg.get("mask") or seg.get("mask_path") or "") or None,
            detection_confidence=float(detection.get("confidence", 0.0) or 0.0),
            segmentation_confidence=float(seg.get("score", 0.0) or 0.0),
            recognition_source="detection",
            quantity_estimate=QuantityEstimate(
                value=quantity_value,
                unit=quantity_unit,
                confidence=max(0.2, min(0.99, quantity_confidence or 0.5)),
                method="ocr" if ocr_name == canonical_name and ocr_quantity else "detection",
            ),
            freshness_visual_score=freshness,
            spoilage_flags=_spoilage_flags(canonical_name, ocr_expiry),
            label_text=label_text,
            expiry_date=ocr_expiry,
            zone_guess=_SCENE_LABELS.get(scene, "Other"),
            notes=[f"segment_score:{seg.get('score', 0.0)}"] if seg else [],
        )
        instances.append(instance)

    if not instances and ocr_name:
        instances.append(
            VisibleItemInstance(
                instance_id=uuid4().hex[:12],
                canonical_name=ocr_name,
                display_name=ocr_name.replace("_", " ").title(),
                bbox=[],
                mask_ref=None,
                detection_confidence=ocr_confidence,
                segmentation_confidence=0.0,
                recognition_source="ocr",
                quantity_estimate=QuantityEstimate(
                    value=float(ocr_quantity or 1.0),
                    unit=ocr_unit,
                    confidence=max(0.35, ocr_confidence or 0.5),
                    method="ocr",
                ),
                freshness_visual_score=_visual_freshness(ocr_name, ocr_expiry, scene),
                spoilage_flags=_spoilage_flags(ocr_name, ocr_expiry),
                label_text=str(ocr_payload.get("raw_text", "") or ocr_name.replace("_", " ")),
                expiry_date=ocr_expiry,
                zone_guess=_SCENE_LABELS.get(scene, "Other"),
                notes=["ocr_only_instance"],
            )
        )

    if speech_intent.canonical_items:
        seen = {instance.canonical_name for instance in instances}
        for canonical_name in speech_intent.canonical_items:
            if canonical_name in seen:
                continue
            instances.append(
                VisibleItemInstance(
                    instance_id=uuid4().hex[:12],
                    canonical_name=canonical_name,
                    display_name=canonical_name.replace("_", " ").title(),
                    bbox=[],
                    mask_ref=None,
                    detection_confidence=speech_intent.confidence,
                    segmentation_confidence=0.0,
                    recognition_source="speech",
                    quantity_estimate=QuantityEstimate(
                        value=1.0,
                        unit="unit",
                        confidence=speech_intent.confidence,
                        method="speech",
                    ),
                    freshness_visual_score=None,
                    label_text=speech_intent.translated_text,
                    zone_guess=_SCENE_LABELS.get(scene, "Other"),
                    notes=["speech_only_signal"],
                )
            )

    return instances


def _aggregate_instances(instances: list[VisibleItemInstance]) -> list[AggregatedVisibleItem]:
    buckets: dict[str, list[VisibleItemInstance]] = defaultdict(list)
    for instance in instances:
        buckets[instance.canonical_name].append(instance)

    aggregates: list[AggregatedVisibleItem] = []
    for canonical_name, group in buckets.items():
        matched_home_quantity = 0.0
        lot_ids: list[str] = []
        default_location = ""
        confidence_values = [i.quantity_estimate.confidence for i in group if i.quantity_estimate]
        if group and group[0].zone_guess:
            default_location = group[0].zone_guess
        estimated_quantity = 0.0
        unit = group[0].quantity_estimate.unit if group[0].quantity_estimate else "unit"
        for inst in group:
            estimated_quantity += inst.quantity_estimate.value or 0.0
            if inst.matched_inventory_lot_id:
                lot_ids.append(inst.matched_inventory_lot_id)

        aggregates.append(
            AggregatedVisibleItem(
                canonical_name=canonical_name,
                display_name=canonical_name.replace("_", " ").title(),
                count=len(group),
                estimated_quantity=round(estimated_quantity, 3),
                unit=unit,
                confidence=round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.0,
                matched_home_quantity=matched_home_quantity,
                delta_from_inventory=round(estimated_quantity - matched_home_quantity, 3),
                recommendation="confirm",
                matched_lot_ids=lot_ids,
                instance_ids=[inst.instance_id for inst in group],
                reasons=[],
                warnings=[],
                proposed_actions=[],
                default_location_id=default_location,
            )
        )
    return aggregates


def _attach_inventory_context(
    aggregates: list[AggregatedVisibleItem],
    result: ShelfIntelligenceResult,
    inventory: InventoryRepo,
    scene: ShelfSceneType,
    user_id: str,
) -> None:
    for aggregate in aggregates:
        comparison = inventory.compare_visible(
            aggregate.canonical_name,
            aggregate.estimated_quantity or 1.0,
            aggregate.unit or "unit",
            user_id=user_id,
        )
        matched = _match_lots(inventory, aggregate.canonical_name, user_id)
        match = InventoryMatch(
            canonical_name=aggregate.canonical_name,
            matched_lot_ids=[lot.lot_id for lot in matched],
            total_quantity_at_home=float(comparison.get("total_quantity_at_home", 0.0) or 0.0),
            use_soon_lot_ids=[lot.lot_id for lot in matched if _is_use_soon(lot)],
            matched_location_ids=[lot.storage_location_id for lot in matched if lot.storage_location_id],
            default_location_id=_SCENE_DEFAULT_LOCATION.get(scene, "room"),
            in_home_inventory=bool(matched),
        )
        result.inventory_matches.append(match)
        aggregate.matched_home_quantity = match.total_quantity_at_home
        aggregate.delta_from_inventory = round(aggregate.estimated_quantity - aggregate.matched_home_quantity, 3)
        aggregate.matched_lot_ids = match.matched_lot_ids
        aggregate.default_location_id = match.default_location_id or aggregate.default_location_id
        aggregate.reasons = _build_reasons(aggregate, match, scene)
        aggregate.warnings = _build_warnings(aggregate, match)
        aggregate.recommendation = _recommendation_for(aggregate, match, scene)
        aggregate.proposed_actions = [_action_for(aggregate, match, scene)]
        if match.matched_lot_ids:
            primary = match.matched_lot_ids[0]
            for instance in result.instances:
                if instance.canonical_name == aggregate.canonical_name:
                    instance.matched_inventory_lot_id = primary
                    break


def _build_inventory_matches(
    aggregates: list[AggregatedVisibleItem],
    inventory: InventoryRepo,
    scene: ShelfSceneType,
    user_id: str,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for aggregate in aggregates:
        comparison = inventory.compare_visible(
            aggregate.canonical_name,
            aggregate.estimated_quantity or 1.0,
            aggregate.unit or "unit",
            user_id=user_id,
        )
        matched = _match_lots(inventory, aggregate.canonical_name, user_id)
        matches.append(
            {
                "canonical_name": aggregate.canonical_name,
                "matched_lot_ids": [lot.lot_id for lot in matched],
                "total_quantity_at_home": float(comparison.get("total_quantity_at_home", 0.0) or 0.0),
                "use_soon_lot_ids": [lot.lot_id for lot in matched if _is_use_soon(lot)],
                "matched_location_ids": [lot.storage_location_id for lot in matched if lot.storage_location_id],
                "default_location_id": _SCENE_DEFAULT_LOCATION.get(scene, "room"),
                "in_home_inventory": bool(matched),
            }
        )
    return matches


def _build_actions(
    result: ShelfIntelligenceResult,
    inventory: InventoryRepo,
    scene: ShelfSceneType,
    user_id: str,
) -> list[ProposedInventoryAction]:
    actions: list[ProposedInventoryAction] = []
    for aggregate in result.aggregates:
        match = next((m for m in result.inventory_matches if m.canonical_name == aggregate.canonical_name), None)
        default_location = _SCENE_DEFAULT_LOCATION.get(scene, "room")
        action = _action_for(aggregate, match, scene)
        lot_id = match.matched_lot_ids[0] if match and match.matched_lot_ids else None
        updates: dict[str, Any] = {}
        requires_confirmation = True
        if action in {"update_quantity", "refill"} and lot_id:
            updates = {"quantity": aggregate.estimated_quantity, "unit": aggregate.unit}
        elif action == "mark_use_soon" and lot_id:
            updates = {"status": "low"}
        elif action == "move_location" and lot_id:
            updates = {"storage_location_id": default_location}
        elif action == "add_new_lot":
            updates = {
                "canonical_name": aggregate.canonical_name,
                "display_name": aggregate.display_name,
                "quantity": aggregate.estimated_quantity or 1.0,
                "unit": aggregate.unit or "unit",
                "storage_location_id": default_location,
                "category": _item_category_hint(aggregate.canonical_name, scene),
            }
        elif action == "confirm":
            requires_confirmation = False
        actions.append(
            ProposedInventoryAction(
                action=action,
                canonical_name=aggregate.canonical_name,
                display_name=aggregate.display_name,
                quantity=aggregate.estimated_quantity or 1.0,
                unit=aggregate.unit or "unit",
                confidence=aggregate.confidence,
                reason="; ".join(aggregate.reasons) if aggregate.reasons else aggregate.recommendation,
                requires_confirmation=requires_confirmation,
                source_instance_ids=aggregate.instance_ids,
                target_location_id=default_location,
                lot_id=lot_id,
                field_updates=updates,
            )
        )
    return actions


def _build_confidence_summary(
    result: ShelfIntelligenceResult,
    detections: list[dict[str, Any]],
    ocr_payload: dict[str, Any],
    transcript: dict[str, Any] | None,
) -> ConfidenceSummary:
    image_scores = [float(d.get("confidence", 0.0) or 0.0) for d in detections]
    overall_scores = image_scores[:]
    if ocr_payload:
        overall_scores.append(float(ocr_payload.get("confidence", 0.0) or 0.0))
    if transcript:
        overall_scores.append(float(transcript.get("confidence", 0.0) or 0.0))
    item_scores = [aggregate.confidence for aggregate in result.aggregates]
    if item_scores:
        overall_scores.extend(item_scores)
    return ConfidenceSummary(
        overall_confidence=round(sum(overall_scores) / len(overall_scores), 2) if overall_scores else 0.0,
        scene_confidence=0.7 if result.scene_type != ShelfSceneType.AUTO else 0.5,
        image_confidence=round(sum(image_scores) / len(image_scores), 2) if image_scores else 0.0,
        speech_confidence=float(transcript.get("confidence", 0.0) or 0.0) if transcript else 0.0,
        needs_review_count=sum(1 for aggregate in result.aggregates if aggregate.confidence < 0.65 or aggregate.warnings),
        items_seen=len(result.instances),
        items_grouped=len(result.aggregates),
    )


def _scene_warnings(scene: ShelfSceneType, result: ShelfIntelligenceResult) -> list[str]:
    warnings: list[str] = []
    if not result.instances:
        warnings.append("No visible items detected.")
    if scene == ShelfSceneType.AUTO:
        warnings.append("Scene type was inferred automatically.")
    if result.speech_intent and result.speech_intent.action == "correct":
        warnings.append("Speech correction detected; review the changed item names.")
    return warnings


def _build_corrections(result: ShelfIntelligenceResult) -> list[str]:
    corrections: list[str] = []
    for aggregate in result.aggregates:
        if aggregate.confidence < 0.55:
            corrections.append(f"Review {aggregate.display_name}: confidence {aggregate.confidence:.2f}.")
        if aggregate.warnings:
            corrections.append(f"{aggregate.display_name}: {'; '.join(aggregate.warnings)}")
    if result.speech_intent and result.speech_intent.notes:
        corrections.append(f"Speech notes: {', '.join(result.speech_intent.notes)}")
    return corrections


def _build_reasons(
    aggregate: AggregatedVisibleItem,
    match: InventoryMatch,
    scene: ShelfSceneType,
) -> list[str]:
    reasons = []
    if match.in_home_inventory:
        reasons.append(f"Already at home: {match.total_quantity_at_home:g} {aggregate.unit}")
    else:
        reasons.append("Not currently in home inventory")
    if scene in (ShelfSceneType.BATHROOM_CABINET, ShelfSceneType.MEDICINE_DRAWER, ShelfSceneType.CLEANING_CUPBOARD):
        reasons.append("Household consumable zone")
    if aggregate.delta_from_inventory > 0:
        reasons.append(f"Visible quantity exceeds tracked quantity by {aggregate.delta_from_inventory:g} {aggregate.unit}")
    elif aggregate.delta_from_inventory < 0:
        reasons.append(f"Tracked quantity exceeds visible estimate by {abs(aggregate.delta_from_inventory):g} {aggregate.unit}")
    return reasons


def _build_warnings(aggregate: AggregatedVisibleItem, match: InventoryMatch) -> list[str]:
    warnings = []
    if aggregate.confidence < 0.6:
        warnings.append("low_confidence")
    if not match.in_home_inventory:
        warnings.append("new_item")
    if match.use_soon_lot_ids:
        warnings.append("use_soon_overlap")
    return warnings


def _recommendation_for(
    aggregate: AggregatedVisibleItem,
    match: InventoryMatch,
    scene: ShelfSceneType,
) -> str:
    if match.use_soon_lot_ids:
        return "use_soon"
    if not match.in_home_inventory:
        return "refill" if scene in (ShelfSceneType.BATHROOM_CABINET, ShelfSceneType.MEDICINE_DRAWER, ShelfSceneType.CLEANING_CUPBOARD) else "add_to_list"
    if abs(aggregate.delta_from_inventory) <= 0.25 * max(match.total_quantity_at_home, 1.0):
        return "confirm"
    return "update"


def _action_for(
    aggregate: AggregatedVisibleItem,
    match: InventoryMatch | None,
    scene: ShelfSceneType,
) -> str:
    if match and match.use_soon_lot_ids:
        return "mark_use_soon"
    if not match or not match.in_home_inventory:
        return "add_new_lot" if scene != ShelfSceneType.SHOPPING_BAG else "add_new_lot"
    if abs(aggregate.delta_from_inventory) <= 0.25 * max(match.total_quantity_at_home, 1.0):
        return "confirm"
    if scene in (ShelfSceneType.BATHROOM_CABINET, ShelfSceneType.MEDICINE_DRAWER, ShelfSceneType.CLEANING_CUPBOARD):
        return "refill"
    return "update_quantity"


def _item_category_hint(canonical_name: str, scene: ShelfSceneType) -> str:
    lowered = canonical_name.replace("_", " ")
    if any(token in lowered for token in _MEDICINE_HINTS) or scene == ShelfSceneType.MEDICINE_DRAWER:
        return "medicine"
    if any(token in lowered for token in _BATHROOM_HINTS) or scene == ShelfSceneType.BATHROOM_CABINET:
        return "personal care"
    if any(token in lowered for token in _CLEANING_HINTS) or scene == ShelfSceneType.CLEANING_CUPBOARD:
        return "cleaning"
    if scene == ShelfSceneType.FRIDGE:
        return "food"
    if scene == ShelfSceneType.PANTRY:
        return "pantry"
    return "household"


def _spoilage_flags(canonical_name: str, expiry_date: date | None) -> list[str]:
    flags: list[str] = []
    if expiry_date is not None:
        risk = expiry_risk_label(expiry_date)
        if risk in {"today", "tomorrow", "soon"}:
            flags.append(f"expiry_{risk}")
        elif risk == "expired":
            flags.append("expired")
    lowered = canonical_name.replace("_", " ")
    if any(token in lowered for token in ("coriander", "mint", "spinach", "lettuce")):
        flags.append("leafy_green")
    if any(token in lowered for token in ("milk", "curd", "paneer")):
        flags.append("perishable")
    return flags


def _visual_freshness(canonical_name: str, expiry_date: date | None, scene: ShelfSceneType) -> float | None:
    if expiry_date is not None:
        risk = expiry_risk_label(expiry_date)
        return {
            "expired": 0.0,
            "today": 0.1,
            "tomorrow": 0.35,
            "soon": 0.55,
            "fine": 0.85,
            "unknown": 0.5,
        }.get(risk, 0.5)
    lowered = canonical_name.replace("_", " ")
    if scene == ShelfSceneType.FRIDGE and any(token in lowered for token in ("milk", "curd", "coriander", "spinach")):
        return 0.7
    return None


def _match_lots(inventory: InventoryRepo, canonical_name: str, user_id: str) -> list[Any]:
    db = getattr(inventory, "db", None)
    if db is None:
        return []
    return [
        lot for lot in db.get_inventory(user_id=user_id)
        if normalize_item_name(lot.canonical_name) == normalize_item_name(canonical_name)
        and lot.status == "active"
    ]


def _is_use_soon(lot: Any) -> bool:
    today = date.today()
    ref = getattr(lot, "label_expiry_date", None) or getattr(lot, "estimated_use_by_date", None)
    if ref is not None and 0 <= (ref - today).days <= 3:
        return True
    return getattr(lot, "status", "") == "low"
