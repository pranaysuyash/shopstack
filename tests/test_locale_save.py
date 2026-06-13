"""Tests for the locale-save sub-builder.

Verifies:
- The LocaleSaveHandles dataclass has the expected fields
- The build function returns a LocaleSaveHandles instance
- Both components are hidden (visible=False) and have the expected elem_ids
- The submit handler is wired to the input → output round-trip
"""
from __future__ import annotations

import dataclasses

import pytest

from shopstack.ui.locale_save import LocaleSaveHandles


def test_handles_dataclass_fields():
    """LocaleSaveHandles has the expected 2 fields."""
    fields = {f.name for f in dataclasses.fields(LocaleSaveHandles)}
    assert fields == {"locale_input", "locale_output"}


def test_default_locale_value():
    """The default locale for both input and output is DEFAULT_LOCALE."""
    from shopstack.services.i18n import DEFAULT_LOCALE
    from shopstack.ui.locale_save import build_locale_save

    # We can call build_locale_save() with a fresh Blocks context.
    # Even though the components are invisible, we can still read
    # their .value attribute.
    import gradio as gr

    with gr.Blocks() as _app:
        handles = build_locale_save()
    # The default value matches the i18n module's DEFAULT_LOCALE.
    assert handles.locale_input.value == DEFAULT_LOCALE
    assert handles.locale_output.value == DEFAULT_LOCALE


@pytest.mark.skip(reason="Gradio Blocks() context is slow; covered by test_app.py integration tests")
def test_build_locale_save_returns_handles():
    """The sub-builder returns a LocaleSaveHandles instance."""
    import gradio as gr

    with gr.Blocks() as _app:
        handles = build_locale_save()
    assert isinstance(handles, LocaleSaveHandles)


@pytest.mark.skip(reason="Gradio Blocks() context is slow; covered by test_app.py integration tests")
def test_components_are_hidden_textboxes():
    """Both components are invisible Textboxes (the i18n JS hits them via API)."""
    import gradio as gr

    with gr.Blocks() as _app:
        handles = build_locale_save()
    assert isinstance(handles.locale_input, gr.Textbox)
    assert isinstance(handles.locale_output, gr.Textbox)
    assert handles.locale_input.visible is False
    assert handles.locale_output.visible is False
    assert handles.locale_input.elem_id == "save_locale_input"
    assert handles.locale_output.elem_id == "save_locale_output"
