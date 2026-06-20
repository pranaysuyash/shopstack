from __future__ import annotations

from collections import defaultdict
from datetime import date
import os
import logging
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from shopstack.domain import normalize_item_name, parse_size
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
from shopstack.providers.image_gen_provider import resolve_detection_bbox

logger = logging.getLogger(__name__)


def _frame_tag(frame_path: str, index: int) -> str:
    stem = Path(frame_path).stem or f"frame_{index:02d}"
    return f"frame:{stem}"


def _first_frame_from_video(video_path: str) -> str | None:
    """Extract the first frame of a video as a temporary PNG.

    Returns the path to the extracted frame, or ``None`` when no
    decoder is available. We prefer ``cv2`` (OpenCV) and fall back to
    ``ffmpeg`` via subprocess. Failure is logged at info level and the
    caller treats it as "no image available".
    """
    if not video_path:
        return None
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        cv2 = None
    if cv2 is not None:
        try:
            cap = cv2.VideoCapture(video_path)
            ok, frame = cap.read()
            cap.release()
            if not ok or frame is None:
                return None
            fd, out_path = tempfile.mkstemp(suffix=".png", prefix="shelf_frame_")
            os.close(fd)
            Path(out_path).unlink(missing_ok=True)
            cv2.imwrite(out_path, frame)
            return out_path
        except Exception as exc:
            logger.info("cv2 frame extraction failed: %s", exc)
            return None
    try:
        import imageio.v3 as iio  # type: ignore[import-not-found]
        from PIL import Image

        for frame in iio.imiter(video_path):
            fd, out_path = tempfile.mkstemp(suffix=".png", prefix="shelf_frame_")
            os.close(fd)
            Path(out_path).unlink(missing_ok=True)
            Image.fromarray(frame).save(out_path)
            return out_path
        return None
    except Exception as exc:
        logger.info("video first-frame extraction failed: %s", exc)
        return None


def _collect_frame_paths(image_path: str | None, video_path: str | None, max_frames: int = 6) -> list[str]:
    """Collect frame paths from an image and/or video.

    If ``image_path`` is provided, it is included as the first frame.
    If ``video_path`` is provided, up to ``max_frames`` frames are
    extracted at regular intervals using ``_extract_video_frames``.

    ``max_frames`` is clamped to the range ``[1, 50]`` to bound
    storage and per-scan latency. Out-of-range or non-positive values
    fall back to the default of 6.

    Returns a list of frame file paths (may be empty).
    """
    safe_max = _clamp_max_frames(max_frames)
    frames: list[str] = []
    if image_path:
        frames.append(image_path)
    if video_path:
        frames.extend(_extract_video_frames(video_path, max_frames=safe_max))
    return frames


def _clamp_max_frames(value: int | float | None, default: int = 6, lo: int = 1, hi: int = 50) -> int:
    """Clamp a user-supplied max-frames value to a safe range.

    Defensive helper so callers (UI sliders, scripted APIs) cannot
    request zero frames (would skip video analysis) or 10,000 frames
    (would explode the temp dir). ``None``/non-numeric → ``default``.
    """
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if n < lo:
        return lo
    if n > hi:
        return hi
    return n


