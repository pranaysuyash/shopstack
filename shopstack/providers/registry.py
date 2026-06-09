from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from shopstack.config import Settings
from shopstack.providers.interfaces import (
    EmbeddingsProvider,
    GroundingProvider,
    ImageEditProvider,
    ObjectDetectionProvider,
    OCRProvider,
    PlannerProvider,
    SegmentationProvider,
    STTProvider,
    ToolCallParserProvider,
    TTSProvider,
    VisionProvider,
)

from shopstack.providers.mock_providers import (
    MockEmbeddingsProvider,
    MockGroundingProvider,
    MockImageEditProvider,
    MockDetectionProvider,
    MockOCRProvider,
    MockPlannerProvider,
    MockSegmentationProvider,
    MockSTTProvider,
    MockToolCallParser,
    MockTTSProvider,
    MockUnifiedProvider,
    MockVisionProvider,
)

from shopstack.providers.image_gen_provider import FluxImageProvider

logger = logging.getLogger(__name__)


# ── Lazy loader helpers ────────────────────────────────────────────────


def _load_local_whisper():
    try:
        from shopstack.providers.local_whisper_provider import LocalWhisperProvider
        return LocalWhisperProvider
    except ImportError:
        return None


def _load_openai():
    try:
        from shopstack.providers.openai_provider import OpenAIProvider
        return OpenAIProvider
    except ImportError:
        return None


def _load_whisper():
    try:
        from shopstack.providers.whisper_provider import WhisperProvider
        return WhisperProvider
    except ImportError:
        return None


def _load_local():
    try:
        from shopstack.providers.local_provider import LocalProvider
        return LocalProvider
    except ImportError:
        return None


def _load_huggingface():
    try:
        from shopstack.providers.huggingface_provider import HuggingFaceProvider
        return HuggingFaceProvider
    except ImportError:
        return None


def _load_sensevoice():
    try:
        from shopstack.providers.stt_provider import SenseVoiceSTTProvider
        return SenseVoiceSTTProvider
    except ImportError:
        return None


def _load_qwen3_asr():
    try:
        from shopstack.providers.stt_provider import Qwen3ASRProvider
        return Qwen3ASRProvider
    except ImportError:
        return None


def _load_kokoro_tts():
    try:
        from shopstack.providers.tts_provider import KokoroTTSProvider
        return KokoroTTSProvider
    except ImportError:
        return None


def _load_bge_m3():
    try:
        from shopstack.providers.embeddings_provider import BGEM3EmbeddingProvider
        return BGEM3EmbeddingProvider
    except ImportError:
        return None


def _load_minicpmv():
    try:
        from shopstack.providers.vision_provider import MiniCPMVProvider
        return MiniCPMVProvider
    except ImportError:
        return None


def _load_minicpm5():
    try:
        from shopstack.providers.planner_provider import MiniCPM5Provider
        return MiniCPM5Provider
    except ImportError:
        return None


def _load_qwen3_tts():
    try:
        from shopstack.providers.tts_provider import Qwen3TTSProvider
        return Qwen3TTSProvider
    except ImportError:
        return None


def _load_nuextract3():
    try:
        from shopstack.providers.ocr_provider import NuExtract3OCRProvider
        return NuExtract3OCRProvider
    except ImportError:
        return None


def _load_rmbg():
    try:
        from shopstack.providers.segmentation_provider import RMBGSegmentationProvider
        return RMBGSegmentationProvider
    except ImportError:
        return None


def _load_glm_ocr():
    try:
        from shopstack.providers.ocr_provider import GlmOCRProvider
        return GlmOCRProvider
    except ImportError:
        return None


def _load_tesseract():
    try:
        from shopstack.providers.tesseract_provider import TesseractOCRProvider
        return TesseractOCRProvider
    except ImportError:
        return None


def _load_parakeet():
    try:
        from shopstack.providers.stt_provider import ParakeetSTTProvider
        return ParakeetSTTProvider
    except ImportError:
        return None


# ── Provider specification table ───────────────────────────────────────
# Adding a new provider = one entry here + a _load_* function above.


@dataclass
class _ProviderSpec:
    loader: Callable[[], type | None]
    kwargs_fn: Callable[[Settings], dict[str, Any]]
    unavailable_msg: str


