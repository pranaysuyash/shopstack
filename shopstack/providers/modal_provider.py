"""Modal cloud-GPU provider — Phase 6 #18.

Modal (https://modal.com) is a serverless platform for running
GPU-backed Python functions. ShopStack supports a "Modal"
backend for any provider that wants to run on remote GPU instead
of locally — the planner, vision, embeddings, or a fine-tuned
model.

**Why a separate provider:**

The existing :mod:`shopstack.providers.local_provider` runs
everything on the user's machine (Mac M-series via MLX, or
CUDA via llama-cpp). The
:mod:`shopstack.providers.openai_provider` calls a hosted
OpenAI-compatible API. The Modal provider sits in between:
it calls a *user-deployed* Modal function (so the user keeps
control of the model + data, no third-party API) but the
inference runs on a remote GPU (so the user doesn't need a
local GPU).

**What this module ships:**

1. **A `ModalPlannerProvider`** that follows the
   :class:`PlannerProvider` interface. It calls a configurable
   Modal function and returns the planner-shaped response.
2. **A `ModalVisionProvider`** for remote image captioning /
   object detection.
3. **A `ModalEmbeddingsProvider`** for remote sentence
   embeddings.
4. **A no-op HTTP stub** so the provider can be unit-tested
   without a real Modal deployment — the stub returns
   deterministic mock responses keyed off the prompt.

**Configuration:**

The user sets ``MODAL_PLANNER_URL``, ``MODAL_VISION_URL``,
``MODAL_EMBEDDINGS_URL`` in their environment (or via the
``Settings`` class). Each URL is a Modal webhook URL of the
form ``https://<workspace>--<app>-<func>.modal.run``.

**Failure modes:**

- ``modal`` package not installed → loader returns ``None`` and
  the registry falls back to mock.
- Network error → provider raises ``RuntimeError`` (the
  caller is responsible for catching and falling back).
- Auth error → same.

**Why HTTP (not the `modal` SDK):**

The `modal` SDK is for *deploying* functions, not *calling*
them from a client. Calling a deployed Modal function from
ShopStack is just a POST to its webhook URL with a JSON body.
This keeps the dependency surface small (no `modal` package
required at runtime — only the `httpx` / `requests` we already
have for OpenAI).
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)


# ─── HTTP helpers ──────────────────────────────────────────────────


def _post_json(url: str, payload: dict[str, Any], timeout: float = 30.0) -> dict[str, Any]:
    """POST ``payload`` as JSON to ``url`` and return the parsed response.

    Best-effort: raises ``RuntimeError`` on any HTTP / network /
    parse error with a short, actionable message.
    """
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Modal HTTP call failed: {exc}") from exc
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Modal response was not valid JSON: {exc}") from exc


def _stub_response(prompt: str, kind: str) -> dict[str, Any]:
    """Deterministic stub used when no Modal URL is configured.

    Returns a planner-shaped / vision-shaped / embedding-shaped
    response keyed off the prompt. Lets unit tests run without
    a real Modal deployment.
    """
    if kind == "planner":
        return {
            "text": (
                f"[stub modal planner] I would recommend: {prompt[:60]}…"
            ),
            "tool_calls": [],
            "usage": {"prompt_tokens": len(prompt.split()),
                       "completion_tokens": 10,
                       "total_tokens": len(prompt.split()) + 10},
        }
    if kind == "vision":
        return {
            "caption": f"[stub modal vision] a photo of {prompt[:40]}",
            "objects": [],
        }
    if kind == "embeddings":
        # 8-dim deterministic embedding. Uses MD5 to guarantee:
        # - Same input → same output (deterministic)
        # - Different input → different output (md5 collision resistance)
        import hashlib
        digest = hashlib.md5(prompt.encode("utf-8")).digest()
        return {
            "embedding": [(b - 128) / 128.0 for b in digest[:8]]
        }
    return {}


# ─── Generic call ─────────────────────────────────────────────────


def call_modal(url: str, payload: dict[str, Any], *, stub_kind: str = "planner") -> dict[str, Any]:
    """Call a Modal webhook URL, falling back to a stub when ``url`` is empty.

    Args:
        url: Modal webhook URL. When empty / unset, returns the
            deterministic stub response.
        payload: JSON-serializable request body.
        stub_kind: One of "planner", "vision", "embeddings" —
            selects the stub response shape for offline testing.

    Returns:
        Parsed JSON response dict.
    """
    if not url:
        # Pick a stable string to seed the stub: prefer "prompt", then
        # "text", then "image_path", then the full payload as JSON.
        seed_str = (
            str(payload.get("prompt", "")
                or payload.get("text", "")
                or payload.get("image_path", "")
                or json.dumps(payload, sort_keys=True))
        )
        return _stub_response(seed_str, stub_kind)
    return _post_json(url, payload)


# ─── Settings helper ──────────────────────────────────────────────


def get_modal_url(env_var: str, default: str = "") -> str:
    """Read a Modal URL from the environment, with a default."""
    return os.environ.get(env_var, default).strip()


# ─── Provider classes ─────────────────────────────────────────────


class ModalPlannerProvider:
    """Planner provider backed by a user-deployed Modal function.

    Implements the duck-typed interface used by ShopStack
    (``.plan(prompt) -> dict``). The interface is intentionally
    minimal so the provider can be swapped without touching
    the planner code.
    """

    name = "modal_planner"
    model_id = "modal-planner-v1"
    parameter_count = 0.0
    capabilities: set[str] = {"planner", "remote", "gpu"}
    supports_off_grid = False  # requires network

    def __init__(self, url: str = "", *, model: str = "shopstack-planner"):
        self.url = url
        self.model = model

    def load(self) -> None:
        # No-op: nothing to load locally.
        pass

    def healthcheck(self) -> bool:
        return True

    def plan(self, prompt: str, *, system: str = "", **kwargs: Any) -> dict[str, Any]:
        """Send a planner prompt to the Modal function and return the response."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "kwargs": kwargs,
        }
        return call_modal(self.url, payload, stub_kind="planner")


