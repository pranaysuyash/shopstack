from __future__ import annotations

import os
from pathlib import Path

import gradio as gr
import pytest


@pytest.fixture(scope="module")
def fresh_app():
    os.environ["SHOPSTACK_DB_PATH"] = ":memory:"
    import importlib
    import sys
    # Save the entire module state before manipulation so we can restore it
    # after this module's tests finish. Without restoration, the aggressive
    # sys.modules cleanup below poisons the cache for every subsequent test
    # file that imports shopstack packages.
    saved_modules = dict(sys.modules)
    _preserved = {"shopstack.schemas", "shopstack.schemas.models"}
    for mod in list(sys.modules.keys()):
        if mod in ("app",) or (mod.startswith("shopstack") and mod not in _preserved):
            del sys.modules[mod]
    import app as _app
    yield _app
    # Restore the original module state gentler without clearing C-extensions
    for k in list(sys.modules.keys()):
        if k not in saved_modules:
            del sys.modules[k]
    sys.modules.update(saved_modules)



def test_build_app_returns_blocks(fresh_app):
    app = fresh_app.build_app()
    assert isinstance(app, gr.Blocks)


def test_build_app_title(fresh_app):
    app = fresh_app.build_app()
    assert app.title == "ShopStack"


def test_today_dashboard_returns_correct_shape(fresh_app):
    results = fresh_app.today_dashboard()
    assert len(results) == 6
    for r in results:
        assert isinstance(r, str)


def test_all_view_functions_importable(fresh_app):
    views = [
        "today_dashboard",
        "runtime_proof_view",
        "shopping_list_view_with_cards",
        "build_shopping_list_and_refresh",
        "add_purchase_form",
        "inventory_view",
        "consume_item",
        "use_soon_view",
        "household_map_view",
        "agent_trace_view",
        "agent_trace_bootstrap",
        "price_memory_view",
        "field_notes_view",
        "field_notes_save",
    ]
    for name in views:
        assert hasattr(fresh_app, name), f"app missing {name}"
        callable(getattr(fresh_app, name))


def test_build_app_appears_to_have_tabs(fresh_app):
    app = fresh_app.build_app()
    children = list(app.children)
    assert len(children) > 0


def test_generate_shopping_poster_e2e(fresh_app):
    """End-to-end: seed demo data → generate shopping poster → verify output.

    Seeds an in-memory database with stores, inventory items, and an active
    shopping list, then calls ``generate_shopping_poster()`` (simulating the
    Gradio button click) and verifies the output.
    """
    import os
    from datetime import date, timedelta
    from pathlib import Path

    from shopstack.app_context import db
    from shopstack.schemas.models import InventoryLot, ShoppingListItem, Store

    uid = db.active_household_id
    assert uid, "Default household should be available for user_id scoping"

    # ── Seed test data ──────────────────────────────────────────
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

    # ── Call poster generation (simulates Gradio button click) ──
    poster_path, status_html = fresh_app.generate_shopping_poster()

    assert status_html, "Status HTML should not be empty"

    if poster_path:
        # Provider is available — verify the output file
        assert os.path.isfile(poster_path), f"Poster file should exist: {poster_path}"

        # File is either SVG (text) or PNG (binary with cairosvg/svglib)
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
            # PNG — verify valid image structure
            try:
                from PIL import Image
                img = Image.open(poster_path).convert("RGB")
                w, h = img.size
                assert w > 0 and h > 0, f"Poster image has invalid dimensions: {w}x{h}"
            except ImportError:
                pass  # Skip pixel-level check when PIL unavailable

        # Status should indicate success
        assert "saved" in status_html.lower() or "\u2713" in status_html

        # Clean up
        os.unlink(poster_path)
        try:
            Path(poster_path).parent.rmdir()
        except OSError:
            pass
    else:
        # Provider not available — status should explain
        assert "provider" in status_html.lower() or "available" in status_html.lower()


def test_today_tab_does_not_expose_demo_loader():
    app_source = Path(__file__).resolve().parents[1] / "app.py"
    text = app_source.read_text()
    assert "Load Demo Data" not in text
    assert "seed_demo_inventory" not in text
