"""Tests for the basket Compare sub-tab sub-builder.

The Compare sub-tab is self-contained (no cross-tab
references), so the sub-builder returns ``None``. The tests
verify that the function is callable.
"""
from __future__ import annotations

import pytest

from shopstack.ui.tabs.basket_compare import build_basket_compare


def test_build_basket_compare_is_callable():
    """The sub-builder is importable and callable (sanity check)."""
    assert callable(build_basket_compare)


@pytest.mark.skip(reason="Gradio Blocks() context is slow; covered by test_app.py integration tests")
def test_build_basket_compare_returns_none():
    """The sub-builder returns None (no cross-tab references)."""
    import gradio as gr

    with gr.Blocks() as app:
        result = build_basket_compare(app, ctx=type("Ctx", (), {})())
    assert result is None