_PROVIDER_SPECS: dict[str, _ProviderSpec] = {
    "local_whisper": _ProviderSpec(
        loader=_load_local_whisper,
        kwargs_fn=lambda s: {
            "model_dir": s.local_model_dir,
            "model_size": s.local_whisper_size,
            "auto_unload": s.local_whisper_auto_unload,
        },
        unavailable_msg="Local Whisper provider not available (mlx-whisper / faster-whisper missing), falling back to mock",
    ),
    "openai": _ProviderSpec(
        loader=_load_openai,
        kwargs_fn=lambda s: {"api_key": s.openai_api_key},
        unavailable_msg="OpenAI provider not available (openai package missing), falling back to mock",
    ),
    "whisper": _ProviderSpec(
        loader=_load_whisper,
        kwargs_fn=lambda s: {"api_key": s.openai_api_key},
        unavailable_msg="Whisper provider not available (openai package missing), falling back to mock",
    ),
    "local": _ProviderSpec(
        loader=_load_local,
        kwargs_fn=lambda s: {
            "model_dir": s.local_model_dir,
            "model_repo": s.local_model_repo,
            "model_file": s.local_model_file,
            "mlx_model": s.local_mlx_model,
            "allow_download": s.local_auto_download,
            "auto_unload": s.local_auto_unload,
        },
        unavailable_msg="Local provider not available (mlx-lm / llama-cpp-python missing), falling back to mock",
    ),
    "huggingface": _ProviderSpec(
        loader=_load_huggingface,
        kwargs_fn=lambda s: {"api_key": s.hf_api_key},
        unavailable_msg="HuggingFace provider not available (huggingface_hub package missing), falling back to mock",
    ),
    "sensevoice": _ProviderSpec(
        loader=_load_sensevoice,
        kwargs_fn=lambda _s: {},
        unavailable_msg="SenseVoice STT provider not available (funasr package missing), falling back to mock",
    ),
    "kokoro": _ProviderSpec(
        loader=_load_kokoro_tts,
        kwargs_fn=lambda _s: {},
        unavailable_msg="Kokoro TTS provider not available (kokoro package missing), falling back to mock",
    ),
    "qwen3_asr": _ProviderSpec(
        loader=_load_qwen3_asr,
        kwargs_fn=lambda _s: {},
        unavailable_msg="Qwen3-ASR provider not available (transformers/torch missing), falling back to mock",
    ),
    "bge_m3": _ProviderSpec(
        loader=_load_bge_m3,
        kwargs_fn=lambda _s: {},
        unavailable_msg="BGE-M3 provider not available (sentence-transformers missing), falling back to mock",
    ),
    "minicpmv": _ProviderSpec(
        loader=_load_minicpmv,
        kwargs_fn=lambda _s: {},
        unavailable_msg="MiniCPM-V provider not available (transformers/torch missing), falling back to mock",
    ),
    "minicpm5": _ProviderSpec(
        loader=_load_minicpm5,
        kwargs_fn=lambda _s: {},
        unavailable_msg="MiniCPM5 provider not available (transformers/torch missing), falling back to mock",
    ),
    "qwen3_tts": _ProviderSpec(
        loader=_load_qwen3_tts,
        kwargs_fn=lambda _s: {},
        unavailable_msg="Qwen3-TTS provider not available (transformers/torch missing), falling back to mock",
    ),
    "nuextract3": _ProviderSpec(
        loader=_load_nuextract3,
        kwargs_fn=lambda _s: {},
        unavailable_msg="NuExtract3 provider not available (transformers/torch missing), falling back to mock",
    ),
    "glm_ocr": _ProviderSpec(
        loader=_load_glm_ocr,
        kwargs_fn=lambda _s: {},
        unavailable_msg="GLM-OCR provider not available (transformers/torch/torchvision missing), falling back to mock",
    ),
    "tesseract": _ProviderSpec(
        loader=_load_tesseract,
        kwargs_fn=lambda _s: {},
        unavailable_msg="Tesseract OCR provider not available (pytesseract missing), falling back to mock",
    ),
    "rmbg": _ProviderSpec(
        loader=_load_rmbg,
        kwargs_fn=lambda _s: {},
        unavailable_msg="RMBG provider not available (transformers/torch missing), falling back to mock",
    ),
    "parakeet": _ProviderSpec(
        loader=_load_parakeet,
        kwargs_fn=lambda _s: {},
        unavailable_msg="Parakeet provider not available (transformers/torch missing), falling back to mock",
    ),
}