def _extract_video_frames(video_path: str, max_frames: int = 6) -> list[str]:
    """Extract up to ``max_frames`` frames from a video at regular intervals.

    Uses ``cv2`` (OpenCV) when available, otherwise falls back to ``ffmpeg``
    or ``imageio``. Returns a list of temporary PNG file paths.
    """
    if not video_path:
        return []
    # Try OpenCV first
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError:
        cv2 = None
    frames: list[str] = []
    if cv2 is not None:
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return []
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            fps = cap.get(cv2.CAP_PROP_FPS)
            step = max(1, int(round(fps))) if fps > 0 else max(1, frame_count // max_frames if frame_count else 1)
            frame_index = 0
            captured = 0
            while captured < max_frames:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                ok, frame = cap.read()
                if not ok:
                    break
                fd, out_path = tempfile.mkstemp(suffix=".png", prefix="shelf_frame_")
                os.close(fd)
                Path(out_path).unlink(missing_ok=True)
                cv2.imwrite(out_path, frame)
                frames.append(out_path)
                captured += 1
                frame_index += step
                if frame_count and frame_index >= frame_count:
                    break
            cap.release()
            if frames:
                return frames
        except Exception as exc:
            logger.info("cv2 frame extraction failed: %s", exc)
            # fall through to ffmpeg fallback
        finally:
            try:
                cap.release()
            except Exception:
                pass
    # ffmpeg fallback
    try:
        frames.clear()
        import imageio.v3 as iio  # type: ignore[import-not-found]
        from PIL import Image
        for idx, frame in enumerate(iio.imiter(video_path)):
            if idx >= max_frames:
                break
            fd, out_path = tempfile.mkstemp(suffix=".png", prefix="shelf_frame_")
            os.close(fd)
            Path(out_path).unlink(missing_ok=True)
            Image.fromarray(frame).save(out_path)
            frames.append(out_path)
        return frames
    except Exception as exc:
        logger.info("imageio frame extraction failed: %s", exc)
        return []


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


def _candidate_ground_prompts(
    detections: list[dict[str, Any]],
    speech_intent: SpeechIntent,
    ocr_payload: dict[str, Any],
) -> list[str]:
    prompts: list[str] = []
    seen: set[str] = set()

    def _add(prompt: str) -> None:
        canonical = normalize_item_name(prompt)
        if not canonical or canonical in seen:
            return
        seen.add(canonical)
        prompts.append(canonical.replace("_", " "))

    for item in speech_intent.canonical_items:
        _add(item)
    for det in detections:
        _add(str(det.get("label", "")))
    for key in ("product_name", "brand", "text", "raw_text"):
        _add(str(ocr_payload.get(key, "")))
    return prompts[:4]


def _run_frame_perception(
    providers: Any,
    frame_path: str,
    speech_intent: SpeechIntent,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any], bool]:
    detections = _safe_detection(providers, frame_path)
    ocr_payload = _safe_ocr(providers, frame_path)

    grounding_prompts = _candidate_ground_prompts(detections, speech_intent, ocr_payload)
    if grounding_prompts:
        grounded = _safe_grounding(providers, frame_path, grounding_prompts)
        if grounded:
            detections.extend(grounded)

    segments = _safe_segmentation(providers, frame_path)
    promptable_segments = _safe_promptable_segmentation(providers, frame_path, detections, speech_intent)
    if promptable_segments:
        segments = promptable_segments

    return detections, segments, ocr_payload, bool(promptable_segments)


