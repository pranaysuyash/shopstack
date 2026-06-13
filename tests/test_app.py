from __future__ import annotations

import os
from pathlib import Path

import gradio as gr


def test_build_app_returns_blocks(app):
    built = app.build_app()
    assert isinstance(built, gr.Blocks)


def test_build_app_title(app):
    built = app.build_app()
    assert built.title == "ShopStack"


def test_today_dashboard_returns_correct_shape(app):
    from shopstack.ui.screens import today_dashboard
    results = today_dashboard()
    assert len(results) == 6
    for r in results:
        assert isinstance(r, str)


def test_all_view_functions_importable(app):
    builders = [
        "build_today_tab",
        "build_basket_tab",
        "build_market_tab",
        "build_reconcile_tab",
        "build_memory_tab",
    ]
    for name in builders:
        assert hasattr(app, name), f"app missing {name}"
        callable(getattr(app, name))

    from shopstack.ui.screens import (
        shelf_scan_confirm,
        shelf_scan_process,
        shelf_scan_save_trace,
        shelf_scan_skip,
    )
    for fn in (
        shelf_scan_process,
        shelf_scan_confirm,
        shelf_scan_skip,
        shelf_scan_save_trace,
    ):
        assert callable(fn)


def test_build_app_appears_to_have_tabs(app):
    built = app.build_app()
    children = list(built.children)
    assert len(children) > 0


def test_generate_shopping_poster_e2e(app):
    from datetime import date, timedelta

    from shopstack.app_context import db
    from shopstack.schemas.models import InventoryLot, ShoppingListItem, Store

    uid = db.active_household_id or "default_household"
    db.active_household_id = uid
    assert uid in {h["household_id"] for h in db.list_households()}

    db.add_store(Store(
        store_id="test_store", name="Test Store",
        location="Test", store_type="supermarket",
    ))

    today = date.today()
    db.add_inventory_lot(InventoryLot(
        lot_id="test_milk", canonical_name="milk",
        display_name="Test Milk", quantity=0.5, unit="L",
        storage_location_id="fridge",
        purchase_date=today - timedelta(days=2),
    ), user_id=uid)

    sl = db.create_shopping_list(
        name="Weekly Grocery Run",
        goal="Stock up for the week",
        user_id=uid,
    )

    items_data = [
        ("milk", 2.0, "L", "must_buy", "Only 0.5L left"),
        ("tomato", 1.0, "kg", "must_buy", "Almost out"),
        ("bread", 1.0, "loaf", "optional", "Current loaf expires soon"),
        ("toor_dal", 1.0, "kg", "must_buy", "Running low on dal"),
    ]
    for canonical, qty, unit, priority, reason in items_data:
        item = ShoppingListItem(
            canonical_name=canonical,
            requested_quantity=qty,
            unit=unit,
            priority=priority,
            reason=reason,
        )
        db.add_list_item(sl.list_id, item)

    from shopstack.ui.screens import generate_shopping_poster
    poster_path, status_html = generate_shopping_poster()

    assert status_html, "Status HTML should not be empty"

    if poster_path:
        assert os.path.isfile(poster_path), f"Poster file should exist: {poster_path}"

        is_svg = poster_path.endswith(".svg")
        is_png = poster_path.endswith(".png")
        assert is_svg or is_png, f"Expected .svg or .png, got {Path(poster_path).suffix}"

        if is_svg:
            with open(poster_path, errors="replace") as f:
                content = f.read()
            assert "milk" in content.lower()
            assert "tomato" in content.lower()
            assert "bread" in content.lower()
        else:
            try:
                from PIL import Image
                img = Image.open(poster_path).convert("RGB")
                w, h = img.size
                assert w > 0 and h > 0, f"Poster image has invalid dimensions: {w}x{h}"
            except ImportError:
                pass

        assert "saved" in status_html.lower() or "✓" in status_html

        os.unlink(poster_path)
        try:
            Path(poster_path).parent.rmdir()
        except OSError:
            pass
    else:
        assert "provider" in status_html.lower() or "available" in status_html.lower()


def test_today_tab_does_not_expose_demo_loader():
    app_source = Path(__file__).resolve().parents[1] / "app.py"
    text = app_source.read_text()
    assert "Load Demo Data" not in text
    assert "seed_demo_inventory" not in text
