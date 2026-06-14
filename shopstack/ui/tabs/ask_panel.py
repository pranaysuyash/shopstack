"""Ask ShopStack panel — natural-language queries across the full app.

This is a sub-builder of the Today tab: a textbox + button that fires the
AI planner (via `shopstack.ui.screens.ask_shopstack`) and renders the
structured response as friendly HTML. The submit button and Enter-key
both fire the handler.

Extracted from `build_today_tab()` so that:
- The Ask feature is independently testable in isolation.
- The Today tab builder is shorter and more focused on the dashboard.
- The same panel can be reused in other tabs (e.g. a future Help tab)
  without duplicating the wiring.

The panel returns an `AskPanelHandles` dataclass exposing the
`ask_input` and `ask_output` components. Currently nothing else in the
app references them, but the handles are exposed for symmetry with the
tab-builder pattern and to enable future cross-tab interactions (e.g.
clearing the input on tab switch).
"""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

import gradio as gr

from shopstack.ui.screens import ask_shopstack
from shopstack.ui.screens.ask import render_ask_response as _render_answer
from shopstack.ui.components.primitives import empty_state_enhanced
from shopstack.ui.tabs.context import TabContext


@dataclass
class AskPanelHandles:
    """Components that other parts of the app may reference after the Ask panel builds.

    Currently no cross-tab references exist, but the handles are
    exposed for future use (e.g. clearing `ask_input` on household
    switch, or populating `ask_input` from a quick-action elsewhere).
    """
    ask_input: gr.Textbox
    ask_output: gr.HTML


def _ask_and_reveal(question: str) -> dict[str, Any]:
    """Run Ask ShopStack and render the response as HTML.

    The result HTML carries ``aria-live="polite"`` via the home-card
    wrapper so screen readers announce the new answer without the user
    having to navigate to the panel.
    """
    answer = ask_shopstack(question)
    html = _render_answer(answer)
    return gr.update(value=html, visible=True)


def build_ask_panel(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> AskPanelHandles:
    """Build the Ask ShopStack panel inside the parent's `gr.Tabs` context.

    Adds a `gr.Markdown` separator, a `gr.Markdown` heading, a text input,
    a submit button, and a `gr.JSON` output. Wires:
    - The button's `click` event to `ask_shopstack`.
    - The textbox's `submit` event (Enter key) to `ask_shopstack`.

    Args:
        blocks: Alias for the parent gr.Blocks. Kept for symmetry with
            the other tab builders.
        app: The root gr.Blocks instance — needed for `app.load(...)`
            handlers (not used in this panel, but part of the uniform
            builder signature).
        ctx: Shared dependencies (unused in this panel, but part of the
            uniform builder signature).

    Returns:
        AskPanelHandles: the input and output components, in case future
        cross-tab interactions need them.
    """
    gr.Markdown("---")
    gr.Markdown("### Ask about home, shopping, or prices")
    ask_input = gr.Textbox(
        label="Your question",
        placeholder="Do we have milk?  |  What should I buy today?  |  Where is toothpaste?",
        lines=2,
    )
    ask_btn = gr.Button("Ask")
    # Pre-populate with an empty-state so users see the panel is ready
    # and so the panel has an aria-live region for screen readers from
    # the very first render.
    ask_output = gr.HTML(
        value=empty_state_enhanced(
            "Ask a question to see an answer here.",
            icon="💬",
        ),
        elem_id="ask-answer",
        elem_classes="ask-output",
        visible=True,
    )
    # ── Phase 8 #16: "What the parser understood" preview ─────────
    # Shows the user's utterance run through the fine-tuned intent
    # classifier — useful when the answer is "I don't understand" and
    # the user wants to see what the system thought they said.
    ask_parser_preview = gr.HTML("", elem_id="ask-parser-preview")
    ask_btn.click(
        _ask_and_reveal,
        ask_input,
        ask_output,
        api_name="ask",
        api_description="Ask the ShopStack agent a natural language question about inventory, shopping, or prices",
    ).then(
        _parser_preview_and_reveal,
        ask_input,
        ask_parser_preview,
    )
    ask_input.submit(
        _ask_and_reveal,
        ask_input,
        ask_output,
        api_name="ask_submit",
        api_description="Submit question via Enter key",
    ).then(
        _parser_preview_and_reveal,
        ask_input,
        ask_parser_preview,
    )

    # ── Phase 8 #23 Voice memo (continuous-listening) ─────────────
    gr.Markdown("---")
    gr.Markdown("### 🎙️ Voice memo")
    gr.Markdown(
        "Push to record, speak one or more commands ('add milk', "
        "'consume bread'), then release. Each utterance is parsed "
        "and dispatched. Say 'stop' to end the session."
    )
    from shopstack.services.voice_memo import end_session as _end_vm
    from shopstack.services.voice_memo import start_session as _start_vm
    from shopstack.services.voice_memo import capture_chunk as _capture_vm
    from shopstack.services.voice_memo import render_session_summary_html as _render_vm

    voice_memo_state = gr.State(_start_vm())
    with gr.Row():
        voice_record = gr.Audio(
            sources=["microphone"],
            type="filepath",
            label="Hold to record",
        )
        voice_process_btn = gr.Button("Process audio", variant="primary")
    voice_session_html = gr.HTML("<div class='vm-empty'>No voice memo captured yet.</div>")
    voice_reset_btn = gr.Button("End session", elem_classes="secondary")

    def _process_voice(audio_path, session):
        from shopstack.app_context import db as _db
        from shopstack.app_context import providers as _providers
        if not audio_path:
            return session, "<div class='vm-empty'>No audio captured. Press the mic and try again.</div>"
        # Find an STT provider (whisper, local_whisper, sensevoice, mock_stt)
        stt = None
        try:
            for name in ("whisper", "local_whisper", "sensevoice", "qwen3_asr", "mock_stt"):
                stt = _providers.get(name)
                if stt is not None:
                    break
        except Exception:
            stt = None
        if stt is None:
            return session, "<div class='vm-empty'>No STT provider loaded — voice memo needs an STT backend.</div>"
        # Best-effort dispatcher: append to a local list, no real DB write
        # (the user reviews in the voice session summary).
        log: list[dict] = []
        from shopstack.services.voice_memo import make_recording_dispatcher
        _capture_vm(session, audio_path, stt,
                    dispatcher=make_recording_dispatcher(log))
        return session, _render_vm(_end_vm(session))

    def _reset_voice():
        return _start_vm(), "<div class='vm-empty'>New session started.</div>"

    voice_process_btn.click(
        _process_voice,
        [voice_record, voice_memo_state],
        [voice_memo_state, voice_session_html],
        api_name="voice_memo_process",
        api_description="Transcribe the latest audio chunk and dispatch commands",
    )
    voice_reset_btn.click(
        _reset_voice,
        outputs=[voice_memo_state, voice_session_html],
        api_name="voice_memo_reset",
        api_description="End the current voice memo session and start a new one",
    )

    return AskPanelHandles(ask_input=ask_input, ask_output=ask_output)


def _parser_preview_and_reveal(utterance: str) -> str:
    """Render the "what the parser understood" panel."""
    from shopstack.ui.screens.parser_preview import parser_preview_screen
    return parser_preview_screen(utterance or "")
