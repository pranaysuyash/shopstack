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

logger = logging.getLogger(__name__)

_REAL_PROVIDER_MAP: dict[str, str] = {}


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


def _try_real_provider(backend: str, settings: Settings) -> Any | None:
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
            )
        logger.info("Local provider not available (llama-cpp-python missing), falling back to mock")
        return None
    return None


class ProviderRegistry:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._providers: dict[str, Any] = {}
        self._unified: Any | None = None
        self._init_all()

    def _init_all(self) -> None:
        if self._settings.off_the_grid:
            self._init_mock_all()
        else:
            self._init_configured()
        self._unified = MockUnifiedProvider()

    def _init_mock_all(self) -> None:
        for name, provider in [
            ("stt", MockSTTProvider()),
            ("tts", MockTTSProvider()),
            ("vision", MockVisionProvider()),
            ("object_detection", MockDetectionProvider()),
            ("grounding", MockGroundingProvider()),
            ("segmentation", MockSegmentationProvider()),
            ("ocr", MockOCRProvider()),
            ("planner", MockPlannerProvider()),
            ("tool_call_parser", MockToolCallParser()),
            ("embeddings", MockEmbeddingsProvider()),
            ("image_edit", MockImageEditProvider()),
        ]:
            self.register(name, provider)

    def _init_configured(self) -> None:
        backends = self._settings.provider_backends

        for name, mock_factory in [
            ("stt", MockSTTProvider),
            ("tts", MockTTSProvider),
            ("vision", MockVisionProvider),
            ("object_detection", MockDetectionProvider),
            ("grounding", MockGroundingProvider),
            ("segmentation", MockSegmentationProvider),
            ("ocr", MockOCRProvider),
            ("planner", MockPlannerProvider),
            ("tool_call_parser", MockToolCallParser),
            ("embeddings", MockEmbeddingsProvider),
            ("image_edit", MockImageEditProvider),
        ]:
            backend = (backends.get(name) or "mock").lower().strip()
            if backend == "mock" or backend == "mocked":
                self.register(name, mock_factory())
                continue
            real = _try_real_provider(backend, self._settings)
            if real:
                self.register(name, real)
            else:
                self.register(name, mock_factory())

    def register(self, name: str, provider: Any) -> None:
        self._providers[name] = provider

    def get(self, name: str) -> Any:
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
        return self._providers.get("stt")

    @property
    def tts(self) -> TTSProvider:
        return self._providers.get("tts")

    @property
    def vision(self) -> VisionProvider:
        return self._providers.get("vision")

    @property
    def object_detection(self) -> ObjectDetectionProvider:
        return self._providers.get("object_detection")

    @property
    def grounding(self) -> GroundingProvider:
        return self._providers.get("grounding")

    @property
    def segmentation(self) -> SegmentationProvider:
        return self._providers.get("segmentation")

    @property
    def ocr(self) -> OCRProvider:
        return self._providers.get("ocr")

    @property
    def planner(self) -> PlannerProvider:
        return self._providers.get("planner")

    @property
    def tool_call_parser(self) -> ToolCallParserProvider:
        return self._providers.get("tool_call_parser")

    @property
    def embeddings(self) -> EmbeddingsProvider:
        return self._providers.get("embeddings")

    @property
    def image_edit(self) -> ImageEditProvider:
        return self._providers.get("image_edit")

    @property
    def unified(self) -> Any:
        return self._unified

    def list_providers(self) -> list[dict[str, str]]:
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
