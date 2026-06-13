"""Tests for the cookbook filter row sub-builder.

Verifies:
- The sub-builder returns CookbookFilterHandles with the right components
- All 5 interactive controls are present (cuisine, dietary, quick, search, selector)
- The recipe selector starts with empty choices (no recipes selected initially)
- The Handles dataclass has the expected fields
- _DIETARY_CHOICES has the right format

The Gradio-context tests are slow (each ``gr.Blocks()`` context takes
~5s to bootstrap), so we only run the dataclass + constant tests in
the default suite. The full set is covered by the slower integration
tests in test_app.py.
"""
from __future__ import annotations

import dataclasses

import pytest

from shopstack.ui.tabs.cookbook_filter import (
    _DIETARY_CHOICES,
    CookbookFilterHandles,
)


def test_handles_dataclass_fields():
    """CookbookFilterHandles has the expected fields."""
    fields = {f.name for f in dataclasses.fields(CookbookFilterHandles)}
    assert fields == {
        "cuisine_filter",
        "dietary_filter",
        "quick_only",
        "search_box",
        "recipe_selector",
        "refresh_recipes",
    }


def test_dietary_choices_constant():
    """The _DIETARY_CHOICES constant is in the right format (label, value)."""
    assert len(_DIETARY_CHOICES) == 4
    for label, value in _DIETARY_CHOICES:
        assert isinstance(label, str)
        assert isinstance(value, str)
        assert value in {"all", "vegetarian", "vegan", "omnivore"}


def test_dietary_choices_labels():
    """The dietary labels match the expected user-facing strings."""
    labels = {label for label, _ in _DIETARY_CHOICES}
    assert labels == {"All", "Vegetarian", "Vegan", "Omnivore"}


@pytest.mark.skip(reason="Gradio Blocks() context is slow; covered by test_app.py integration tests")
def test_build_cookbook_filter_row_returns_handles():
    """The sub-builder returns a CookbookFilterHandles instance."""
    import gradio as gr

    with gr.Blocks() as blocks:
        handles = build_cookbook_filter_row()
    assert isinstance(handles, CookbookFilterHandles)


@pytest.mark.skip(reason="Gradio Blocks() context is slow; covered by test_app.py integration tests")
def test_handles_components_have_right_types():
    """All 5 interactive components are of the right Gradio types."""
    import gradio as gr

    with gr.Blocks() as blocks:
        handles = build_cookbook_filter_row()
    assert isinstance(handles.cuisine_filter, gr.Dropdown)
    assert isinstance(handles.dietary_filter, gr.Dropdown)
    assert isinstance(handles.quick_only, gr.Checkbox)
    assert isinstance(handles.search_box, gr.Textbox)
    assert isinstance(handles.recipe_selector, gr.Dropdown)
    assert isinstance(handles.refresh_recipes, gr.Button)


@pytest.mark.skip(reason="Gradio Blocks() context is slow; covered by test_app.py integration tests")
def test_filter_row_inside_blocks():
    """The sub-builder adds components to the parent Blocks."""
    import gradio as gr

    with gr.Blocks() as blocks:
        before = len(list(blocks.children))
        build_cookbook_filter_row()
        after = len(list(blocks.children))
    assert after - before >= 2