def analyze_shelf_scene(
    image_path: str | None,
    video_path: str | None,
    audio_path: str | None,
    scene_type: str | ShelfSceneType | None,
    providers: Any,
    inventory: InventoryRepo,
    user_id: str = "",
    max_frames: int = 6,
) -> ShelfIntelligenceResult:
    """Run the full shelf-intelligence pipeline on the supplied inputs.

    Accepts at least one of ``image_path``, ``video_path``, ``audio_path``.
    When ``video_path`` is provided, up to ``max_frames`` frames are
    extracted at regular intervals (see :func:`_collect_frame_paths`)
    and every frame is merged into one household-memory result. The
    first frame anchors the annotated preview, while later frames catch
    objects that were briefly visible during the sweep. ``max_frames``
    is clamped to ``[1, 50]`` to bound per-scan latency and storage.

    The returned ``ShelfIntelligenceResult`` carries the full provenance:
    ``image_path``, ``video_path``, ``audio_path``, ``frame_paths``
    (video frames only), and ``frame_count`` (the size of that list).
    """
    safe_max_frames = _clamp_max_frames(max_frames)
    scene = _normalize_scene_type(scene_type)
    result = ShelfIntelligenceResult(
        scene_type=scene,
        scene_label=_SCENE_LABELS.get(scene, "Other"),
        image_path=image_path,
        video_path=video_path,
        audio_path=audio_path,
    )

    if not image_path and not video_path and not audio_path:
        result.warnings.append("No image, video, or audio input provided.")
        return result

    frame_paths: list[str] = _collect_frame_paths(image_path, video_path, max_frames=safe_max_frames)
    if not frame_paths and video_path:
        fallback_frame = _first_frame_from_video(video_path)
        if fallback_frame:
            frame_paths = [fallback_frame]
    if frame_paths and not image_path:
        result.image_path = frame_paths[0]
    if image_path and not result.image_path:
        result.image_path = image_path
    if video_path:
        result.video_path = video_path
        result.frame_paths = frame_paths
        result.frame_count = len(frame_paths)

    transcript: dict[str, Any] | None = None

    if audio_path and hasattr(providers, "stt"):
        try:
            from shopstack.eval.recorder import CAP_STT, SHAPE_TEXT, record_model_call

            with record_model_call(
                domain_route="shelf_intelligence",
                capability=CAP_STT,
                capability_expected_shape=SHAPE_TEXT,
            ) as rec:
                rec.set_prompt(f"transcribe:{audio_path}")
                transcript = providers.stt.transcribe(audio_path)
                rec.set_output(str(transcript))
        except Exception:
            transcript = None

    speech_intent = _build_speech_intent(transcript, scene)
    frame_records: list[dict[str, Any]] = []
    all_detections: list[dict[str, Any]] = []
    best_ocr_payload: dict[str, Any] = {}
    best_ocr_confidence = -1.0
    primary_frame_image = frame_paths[0] if frame_paths else result.image_path
    primary_detections: list[dict[str, Any]] = []
    used_promptable = False
    used_detection = False
    used_segmentation = False

    for index, frame_path in enumerate(frame_paths or ([result.image_path] if result.image_path else [])):
        frame_detections, frame_segments, frame_ocr, promptable_used = _run_frame_perception(
            providers,
            frame_path,
            speech_intent,
        )
        if not primary_detections:
            primary_detections = list(frame_detections)
            primary_frame_image = frame_path
        frame_records.append(
            {
                "frame_path": frame_path,
                "detections": frame_detections,
                "segments": frame_segments,
                "ocr": frame_ocr,
                "frame_tag": _frame_tag(frame_path, index),
            }
        )
        all_detections.extend(frame_detections)
        used_promptable = used_promptable or promptable_used
        used_detection = used_detection or bool(frame_detections)
        used_segmentation = used_segmentation or bool(frame_segments)
        ocr_confidence = float(frame_ocr.get("confidence", 0.0) or 0.0)
        if frame_ocr and ocr_confidence >= best_ocr_confidence:
            best_ocr_confidence = ocr_confidence
            best_ocr_payload = frame_ocr

    if primary_frame_image and audio_path:
        result.perception_mode = "multimodal"
    elif primary_frame_image:
        result.perception_mode = "vision"
    else:
        result.perception_mode = "speech"

    if used_promptable:
        result.perception_mode = "promptable_segmentation"
    elif used_detection and used_segmentation:
        result.perception_mode = "detection_segmentation"
    elif used_detection:
        result.perception_mode = "detection_only"
    elif primary_frame_image and best_ocr_payload:
        result.perception_mode = "ocr_only"

    if result.frame_count > 1 and result.perception_mode != "speech":
        result.perception_mode = f"video_{result.perception_mode}"

    scene = _infer_scene_type(scene, speech_intent, all_detections, best_ocr_payload)
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
    if best_ocr_payload:
        _populate_ocr_findings(result, best_ocr_payload)

    instances: list[VisibleItemInstance] = []
    for record in frame_records:
        instances.extend(
            _build_instances(
                detections=record["detections"],
                segments=record["segments"],
                ocr_payload=record["ocr"],
                speech_intent=speech_intent,
                scene=scene,
                frame_tag=record["frame_tag"],
            )
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
                notes=["speech_only_instance", "frame:speech"],
            )
            for item in speech_intent.canonical_items
        ]

    aggregates = _aggregate_instances(result.instances)
    _attach_inventory_context(aggregates, result, inventory, scene, user_id)
    result.aggregates = aggregates
    result.inventory_matches = [InventoryMatch.model_validate(match) for match in _build_inventory_matches(aggregates, inventory, scene, user_id)]
    result.proposed_actions = _build_actions(result, inventory, scene, user_id)
    result.confidence_summary = _build_confidence_summary(result, all_detections, best_ocr_payload, transcript)
    result.warnings.extend(_scene_warnings(scene, result))
    result.corrections_needed = _build_corrections(result)
    # ── Condition / damage detection hook (Task 4) ──
    # After inventory matches are known, scan matched lots for any
    # existing open condition issues. If a matched lot has open
    # damage/expired issues, surface a warning so the operator knows
    # the shelf scan is interacting with a problem item.
    if result.inventory_matches:
        try:
            from shopstack.services.condition import get_lot_condition
            db = getattr(inventory, "db", None)
            if db is not None:
                for match in result.inventory_matches:
                    for lot_id in match.matched_lot_ids:
                        agg = get_lot_condition(db, lot_id, include_closed=False)
                        if agg.has_open_issue and agg.highest_severity.value in {"broken", "spoiled"}:
                            result.warnings.append(
                                f"⚠ {match.canonical_name}: open {agg.highest_severity.value} issue ({agg.occurrences}x, {agg.dominant_kind.value})."
                            )
        except Exception as exc:
            # Best-effort: never let the condition hook break the scan.
            logger = __import__("logging").getLogger(__name__)
            logger.debug("condition hook failed: %s", exc)
    if primary_frame_image and primary_detections and not result.annotated_image_path:
        result.annotated_image_path = _annotate_home_scan(primary_frame_image, primary_detections, providers)

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
        from shopstack.eval.recorder import record_model_call
        with record_model_call(
            domain_route="shelf_intelligence",
            capability="object_detection",
            capability_expected_shape="structured",
        ) as rec:
            rec.set_prompt(f"detect:{image_path}")
            detections = detection_provider.detect(image_path)
            rec.set_output(str(detections))
        return [d for d in detections if isinstance(d, dict) and d.get("label")]
    except Exception as exc:  # noqa: BLE001
        # Item #5 (motto_v3 §0.6 risk-based verification): a
        # silent return on provider failure left the user
        # with no detections AND no audit trail. We now log
        # the failure at WARNING so the operator can see it
        # in the logs and the future /health/ui error surface
        # can pick it up. The empty-list return preserves
        # the existing contract: the rest of the scan still
        # completes, the user just doesn't get fake detections.
        logger.warning(
            "shelf_intelligence._safe_detection: object_detection "
            "failed for image=%r: %s",
            image_path, exc,
        )
        return []


