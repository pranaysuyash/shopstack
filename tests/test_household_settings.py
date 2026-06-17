"""Tests for the household settings sub-builder.

Verifies:
- The HouseholdSettingsHandles dataclass has the expected fields
- The build function returns a HouseholdSettingsHandles instance
- All 6 wired components are of the right Gradio types
- The accordion is populated with the expected sub-sections

All Gradio-context tests use a function-scoped gr.Blocks() fixture.
Blocks() init is ~0.08s, so the per-test overhead is negligible.
"""
from __future__ import annotations

import dataclasses

import pytest

from shopstack.ui.household_settings import (
    HouseholdSettingsHandles,
    build_household_settings,
)

# ── Gradio context fixture (function-scoped) ───────────────────────
# Blocks() init is ~0.08s — well within acceptable per-test overhead.
# Function scope isolates tests so shared state from earlier builds
# (duplicate component IDs, polluted children lists) cannot interfere.


@pytest.fixture
def gr_blocks():
    """Create a fresh gr.Blocks() context for each test.

    The ``with gr.Blocks() as app:`` context is required by all Gradio
    component constructors (gr.Dropdown, gr.Button, gr.Row, etc.).
    """
    import gradio as gr
    with gr.Blocks() as app:
        yield app


# ── Dataclass shape test (no Gradio context needed) ────────────────


def test_handles_dataclass_fields():
    """HouseholdSettingsHandles has the expected 6 fields."""
    fields = {f.name for f in dataclasses.fields(HouseholdSettingsHandles)}
    assert fields == {
        "household_dropdown",
        "add_hh_btn",
        "hh_add_row",
        "hh_name_input",
        "hh_create_btn",
        "hh_cancel_btn",
    }


# ── Builder output tests (need Gradio context) ─────────────────────


def test_build_household_settings_returns_handles(gr_blocks):
    """The sub-builder returns a HouseholdSettingsHandles instance."""
    handles = build_household_settings(gr_blocks)
    assert isinstance(handles, HouseholdSettingsHandles)


def test_handles_components_have_right_types(gr_blocks):
    """All 6 exposed components are of the right Gradio types."""
    import gradio as gr

    handles = build_household_settings(gr_blocks)
    assert isinstance(handles.household_dropdown, gr.Dropdown)
    assert isinstance(handles.add_hh_btn, gr.Button)
    assert isinstance(handles.hh_add_row, gr.Row)
    assert isinstance(handles.hh_name_input, gr.Textbox)
    assert isinstance(handles.hh_create_btn, gr.Button)
    assert isinstance(handles.hh_cancel_btn, gr.Button)


def test_accordion_added_to_blocks(gr_blocks):
    """The sub-builder adds a top-level Accordion to the parent Blocks."""
    import gradio as gr

    before = len(list(gr_blocks.children))
    _ = build_household_settings(gr_blocks)
    after = len(list(gr_blocks.children))
    assert after > before, (
        "Expected at least one new child (the Accordion) to be added "
        f"to the Blocks. Before: {before}, After: {after}"
    )


# ── Component property tests ───────────────────────────────────────


def test_dropdown_is_interactive(gr_blocks):
    """The household dropdown is interactive."""
    handles = build_household_settings(gr_blocks)
    dd = handles.household_dropdown
    assert getattr(dd, "interactive", True) is True
    label = getattr(dd, "label", "")
    assert "Household" in label


def test_add_hh_button_exists(gr_blocks):
    """The add-household button has the expected label."""
    handles = build_household_settings(gr_blocks)
    btn = handles.add_hh_btn
    label_text = str(getattr(btn, "value", "") or "")
    assert "Add" in label_text or "household" in label_text.lower()


def test_hh_form_has_textbox_and_buttons(gr_blocks):
    """The hidden add-household form row contains textbox + create + cancel."""
    import gradio as gr

    handles = build_household_settings(gr_blocks)
    assert isinstance(handles.hh_name_input, gr.Textbox)
    assert isinstance(handles.hh_create_btn, gr.Button)
    assert isinstance(handles.hh_cancel_btn, gr.Button)
    create_label = str(getattr(handles.hh_create_btn, "value", "") or "")
    cancel_label = str(getattr(handles.hh_cancel_btn, "value", "") or "")
    assert "Create" in create_label or "create" in create_label
    assert "Cancel" in cancel_label or "cancel" in cancel_label


def test_hh_add_row_hidden_by_default(gr_blocks):
    """The add-household form row is hidden (visible=False) by default."""
    handles = build_household_settings(gr_blocks)
    visible = getattr(handles.hh_add_row, "visible", True)
    assert visible is False, "Add-household form should be hidden by default"
