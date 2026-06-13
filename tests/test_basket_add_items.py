"""Tests for the basket Add Items sub-tab sub-builder.

The Add Items sub-tab is self-contained (no cross-tab
references), so the sub-builder returns ``None``. The tests
verify that the function is callable.
"""
from __future__ import annotations

import pytest

from shopstack.ui.tabs.basket_add_items import build_basket_add_items


def test_build_basket_add_items_is_callable():
    """The sub-builder is importable and callable (sanity check)."""
    assert callable(build_basket_add_items)


@pytest.mark.skip(reason="Gradio Blocks() context is slow; covered by test_app.py integration tests")
def test_build_basket_add_items_returns_none():
    """The sub-builder returns None (no cross-tab references)."""
    import gradio as gr

    with gr.Blocks() as app:
        result = build_basket_add_items(app, ctx=type("Ctx", (), {})())
    assert result is None
