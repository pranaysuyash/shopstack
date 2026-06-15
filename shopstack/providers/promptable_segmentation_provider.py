from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _bbox_to_xyxy(bbox: list[float], width: int, height: int) -> list[float]:
    if not bbox:
        return [0.0, 0.0, float(width), float(height)]
    if max(abs(v) for v in bbox) <= 1.5:
        x1, y1, x2, y2 = bbox
        return [x1 * width, y1 * height, x2 * width, y2 * height]
    return [float(v) for v in bbox[:4]]


def _mask_path_from_result(mask: Any) -> str | None:
    try:
        import numpy as np
        from PIL import Image

        arr = mask.detach().cpu().numpy() if hasattr(mask, "detach") else np.asarray(mask)
        if arr.ndim == 3:
            arr = arr[0]
        arr = (arr > 0.5).astype("uint8") * 255
        fd, out_path = tempfile.mkstemp(prefix="prompt_mask_", suffix=".png")
        os.close(fd)
        Image.fromarray(arr).save(out_path)
        return out_path
    except Exception as exc:
        logger.debug("failed to persist prompt mask: %s", exc)
        return None


class UltralyticsPromptableSegmentationProvider:
    """Promptable segmentation provider backed by Ultralytics SAM-family models.

    This wraps the commercial-allowed primary lane from the promptable
    segmentation benchmark:
    - SAM 2
    - MobileSAM
    - FastSAM
    - SAM 3 comparison lane

    The provider exposes `segment_with_prompts()` for box / point / text
    prompts. The plain `segment()` method intentionally returns a prompt-needed
    error so callers use the promptable path instead of assuming background
    removal semantics.
    """

    name = "promptable_segmentation"
    model_id = ""
    parameter_count = 0.0
    license_note = "commercial-allowed primary lane"
    runtime_type = "ultralytics"
    supports_off_grid = True
    capabilities: set[str] = {"segmentation", "promptable_segmentation"}

    def __init__(
        self,
        model_name: str = "sam2.1_b.pt",
        family: str = "sam",
        device: str = "auto",
    ):
        self._model_name = model_name
        self._family = family
        self._device = device
        self.model_id = model_name
        self._model = None
        self._available = False
        self._error: str | None = None
        self._last_latency_ms: float | None = None
        self._init()

    def _init(self) -> None:
        try:
            from ultralytics import FastSAM, SAM  # noqa: F401
            self._available = True
            self._error = None
        except ImportError:
            self._available = False
            self._error = "ultralytics not installed. Run: uv pip install ultralytics"

    def load(self) -> None:
        if self._model is not None:
            return
        self._load_model()

    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            from ultralytics import FastSAM, SAM

            if self._family == "fastsam":
                self._model = FastSAM(self._model_name)
            else:
                self._model = SAM(self._model_name)
            return True
        except Exception as exc:
            self._error = f"Failed to load promptable segmentation model: {exc}"
            logger.warning("promptable segmentation load failed", exc_info=True)
            return False

    def segment(self, image_path: str) -> list[dict[str, Any]]:
        return [{"error": "Promptable segmentation requires prompts"}]

    def segment_with_prompts(
        self,
        image_path: str,
        *,
        bboxes: list[list[float]] | None = None,
        points: list[list[float]] | None = None,
        labels: list[str] | None = None,
        texts: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if not self._available:
            return [{"error": self._error or "Promptable segmentation not available"}]
        if not os.path.isfile(image_path):
            return [{"error": f"Image file not found: {image_path}"}]
        if not (bboxes or points or labels or texts):
            return [{"error": "Promptable segmentation requires boxes, points, labels, or texts"}]
        if self._model is None and not self._load_model():
            return [{"error": self._error or "Failed to load model"}]

        try:
            from PIL import Image

            image = Image.open(image_path).convert("RGB")
            width, height = image.size
            norm_boxes = [_bbox_to_xyxy(list(box), width, height) for box in (bboxes or [])]
            t0 = time.monotonic()
            kwargs: dict[str, Any] = {}
            if norm_boxes:
                kwargs["bboxes"] = norm_boxes
            if points:
                kwargs["points"] = points
            if labels:
                kwargs["labels"] = labels
            if texts:
                kwargs["texts"] = texts

            results = self._model(image_path, **kwargs)
            elapsed = time.monotonic() - t0
            self._last_latency_ms = round(elapsed * 1000, 1)
            out: list[dict[str, Any]] = []
            result = results[0] if isinstance(results, list) and results else results
            masks = getattr(result, "masks", None)
            boxes = getattr(result, "boxes", None)
            if masks is not None and getattr(masks, "data", None) is not None:
                mask_data = masks.data
                count = len(mask_data) if hasattr(mask_data, "__len__") else 1
                for idx in range(count):
                    mask = mask_data[idx]
                    mask_path = _mask_path_from_result(mask)
                    box = None
                    if boxes is not None and getattr(boxes, "xyxy", None) is not None:
                        try:
                            box_tensor = boxes.xyxy[idx]
                            box = box_tensor.tolist() if hasattr(box_tensor, "tolist") else list(box_tensor)
                        except Exception:
                            box = norm_boxes[idx] if idx < len(norm_boxes) else [0.0, 0.0, float(width), float(height)]
                    else:
                        box = norm_boxes[idx] if idx < len(norm_boxes) else [0.0, 0.0, float(width), float(height)]
                    out.append(
                        {
                            "label": labels[idx] if labels and idx < len(labels) else texts[idx] if texts and idx < len(texts) else "prompted_item",
                            "score": round(float(getattr(boxes, "conf", [0.9] * len(mask_data))[idx]) if boxes is not None and getattr(boxes, "conf", None) is not None and idx < len(boxes.conf) else 0.9, 3),
                            "mask": mask_path,
                            "mask_path": mask_path,
                            "bbox": box[:4] if box else [0.0, 0.0, float(width), float(height)],
                            "latency_ms": self._last_latency_ms,
                        }
                    )
            else:
                # Some promptable flows may return boxes only.
                if boxes is not None and getattr(boxes, "xyxy", None) is not None:
                    for idx, box_tensor in enumerate(boxes.xyxy):
                        box = box_tensor.tolist() if hasattr(box_tensor, "tolist") else list(box_tensor)
                        out.append(
                            {
                                "label": labels[idx] if labels and idx < len(labels) else texts[idx] if texts and idx < len(texts) else "prompted_item",
                                "score": round(float(boxes.conf[idx]) if getattr(boxes, "conf", None) is not None and idx < len(boxes.conf) else 0.9, 3),
                                "mask": None,
                                "mask_path": None,
                                "bbox": box[:4],
                                "latency_ms": self._last_latency_ms,
                            }
                        )
            return out or [{"error": "Promptable segmentation returned no masks"}]
        except Exception as exc:
            logger.warning("Promptable segmentation failed", exc_info=True)
            return [{"error": str(exc)}]

    def healthcheck(self) -> bool:
        return self._available

    @property
    def available(self) -> bool:
        return self._available

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def last_latency_ms(self) -> float | None:
        return self._last_latency_ms

