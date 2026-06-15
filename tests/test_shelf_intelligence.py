from __future__ import annotations

from datetime import date
from pathlib import Path

from PIL import Image

from shopstack.services.expiry_parser import expiry_risk_label, parse_expiry_value
from shopstack.services.shelf_intelligence import (
    _clamp_max_frames,
    _collect_frame_paths,
    analyze_shelf_scene,
)
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
        providers.promptable_segmentation,
        "segment_with_prompts",
        lambda _path, **kwargs: [
            {"label": "toothpaste", "score": 0.95, "mask": "prompt_mask_a", "bbox": [0.1, 0.2, 0.3, 0.4]},
            {"label": "toothpaste", "score": 0.94, "mask": "prompt_mask_b", "bbox": [0.4, 0.2, 0.5, 0.4]},
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
        None,
        "fake-home-note.wav",
        "bathroom_cabinet",
        providers,
        tool_registry.inventory,
        user_id="",
    )

    assert result.scene_type.value == "bathroom_cabinet"
    assert result.perception_mode == "promptable_segmentation"
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
        None,
        "fridge",
        providers,
        tool_registry.inventory,
        user_id="",
    )

    assert result.annotated_image_path
    assert result.annotated_image_path != str(image_path)
    assert Path(result.annotated_image_path).exists()


# ───────────────────────────────────────────────────────────────────────
# Frame-sweep / video support tests
# ───────────────────────────────────────────────────────────────────────


class TestClampMaxFrames:
    """The defensive ``_clamp_max_frames`` helper bounds the user-supplied
    frame budget so the scan pipeline cannot be asked to extract zero
    frames (skips the video) or 10,000 frames (explodes the temp dir).
    """

    def test_default_when_none(self):
        assert _clamp_max_frames(None) == 6

    def test_default_when_non_numeric(self):
        assert _clamp_max_frames("not a number") == 6
        assert _clamp_max_frames([1, 2]) == 6
        assert _clamp_max_frames({"k": 1}) == 6

    def test_passes_through_in_range(self):
        assert _clamp_max_frames(1) == 1
        assert _clamp_max_frames(6) == 6
        assert _clamp_max_frames(12) == 12
        assert _clamp_max_frames(50) == 50

    def test_clamps_below_floor(self):
        assert _clamp_max_frames(0) == 1
        assert _clamp_max_frames(-5) == 1

    def test_clamps_above_ceiling(self):
        assert _clamp_max_frames(51) == 50
        assert _clamp_max_frames(10_000) == 50

    def test_coerces_floats(self):
        # 6.7 should be truncated to 6 (int conversion).
        assert _clamp_max_frames(6.7) == 6
        # 0.5 should be clamped up to 1.
        assert _clamp_max_frames(0.5) == 1