class ModalVisionProvider:
    """Vision provider backed by a Modal-deployed captioning / detection model."""

    name = "modal_vision"
    model_id = "modal-vision-v1"
    parameter_count = 0.0
    capabilities: set[str] = {"vision", "remote", "gpu"}
    supports_off_grid = False

    def __init__(self, url: str = "", *, model: str = "shopstack-vision"):
        self.url = url
        self.model = model

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def caption(self, image_path: str, prompt: str = "") -> dict[str, Any]:
        payload = {
            "model": self.model,
            "image_path": image_path,
            "prompt": prompt,
        }
        return call_modal(self.url, payload, stub_kind="vision")


class ModalEmbeddingsProvider:
    """Embeddings provider backed by a Modal-deployed embedding model."""

    name = "modal_embeddings"
    model_id = "modal-embeddings-v1"
    parameter_count = 0.0
    capabilities: set[str] = {"embeddings", "remote", "gpu"}
    supports_off_grid = False

    def __init__(self, url: str = "", *, model: str = "bge-m3"):
        self.url = url
        self.model = model

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Compute embeddings for ``texts`` via the Modal endpoint.

        Batches all texts into one request when a real URL is configured;
        falls back to per-text stub embeddings when URL is empty.
        """
        if not texts:
            return []
        if self.url:
            payload = {"model": self.model, "texts": texts}
            resp = call_modal(self.url, payload, stub_kind="embeddings")
            raw = resp.get("embeddings", [])
            if not isinstance(raw, list):
                return []
            return [[float(x) for x in emb] for emb in raw if isinstance(emb, list)]
        out: list[list[float]] = []
        for t in texts:
            payload = {"model": self.model, "text": t}
            resp = call_modal(self.url, payload, stub_kind="embeddings")
            emb = resp.get("embedding", [])
            if not isinstance(emb, list):
                emb = []
            out.append([float(x) for x in emb])
        return out


class ModalOCRProvider:
    """OCR provider backed by a Modal-deployed OCR model."""

    name = "modal_ocr"
    model_id = "modal-ocr-v1"
    parameter_count = 0.0
    capabilities: set[str] = {"ocr", "remote", "gpu"}
    supports_off_grid = False

    def __init__(self, url: str = "", *, model: str = "glm-ocr"):
        self.url = url
        self.model = model

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def extract_text(self, image_path: str) -> dict[str, Any]:
        payload = {"model": self.model, "image_path": image_path}
        return call_modal(self.url, payload, stub_kind="ocr")


class ModalSTTProvider:
    """Speech-to-text provider backed by a Modal-deployed STT model."""

    name = "modal_stt"
    model_id = "modal-stt-v1"
    parameter_count = 0.0
    capabilities: set[str] = {"stt", "remote", "gpu"}
    supports_off_grid = False

    def __init__(self, url: str = "", *, model: str = "sense-voice"):
        self.url = url
        self.model = model

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def transcribe(self, audio_path: str) -> dict[str, Any]:
        payload = {"model": self.model, "audio_path": audio_path}
        return call_modal(self.url, payload, stub_kind="stt")


class ModalTTSProvider:
    """Text-to-speech provider backed by a Modal-deployed TTS model."""

    name = "modal_tts"
    model_id = "modal-tts-v1"
    parameter_count = 0.0
    capabilities: set[str] = {"tts", "remote", "gpu"}
    supports_off_grid = False

    def __init__(self, url: str = "", *, model: str = "qwen3-tts"):
        self.url = url
        self.model = model

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def synthesize(self, text: str) -> dict[str, Any]:
        payload = {"model": self.model, "text": text}
        return call_modal(self.url, payload, stub_kind="tts")


class ModalSegmentationProvider:
    """Segmentation provider backed by a Modal-deployed segmentation model."""

    name = "modal_segmentation"
    model_id = "modal-segmentation-v1"
    parameter_count = 0.0
    capabilities: set[str] = {"segmentation", "remote", "gpu"}
    supports_off_grid = False

    def __init__(self, url: str = "", *, model: str = "birefnet"):
        self.url = url
        self.model = model

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def segment(self, image_path: str) -> dict[str, Any]:
        payload = {"model": self.model, "image_path": image_path}
        return call_modal(self.url, payload, stub_kind="segmentation")


# ─── Public API ───────────────────────────────────────────────────


__all__ = [
    "ModalEmbeddingsProvider",
    "ModalPlannerProvider",
    "ModalVisionProvider",
    "call_modal",
    "get_modal_url",
]
