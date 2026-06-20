from __future__ import annotations

import json
import os

import pytest

from shopstack.app_context import (
    current_user_id,
    db as app_db,
    providers as app_providers,
)
from shopstack.schemas.models import Trace
from shopstack.ui.screens.shelf_scan import (
    shelf_scan_confirm,
    shelf_scan_process,
    shelf_scan_save_trace,
    shelf_scan_skip,
)


@pytest.fixture(scope="session", autouse=True)
def _set_test_env():
    os.environ["SHOPSTACK_DB_PATH"] = ":memory:"
    yield


@pytest.fixture(scope="session")
def _app_session():
    import app as _app
    return _app


@pytest.fixture
def app(_app_session):
    app_mod = _app_session
    conn = app_mod.db.conn
    conn.execute("PRAGMA foreign_keys = OFF")
    for table in ["inventory_lots", "shopping_list_items", "shopping_lists",
                  "movement_events", "price_observations", "purchase_events",
                  "traces", "household_locations"]:
        conn.execute(f"DELETE FROM {table}")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    app_mod.db._seed_locations()
    app_mod.db._seed_default_household()
    # ``active_household_id`` must point at a real household+owner pair, since
    # Phase 11 write paths verify membership before persisting. Setting it to
    # empty silently broke every write through shelf-scan, which falls back
    # to ``active_household_id`` when no explicit ``user_id`` is passed.
    app_mod.db.set_config_value("active_household_id", "default_household")
    app_mod.db.active_household_id = "default_household"
    return app_mod


def test_shelf_scan_process_and_confirm_updates_inventory(app, monkeypatch):
    monkeypatch.setattr(
        app_providers.object_detection,
        "detect",
        lambda _path: [{"label": "toothpaste", "confidence": 0.96, "bbox": [0.1, 0.2, 0.3, 0.4], "class_id": 0}],
    )
    monkeypatch.setattr(
        app_providers.segmentation,
        "segment",
        lambda _path: [{"label": "toothpaste", "score": 0.88, "mask": "mask_a", "bbox": [0.1, 0.2, 0.3, 0.4]}],
    )
    monkeypatch.setattr(
        app_providers.ocr,
        "extract",
        lambda _path: {
            "product_name": "Toothpaste",
            "weight": "1 piece",
            "confidence": 0.91,
            "raw_text": "Toothpaste",
        },
    )

    html, scan_state, trace_id, annotated = shelf_scan_process("fake-home-scan.jpg", None, "bathroom_cabinet")

    assert "Home Scan" in html
    assert trace_id
    assert annotated

    parsed = json.loads(scan_state)
    assert parsed["scene_type"] == "bathroom_cabinet"
    assert parsed["proposed_actions"]

    result = shelf_scan_confirm(scan_state, trace_id)
    assert "Applied" in result or "Nothing needed" in result
    items = app_db.get_inventory(user_id=current_user_id())
    assert any(item.canonical_name == "toothpaste" for item in items)


def test_shelf_scan_skip_and_save_trace(app, monkeypatch):
    monkeypatch.setattr(
        app_providers.object_detection,
        "detect",
        lambda _path: [{"label": "soap", "confidence": 0.86, "bbox": [0.1, 0.2, 0.3, 0.4], "class_id": 0}],
    )
    monkeypatch.setattr(
        app_providers.segmentation,
        "segment",
        lambda _path: [{"label": "soap", "score": 0.83, "mask": "mask_b", "bbox": [0.1, 0.2, 0.3, 0.4]}],
    )
    monkeypatch.setattr(
        app_providers.ocr,
        "extract",
        lambda _path: {
            "product_name": "Soap",
            "weight": "1 piece",
            "confidence": 0.89,
            "raw_text": "Soap",
        },
    )

    _, scan_state, trace_id, _ = shelf_scan_process("fake-soap-scan.jpg", None, None, "bathroom_cabinet")
    skip = shelf_scan_skip(scan_state, trace_id)
    save = shelf_scan_save_trace(scan_state, trace_id)

    assert "Saved this shelf scan" in skip
    assert "saved" in save.lower()


