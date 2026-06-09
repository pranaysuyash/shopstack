from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)


class GlmOCRProvider:
    """OCR / receipt text extraction provider using GLM-OCR via transformers.

    GLM-OCR (zai-org/GLM-OCR, 0.9B params) is a vision-language model
    specialised for document OCR and text extraction from images.
    Uses the GlmOcrForConditionalGeneration architecture with Glm46VProcessor.
    Requires torchvision (for image processing) and transformers >= 5.10.
    """

    name = "glm_ocr"
    model_id = "glm-ocr-0.9b"
    parameter_count = 0.9
    license_note = "MIT"
    runtime_type = "transformers"
    supports_off_grid = True
    capabilities: set[str] = {"ocr"}

    def __init__(
        self,
        model_name: str = "zai-org/GLM-OCR",
        device: str = "auto",
        max_new_tokens: int = 1024,
    ):
        self._model_name = model_name
        self._device = device
        self._max_new_tokens = max_new_tokens
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
                Glm46VProcessor,
                GlmOcrForConditionalGeneration,
            )
            self._available = True
            self._error = None
            logger.info("GLM-OCR provider initialised (model=%s)", self._model_name)
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch torchvision"
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
            from transformers import Glm46VProcessor, GlmOcrForConditionalGeneration

            logger.info("Loading GLM-OCR model %s ...", self._model_name)
            self._processor = Glm46VProcessor.from_pretrained(self._model_name)
            self._model = GlmOcrForConditionalGeneration.from_pretrained(
                self._model_name,
                torch_dtype=torch.bfloat16,
                device_map="auto" if self._device == "auto" else None,
                low_cpu_mem_usage=True,
            )
            if self._device != "auto":
                self._model = self._model.to(self._device)
            self._model.eval()
            logger.info("GLM-OCR model loaded (%.0fM params)", self.parameter_count * 1000)
            return True
        except ImportError as e:
            self._error = (
                f"Missing dependency: {e}. "
                "Run: uv pip install transformers torch torchvision"
            )
            return False
        except Exception as e:
            self._error = f"Failed to load GLM-OCR model: {e}"
            logger.warning("GLM-OCR model load failed", exc_info=True)
            return False

    def extract(self, image_path: str) -> dict[str, Any]:
        """Extract text from a receipt or document image using GLM-OCR.

        Returns the extracted text as raw_text, along with metadata.
        """
        if not self._available:
            return {"error": self._error or "GLM-OCR not available", "model": self.name}
        if not os.path.isfile(image_path):
            return {"error": f"Image file not found: {image_path}", "model": self.name}

        if self._model is None and not self._load_model():
            return {"error": self._error or "Failed to load model", "model": self.name}

        try:
            from PIL import Image

            t0 = time.monotonic()
            img = Image.open(image_path).convert("RGB")

            # Build conversation with image reference
            conv = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image"},
                        {"type": "text", "text": "Extract all text from this receipt or document image. Return exactly what is written, preserving the original formatting."},
                    ],
                },
            ]

            formatted_text = self._processor.tokenizer.apply_chat_template(
                conv, tokenize=False, add_generation_prompt=True
            )

            inputs = self._processor(
                images=img,
                text=formatted_text,
                return_tensors="pt",
            ).to(self._model.device)

            import torch
            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=self._max_new_tokens,
                    do_sample=False,
                )

            # Strip the input tokens from the output to get just the generated text
            input_len = inputs["input_ids"].shape[1]
            generated_ids = outputs[0][input_len:]
            text = self._processor.decode(generated_ids, skip_special_tokens=True)

            elapsed = time.monotonic() - t0
            self._last_latency_ms = round(elapsed * 1000, 1)

            return {
                "raw_text": text.strip(),
                "text": text.strip(),
                "model": self._model_name,
                "latency_ms": self._last_latency_ms,
                "parameter_count": self.parameter_count,
            }
        except Exception as e:
            logger.warning("GLM-OCR extraction failed", exc_info=True)
            return {"error": str(e), "model": self.name}

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


