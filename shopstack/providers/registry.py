from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from shopstack.config import Settings
from shopstack.providers.image_gen_provider import FluxImageProvider
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
    MockDetectionProvider,
    MockEmbeddingsProvider,
    MockGroundingProvider,
    MockOCRProvider,
    MockPlannerProvider,
    MockSegmentationProvider,
    MockSTTProvider,
    MockToolCallParser,
    MockTTSProvider,
    MockUnifiedProvider,
    MockVisionProvider,
)

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


def _load_modal():
    """Lazy-load the Modal provider (Phase 6 #18).

    Returns the class so the registry can instantiate it; the
    class itself is in :mod:`shopstack.providers.modal_provider`.
    The loader never raises; it returns ``None`` on import error
    so the registry can fall back to the mock provider.
    """
    try:
        from shopstack.providers.modal_provider import ModalPlannerProvider
        return ModalPlannerProvider
    except ImportError:
        return None


def _load_modal_vision():
    try:
        from shopstack.providers.modal_provider import ModalVisionProvider
        return ModalVisionProvider
    except ImportError:
        return None


def _load_modal_ocr():
    try:
        from shopstack.providers.modal_provider import ModalOCRProvider
        return ModalOCRProvider
    except ImportError:
        return None


def _load_modal_embeddings():
    try:
        from shopstack.providers.modal_provider import ModalEmbeddingsProvider
        return ModalEmbeddingsProvider
    except ImportError:
        return None


def _load_modal_stt():
    try:
        from shopstack.providers.modal_provider import ModalSTTProvider
        return ModalSTTProvider
    except ImportError:
        return None


def _load_modal_tts():
    try:
        from shopstack.providers.modal_provider import ModalTTSProvider
        return ModalTTSProvider
    except ImportError:
        return None


def _load_modal_segmentation():
    try:
        from shopstack.providers.modal_provider import ModalSegmentationProvider
        return ModalSegmentationProvider
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


def _load_nomic():
    try:
        from shopstack.providers.embeddings_provider import NomicEmbeddingProvider
        return NomicEmbeddingProvider
    except ImportError:
        return None


def _load_minicpmv():
    try:
        from shopstack.providers.vision_provider import MiniCPMVProvider
        return MiniCPMVProvider
    except ImportError:
        return None


def _load_qwen3vl():
    try:
        from shopstack.providers.vision_provider import Qwen3VLProvider
        return Qwen3VLProvider
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


def _load_birefnet():
    try:
        from shopstack.providers.segmentation_provider import (
            BiRefNetSegmentationProvider,
        )
        return BiRefNetSegmentationProvider
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


def _load_cosyvoice():
    try:
        from shopstack.providers.cosyvoice_provider import CosyVoiceTTSProvider
        return CosyVoiceTTSProvider
    except ImportError:
        return None


def _load_grounding_dino():
    try:
        from shopstack.providers.grounding_provider import GroundingDINOProvider
        return GroundingDINOProvider
    except ImportError:
        return None


def _load_promptable_segmentation():
    try:
        from shopstack.providers.promptable_segmentation_provider import (
            UltralyticsPromptableSegmentationProvider,
        )
        return UltralyticsPromptableSegmentationProvider
    except ImportError:
        return None


# ── Provider specification table ───────────────────────────────────────
# Adding a new provider = one entry here + a _load_* function above.


