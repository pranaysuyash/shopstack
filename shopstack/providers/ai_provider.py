from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ProviderInfo:
    name: str
    capabilities: set[str] = field(default_factory=set)
    available: bool = True
    error: str | None = None


class AIProvider(Protocol):
    name: str
    capabilities: set[str]

    def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        ...

    def analyze_image(self, image_path: str, prompt: str = "") -> dict[str, Any]:
        ...

    def transcribe_audio(self, audio_path: str, language: str = "en") -> dict[str, Any]:
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...

    def detect_objects(self, image_path: str) -> list[dict[str, Any]]:
        ...

    def extract_text(self, image_path: str) -> dict[str, Any]:
        ...