def _try_real_provider(backend: str, settings: Settings) -> Any | None:
    normalized = backend.replace("-", "_")
    spec = _PROVIDER_SPECS.get(normalized)
    if spec is None:
        return None
    cls = spec.loader()
    if cls:
        return cls(**spec.kwargs_fn(settings))
    logger.info(spec.unavailable_msg)
    return None


# ── Provider registry ──────────────────────────────────────────────────


class ProviderRegistry:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._providers: dict[str, Any] = {}
        self._pending: dict[str, str] = {}
        self._unified: Any | None = None
        self._init_lazy()

    def _init_lazy(self) -> None:
        backends = self._settings.provider_backends
        offline_mock = {"vision", "object_detection", "grounding", "segmentation", "tool_call_parser", "image_edit"}
        for name in ["stt", "tts", "vision", "object_detection", "grounding",
                     "segmentation", "ocr", "planner", "tool_call_parser",
                     "embeddings", "image_edit", "image_gen"]:
            if self._settings.off_the_grid and name in offline_mock:
                self._pending[name] = "mock"
            else:
                self._pending[name] = backends.get(name, "mock")
        self._unified = MockUnifiedProvider()

    def _resolve(self, name: str) -> Any:
        backend = self._pending.pop(name, "mock")
        if backend in {"mock", "mocked", ""}:
            return self._mock_for(name)
        real = _try_real_provider(backend, self._settings)
        if real:
            return real
        return self._mock_for(name)

    def _mock_for(self, name: str) -> Any:
        mocks = {
            "stt": MockSTTProvider, "tts": MockTTSProvider,
            "vision": MockVisionProvider, "object_detection": MockDetectionProvider,
            "grounding": MockGroundingProvider, "segmentation": MockSegmentationProvider,
            "ocr": MockOCRProvider, "planner": MockPlannerProvider,
            "tool_call_parser": MockToolCallParser, "embeddings": MockEmbeddingsProvider,
            "image_edit": MockImageEditProvider, "image_gen": FluxImageProvider,
        }
        cls = mocks.get(name)
        if cls:
            return cls() if callable(cls) else cls
        return None

    def register(self, name: str, provider: Any) -> None:
        self._providers[name] = provider
        self._pending.pop(name, None)

    def get(self, name: str) -> Any:
        if name not in self._providers and name in self._pending:
            self._providers[name] = self._resolve(name)
        return self._providers.get(name)

    def supports(self, capability: str) -> bool:
        for provider in self._providers.values():
            caps = getattr(provider, "capabilities", set())
            if capability in caps:
                return True
        if self._unified and capability in self._unified.capabilities:
            return True
        return False

    @property
    def stt(self) -> STTProvider:
        return self.get("stt")

    @property
    def tts(self) -> TTSProvider:
        return self.get("tts")

    @property
    def vision(self) -> VisionProvider:
        return self.get("vision")

    @property
    def object_detection(self) -> ObjectDetectionProvider:
        return self.get("object_detection")

    @property
    def grounding(self) -> GroundingProvider:
        return self.get("grounding")

    @property
    def segmentation(self) -> SegmentationProvider:
        return self.get("segmentation")

    @property
    def ocr(self) -> OCRProvider:
        return self.get("ocr")

    @property
    def planner(self) -> PlannerProvider:
        return self.get("planner")

    @property
    def tool_call_parser(self) -> ToolCallParserProvider:
        return self.get("tool_call_parser")

    @property
    def embeddings(self) -> EmbeddingsProvider:
        return self.get("embeddings")

    @property
    def image_edit(self) -> ImageEditProvider:
        return self.get("image_edit")

    @property
    def image_gen(self) -> Any:
        return self.get("image_gen")

    @property
    def unified(self) -> Any:
        return self._unified

    def list_providers(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "type": type(provider).__name__,
                "available": getattr(provider, "available", True),
                "capabilities": ", ".join(sorted(getattr(provider, "capabilities", set()))),
            }
            for name, provider in self._providers.items()
        ]

    def get_runtime_diagnostics(self) -> Any:
        from shopstack.providers.runtime import collect_runtime_diagnostics
        return collect_runtime_diagnostics(self)