@dataclass
class _ProviderSpec:
    loader: Callable[[], type | None]
    kwargs_fn: Callable[[Settings], dict[str, Any]]
    unavailable_msg: str
    supports_off_grid: bool = True


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
        supports_off_grid=False,
    ),
    "whisper": _ProviderSpec(
        loader=_load_whisper,
        kwargs_fn=lambda s: {"api_key": s.openai_api_key},
        unavailable_msg="Whisper provider not available (openai package missing), falling back to mock",
        supports_off_grid=False,
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
        supports_off_grid=False,
    ),
    "modal": _ProviderSpec(
        # ── Phase 6 #18: Modal cloud-GPU provider ─────────────
        # Calls a user-deployed Modal function via HTTP webhook.
        # No `modal` SDK needed at runtime — the function URL is
        # enough. See shopstack/providers/modal_provider.py.
        loader=lambda: _load_modal(),
        kwargs_fn=lambda s: {
            "url": getattr(s, "modal_planner_url", "") or "",
        },
        unavailable_msg="Modal provider not available (modal_provider import failed), falling back to mock",
        supports_off_grid=False,
    ),
    "modal_vision": _ProviderSpec(
        loader=lambda: _load_modal_vision(),
        kwargs_fn=lambda s: {
            "url": getattr(s, "modal_vision_url", "") or "",
        },
        unavailable_msg="Modal Vision provider not available, falling back to mock",
        supports_off_grid=False,
    ),
    "modal_ocr": _ProviderSpec(
        loader=lambda: _load_modal_ocr(),
        kwargs_fn=lambda s: {
            "url": getattr(s, "modal_ocr_url", "") or "",
        },
        unavailable_msg="Modal OCR provider not available, falling back to mock",
        supports_off_grid=False,
    ),
    "modal_embeddings": _ProviderSpec(
        loader=lambda: _load_modal_embeddings(),
        kwargs_fn=lambda s: {
            "url": getattr(s, "modal_embeddings_url", "") or "",
        },
        unavailable_msg="Modal Embeddings provider not available, falling back to mock",
        supports_off_grid=False,
    ),
    "modal_stt": _ProviderSpec(
        loader=lambda: _load_modal_stt(),
        kwargs_fn=lambda s: {
            "url": getattr(s, "modal_stt_url", "") or "",
        },
        unavailable_msg="Modal STT provider not available, falling back to mock",
        supports_off_grid=False,
    ),
    "modal_tts": _ProviderSpec(
        loader=lambda: _load_modal_tts(),
        kwargs_fn=lambda s: {
            "url": getattr(s, "modal_tts_url", "") or "",
        },
        unavailable_msg="Modal TTS provider not available, falling back to mock",
        supports_off_grid=False,
    ),
    "modal_segmentation": _ProviderSpec(
        loader=lambda: _load_modal_segmentation(),
        kwargs_fn=lambda s: {
            "url": getattr(s, "modal_segmentation_url", "") or "",
        },
        unavailable_msg="Modal Segmentation provider not available, falling back to mock",
        supports_off_grid=False,
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
    "nomic": _ProviderSpec(
        loader=_load_nomic,
        kwargs_fn=lambda _s: {},
        unavailable_msg="Nomic-Embed provider not available (sentence-transformers missing), falling back to mock",
    ),
    "minicpmv": _ProviderSpec(
        loader=_load_minicpmv,
        kwargs_fn=lambda _s: {},
        unavailable_msg="MiniCPM-V provider not available (transformers/torch missing), falling back to mock",
    ),
    "qwen3vl": _ProviderSpec(
        loader=_load_qwen3vl,
        kwargs_fn=lambda _s: {},
        unavailable_msg="Qwen3-VL provider not available (transformers/torch missing), falling back to mock",
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
    "birefnet": _ProviderSpec(
        loader=_load_birefnet,
        kwargs_fn=lambda _s: {},
        unavailable_msg="BiRefNet provider not available (torch/torchvision/huggingface_hub missing), falling back to mock",
    ),
    "parakeet": _ProviderSpec(
        loader=_load_parakeet,
        kwargs_fn=lambda _s: {},
        unavailable_msg="Parakeet provider not available (transformers/torch missing), falling back to mock",
    ),
    "cosyvoice": _ProviderSpec(
        loader=_load_cosyvoice,
        kwargs_fn=lambda _s: {},
        unavailable_msg="CosyVoice TTS provider not available (cosyvoice package missing), falling back to mock",
    ),
    "grounding_dino": _ProviderSpec(
        loader=_load_grounding_dino,
        kwargs_fn=lambda _s: {},
        unavailable_msg="GroundingDINO provider not available (transformers/torch missing), falling back to mock",
    ),
    "sam2": _ProviderSpec(
        loader=_load_promptable_segmentation,
        kwargs_fn=lambda _s: {"model_name": "sam2.1_b.pt", "family": "sam"},
        unavailable_msg="SAM2 promptable segmentation provider not available (ultralytics missing), falling back to mock",
    ),
    "mobile_sam": _ProviderSpec(
        loader=_load_promptable_segmentation,
        kwargs_fn=lambda _s: {"model_name": "mobile_sam.pt", "family": "sam"},
        unavailable_msg="MobileSAM promptable segmentation provider not available (ultralytics missing), falling back to mock",
    ),
    "fastsam": _ProviderSpec(
        loader=_load_promptable_segmentation,
        kwargs_fn=lambda _s: {"model_name": "FastSAM-s.pt", "family": "fastsam"},
        unavailable_msg="FastSAM promptable segmentation provider not available (ultralytics missing), falling back to mock",
    ),
    "sam3": _ProviderSpec(
        loader=_load_promptable_segmentation,
        kwargs_fn=lambda _s: {"model_name": "sam3.pt", "family": "sam"},
        unavailable_msg="SAM3 promptable segmentation provider not available (ultralytics missing), falling back to mock",
    ),
    "svg": _ProviderSpec(
        loader=lambda: FluxImageProvider,
        kwargs_fn=lambda _s: {},
        unavailable_msg="SVG/Flux image provider not available, falling back to mock",
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
        self._backend_requests: dict[str, str] = {}
        self._fallback_backends: dict[str, str] = {}
        self._blocked_backends: dict[str, str] = {}
        self._unified: Any | None = None
        self._init_lazy()

    def _init_lazy(self) -> None:
        backends = self._settings.provider_backends
        for name in ["stt", "tts", "vision", "object_detection", "grounding",
                     "segmentation", "promptable_segmentation", "ocr", "planner", "tool_call_parser",
                     "embeddings", "image_edit", "image_gen"]:
            self._pending[name] = backends.get(name, "mock")
            self._backend_requests[name] = self._pending[name]
        self._unified = MockUnifiedProvider()

    def _resolve(self, name: str, expected_cap: str) -> Any:
        backend = self._pending.pop(name, "mock")
        self._backend_requests[name] = backend
        self._fallback_backends.pop(name, None)
        if not backend or backend in {"mock", "mocked"}:
            return self._mock_for(name)
        spec = _PROVIDER_SPECS.get(backend.replace("-", "_"))
        if self._settings.off_the_grid and spec is not None and not spec.supports_off_grid:
            logger.info("Provider %s blocked by off-grid policy, falling back to mock", backend)
            self._blocked_backends[name] = backend
            mock = self._mock_for(name)
            if mock is not None:
                mock.backend = backend
            return mock
        real = _try_real_provider(backend, self._settings)
        if real:
            caps = getattr(real, "capabilities", set())
            if expected_cap in caps:
                return real
            else:
                logger.warning(f"Provider {backend} does not support '{expected_cap}', falling back")
        mock = self._mock_for(name)
        if mock is not None and backend not in {"", "mock", "mocked"}:
            self._fallback_backends[name] = backend
            mock.backend = backend
        return mock

    def _mock_for(self, name: str) -> Any:
        mocks = {
            "stt": MockSTTProvider, "tts": MockTTSProvider,
            "vision": MockVisionProvider, "object_detection": MockDetectionProvider,
            "grounding": MockGroundingProvider, "segmentation": MockSegmentationProvider,
            "promptable_segmentation": MockSegmentationProvider,
            "ocr": MockOCRProvider, "planner": MockPlannerProvider,
            "tool_call_parser": MockToolCallParser, "embeddings": MockEmbeddingsProvider,
            "image_edit": FluxImageProvider, "image_gen": FluxImageProvider,
        }
        # cosyvoice resolves through the provider spec; no dedicated mock needed.
        cls = mocks.get(name)
        if cls:
            return cls() if callable(cls) else cls
        return None

    def register(self, name: str, provider: Any) -> None:
        self._providers[name] = provider
        self._pending.pop(name, None)
        self._fallback_backends.pop(name, None)
        if provider is not None:
            self._backend_requests[name] = getattr(provider, "backend", provider.name if hasattr(provider, "name") else "registered")

    def get(self, name: str) -> Any:
        expected_cap = "planning" if name == "planner" else name
        if name not in self._providers and name in self._pending:
            self._providers[name] = self._resolve(name, expected_cap)
            
        return self._providers.get(name)

    def supports(self, capability: str) -> bool:
        for provider in self._providers.values():
            caps = getattr(provider, "capabilities", set())
            if capability in caps:
                return True
        for name in self._pending.keys():
            provider = self._mock_for(name)
            if provider and capability in getattr(provider, "capabilities", set()):
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
    def promptable_segmentation(self) -> Any:
        return self.get("promptable_segmentation")

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
        names = set(self._providers.keys()) | set(self._pending.keys())
        return [
            self._provider_summary(name, provider)
            for name, provider in sorted(
                [(name, self._providers.get(name)) for name in names],
                key=lambda pair: pair[0],
            )
        ]

    def _provider_summary(self, name: str, provider: Any) -> dict[str, Any]:
        pending_backend = self._pending.get(name, self._backend_requests.get(name, "mock"))
        normalized_backend = pending_backend.lower() if pending_backend else ""
        is_mock_backend = normalized_backend in {"mock", "mocked", ""}
        blocked_backend = self._blocked_backends.get(name, "")
        if provider is None:
            mock = self._mock_for(name)
            requested_backend = pending_backend or "mock"
            row_type = requested_backend if not is_mock_backend else (type(mock).__name__ if mock else "mock")
            return {
                "name": name,
                "type": row_type,
                "backend": requested_backend,
                "available": bool(mock) if is_mock_backend else False,
                "pending": bool(blocked_backend == ""),
                "capabilities": ", ".join(sorted(getattr(mock, "capabilities", set()))) if mock else "",
                "status": "blocked_off_grid" if blocked_backend else "pending",
            }

        requested_backend = pending_backend or self._backend_requests.get(name, "mock")
        _normalized_requested = requested_backend.lower() if requested_backend else ""
        is_real_request_for_mock_provider = (
            not is_mock_backend
            and self._fallback_backends.get(name) == requested_backend
            and type(provider).__name__.lower().startswith("mock")
        )
        is_blocked_off_grid = bool(blocked_backend)
        is_available_default = getattr(provider, "available", True)
        available = False if (is_real_request_for_mock_provider or is_blocked_off_grid) else is_available_default
        return {
            "name": name,
            "type": type(provider).__name__,
            "backend": getattr(provider, "backend", pending_backend),
            "available": available,
            "pending": bool(is_real_request_for_mock_provider),
            "capabilities": ", ".join(sorted(getattr(provider, "capabilities", set()))),
            "status": (
                "blocked_off_grid"
                if is_blocked_off_grid
                else ("fallback" if is_real_request_for_mock_provider else getattr(provider, "status", "resolved"))
            ),
            "blocked_by_off_grid": is_blocked_off_grid,
        }

    def get_runtime_diagnostics(self) -> Any:
        from shopstack.providers.runtime import collect_runtime_diagnostics
        return collect_runtime_diagnostics(self)
