from __future__ import annotations

import re
from dataclasses import dataclass

from shopstack.market.normalization import normalize_item_name
from shopstack.schemas.shelf import ShelfSceneType, SpeechIntent

_HOUSEHOLD_ALIASES: dict[str, str] = {
    "tamatar": "tomato",
    "pyaaz": "onion",
    "pyaz": "onion",
    "aloo": "potato",
    "batata": "potato",
    "doodh": "milk",
    "dhaniya": "coriander",
    "dhania": "coriander",
    "sabun": "soap",
    "shampoo": "shampoo",
    "surf excel": "detergent",
    "detergent": "detergent",
    "tooth paste": "toothpaste",
    "toothpaste": "toothpaste",
    "medicine": "medicine",
    "dawai": "medicine",
    "band aid": "bandage",
    "bandage": "bandage",
    "battery": "battery",
    "batteries": "battery",
    "gas lighter": "gas_lighter",
    "lighter": "gas_lighter",
    "water filter": "water_filter",
    "filter candle": "water_filter",
}

_SCENE_KEYWORDS: dict[str, ShelfSceneType] = {
    "fridge": ShelfSceneType.FRIDGE,
    "freezer": ShelfSceneType.FRIDGE,
    "pantry": ShelfSceneType.PANTRY,
    "grocery": ShelfSceneType.PANTRY,
    "bag": ShelfSceneType.SHOPPING_BAG,
    "shopping": ShelfSceneType.SHOPPING_BAG,
    "bathroom": ShelfSceneType.BATHROOM_CABINET,
    "toilet": ShelfSceneType.BATHROOM_CABINET,
    "medicine": ShelfSceneType.MEDICINE_DRAWER,
    "first aid": ShelfSceneType.MEDICINE_DRAWER,
    "cleaning": ShelfSceneType.CLEANING_CUPBOARD,
    "bedroom": ShelfSceneType.BEDROOM,
    "document": ShelfSceneType.DOCUMENTS,
    "utility": ShelfSceneType.UTILITY,
}


@dataclass(frozen=True)
class ParsedSpeech:
    translated_text: str
    canonical_items: list[str]
    action: str
    target_scene: ShelfSceneType
    confidence: float
    notes: list[str]


def parse_speech_intent(text: str, language: str = "en") -> SpeechIntent:
    parsed = _parse_speech_text(text)
    return SpeechIntent(
        original_text=text or "",
        translated_text=parsed.translated_text,
        language=(language or "en"),
        action=parsed.action,
        canonical_items=parsed.canonical_items,
        target_scene=parsed.target_scene,
        confidence=parsed.confidence,
        notes=parsed.notes,
    )


def _parse_speech_text(text: str) -> ParsedSpeech:
    raw = (text or "").strip()
    lowered = raw.lower()
    notes: list[str] = []

    action = "observe"
    if any(token in lowered for token in ("use soon", "expiry", "expires", "best before", "kal ka", "tomorrow")):
        action = "mark_use_soon"
    if any(token in lowered for token in ("skip", "mat lena", "don't buy", "do not buy", "avoid")):
        action = "skip"
    if any(token in lowered for token in ("add", "kharid", "buy", "put", "le aao", "laho", "lao")):
        action = "add"
    if any(token in lowered for token in ("move", "rakh", "place", "shift")):
        action = "move"
    if any(token in lowered for token in ("find", "kahan", "where", "locate")):
        action = "locate"

    canonical_items: list[str] = []
    translated = lowered
    for alias, canonical in sorted(_HOUSEHOLD_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if alias in lowered:
            canonical_name = normalize_item_name(canonical)
            canonical_items.append(canonical_name)
            translated = re.sub(rf"\b{re.escape(alias)}\b", canonical.replace("_", " "), translated)
            notes.append(f"alias:{alias}->{canonical}")

    target_scene = ShelfSceneType.AUTO
    for keyword, scene in _SCENE_KEYWORDS.items():
        if keyword in lowered:
            target_scene = scene
            break

    if not canonical_items and raw:
        # Try a generic canonicalization so “not X” phrases still bind to a thing.
        generic = normalize_item_name(raw)
        if generic and generic != raw.lower():
            canonical_items.append(generic)

    confidence = 0.35
    if canonical_items:
        confidence += 0.25
    if action != "observe":
        confidence += 0.2
    if target_scene != ShelfSceneType.AUTO:
        confidence += 0.1
    if any(token in lowered for token in ("nahi", "not", "don't", "do not")):
        notes.append("correction_phrase")
        confidence += 0.05
        if action == "add":
            action = "correct"

    translated = re.sub(r"\s+", " ", translated).strip()
    if not translated:
        translated = raw

    return ParsedSpeech(
        translated_text=translated,
        canonical_items=sorted(set(canonical_items)),
        action=action,
        target_scene=target_scene,
        confidence=min(0.95, confidence),
        notes=notes,
    )

