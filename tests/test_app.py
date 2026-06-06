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
    _preserved = {"shopstack.schemas", "shopstack.schemas.models"}
    for mod in list(sys.modules.keys()):
        if mod in ("app",) or (mod.startswith("shopstack") and mod not in _preserved):
            del sys.modules[mod]
    import app as _app
    return _app


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
        "shopping_list_view",
        "shopping_list_create",
        "add_purchase_form",
        "inventory_view",
        "consume_item",
        "use_soon_view",
        "household_map_view",
        "agent_trace_view",
        "agent_trace_detail",
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
