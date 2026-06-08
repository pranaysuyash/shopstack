from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class RMBGSegmentationProvider:
    """Segmentation provider using RMBG-1.4 via transformers.

    Provides background removal and segmentation for item card images.
    Falls back gracefully when deps are missing.
    """

    name = "rmbg"
    model_id = "rmbg-1.4"
    parameter_count = 0.3
    license_note = "Apache-2.0"
    runtime_type = "transformers"
    supports_off_grid = True
    capabilities: set[str] = {"segmentation"}

    def __init__(
        self,
        model_name: str = "briaai/RMBG-1.4",
        device: str = "auto",
    ):
        self._model_name = model_name
        self._device = device
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
                AutoModelForImageSegmentation,
                AutoImageProcessor,
            )
            self._available = True
            self._error = None
            logger.info("RMBG provider initialised (model=%s)", self._model_name)
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
            from transformers import AutoModelForImageSegmentation, AutoImageProcessor

            logger.info("Loading RMBG model %s ...", self._model_name)
            self._processor = AutoImageProcessor.from_pretrained(self._model_name)
            self._model = AutoModelForImageSegmentation.from_pretrained(
                self._model_name,
                torch_dtype=torch.bfloat16,
            )
            if self._device == "auto":
                if torch.cuda.is_available():
                    self._model = self._model.to("cuda")
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    self._model = self._model.to("mps")
            else:
                self._model = self._model.to(self._device)
            self._model.eval()
            logger.info("RMBG model loaded")
            return True
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch"
            )
            return False
        except Exception as e:
            self._error = f"Failed to load RMBG model: {e}"
            logger.warning("RMBG model load failed", exc_info=True)
            return False

    def segment(self, image_path: str) -> list[dict[str, Any]]:
        """Segment an image and return mask data.

        Returns a list of detected segments with masks and bounding boxes.
        For RMBG-1.4, outputs a single background-removal mask.
        """
        if not self._available:
            return [{"error": self._error or "RMBG not available"}]
        if not os.path.isfile(image_path):
            return [{"error": f"Image file not found: {image_path}"}]

        if self._model is None and not self._load_model():
            return [{"error": self._error or "Failed to load model"}]

        try:
            import torch
            from PIL import Image

            t0 = time.monotonic()

            image = Image.open(image_path).convert("RGB")
            inputs = self._processor(images=image, return_tensors="pt")
            if torch.cuda.is_available():
                inputs = {k: v.to("cuda") for k, v in inputs.items()}
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                inputs = {k: v.to("mps") for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model(**inputs)
                # The model outputs a predicted mask
                mask = torch.sigmoid(outputs.pred_masks[0, 0]).cpu().numpy()

            elapsed = time.monotonic() - t0
            self._last_latency_ms = round(elapsed * 1000, 1)

            height, width = mask.shape
            # Find bounding box around the foreground
            import numpy as np
            fg_pixels = np.argwhere(mask > 0.5)
            if len(fg_pixels) > 0:
                y1, x1 = fg_pixels.min(axis=0)
                y2, x2 = fg_pixels.max(axis=0)
                bbox = [
                    round(x1 / width, 3),
                    round(y1 / height, 3),
                    round(x2 / width, 3),
                    round(y2 / height, 3),
                ]
            else:
                bbox = [0.0, 0.0, 1.0, 1.0]

            return [{
                "label": "foreground",
                "score": round(float(mask.mean()), 3),
                "mask": None,  # mask data too large for JSON
                "bbox": bbox,
                "latency_ms": self._last_latency_ms,
            }]
        except Exception as e:
            logger.warning("RMBG segmentation failed", exc_info=True)
            return [{"error": str(e)}]

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
