from __future__ import annotations

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
    MockVisionProvider,
)


class ProviderRegistry:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._providers: dict[str, Any] = {}
        self._init_all()

    def _init_all(self) -> None:
        if self._settings.off_the_grid:
            self._init_mock_all()
        else:
            self._init_configured()

    def _init_mock_all(self) -> None:
        self.register("stt", MockSTTProvider())
        self.register("tts", MockTTSProvider())
        self.register("vision", MockVisionProvider())
        self.register("object_detection", MockDetectionProvider())
        self.register("grounding", MockGroundingProvider())
        self.register("segmentation", MockSegmentationProvider())
        self.register("ocr", MockOCRProvider())
        self.register("planner", MockPlannerProvider())
        self.register("tool_call_parser", MockToolCallParser())
        self.register("embeddings", MockEmbeddingsProvider())
        self.register("image_edit", MockImageEditProvider())

    def _init_configured(self) -> None:
        backend_map = {
            "stt": (MockSTTProvider, self._get_mock("stt")),
            "tts": (MockTTSProvider, self._get_mock("tts")),
            "vision": (MockVisionProvider, self._get_mock("vision")),
            "object_detection": (MockDetectionProvider, self._get_mock("object_detection")),
            "grounding": (MockGroundingProvider, self._get_mock("grounding")),
            "segmentation": (MockSegmentationProvider, self._get_mock("segmentation")),
            "ocr": (MockOCRProvider, self._get_mock("ocr")),
            "planner": (MockPlannerProvider, self._get_mock("planner")),
            "tool_call_parser": (MockToolCallParser, self._get_mock("tool_call_parser")),
            "embeddings": (MockEmbeddingsProvider, self._get_mock("embeddings")),
            "image_edit": (MockImageEditProvider, self._get_mock("image_edit")),
        }
        for provider_name, (mock_factory, backend) in backend_map.items():
            if backend == "mock":
                self.register(provider_name, mock_factory())

    def _get_mock(self, provider_name: str) -> str:
        backends = self._settings.provider_backends
        backend = (backends.get(provider_name) or "mock").lower().strip()
        if backend not in {"mock", "mocked"}:
            # Real provider execution is not yet implemented, so fallback to mock.
            return "mock"
        return backend

    def register(self, name: str, provider: Any) -> None:
        self._providers[name] = provider

    def get(self, name: str) -> Any:
        return self._providers.get(name)

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

    def list_providers(self) -> list[dict[str, str]]:
        return [
            {
                "name": name,
                "type": type(provider).__name__,
                "available": hasattr(provider, "transcribe" if name == "stt" else "generate"),
            }
            for name, provider in self._providers.items()
        ]
