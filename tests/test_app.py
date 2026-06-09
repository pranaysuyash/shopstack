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
    # Restore the original module state so downstream tests aren't contaminated.
    sys.modules.clear()
    sys.modules.update(saved_modules)


def test_build_app_returns_blocks(fresh_app):
    app = fresh_app.build_app()
    assert isinstance(app, gr.Blocks)


def test_build_app_title(fresh_app):
    app = fresh_app.build_app()
    assert app.title == "ShopStack"


def test_today_dashboard_returns_correct_shape(fresh_app):
    results = fresh_app.today_dashboard()
    assert len(results) == 7
    for r in results:
        assert isinstance(r, str)


def test_all_view_functions_importable(fresh_app):
    views = [
        "today_dashboard",
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


def test_today_tab_does_not_expose_demo_loader():
    app_source = Path(__file__).resolve().parents[1] / "app.py"
    text = app_source.read_text()
    assert "Load Demo Data" not in text
    assert "seed_demo_inventory" not in text
