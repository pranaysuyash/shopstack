from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class MiniCPMVProvider:
    """Local vision provider using MiniCPM-V-2.6 via transformers.

    Provides vision understanding, object detection, and image analysis
    for household items. Falls back gracefully when deps are missing.
    """

    name = "minicpmv"
    model_id = "minicpm-v-8b"
    parameter_count = 8.0
    license_note = "Apache-2.0"
    runtime_type = "transformers"
    supports_off_grid = True
    capabilities: set[str] = {"vision", "object_detection"}

    def __init__(
        self,
        model_name: str = "openbmb/MiniCPM-V-2_6",
        device: str = "auto",
        max_new_tokens: int = 512,
        load_in_4bit: bool = True,
    ):
        self._model_name = model_name
        self._device = device
        self._max_new_tokens = max_new_tokens
        self._load_in_4bit = load_in_4bit
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
                AutoModel,
                AutoProcessor,
            )
            self._available = True
            self._error = None
            logger.info("MiniCPM-V provider initialised (model=%s)", self._model_name)
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
            from transformers import AutoModel, AutoProcessor

            logger.info("Loading MiniCPM-V model %s ...", self._model_name)
            self._processor = AutoProcessor.from_pretrained(
                self._model_name, trust_remote_code=True
            )
            kwargs = {
                "trust_remote_code": True,
                "torch_dtype": torch.bfloat16,
            }
            if self._load_in_4bit and torch.cuda.is_available():
                from transformers import BitsAndBytesConfig
                kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                )
            self._model = AutoModel.from_pretrained(self._model_name, **kwargs)
            if self._device == "auto":
                if torch.cuda.is_available():
                    self._model = self._model.to("cuda")
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    self._model = self._model.to("mps")
            else:
                self._model = self._model.to(self._device)
            self._model.eval()
            logger.info("MiniCPM-V model loaded")
            return True
        except Exception as e:
            self._error = f"Failed to load MiniCPM-V model: {e}"
            logger.warning("MiniCPM-V model load failed", exc_info=True)
            return False

    def understand(self, image_path: str, prompt: str = "") -> dict[str, Any]:
        if not self._available:
            return {"error": self._error or "MiniCPM-V not available", "model": self.name}
        if not os.path.isfile(image_path):
            return {"error": f"Image file not found: {image_path}", "model": self.name}

        if self._model is None and not self._load_model():
            return {"error": self._error or "Failed to load model", "model": self.name}

        try:
            import torch
            from PIL import Image

            t0 = time.monotonic()

            image = Image.open(image_path).convert("RGB")
            msgs = [{"role": "user", "content": [image, prompt or "Describe what you see in this image. List any food items, products, or text visible."]}]

            result = self._model.chat(
                image=image,
                msgs=msgs,
                processor=self._processor,
                max_new_tokens=self._max_new_tokens,
            )

            elapsed = time.monotonic() - t0
            self._last_latency_ms = round(elapsed * 1000, 1)

            return {
                "description": result,
                "model": self._model_name,
                "latency_ms": self._last_latency_ms,
            }
        except Exception as e:
            logger.warning("MiniCPM-V understand failed", exc_info=True)
            return {"error": str(e), "model": self.name}

    def detect(self, image_path: str) -> list[dict[str, Any]]:
        """Detect objects in an image. Uses the VLM's chat capability."""
        result = self.understand(
            image_path,
            prompt="List every food item, product, or object you can see in this image. Format: one item per line with confidence."
        )
        if "error" in result:
            return [result]
        return [{"label": item.strip(), "confidence": 0.5}
                for item in result.get("description", "").split("\n")
                if item.strip()]

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
