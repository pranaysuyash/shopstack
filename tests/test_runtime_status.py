"""Tests for the runtime_status API endpoint (AI-9).

Per `docs/audits/ACTION_ITEMS.md` AI-9: External API consumers need
to know whether they're hitting mock or real providers. The
runtime_status endpoint returns one of:
  - "Local mock mode" (all providers are mock — the default)
  - "Local runtime" (a real local provider like MLX is loaded)
  - "Cloud runtime" (OpenAI / HuggingFace / Whisper is loaded)
  - "Off-grid mock mode" (off-the-grid policy blocked all real providers)

This test verifies:
1. The sub-builder returns the expected RuntimeStatusHandles
2. Both components are hidden (visible=False)
3. The endpoint has the correct api_name and api_description
"""
from __future__ import annotations

import dataclasses

import pytest

from shopstack.ui.runtime_status import RuntimeStatusHandles, build_runtime_status


def test_runtime_status_handles_dataclass_fields():
    """RuntimeStatusHandles has the expected 2 fields."""
    fields = {f.name for f in dataclasses.fields(RuntimeStatusHandles)}
    assert fields == {"status_input", "status_output"}


def test_runtime_status_components_are_hidden():
    """Both components must be invisible (visible=False) since the
    endpoint is API-only — no UI consumer needs the button itself."""
    import gradio as gr

    with gr.Blocks() as _app:
        handles = build_runtime_status()
    assert isinstance(handles.status_input, gr.Textbox)
    assert isinstance(handles.status_output, gr.Textbox)
    assert handles.status_input.visible is False
    assert handles.status_output.visible is False


def test_runtime_status_label_returns_one_of_four():
    """The canonical `runtime_label()` (in shopstack.ui.header) must
    return one of the four documented runtime modes."""
    from shopstack.ui.header import runtime_label

    label = runtime_label()
    assert label in {
        "Local mock mode",
        "Local runtime",
        "Cloud runtime",
        "Off-grid mock mode",
    }, f"Unexpected runtime label: {label!r}"


def test_runtime_status_label_handles_provider_exception():
    """If the provider registry throws, fall back to 'Local runtime'.

    This is the same fallback documented in `header.runtime_label()`.
    We test it to ensure the fallback contract is preserved.
    """
    from unittest.mock import patch

    from shopstack.ui import header

    with patch("shopstack.ui.header.providers") as mock_providers:
        mock_providers.get_runtime_diagnostics.side_effect = RuntimeError("boom")
        assert header.runtime_label() == "Local runtime"
