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
        backends = self._settings.provider_backends
        if backends.get("stt") == "mock":
            self.register("stt", MockSTTProvider())
        if backends.get("tts") == "mock":
            self.register("tts", MockTTSProvider())
        if backends.get("vision") == "mock":
            self.register("vision", MockVisionProvider())
        if backends.get("object_detection") == "mock":
            self.register("object_detection", MockDetectionProvider())
        if backends.get("grounding") == "mock":
            self.register("grounding", MockGroundingProvider())
        if backends.get("segmentation") == "mock":
            self.register("segmentation", MockSegmentationProvider())
        if backends.get("ocr") == "mock":
            self.register("ocr", MockOCRProvider())
        if backends.get("planner") == "mock":
            self.register("planner", MockPlannerProvider())
        if backends.get("tool_call_parser") == "mock":
            self.register("tool_call_parser", MockToolCallParser())
        if backends.get("embeddings") == "mock":
            self.register("embeddings", MockEmbeddingsProvider())
        if backends.get("image_edit") == "mock":
            self.register("image_edit", MockImageEditProvider())

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