class TestFrameSweepTransparent:
    """``analyze_shelf_scene`` must report frame count + paths so the UI
    can render a frame-sweep gallery and the user can sanity-check the
    result against the source video.
    """

    def test_no_video_yields_zero_frame_count(
        self, providers, tool_registry, tmp_path,
    ):
        image_path = tmp_path / "still.png"
        Image.new("RGB", (60, 60), "white").save(image_path)

        result = analyze_shelf_scene(
            str(image_path), None, None, "fridge",
            providers, tool_registry.inventory, user_id="",
            max_frames=8,
        )

        assert result.frame_count == 0
        assert result.frame_paths == []
        # The image still flows through (as the source for the first frame
        # of the conceptual sweep), but ``frame_count`` is the video-frame
        # counter — it stays 0 when no video was uploaded.
        assert result.video_path is None

    def test_video_path_is_recorded_even_when_decode_fails(
        self, providers, tool_registry, tmp_path, monkeypatch,
    ):
        """When cv2/imageio both fail, ``video_path`` is still set
        (for provenance) but ``frame_count`` is 0 (no frames usable).
        """
        monkeypatch.setattr(
            "shopstack.services.shelf_intelligence._first_frame_from_video",
            lambda _path: None,
        )
        monkeypatch.setattr(
            "shopstack.services.shelf_intelligence._extract_video_frames",
            lambda _path, max_frames=6: [],
        )

        result = analyze_shelf_scene(
            None, "/tmp/fake-sweep.mp4", None, "fridge",
            providers, tool_registry.inventory, user_id="",
            max_frames=4,
        )

        assert result.video_path == "/tmp/fake-sweep.mp4"
        assert result.frame_count == 0
        assert result.frame_paths == []

    def test_max_frames_clamps_to_range(
        self, providers, tool_registry, tmp_path, monkeypatch,
    ):
        """Out-of-range max_frames values are clamped, not passed through."""
        captured: dict[str, int] = {}

        def fake_extract(_path: str, max_frames: int = 6) -> list[str]:
            captured["max_frames"] = max_frames
            return []

        monkeypatch.setattr(
            "shopstack.services.shelf_intelligence._first_frame_from_video",
            lambda _path: None,
        )
        monkeypatch.setattr(
            "shopstack.services.shelf_intelligence._extract_video_frames",
            fake_extract,
        )

        # Caller passes 10,000 — should be clamped to 50.
        analyze_shelf_scene(
            None, "/tmp/sweep.mp4", None, "fridge",
            providers, tool_registry.inventory, user_id="",
            max_frames=10_000,
        )
        assert captured["max_frames"] == 50

        # Caller passes 0 — should be clamped to 1.
        analyze_shelf_scene(
            None, "/tmp/sweep.mp4", None, "fridge",
            providers, tool_registry.inventory, user_id="",
            max_frames=0,
        )
        assert captured["max_frames"] == 1

    def test_extract_count_is_recorded_on_result(
        self, providers, tool_registry, tmp_path, monkeypatch,
    ):
        """When frame extraction succeeds, frame_count == len(frame_paths)."""
        fake_frames = [f"/tmp/frame_{i}.png" for i in range(3)]

        monkeypatch.setattr(
            "shopstack.services.shelf_intelligence._first_frame_from_video",
            lambda _path: None,
        )
        monkeypatch.setattr(
            "shopstack.services.shelf_intelligence._extract_video_frames",
            lambda _path, max_frames=6: fake_frames,
        )

        result = analyze_shelf_scene(
            None, "/tmp/sweep.mp4", None, "fridge",
            providers, tool_registry.inventory, user_id="",
            max_frames=6,
        )

        assert result.frame_count == 3
        assert result.frame_paths == fake_frames
        assert result.video_path == "/tmp/sweep.mp4"


class TestCollectFramePaths:
    """``_collect_frame_paths`` merges a still image (as the first frame)
    with up to ``max_frames`` extracted from a video, with safe clamping.
    """

    def test_image_only(self):
        out = _collect_frame_paths("/tmp/photo.jpg", None, max_frames=6)
        assert out == ["/tmp/photo.jpg"]

    def test_video_only_uses_extractor(self, monkeypatch):
        monkeypatch.setattr(
            "shopstack.services.shelf_intelligence._extract_video_frames",
            lambda _path, max_frames=6: ["/tmp/f1.png", "/tmp/f2.png"],
        )
        out = _collect_frame_paths(None, "/tmp/sweep.mp4", max_frames=6)
        assert out == ["/tmp/f1.png", "/tmp/f2.png"]

    def test_image_and_video_merge_with_image_first(self, monkeypatch):
        monkeypatch.setattr(
            "shopstack.services.shelf_intelligence._extract_video_frames",
            lambda _path, max_frames=6: ["/tmp/v1.png", "/tmp/v2.png"],
        )
        out = _collect_frame_paths(
            "/tmp/photo.jpg", "/tmp/sweep.mp4", max_frames=6,
        )
        assert out == ["/tmp/photo.jpg", "/tmp/v1.png", "/tmp/v2.png"]

    def test_max_frames_is_clamped_before_extractor_runs(self, monkeypatch):
        seen: list[int] = []

        def fake_extract(_path: str, max_frames: int = 6) -> list[str]:
            seen.append(max_frames)
            return []

        monkeypatch.setattr(
            "shopstack.services.shelf_intelligence._extract_video_frames",
            fake_extract,
        )
        _collect_frame_paths(None, "/tmp/sweep.mp4", max_frames=999)
        assert seen == [50]  # clamped from 999 to 50
