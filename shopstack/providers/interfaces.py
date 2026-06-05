from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from shopstack.model_registry import RuntimeType


class ProviderBase(ABC):
    name: str = ""
    model_id: str = ""
    parameter_count: float = 0.0
    license_note: str = ""
    runtime_type: RuntimeType = "mock"
    supports_off_grid: bool = True

    @abstractmethod
    def load(self) -> None:
        ...

    @abstractmethod
    def healthcheck(self) -> bool:
        ...


class STTProvider(ProviderBase):
    @abstractmethod
    def transcribe(self, audio_path: str, language: str = "en") -> dict[str, Any]:
        ...


class TTSProvider(ProviderBase):
    @abstractmethod
    def synthesize(self, text: str, language: str = "en") -> bytes | str:
        ...


class VisionProvider(ProviderBase):
    @abstractmethod
    def understand(self, image_path: str, prompt: str = "") -> dict[str, Any]:
        ...


class ObjectDetectionProvider(ProviderBase):
    @abstractmethod
    def detect(self, image_path: str) -> list[dict[str, Any]]:
        ...


class GroundingProvider(ProviderBase):
    @abstractmethod
    def ground(self, image_path: str, text_prompt: str) -> dict[str, Any]:
        ...


class SegmentationProvider(ProviderBase):
    @abstractmethod
    def segment(self, image_path: str) -> list[dict[str, Any]]:
        ...


class OCRProvider(ProviderBase):
    @abstractmethod
    def extract(self, image_path: str) -> dict[str, Any]:
        ...


class PlannerProvider(ProviderBase):
    @abstractmethod
    def plan(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        ...


class ToolCallParserProvider(ProviderBase):
    @abstractmethod
    def parse(self, utterance: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        ...


class EmbeddingsProvider(ProviderBase):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


class ImageEditProvider(ProviderBase):
    @abstractmethod
    def generate_card(self, item_name: str, details: dict[str, Any]) -> str:
        ...

    @abstractmethod
    def annotate_image(self, image_path: str, detections: list[dict]) -> str:
        ...
