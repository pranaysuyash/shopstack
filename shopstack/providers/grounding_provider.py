from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class GroundingDINOProvider:
    """Visual grounding provider using Grounding DINO via transformers.

    Grounding DINO (IDEA-Research/grounding-dino-tiny, ~43M params) is an
    open-set object detector that takes an image and a free-form text query
    (e.g. "a red apple on the counter") and returns bounding boxes with
    confidence scores for objects matching the query.

    Provides the ``ground()`` method to support visual grounding tasks:
    - "Where is the tomato in this image?" → bbox
    - "Find the milk packet" → bbox with confidence
    - "Point to the dal" → bbox + label match

    Falls back gracefully when deps are missing.
    """

    name = "grounding_dino"
    model_id = "grounding-dino-tiny"
    parameter_count = 0.043  # 43M params
    license_note = "Apache-2.0"
    runtime_type = "transformers"
    supports_off_grid = True
    capabilities: set[str] = {"grounding"}

    def __init__(
        self,
        model_name: str = "IDEA-Research/grounding-dino-tiny",
        device: str = "auto",
        box_threshold: float = 0.3,
        text_threshold: float = 0.25,
    ):
        self._model_name = model_name
        self._device = device
        self._box_threshold = box_threshold
        self._text_threshold = text_threshold
        self._model = None
        self._processor = None
        self._available = False
        self._error: str | None = None
        self._last_latency_ms: float | None = None
        self._init()

    def _init(self) -> None:
        try:
            import torch  # noqa: F401
            from transformers import (  # noqa: F401
                AutoModelForZeroShotObjectDetection,
                AutoProcessor,
            )
            self._available = True
            self._error = None
            logger.info(
                "GroundingDINO provider initialised (model=%s)",
                self._model_name,
            )
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch"
            )
            self._available = False

    def load(self) -> None:
        if self._model is not None:
            return
        self._load_model()

    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            import torch
            from transformers import (
                AutoModelForZeroShotObjectDetection,
                AutoProcessor,
            )

            logger.info("Loading GroundingDINO model %s ...", self._model_name)
            self._processor = AutoProcessor.from_pretrained(self._model_name)
            self._model = AutoModelForZeroShotObjectDetection.from_pretrained(
                self._model_name,
                torch_dtype=torch.float32,
            )
            if self._device == "auto":
                if torch.cuda.is_available():
                    self._model = self._model.to("cuda")
                elif (
                    hasattr(torch.backends, "mps")
                    and torch.backends.mps.is_available()
                ):
                    self._model = self._model.to("mps")
            else:
                self._model = self._model.to(self._device)
            self._model.eval()
            logger.info("GroundingDINO model loaded (%.0fM params)", self.parameter_count * 1000)
            return True
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch"
            )
            return False
        except Exception as e:
            self._error = f"Failed to load GroundingDINO model: {e}"
            logger.warning("GroundingDINO model load failed", exc_info=True)
            return False

    def ground(self, image_path: str, text_prompt: str) -> dict[str, Any]:
        """Ground a text query in an image and return bounding box results.

        Args:
            image_path: Path to the image file.
            text_prompt: Free-form text query describing the object to find,
                e.g. "tomato", "a red apple", "milk packet on the shelf".

        Returns:
            Dict with keys:
                - ``found``: bool — whether any object matching the query was found.
                - ``bbox``: list[float] — normalized [xmin, ymin, xmax, ymax] or empty list.
                - ``confidence``: float — highest matching confidence score (0-1).
                - ``label``: str — matched label text.
                - ``all_detections``: list[dict] — all detections with their bbox, label, score.
                - ``latency_ms``: float — inference time in milliseconds.
                - ``model``: str — model identifier.
        """
        if not self._available:
            return {
                "found": False,
                "bbox": [],
                "confidence": 0.0,
                "label": "",
                "all_detections": [],
                "error": self._error or "GroundingDINO not available",
                "model": self.name,
            }
        if not os.path.isfile(image_path):
            return {
                "found": False,
                "bbox": [],
                "confidence": 0.0,
                "label": "",
                "all_detections": [],
                "error": f"Image file not found: {image_path}",
                "model": self.name,
            }

        if self._model is None and not self._load_model():
            return {
                "found": False,
                "bbox": [],
                "confidence": 0.0,
                "label": "",
                "all_detections": [],
                "error": self._error or "Failed to load model",
                "model": self.name,
            }

        try:
            import torch
            from PIL import Image

            t0 = time.monotonic()

            if not text_prompt or not text_prompt.strip():
                return {
                    "found": False,
                    "bbox": [],
                    "confidence": 0.0,
                    "label": "",
                    "all_detections": [],
                    "error": "Empty text prompt",
                    "model": self.name,
                }

            image = Image.open(image_path).convert("RGB")
            inputs = self._processor(
                images=image,
                text=text_prompt,
                return_tensors="pt",
            )
            # Keep CPU copy of input_ids for post-processing
            input_ids = inputs["input_ids"]

            # Move inputs to the correct device, and keep floating point tensors
            # aligned with the model dtype. GroundingDINO loads in bf16 on our
            # Modal path, while processors default to float32 pixel values.
            if hasattr(self._model, "device"):
                model_device = self._model.device
                model_dtype = None
                try:
                    model_dtype = next(self._model.parameters()).dtype
                except Exception:
                    model_dtype = None

                moved_inputs = {}
                for key, value in inputs.items():
                    if not hasattr(value, "to"):
                        moved_inputs[key] = value
                        continue
                    if key == "pixel_values" and model_dtype is not None:
                        moved_inputs[key] = value.to(device=model_device, dtype=model_dtype)
                    else:
                        moved_inputs[key] = value.to(model_device)
                inputs = moved_inputs

            with torch.no_grad():
                outputs = self._model(**inputs)

            results = self._processor.post_process_grounded_object_detection(
                outputs,
                input_ids,
                threshold=self._box_threshold,
                text_threshold=self._text_threshold,
                target_sizes=[(image.height, image.width)],
            )

            elapsed = time.monotonic() - t0
            self._last_latency_ms = round(elapsed * 1000, 1)

            boxes = results[0].get("boxes", [])
            labels = results[0].get("labels", [])
            scores = results[0].get("scores", [])

            # Build detections list, normalising bbox to [xmin, ymin, xmax, ymax]
            all_detections = []
            for i in range(len(boxes)):
                box_tensor = boxes[i]
                box = box_tensor.tolist() if hasattr(box_tensor, "tolist") else list(box_tensor)
                all_detections.append({
                    "bbox": [
                        round(float(box[0]), 3),
                        round(float(box[1]), 3),
                        round(float(box[2]), 3),
                        round(float(box[3]), 3),
                    ],
                    "label": labels[i] if i < len(labels) else "",
                    "score": round(float(scores[i]), 4) if i < len(scores) else 0.0,
                })

            if all_detections:
                # Best detection is the one with highest score
                best = max(all_detections, key=lambda d: d["score"])
                return {
                    "found": True,
                    "bbox": best["bbox"],
                    "confidence": best["score"],
                    "label": best["label"],
                    "all_detections": all_detections,
                    "latency_ms": self._last_latency_ms,
                    "model": self._model_name,
                }

            return {
                "found": False,
                "bbox": [],
                "confidence": 0.0,
                "label": text_prompt,
                "all_detections": [],
                "latency_ms": self._last_latency_ms,
                "model": self._model_name,
            }

        except Exception as e:
            logger.warning("GroundingDINO inference failed", exc_info=True)
            return {
                "found": False,
                "bbox": [],
                "confidence": 0.0,
                "label": "",
                "all_detections": [],
                "error": str(e),
                "model": self.name,
            }

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
