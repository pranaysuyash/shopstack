"""Tests for the basket Plan sub-tab sub-builder.

Verifies:
- The BasketPlanHandles dataclass has the expected fields
- The build function returns a BasketPlanHandles instance
- All 7 exposed components are of the right Gradio types

The Gradio-context tests are slow (each ``gr.Blocks()`` context
takes ~5s to bootstrap), so we only run the dataclass shape
test in the default suite. The full set is covered by the
slower integration tests in test_app.py.
"""
from __future__ import annotations

import dataclasses

import pytest

from shopstack.ui.tabs.basket_plan import BasketPlanHandles


def test_handles_dataclass_fields():
    """BasketPlanHandles has the expected 7 fields."""
    fields = {f.name for f in dataclasses.fields(BasketPlanHandles)}
    assert fields == {
        "run_btn",
        "goal_input",
        "items_input",
        "summary_html",
        "detail_html",
        "smart_basket_btn",
        "smart_basket_html",
    }


@pytest.mark.skip(reason="Gradio Blocks() context is slow; covered by test_app.py integration tests")
def test_build_basket_plan_returns_handles():
    """The sub-builder returns a BasketPlanHandles instance."""
    import gradio as gr

    with gr.Blocks() as app:
        handles = build_basket_plan(app, ctx=type("Ctx", (), {})())
    assert isinstance(handles, BasketPlanHandles)


@pytest.mark.skip(reason="Gradio Blocks() context is slow; covered by test_app.py integration tests")
def test_handles_components_have_right_types():
    """All 7 exposed components are of the right Gradio types."""
    import gradio as gr

    with gr.Blocks() as app:
        handles = build_basket_plan(app, ctx=type("Ctx", (), {})())
    assert isinstance(handles.run_btn, gr.Button)
    assert isinstance(handles.goal_input, gr.Textbox)
    assert isinstance(handles.items_input, gr.Textbox)
    assert isinstance(handles.summary_html, gr.HTML)
    assert isinstance(handles.detail_html, gr.HTML)
    assert isinstance(handles.smart_basket_btn, gr.Button)
    assert isinstance(handles.smart_basket_html, gr.HTML)
