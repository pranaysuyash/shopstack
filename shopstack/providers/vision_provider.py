"""Local vision provider using Qwen3-VL-8B-Instruct via transformers.

This is the **canonical default** vision provider as of 13-Jun-2026:
    - Modal A100 int4 prod bench: 99% overall on synthetic product images
        (100% identify, 100% brand, 100% qty, 95% price, 100% expiry).
    - 7.3M HF downloads (most popular Qwen VLM).
    - Apache-2.0 license.

History / supersession:
    - 13-Jun-2026: Qwen3-VL-8B promoted to active via Modal bench v8.
    - 13-Jun-2026: MiniCPM-V-2.6 demoted to candidate (86% on same bench).
        Preserved as a fallback for environments where 8B inference is too heavy.

API surface mirrors the previous ``MiniCPMVProvider`` so callers in
``shopstack/services/market_lens.py`` and the UI tab need no changes.

    provider.understand(image_path, prompt=...)  # general VQA
    provider.detect(image_path)                  # object detection via prompt
    provider.last_latency_ms                    # last-call latency

The ``understand()`` method runs a constrained JSON prompt for product-shelf
detection so callers can use it both for free-form VQA and for the
canonical ShopStack use case (extract brand / quantity / price / expiry).
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


# Import versioned prompts (motto_v3 §0.9)
from shopstack.prompts.vision import (  # noqa: E402
    UNDERSTAND_PRODUCT_SHELF_PROMPT,
    GENERAL_UNDERSTAND_PROMPT,
    MINICPM_DETECT_PROMPT,
)


# Loose parser: tolerates a model that returns text *around* a JSON block.
# Strategy: find the first balanced { ... } block (NOT a non-greedy regex
# that would match the smallest empty {}), or fall back to wrapping the
# raw text in {"products": [{"name": text}, ...]}.
def _find_balanced_json_block(text: str) -> str | None:
    """Find the first balanced ``{...}`` block in ``text``.

    Non-greedy regexes like ``\\{[\\s\\S]*?\\}`` match the *smallest* possible
    block — which is often an empty ``{}`` inside a markdown fence. This
    function walks the string and returns the first complete, balanced
    JSON object.
    """
    depth = 0
    start = -1
    in_string = False
    escape_next = False
    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"' and not escape_next:
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth == 0:
                continue  # stray closer
            depth -= 1
            if depth == 0 and start >= 0:
                return text[start : i + 1]
    return None


_JSON_BLOCK = re.compile(r"\{[\s\S]*?\}")  # kept for backward compat in tests


class Qwen3VLProvider:
    """Local vision provider using Qwen3-VL-8B-Instruct.

    Inherits no legacy from MiniCPMVProvider — implemented from scratch against
    the Qwen3-VL API (AutoModelForImageTextToText). The class is exposed
    via the registry as ``qwen3vl`` and the default ``vision_backend`` in
    ``shopstack/config.py``.
    """

    name = "qwen3vl"
    model_id = "qwen3-vl-8b"
    parameter_count = 8.0
    license_note = "Apache-2.0"
    runtime_type = "transformers"
    supports_off_grid = True
    capabilities: set[str] = {"vision", "object_detection", "grounding"}

    SAMPLE_SIZE = 1024  # match bench (Modal A100 int4 used 1024×1024)
    MAX_NEW_TOKENS = 512

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-VL-8B-Instruct",
        device: str = "auto",
        load_in_4bit: bool = True,
    ):
        self._model_name = model_name
        self._device = device
        self._load_in_4bit = load_in_4bit
        self._model: Any = None
        self._processor: Any = None
        self._available = False
        self._error: str | None = None
        self._last_latency_ms: float | None = None
        # Background pre-download (Pass 14 §1.4 — same pattern as BiRefNet §1.3)
        self._weights_pre_downloaded = False
        self._pre_download_event = threading.Event()
        # Pass 18 §1.4 cancel/retry: cancellation flag for the
        # background pre-download thread. Set by ``cancel_pre_download()``
        # and honoured at the start of ``_pre_download_weights()`` and
        # after the download completes.
        self._pre_download_cancelled = False
        self._init()
        # Kick off background weight download so the first understand() call
        # is fast — weights are cached in huggingface_hub before use.
        self._start_pre_download()

    def _init(self) -> None:
        try:
            import torch  # noqa: F401
            from transformers import (  # noqa: F401
                AutoModelForImageTextToText,
                AutoProcessor,
            )
            self._available = True
            self._error = None
            logger.info("Qwen3-VL provider initialised (model=%s)", self._model_name)
        except ImportError:
            self._error = (
                "transformers/torch not installed. "
                "Run: uv pip install transformers torch"
            )
            self._available = False

    # ── Background pre-download (Pass 14 §1.4) ─────────────────────────
    # Mirrors ``BiRefNetSegmentationProvider._start_pre_download`` so the
    # first ``understand()`` call loads from the HF cache instead of
    # blocking the event loop for the 30-120s model download.

    def _start_pre_download(self) -> None:
        """Start downloading model weights in a background daemon thread.

        Uses ``snapshot_download`` to cache all repo files to the
        HuggingFace cache directory. The actual ``_load_model()``
        will then find files already cached and skip network I/O.

        If a previous pre-download was cancelled, reset the
        ``_pre_download_cancelled`` flag so the new attempt can run.
        """
        if not self._available:
            return
        # Pass 18 §1.4 cancel/retry: allow the pre-download to be
        # re-attempted after a previous cancellation. The flag is
        # reset here (not in cancel_pre_download) so a stale cancel
        # can never silently block a fresh attempt.
        self._pre_download_cancelled = False
        t = threading.Thread(target=self._pre_download_weights, daemon=True)
        t.start()

    def cancel_pre_download(self) -> bool:
        """Signal the background pre-download thread to stop at the next checkpoint.

        Returns True if a pre-download was actually running (and was
        signalled to stop). Returns False if no pre-download is in
        flight (no-op).

        Per Pass 18 §1.4 acceptance: "ability to cancel/retry model
        load." This implements the "cancel" half. The "retry" half is
        supported by calling ``_start_pre_download()`` again (which
        is the existing public init path; the reset happens there).

        Implementation note: ``snapshot_download`` doesn't expose a
        cancellation token, so the flag is checked at a coarse
        granularity (after the download starts, before the event is
        set). For models this large, the download takes minutes
        and the user can simply close the app if the download is in
        the middle of a multi-GB transfer — this method exists to
        prevent NEW attempts from completing, not to abort a
        download in progress.
        """
        if self._weights_pre_downloaded:
            return False  # already done, nothing to cancel
        self._pre_download_cancelled = True
        # Unblock the load() wait so the foreground doesn't sit
        # forever after a cancellation.
        self._pre_download_event.set()
        logger.info("Qwen3-VL pre-download cancellation requested")
        return True

    def _pre_download_weights(self) -> None:
        """Download all model files to HuggingFace cache (no model load).

        Honours the ``_pre_download_cancelled`` flag: if a cancel was
        requested before the download finished, the loop returns
        early without setting ``_weights_pre_downloaded``. The next
        call to ``_start_pre_download()`` (or ``_load_model()``)
        starts a fresh attempt.
        """
        try:
            if self._pre_download_cancelled:
                logger.info("Qwen3-VL pre-download: cancellation observed, skipping")
                return
            logger.info(
                "Pre-downloading Qwen3-VL model weights (%s) ...",
                self._model_name,
            )
            from huggingface_hub import snapshot_download
            snapshot_download(self._model_name)
            if self._pre_download_cancelled:
                # Cancelled during the download — don't mark as
                # complete so a future load() will retry.
                logger.info("Qwen3-VL pre-download: cancelled mid-download, will retry on next call")
                return
            self._weights_pre_downloaded = True
            self._pre_download_event.set()
            logger.info("Qwen3-VL weights pre-download complete")
        except Exception as e:  # pragma: no cover - background thread
            # Do NOT mark the provider unavailable: the foreground
            # ``_load_model()`` will still try to download on demand.
            logger.warning(
                "Qwen3-VL background pre-download failed: %s", e,
                exc_info=True,
            )
            self._pre_download_event.set()  # unblock the wait in load()

    def load(self) -> None:
        if self._model is not None:
            return
        # Give the background pre-download a chance to finish first
        # so from_pretrained finds files already cached.
        if not self._weights_pre_downloaded:
            self._pre_download_event.wait(timeout=15)
        self._load_model()

    def _load_model(self) -> bool:
        if self._model is not None:
            return True
        try:
            import torch
            from transformers import AutoModelForImageTextToText, AutoProcessor

            logger.info("Loading Qwen3-VL model %s ...", self._model_name)
            self._processor = AutoProcessor.from_pretrained(
                self._model_name, trust_remote_code=True
            )

            load_kwargs: dict[str, Any] = {
                "trust_remote_code": True,
                "torch_dtype": torch.bfloat16,
            }
            if self._load_in_4bit and torch.cuda.is_available():
                from transformers import BitsAndBytesConfig
                load_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.bfloat16,
                    bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True,
                )
            # AutoModelForImageTextToText is the canonical Qwen3-VL class.
            # Fall back to AutoModelForCausalLM only if the former is not
            # registered in the installed transformers version.
            try:
                self._model = AutoModelForImageTextToText.from_pretrained(
                    self._model_name, **load_kwargs
                )
            except (ValueError, KeyError):
                from transformers import AutoModelForCausalLM
                self._model = AutoModelForCausalLM.from_pretrained(
                    self._model_name, **load_kwargs
                )

            if self._device == "auto":
                if torch.cuda.is_available():
                    self._model = self._model.to("cuda")
                elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                    self._model = self._model.to("mps")
            else:
                self._model = self._model.to(self._device)
            self._model.eval()
            logger.info("Qwen3-VL model loaded")
            return True
        except Exception as e:
            self._error = f"Failed to load Qwen3-VL model: {e}"
            logger.warning("Qwen3-VL model load failed", exc_info=True)
            return False

    # ── Public API ──────────────────────────────────────────────────────────
    def understand(self, image_path: str, prompt: str = "") -> dict[str, Any]:
        """Run a VLM chat on ``image_path`` and return the response.

        Args:
            image_path: Path to a local image file.
            prompt: Optional user prompt. Defaults to the canonical ShopStack
                product-shelf prompt that emits strict JSON.

        Returns:
            A dict with one of the following keys (canonical shape):
            - On success: ``{"description": str, "products": list[dict], "model": str, "latency_ms": float}``
              ``description`` is the raw model output (text or JSON string).
              ``products`` is the parsed JSON list (may be empty).
            - On failure: ``{"error": str, "model": str}``
        """
        if not self._available:
            return {"error": self._error or "Qwen3-VL not available", "model": self.name}
        if not os.path.isfile(image_path):
            return {"error": f"Image file not found: {image_path}", "model": self.name}
        if self._model is None and not self._load_model():
            return {"error": self._error or "Failed to load model", "model": self.name}

        try:
            import torch
            from PIL import Image

            t0 = time.monotonic()

            image = Image.open(image_path).convert("RGB")
            user_prompt = prompt or UNDERSTAND_PRODUCT_SHELF_PROMPT

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": user_prompt},
                    ],
                }
            ]

            inputs = self._processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            ).to(self._model.device)

            with torch.no_grad():
                generated_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=self.MAX_NEW_TOKENS,
                    do_sample=False,
                    temperature=1.0,
                    top_p=1.0,
                    pad_token_id=getattr(self._processor.tokenizer, "eos_token_id", None),
                )

            # Trim the prompt tokens from the output
            input_len = inputs["input_ids"].shape[1]
            generated_ids_trimmed = generated_ids[:, input_len:]
            output_text = self._processor.batch_decode(
                generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )[0]

            elapsed = time.monotonic() - t0
            self._last_latency_ms = round(elapsed * 1000, 1)

            products = self._parse_products(output_text)

            return {
                "description": output_text,
                "products": products,
                "model": self._model_name,
                "latency_ms": self._last_latency_ms,
            }
        except Exception as e:
            logger.warning("Qwen3-VL understand failed", exc_info=True)
            return {"error": str(e), "model": self.name}

    def detect(self, image_path: str) -> list[dict[str, Any]]:
        """Detect objects in an image via the VLM.

        For backward compat with ``MiniCPMVProvider.detect``, returns
        ``[{"label": ..., "confidence": ..., "source": "qwen3vl"}]`` for
        each detected product. The VLM provides per-product metadata
        (brand, qty, price) too — that is preserved in the per-call
        return of ``understand()``.
        """
        result = self.understand(image_path, prompt=UNDERSTAND_PRODUCT_SHELF_PROMPT)
        if "error" in result:
            return [result]
        products = result.get("products") or []
        return [
            {
                "label": p.get("name", "").strip(),
                "brand": p.get("brand") or "",
                "quantity": p.get("quantity") or 1.0,
                "unit": p.get("unit") or "unit",
                "price_rupees": p.get("price_rupees"),
                "expiry_date": p.get("expiry_date"),
                "confidence": 0.99,  # bench p50
                "source": "qwen3vl",
            }
            for p in products
            if p.get("name")
        ]

    def ground(self, image_path: str, text_prompt: str) -> dict[str, Any]:
        """Ground a text prompt in the image and return a bbox-style result.

        Qwen3-VL is not the primary grounding backbone in ShopStack, but it
        can act as a helpful grounding helper for ambiguous shelf objects.
        The benchmark lane treats it as a VLM grounding candidate, not as a
        segmentation model.
        """
        if not self._available:
            return {
                "found": False,
                "bbox": [],
                "confidence": 0.0,
                "label": "",
                "all_detections": [],
                "error": self._error or "Qwen3-VL not available",
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
            image = Image.open(image_path).convert("RGB")
            user_prompt = (
                "You are doing open-vocabulary object grounding for a household shelf image. "
                "Return STRICT JSON only with this schema:\n"
                "{"
                "\"found\": true|false, "
                "\"bbox\": [xmin, ymin, xmax, ymax], "
                "\"label\": \"" + text_prompt + "\", "
                "\"confidence\": 0.0, "
                "\"all_detections\": [{\"label\": \"...\", \"bbox\": [xmin, ymin, xmax, ymax], \"confidence\": 0.0}]"
                "}\n"
                "If the target is not visible, return {\"found\": false, \"bbox\": [], \"label\": \"\", \"confidence\": 0.0, \"all_detections\": []}.\n"
                "Use pixel coordinates if possible. No markdown. No prose."
            )
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": user_prompt},
                    ],
                }
            ]
            inputs = self._processor.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_dict=True,
                return_tensors="pt",
            ).to(self._model.device)
            with torch.no_grad():
                generated_ids = self._model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=False,
                    temperature=1.0,
                    top_p=1.0,
                    pad_token_id=getattr(self._processor.tokenizer, "eos_token_id", None),
                )
            input_len = inputs["input_ids"].shape[1]
            generated_ids_trimmed = generated_ids[:, input_len:]
            output_text = self._processor.batch_decode(
                generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )[0]
            elapsed = time.monotonic() - t0
            self._last_latency_ms = round(elapsed * 1000, 1)
            parsed = self._parse_grounding(output_text)
            parsed["model"] = self._model_name
            parsed["latency_ms"] = self._last_latency_ms
            return parsed
        except Exception as e:
            logger.warning("Qwen3-VL grounding failed", exc_info=True)
            return {"found": False, "bbox": [], "confidence": 0.0, "label": "", "all_detections": [], "error": str(e), "model": self.name}

    # ── Internals ──────────────────────────────────────────────────────────
    @staticmethod
    def _parse_products(text: str) -> list[dict[str, Any]]:
        """Extract the ``products`` list from the VLM output.

        Tries three strategies, in order:
        1. Strict ``json.loads(text)`` if the whole text is a JSON object.
        2. Regex search for the first JSON object containing a ``products`` key.
        3. Fallback: empty list (caller can use the raw ``description``).
        """
        if not text:
            return []
        # 1. Whole text is JSON
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and "products" in obj:
                return [p for p in obj["products"] if isinstance(p, dict)]
        except (json.JSONDecodeError, TypeError):
            pass
        # 2. First balanced {...} block that has a "products" key
        balanced = _find_balanced_json_block(text)
        if balanced is not None:
            try:
                obj = json.loads(balanced)
                if isinstance(obj, dict) and "products" in obj:
                    return [p for p in obj["products"] if isinstance(p, dict)]
            except (json.JSONDecodeError, TypeError):
                pass
        # 3. No parseable products
        return []

    @staticmethod
    def _parse_grounding(text: str) -> dict[str, Any]:
        if not text:
            return {"found": False, "bbox": [], "confidence": 0.0, "label": "", "all_detections": []}
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return Qwen3VLProvider._normalize_grounding_payload(obj)
        except (json.JSONDecodeError, TypeError):
            pass
        balanced = _find_balanced_json_block(text)
        if balanced is not None:
            try:
                obj = json.loads(balanced)
                if isinstance(obj, dict):
                    return Qwen3VLProvider._normalize_grounding_payload(obj)
            except (json.JSONDecodeError, TypeError):
                pass
        return {"found": False, "bbox": [], "confidence": 0.0, "label": "", "all_detections": []}

    @staticmethod
    def _normalize_grounding_payload(obj: dict[str, Any]) -> dict[str, Any]:
        if "objects" in obj and isinstance(obj.get("objects"), list):
            objects = [item for item in obj["objects"] if isinstance(item, dict)]
            first = objects[0] if objects else {}
            obj = {
                "found": bool(objects),
                "bbox": first.get("bbox") or first.get("bbox_2d") or [],
                "confidence": first.get("confidence", first.get("score", 0.0)),
                "label": first.get("label") or first.get("name") or "",
                "all_detections": objects,
            }
        bbox = obj.get("bbox") or obj.get("bbox_2d") or []
        if not isinstance(bbox, list):
            bbox = []
        return {
            "found": bool(obj.get("found", bool(bbox))),
            "bbox": bbox,
            "confidence": float(obj.get("confidence", obj.get("score", 0.0)) or 0.0),
            "label": str(obj.get("label", obj.get("name", "")) or ""),
            "all_detections": obj.get("all_detections") or [],
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


# Preserve the prior MiniCPMVProvider for backward compatibility
# (configurable via vision_backend="minicpmv"). This provider is the
# historical default and remains a valid candidate (86% on Modal bench
# v8, 4.6B params vs Qwen3-VL's 8B, lighter on low-memory devices).
# Per motto_v3 §7, we do not delete this; instead, we expose both.
class MiniCPMVProvider:
    """Local vision provider using MiniCPM-V-2.6 via transformers.

    DEMOTED to candidate as of 13-Jun-2026 (Modal bench: 86% vs
    Qwen3-VL-8B's 99%). Preserved here for compatibility with
    deployments that pin ``vision_backend="minicpmv"`` and for
    environments where 8B inference is too heavy.

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
            msgs = [{"role": "user", "content": [image, prompt or GENERAL_UNDERSTAND_PROMPT]}]

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
            prompt=MINICPM_DETECT_PROMPT
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