def _safe_segmentation(providers: Any, image_path: str) -> list[dict[str, Any]]:
    try:
        segmentation_provider = getattr(providers, "segmentation", None)
        if segmentation_provider is None:
            return []
        from shopstack.eval.recorder import record_model_call
        with record_model_call(
            domain_route="shelf_intelligence",
            capability="segmentation",
            capability_expected_shape="structured",
        ) as rec:
            rec.set_prompt(f"segment:{image_path}")
            segments = segmentation_provider.segment(image_path)
            rec.set_output(str(segments))
        return [s for s in segments if isinstance(s, dict)]
    except Exception as exc:  # noqa: BLE001
        # Item #5 (motto_v3 §0.6): see _safe_detection for the
        # log-on-failure rationale. Same pattern across all
        # three helpers so a future operator dashboard can
        # surface a single shelf-scan failure uniformly.
        logger.warning(
            "shelf_intelligence._safe_segmentation: segmentation "
            "failed for image=%r: %s",
            image_path, exc,
        )
        return []


def _safe_promptable_segmentation(
    providers: Any,
    image_path: str,
    detections: list[dict[str, Any]],
    speech_intent: SpeechIntent,
) -> list[dict[str, Any]]:
    try:
        provider = getattr(providers, "promptable_segmentation", None)
        if provider is None or not image_path:
            return []
        segment_with_prompts = getattr(provider, "segment_with_prompts", None)
        if not callable(segment_with_prompts):
            return []
        boxes = [list(d.get("bbox") or []) for d in detections if d.get("bbox")]
        labels = [str(d.get("label", "")) for d in detections if d.get("bbox")]
        texts = speech_intent.canonical_items or []
        segments = segment_with_prompts(image_path, bboxes=boxes or None, labels=labels or None, texts=texts or None)
        if isinstance(segments, list):
            return [seg for seg in segments if isinstance(seg, dict)]
        return []
    except Exception:
        return []


def _safe_grounding(providers: Any, image_path: str, prompts: list[str]) -> list[dict[str, Any]]:
    try:
        grounding_provider = getattr(providers, "grounding", None)
        if grounding_provider is None:
            return []
        from shopstack.eval.recorder import record_model_call
        grounded: list[dict[str, Any]] = []
        with record_model_call(
            domain_route="shelf_intelligence",
            capability="grounding",
            capability_expected_shape="structured",
        ) as rec:
            rec.set_prompt(f"ground:{image_path}:{prompts}")
            for prompt in prompts:
                if not prompt:
                    continue
                result = grounding_provider.ground(image_path, prompt)
                if isinstance(result, dict) and result.get("found"):
                    grounded.append(
                        {
                            "label": result.get("label") or prompt,
                            "confidence": float(result.get("confidence", 0.0) or 0.0),
                            "bbox": list(result.get("bbox") or []),
                            "class_id": len(grounded),
                        }
                    )
            rec.set_output(str(grounded))
        return grounded
    except Exception:
        return []