def test_shelf_scan_process_with_video(app, monkeypatch):
    """Test shelf scan with video input (frame sweep)."""
    monkeypatch.setattr(
        app_providers.object_detection,
        "detect",
        lambda _path: [{"label": "milk", "confidence": 0.95, "bbox": [0.1, 0.1, 0.3, 0.4], "class_id": 0}],
    )
    monkeypatch.setattr(
        app_providers.segmentation,
        "segment",
        lambda _path: [{"label": "milk", "score": 0.92, "mask": "mask_c", "bbox": [0.1, 0.1, 0.3, 0.4]}],
    )
    monkeypatch.setattr(
        app_providers.ocr,
        "extract",
        lambda _path: {
            "product_name": "Milk",
            "weight": "1 L",
            "confidence": 0.93,
            "raw_text": "Milk 1L",
        },
    )
    # Mock frame extraction from video
    monkeypatch.setattr(
        "shopstack.services.shelf_intelligence._collect_frame_paths",
        lambda image_path, video_path, max_frames=6: ["/tmp/test_frame_01.jpg", "/tmp/test_frame_02.jpg"],
    )
    monkeypatch.setattr(
        "shopstack.services.shelf_intelligence._first_frame_from_video",
        lambda _path: "/tmp/test_frame_01.jpg",
    )

    # Test with video input (no image)
    html, scan_state, trace_id, annotated = shelf_scan_process(None, "fake-fridge-sweep.mp4", None, "fridge")

    assert "Home Scan" in html
    assert trace_id
    assert annotated

    parsed = json.loads(scan_state)
    assert parsed["scene_type"] == "fridge"
    assert parsed["frame_count"] == 2
    assert parsed["video_path"] is not None
    # With detections available, the mock promptable path now runs over a
    # merged video sweep, so the mode is prefixed with ``video_``.
    assert parsed["perception_mode"] == "video_promptable_segmentation"


def test_shelf_scan_process_with_video_and_audio(app, monkeypatch):
    """Test shelf scan with video + audio (multimodal)."""
    monkeypatch.setattr(
        app_providers.object_detection,
        "detect",
        lambda _path: [{"label": "orange juice", "confidence": 0.91, "bbox": [0.2, 0.2, 0.4, 0.5], "class_id": 0}],
    )
    monkeypatch.setattr(
        app_providers.segmentation,
        "segment",
        lambda _path: [{"label": "orange juice", "score": 0.88, "mask": "mask_d", "bbox": [0.2, 0.2, 0.4, 0.5]}],
    )
    monkeypatch.setattr(
        app_providers.ocr,
        "extract",
        lambda _path: {
            "product_name": "Orange Juice",
            "weight": "1 L",
            "confidence": 0.87,
            "raw_text": "Orange Juice 1L",
        },
    )
    monkeypatch.setattr(
        app_providers.stt,
        "transcribe",
        lambda _path: {"text": "orange juice in fridge", "confidence": 0.88},
    )
    # Mock frame extraction from video
    monkeypatch.setattr(
        "shopstack.services.shelf_intelligence._first_frame_from_video",
        lambda _path: "/tmp/test_frame_oj.jpg",
    )
    monkeypatch.setattr(
        "shopstack.services.shelf_intelligence._collect_frame_paths",
        lambda image_path, video_path, max_frames=6: ["/tmp/test_frame_01.jpg", "/tmp/test_frame_02.jpg"],
    )

    html, scan_state, trace_id, annotated = shelf_scan_process(
        None, "fake-fridge-sweep.mp4", "fake-voice-note.wav", "fridge"
    )

    assert "Home Scan" in html
    assert trace_id
    assert annotated

    parsed = json.loads(scan_state)
    assert parsed["scene_type"] == "fridge"
    assert parsed["frame_count"] == 2
    # With detections available, the mock promptable path now runs over a
    # merged video sweep, so the mode is prefixed with ``video_`` even with
    # video+audio input.
    assert parsed["perception_mode"] == "video_promptable_segmentation"
