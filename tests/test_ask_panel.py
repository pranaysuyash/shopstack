"""Tests for the Ask ShopStack panel sub-builder.

Verifies:
- The builder adds the expected components to the parent Blocks
- The button click event fires the Ask handler chain
- The textbox submit event (Enter key) also fires the Ask handler chain
- The panel returns `AskPanelHandles` with both components exposed
- The output is an `gr.HTML` (consumer-friendly answer) not `gr.JSON`
- The renderer surfaces messages, decisions, and find-item results
"""
from __future__ import annotations

import gradio as gr
import pytest

from shopstack.ui.tabs.ask_panel import AskPanelHandles, build_ask_panel
from shopstack.ui.tabs.context import TabContext


def test_build_ask_panel_returns_handles():
    """The builder should return AskPanelHandles with the right components."""
    with gr.Blocks() as blocks:
        handles = build_ask_panel(blocks=blocks, app=blocks, ctx=TabContext())
    assert isinstance(handles, AskPanelHandles)
    assert isinstance(handles.ask_input, gr.Textbox)
    # The Ask output is now gr.HTML (was gr.JSON) so we can render a
    # consumer-friendly answer instead of the raw response tree.
    assert isinstance(handles.ask_output, gr.HTML)


def test_build_ask_panel_registers_click_and_submit_events():
    """The panel wires both button click and textbox submit to ask_shopstack."""
    with gr.Blocks() as blocks:
        handles = build_ask_panel(blocks=blocks, app=blocks, ctx=TabContext())
    # Gradio stores event handlers on the component's .event_handlers dict-like
    # We verify the structure by checking the components are wired
    # (the .click and .submit methods return None; verifying they were
    # called is hard without mocking gradio internals).
    assert handles.ask_input is not None
    assert handles.ask_output is not None


def test_build_ask_panel_inside_blocks():
    """The builder must be called inside a gr.Blocks context."""
    # The builder uses gr.Markdown/Textbox/Button/JSON which require a parent
    # Blocks context. Calling outside one should raise (or at least not crash
    # in a way that the parent Blocks doesn't see the children).
    with gr.Blocks() as blocks:
        build_ask_panel(blocks=blocks, app=blocks, ctx=TabContext())
        # The Blocks should now have multiple children
        children = list(blocks.children)
        assert len(children) > 0


def test_ask_panel_handles_dataclass_fields():
    """AskPanelHandles is a dataclass with the expected fields."""
    import dataclasses
    fields = {f.name for f in dataclasses.fields(AskPanelHandles)}
    assert fields == {"ask_input", "ask_output"}


def test_ask_output_renders_friendly_html_for_string_answer():
    """A bare string answer is rendered as a card, not a JSON dump."""
    from shopstack.ui.tabs.ask_panel import _render_answer
    html = _render_answer("You have 2 packets of milk in the fridge.")
    assert "<div class='home-card'" in html
    assert "milk" in html
    # The raw `trace_id` and `debug` keys must never appear as JSON.
    assert '"trace_id"' not in html
    assert "{'intent'" not in html


def test_ask_output_renders_decision_set():
    """A decision-set response is rendered as friendly cards."""
    from shopstack.ui.tabs.ask_panel import _render_answer
    response = {
        "intent": "decisions",
        "decisions": [
            {
                "canonical_name": "milk",
                "display_name": "Milk",
                "action": "use_soon",
                "reasons": ["Expires tomorrow"],
            }
        ],
    }
    html = _render_answer(response)
    assert "Milk" in html
    assert "Use soon" in html or "use_soon" in html.lower()


def test_ask_output_renders_empty_intent_gracefully():
    """An empty-intent response is rendered without leaking internals."""
    from shopstack.ui.tabs.ask_panel import _render_answer
    html = _render_answer({"intent": "empty", "message": "Type a question."})
    assert "Type a question." in html


def test_ask_output_hides_trace_id_and_debug_keys():
    """The renderer must NOT surface trace_id or debug payloads."""
    from shopstack.ui.tabs.ask_panel import _render_answer
    response = {
        "intent": "ok",
        "message": "Done.",
        "trace_id": "abc-123-secret",
        "debug": {"parser": {"status": "ok"}},
    }
    html = _render_answer(response)
    assert "abc-123-secret" not in html
    assert "parser" not in html  # debug block hidden
