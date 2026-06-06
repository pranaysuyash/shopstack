from __future__ import annotations

import json
import random
from datetime import date, datetime, timedelta
from typing import Any

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

MOCK_ITEMS = [
    "tomato", "onion", "potato", "coriander", "chilli", "milk", "bread",
    "eggs", "butter", "cheese", "curd", "rice", "wheat flour", "salt",
    "sugar", "tea", "coffee", "detergent", "soap", "shampoo",
    "toothpaste", "dal", "cooking oil", "spices", "chicken", "fish",
]


class MockSTTProvider(STTProvider):
    name = "mock_stt"
    model_id = "mock-stt-v1"
    parameter_count = 0.0
    capabilities: set[str] = {"stt"}

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def transcribe(self, audio_path: str, language: str = "en") -> dict[str, Any]:
        phrases = [
            "aaj kya kharidna hai",
            "doodh ghar pe hai kya",
            "tamatar aadha kilo add karo",
            "nahi yeh aloo nahi pyaaz hai",
            "bread expiry kal ka hai skip kar do",
            "surf excel already ghar pe hai kya",
        ]
        return {
            "text": random.choice(phrases),
            "confidence": round(random.uniform(0.75, 0.98), 2),
            "language": "hi",
            "duration_s": 2.0,
        }


class MockTTSProvider(TTSProvider):
    name = "mock_tts"
    model_id = "mock-tts-v1"
    parameter_count = 0.0
    capabilities: set[str] = {"tts"}

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def synthesize(self, text: str, language: str = "en") -> bytes | str:
        return b"mock_audio_data"


class MockVisionProvider(VisionProvider):
    name = "mock_vision"
    model_id = "mock-vision-v1"
    parameter_count = 0.0
    capabilities: set[str] = {"vision", "object_detection"}

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def understand(self, image_path: str, prompt: str = "") -> dict[str, Any]:
        count = random.randint(2, 5)
        items = random.sample(MOCK_ITEMS, count)
        return {
            "detected_items": items,
            "description": f"I see {', '.join(items)}",
            "confidences": {item: round(random.uniform(0.6, 0.95), 2) for item in items},
        }


class MockDetectionProvider(ObjectDetectionProvider):
    name = "mock_detection"
    model_id = "mock-detection-v1"
    parameter_count = 0.0
    capabilities: set[str] = {"object_detection"}

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def detect(self, image_path: str) -> list[dict[str, Any]]:
        count = random.randint(2, 5)
        items = random.sample(MOCK_ITEMS, count)
        detections = []
        for i, item in enumerate(items):
            detections.append({
                "label": item,
                "confidence": round(random.uniform(0.55, 0.95), 2),
                "bbox": [random.random() * 0.8 + 0.1 for _ in range(4)],
                "class_id": i,
            })
        return detections


class MockGroundingProvider(GroundingProvider):
    name = "mock_grounding"
    model_id = "mock-grounding-v1"
    parameter_count = 0.0

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def ground(self, image_path: str, text_prompt: str) -> dict[str, Any]:
        return {
            "found": True,
            "bbox": [0.2, 0.3, 0.6, 0.5],
            "confidence": 0.85,
            "label": text_prompt,
        }


class MockSegmentationProvider(SegmentationProvider):
    name = "mock_segmentation"
    model_id = "mock-seg-v1"
    parameter_count = 0.0

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def segment(self, image_path: str) -> list[dict[str, Any]]:
        return [
            {"label": "item", "score": 0.9, "mask": "base64_mock_data", "bbox": [0.1, 0.1, 0.5, 0.5]},
        ]


class MockOCRProvider(OCRProvider):
    name = "mock_ocr"
    model_id = "mock-ocr-v1"
    parameter_count = 0.0
    capabilities: set[str] = {"ocr"}

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def extract(self, image_path: str) -> dict[str, Any]:
        return {
            "brand": "Sample Brand",
            "product_name": "Sample Product",
            "weight": "500g",
            "mrp": 50.0,
            "price_paid": 48.0,
            "expiry_date": (date.today() + timedelta(days=90)).isoformat(),
            "confidence": 0.85,
        }


