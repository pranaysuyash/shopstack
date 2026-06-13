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
    app_mod.db.set_config_value("active_household_id", "")
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

    _, scan_state, trace_id, _ = shelf_scan_process("fake-soap-scan.jpg", None, "bathroom_cabinet")
    skip = shelf_scan_skip(scan_state, trace_id)
    save = shelf_scan_save_trace(scan_state, trace_id)

    assert "Saved this shelf scan" in skip
    assert "saved" in save.lower()