class NuExtract3OCRProvider:
    """OCR / extraction provider using NuExtract3-4B via transformers.

    Provides structured text extraction from images (receipts, labels).
    Falls back gracefully when deps are missing.
    Note: CC-BY-NC-4.0 license — non-commercial use only.
    """

    name = "nuextract3"
    model_id = "nuextract3-4b"
    parameter_count = 4.0
    license_note = "CC-BY-NC-4.0"
    runtime_type = "transformers"
    supports_off_grid = True
    capabilities: set[str] = {"ocr"}

    def __init__(
        self,
        model_name: str = "nuance/NuExtract3-4B",
        device: str = "auto",
        max_new_tokens: int = 512,
        load_in_4bit: bool = True,
    ):
        self._model_name = model_name
        self._device = device
        self._max_new_tokens = max_new_tokens
        self._load_in_4bit = load_in_4bit
        self._model = None
        self._tokenizer = None
        self._available = False
        self._error: str | None = None
        self._last_latency_ms: float | None = None
        self._init()

    def _init(self) -> None:
        try:
            import torch  # noqa: F401
            from transformers import (  # noqa: F401
                AutoModelForCausalLM,
                AutoTokenizer,
            )
            self._available = True
            self._error = None
            logger.info("NuExtract3 provider initialised (model=%s)", self._model_name)
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
            from transformers import AutoModelForCausalLM, AutoTokenizer

            logger.info("Loading NuExtract3 model %s ...", self._model_name)
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_name)
            kwargs = {"torch_dtype": torch.bfloat16}
            if self._load_in_4bit and torch.cuda.is_available():
                from transformers import BitsAndBytesConfig
                kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                )
            self._model = AutoModelForCausalLM.from_pretrained(
                self._model_name, **kwargs
            )
            if self._device == "auto":
                if torch.cuda.is_available():
                    self._model = self._model.to("cuda")
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    self._model = self._model.to("mps")
            else:
                self._model = self._model.to(self._device)
            self._model.eval()
            logger.info("NuExtract3 model loaded")
            return True
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch"
            )
            return False
        except Exception as e:
            self._error = f"Failed to load NuExtract3 model: {e}"
            logger.warning("NuExtract3 model load failed", exc_info=True)
            return False

    def extract(self, image_path: str) -> dict[str, Any]:
        """Extract structured text from an image (receipt/label).

        Returns parsed fields when available, or raw OCR text.
        """
        if not self._available:
            return {"error": self._error or "NuExtract3 not available", "model": self.name}
        if not os.path.isfile(image_path):
            return {"error": f"Image file not found: {image_path}", "model": self.name}

        if self._model is None and not self._load_model():
            return {"error": self._error or "Failed to load model", "model": self.name}

        try:
            t0 = time.monotonic()

            prompt = (
                "<|input|>\n"
                f"### Image: {image_path}\n"
                "Extract the following from this receipt or product label:\n"
                "- brand\n- product_name\n- weight/volume\n- mrp/price\n"
                "- expiry_date\n- manufacturing_date\n- batch_number\n"
                "<|output|>\n"
            )

            inputs = self._tokenizer(prompt, return_tensors="pt")
            import torch
            if torch.cuda.is_available():
                inputs = {k: v.to("cuda") for k, v in inputs.items()}
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                inputs = {k: v.to("mps") for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self._model.generate(
                    **inputs,
                    max_new_tokens=self._max_new_tokens,
                    temperature=0.1,
                    do_sample=False,
                    pad_token_id=self._tokenizer.pad_token_id or self._tokenizer.eos_token_id,
                )

            text = self._tokenizer.decode(
                outputs[0][inputs["input_ids"].shape[1]:],
                skip_special_tokens=True,
            )

            elapsed = time.monotonic() - t0
            self._last_latency_ms = round(elapsed * 1000, 1)

            return {
                "raw_text": text.strip(),
                "model": self._model_name,
                "latency_ms": self._last_latency_ms,
                "brand": None,
                "product_name": None,
                "weight": None,
                "mrp": None,
                "expiry_date": None,
            }
        except Exception as e:
            logger.warning("NuExtract3 extraction failed", exc_info=True)
            return {"error": str(e), "model": self.name}

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