class MockPlannerProvider(PlannerProvider):
    name = "mock_planner"
    model_id = "mock-planner-v1"
    parameter_count = 0.0
    capabilities: set[str] = {"text", "planning"}

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def plan(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "tool": "add_inventory_item",
                "args": {
                    "canonical_name": "tomato",
                    "display_name": "tomato",
                    "quantity": 0.5,
                    "unit": "kg",
                    "storage_location_id": "fridge",
                },
                "confidence": 0.85,
                "requires_confirmation": True,
            }
        ]


class MockToolCallParser(ToolCallParserProvider):
    name = "mock_parser"
    model_id = "mock-parser-v1"
    parameter_count = 0.0

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def parse(self, utterance: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        text_lower = utterance.lower()
        if "add" in text_lower or "kharid" in text_lower or "add karo" in text_lower:
            intent = "add_inventory_item"
            args = {
                "canonical_name": "tomato",
                "display_name": "tamatar",
                "quantity": 0.5,
                "unit": "kg",
                "storage_location_id": "fridge",
            }
        elif "skip" in text_lower or "hata" in text_lower:
            intent = "remove_from_list"
            args = {"item": "unknown"}
        elif "consume" in text_lower or "use" in text_lower or "kha" in text_lower:
            intent = "consume_item"
            args = {"canonical_name": "unknown", "quantity": 1.0, "unit": "unit"}
        elif "move" in text_lower or "rakh" in text_lower:
            intent = "move_item"
            args = {"item": "unknown", "to_location": "pantry"}
        elif "find" in text_lower or "kahan" in text_lower or "hai kya" in text_lower:
            intent = "find_item"
            args = {"query": utterance}
        else:
            intent = "general_query"
            args = {"query": utterance}

        return {
            "intent": intent,
            "tool": intent,
            "args": args,
            "confidence": 0.8,
            "requires_confirmation": True,
            "raw_utterance": utterance,
        }


class MockEmbeddingsProvider(EmbeddingsProvider):
    name = "mock_embeddings"
    model_id = "mock-embeddings-v1"
    parameter_count = 0.0

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[random.random() * 2 - 1 for _ in range(128)] for _ in texts]


class MockImageEditProvider(ImageEditProvider):
    name = "mock_image_edit"
    model_id = "mock-image-edit-v1"
    parameter_count = 0.0

    def load(self) -> None:
        pass

    def healthcheck(self) -> bool:
        return True

    def generate_card(self, item_name: str, details: dict[str, Any]) -> str:
        return f"mock_card_{item_name}.png"

    def annotate_image(self, image_path: str, detections: list[dict]) -> str:
        return "mock_annotated_image.png"


class MockUnifiedProvider:
    name = "mock"
    capabilities: set[str] = {"text", "vision", "stt", "tts", "ocr", "object_detection", "embeddings"}

    def __init__(self):
        self._stt = MockSTTProvider()
        self._vision = MockVisionProvider()
        self._detection = MockDetectionProvider()
        self._ocr = MockOCRProvider()
        self._planner = MockPlannerProvider()

    def complete(self, prompt: str, **kwargs: Any) -> dict[str, Any]:
        return {"text": f"Mock response to: {prompt[:50]}...", "model": self.name}

    def analyze_image(self, image_path: str, prompt: str = "") -> dict[str, Any]:
        return self._vision.understand(image_path, prompt)

    def transcribe_audio(self, audio_path: str, language: str = "en") -> dict[str, Any]:
        return self._stt.transcribe(audio_path, language)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[random.random() * 2 - 1 for _ in range(128)] for _ in texts]

    def detect_objects(self, image_path: str) -> list[dict[str, Any]]:
        return self._detection.detect(image_path)

    def extract_text(self, image_path: str) -> dict[str, Any]:
        return self._ocr.extract(image_path)
