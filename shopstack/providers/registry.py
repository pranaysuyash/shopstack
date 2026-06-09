from __future__ import annotations

import logging
from typing import Any

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

_REAL_PROVIDER_MAP: dict[str, str] = {}


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


def _try_real_provider(backend: str, settings: Settings) -> Any | None:
    if backend == "local_whisper":
        cls = _load_local_whisper()
        if cls:
            return cls(
                model_dir=settings.local_model_dir,
                model_size=settings.local_whisper_size,
                auto_unload=settings.local_whisper_auto_unload,
            )
        logger.info("Local Whisper provider not available (mlx-whisper / faster-whisper missing), falling back to mock")
        return None
    if backend == "openai":
        cls = _load_openai()
        if cls:
            return cls(api_key=settings.openai_api_key)
        logger.info("OpenAI provider not available (openai package missing), falling back to mock")
        return None
    if backend == "whisper":
        cls = _load_whisper()
        if cls:
            return cls(api_key=settings.openai_api_key)
        logger.info("Whisper provider not available (openai package missing), falling back to mock")
        return None
    if backend == "local":
        cls = _load_local()
        if cls:
            return cls(
                model_dir=settings.local_model_dir,
                model_repo=settings.local_model_repo,
                model_file=settings.local_model_file,
                mlx_model=settings.local_mlx_model,
                allow_download=settings.local_auto_download,
                auto_unload=settings.local_auto_unload,
            )
        logger.info("Local provider not available (mlx-lm / llama-cpp-python missing), falling back to mock")
        return None
    if backend == "huggingface":
        cls = _load_huggingface()
        if cls:
            return cls(api_key=settings.hf_api_key)
        logger.info("HuggingFace provider not available (huggingface_hub package missing), falling back to mock")
        return None
    if backend == "sensevoice":
        cls = _load_sensevoice()
        if cls:
            return cls()
        logger.info("SenseVoice STT provider not available (funasr package missing), falling back to mock")
        return None
    if backend == "kokoro":
        cls = _load_kokoro_tts()
        if cls:
            return cls()
        logger.info("Kokoro TTS provider not available (kokoro package missing), falling back to mock")
        return None
    if backend == "qwen3_asr":
        cls = _load_qwen3_asr()
        if cls:
            return cls()
        logger.info("Qwen3-ASR provider not available (transformers/torch missing), falling back to mock")
        return None
    if backend == "bge_m3" or backend == "bge-m3":
        cls = _load_bge_m3()
        if cls:
            return cls()
        logger.info("BGE-M3 provider not available (sentence-transformers missing), falling back to mock")
        return None
    if backend == "minicpmv":
        cls = _load_minicpmv()
        if cls:
            return cls()
        logger.info("MiniCPM-V provider not available (transformers/torch missing), falling back to mock")
        return None
    if backend == "minicpm5":
        cls = _load_minicpm5()
        if cls:
            return cls()
        logger.info("MiniCPM5 provider not available (transformers/torch missing), falling back to mock")
        return None
    if backend == "qwen3_tts":
        cls = _load_qwen3_tts()
        if cls:
            return cls()
        logger.info("Qwen3-TTS provider not available (transformers/torch missing), falling back to mock")
        return None
    if backend == "nuextract3" or backend == "nuextract":
        cls = _load_nuextract3()
        if cls:
            return cls()
        logger.info("NuExtract3 provider not available (transformers/torch missing), falling back to mock")
        return None
    if backend == "glm_ocr" or backend == "glm-ocr":
        cls = _load_glm_ocr()
        if cls:
            return cls()
        logger.info("GLM-OCR provider not available (transformers/torch/torchvision missing), falling back to mock")
        return None
    if backend == "tesseract":
        cls = _load_tesseract()
        if cls:
            return cls()
        logger.info("Tesseract OCR provider not available (pytesseract missing), falling back to mock")
        return None
    if backend == "rmbg":
        cls = _load_rmbg()
        if cls:
            return cls()
        logger.info("RMBG provider not available (transformers/torch missing), falling back to mock")
        return None
    if backend == "parakeet":
        cls = _load_parakeet()
        if cls:
            return cls()
        logger.info("Parakeet provider not available (transformers/torch missing), falling back to mock")
        return None
    return None


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
