from __future__ import annotations

from datetime import date
from pathlib import Path

from PIL import Image

from shopstack.services.expiry_parser import expiry_risk_label, parse_expiry_value
from shopstack.services.shelf_intelligence import analyze_shelf_scene
from shopstack.services.speech_intent import parse_speech_intent


def test_parse_expiry_value_supports_common_indian_formats():
    assert parse_expiry_value("2026-06-13") == date(2026, 6, 13)
    assert parse_expiry_value("13/06/2026") == date(2026, 6, 13)
    assert parse_expiry_value("13 JUN 26") == date(2026, 6, 13)
    assert expiry_risk_label(date.today()) == "today"


def test_parse_speech_intent_translates_local_aliases():
    intent = parse_speech_intent("tamatar aadha kilo add karo", language="hi")

    assert intent.action == "add"
    assert "tomato" in intent.canonical_items
    assert "tomato" in intent.translated_text


def test_analyze_shelf_scene_returns_structured_home_scan(providers, tool_registry, monkeypatch):
    tool_registry.inventory.add_item(
        canonical_name="toothpaste",
        display_name="Toothpaste",
        quantity=1.0,
        unit="tube",
        storage_location_id="bathroom_cabinet",
        user_id="",
    )

    monkeypatch.setattr(
        providers.object_detection,
        "detect",
        lambda _path: [
            {"label": "toothpaste", "confidence": 0.94, "bbox": [0.1, 0.2, 0.3, 0.4], "class_id": 0},
            {"label": "toothpaste", "confidence": 0.91, "bbox": [0.4, 0.2, 0.5, 0.4], "class_id": 1},
        ],
    )
    monkeypatch.setattr(
        providers.segmentation,
        "segment",
        lambda _path: [
            {"label": "toothpaste", "score": 0.88, "mask": "mask_a", "bbox": [0.1, 0.2, 0.3, 0.4]},
            {"label": "toothpaste", "score": 0.84, "mask": "mask_b", "bbox": [0.4, 0.2, 0.5, 0.4]},
        ],
    )
    monkeypatch.setattr(
        providers.ocr,
        "extract",
        lambda _path: {
            "brand": "Sample Brand",
            "product_name": "Toothpaste",
            "weight": "2 pieces",
            "expiry_date": "13 JUN 26",
            "confidence": 0.93,
            "raw_text": "Sample Brand Toothpaste 13 JUN 26",
        },
    )
    monkeypatch.setattr(
        providers.stt,
        "transcribe",
        lambda _path, language="en": {
            "text": "toothpaste expiry tomorrow",
            "confidence": 0.96,
            "language": "en",
        },
    )

    result = analyze_shelf_scene(
        "fake-home-scan.jpg",
        "fake-home-note.wav",
        "bathroom_cabinet",
        providers,
        tool_registry.inventory,
        user_id="",
    )

    assert result.scene_type.value == "bathroom_cabinet"
    assert result.perception_mode == "detection_segmentation"
    assert result.annotated_image_path
    assert len(result.instances) == 2
    assert result.aggregates[0].count == 2
    assert result.aggregates[0].recommendation in {"refill", "confirm", "update"}
    assert any(action.action in {"refill", "update_quantity"} for action in result.proposed_actions)
    assert result.speech_intent is not None
    assert result.speech_intent.action == "mark_use_soon"
    assert result.ocr_findings
    assert result.confidence_summary.items_seen == 2
    assert result.confidence_summary.items_grouped == 1


def test_analyze_shelf_scene_renders_local_annotation_when_provider_fails(
    providers,
    tool_registry,
    monkeypatch,
    tmp_path,
):
    image_path = tmp_path / "home_scan.png"
    Image.new("RGB", (120, 120), "white").save(image_path)

    tool_registry.inventory.add_item(
        canonical_name="milk",
        display_name="Milk",
        quantity=1.0,
        unit="packet",
        storage_location_id="fridge",
        user_id="",
    )

    monkeypatch.setattr(
        providers.object_detection,
        "detect",
        lambda _path: [{"label": "milk", "confidence": 0.88, "bbox": [0.1, 0.2, 0.7, 0.8], "class_id": 0}],
    )
    monkeypatch.setattr(
        providers.image_edit,
        "annotate_image",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("annotator down")),
    )

    result = analyze_shelf_scene(
        str(image_path),
        None,
        "fridge",
        providers,
        tool_registry.inventory,
        user_id="",
    )

    assert result.annotated_image_path
    assert result.annotated_image_path != str(image_path)
    assert Path(result.annotated_image_path).exists()
