"""Tests for the basket Shopping List sub-tab sub-builder.

The Shopping List sub-tab is self-contained (no cross-tab
references), so the sub-builder returns ``None``. The tests
verify that the function is callable and that it doesn't
crash when invoked inside a ``gr.Blocks()`` context.

The Gradio-context tests are slow (each ``gr.Blocks()`` context
takes ~5s to bootstrap), so the integration test is marked
``@pytest.mark.skip`` — covered by the slower integration
tests in test_app.py.
"""
from __future__ import annotations

import pytest

from shopstack.ui.tabs.basket_shopping_list import build_basket_shopping_list


def test_build_basket_shopping_list_is_callable():
    """The sub-builder is importable and callable (sanity check)."""
    assert callable(build_basket_shopping_list)


@pytest.mark.skip(reason="Gradio Blocks() context is slow; covered by test_app.py integration tests")
def test_build_basket_shopping_list_returns_none():
    """The sub-builder returns None (no cross-tab references)."""
    import gradio as gr

    with gr.Blocks() as app:
        # Ctx is unused but part of the uniform signature; pass a dummy
        result = build_basket_shopping_list(app, ctx=type("Ctx", (), {})())
    assert result is None