def _safe_ocr(providers: Any, image_path: str) -> dict[str, Any]:
    try:
        ocr_provider = getattr(providers, "ocr", None)
        if ocr_provider is None:
            return {}
        from shopstack.eval.recorder import record_model_call
        with record_model_call(
            domain_route="shelf_intelligence",
            capability="ocr_extraction",
            capability_expected_shape="structured",
        ) as rec:
            rec.set_prompt(f"ocr:{image_path}")
            payload = ocr_provider.extract(image_path)
            rec.set_output(str(payload))
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
    except Exception as exc:  # noqa: BLE001
        # Item #5 (motto_v3 §0.6): see _safe_detection for the
        # log-on-failure rationale.
        logger.warning(
            "shelf_intelligence._safe_ocr: ocr failed for "
            "image=%r: %s",
            image_path, exc,
        )
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
    frame_tag: str = "",
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
            source_label=frame_tag.removeprefix("frame:") if frame_tag else "",
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
            notes=(
                [f"segment_score:{seg.get('score', 0.0)}"]
                if seg
                else []
            )
            + ([frame_tag] if frame_tag else []),
        )
        instances.append(instance)

    if not instances and ocr_name:
        instances.append(
            VisibleItemInstance(
                instance_id=uuid4().hex[:12],
                canonical_name=ocr_name,
                display_name=ocr_name.replace("_", " ").title(),
                source_label=frame_tag.removeprefix("frame:") if frame_tag else "",
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
                notes=(["ocr_only_instance"] + ([frame_tag] if frame_tag else [])),
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
                    source_label=frame_tag.removeprefix("frame:") if frame_tag else "",
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
                    notes=(["speech_only_signal"] + ([frame_tag] if frame_tag else [])),
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
        frame_tags: set[str] = set()
        for inst in group:
            estimated_quantity += inst.quantity_estimate.value or 0.0
            if inst.matched_inventory_lot_id:
                lot_ids.append(inst.matched_inventory_lot_id)
            for note in inst.notes:
                if note.startswith("frame:"):
                    frame_tags.add(note.split(":", 1)[1])

        aggregates.append(
            AggregatedVisibleItem(
                canonical_name=canonical_name,
                display_name=canonical_name.replace("_", " ").title(),
                count=len(group),
                frame_hits=len(frame_tags) or len(group),
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
    if result.frame_count > 1:
        warnings.append(f"Video sweep merged {result.frame_count} frame(s).")
    if result.speech_intent and result.speech_intent.action == "correct":
        warnings.append("Speech correction detected; review the changed item names.")
    return warnings


def _annotate_home_scan(image_path: str, detections: list[dict[str, Any]], providers: Any) -> str:
    if hasattr(providers, "image_edit"):
        try:
            annotated = providers.image_edit.annotate_image(image_path, detections)
            if annotated:
                return str(annotated)
        except Exception:
            pass

    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception:
        return image_path

    try:
        with Image.open(image_path) as img:
            img = img.convert("RGB")
            draw = ImageDraw.Draw(img)
            width, height = img.size
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
            for idx, det in enumerate(detections[:12], start=1):
                bbox = resolve_detection_bbox(det, width, height)
                if not bbox:
                    continue
                x1 = int(bbox[0] * width)
                y1 = int(bbox[1] * height)
                x2 = int(bbox[2] * width)
                y2 = int(bbox[3] * height)
                color = (255, 139, 61)
                draw.rectangle([x1, y1, x2, y2], outline=color, width=3)
                label = str(det.get("label") or f"item {idx}")
                score = det.get("score")
                caption = f"{idx}. {label}"
                if isinstance(score, (int, float)):
                    caption += f" {float(score):.2f}"
                text_y = max(0, y1 - 14)
                text_bbox = draw.textbbox((x1, text_y), caption, font=font)
                label_pad = 4
                draw.rectangle(
                    [text_bbox[0] - label_pad, text_bbox[1] - label_pad, text_bbox[2] + label_pad, text_bbox[3] + label_pad],
                    fill=color,
                )
                draw.text((x1, text_y), caption, fill="white", font=font)
            out_dir = Path(tempfile.mkdtemp(prefix="shopstack_home_scan_"))
            out_path = out_dir / f"{Path(image_path).stem}_annotated.png"
            img.save(out_path)
            return str(out_path)
    except Exception:
        return image_path


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
