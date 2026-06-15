"""Voice memo sub-builder — extracted from ask_panel.py for repositioning.

Phase 4 repositioning: voice memo is now rendered directly below the
command surface in the Today tab (left column), not buried inside the
Ask panel (right column). This makes it a visible secondary input
method rather than a hidden advanced feature.

User-facing language throughout — no developer jargon.
"""
from __future__ import annotations

import gradio as gr


def build_voice_memo_section(app: gr.Blocks) -> None:
    """Build the voice memo section below the command surface.

    Renders a compact, user-facing voice input area with:
    - A short description using everyday language
    - Record / Process / Stop controls
    - Session summary output
    - Microphone fallback tip

    Args:
        app: The root gr.Blocks instance for event wiring.
    """
    gr.Markdown("### Or say it out loud")
    gr.Markdown(
        'Try: **"Add milk"**, **"I bought rice"**, '
        'or **"We finished bread"**.'
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
            elem_id="voice-record",
        )
        voice_process_btn = gr.Button(
            "Process audio", variant="primary", elem_id="voice-process",
        )
    # Microphone status: clean fallback.
    gr.HTML(
        "<div class='vm-status'>If your browser blocks the "
        "microphone, type the same command in the box above.</div>"
    )
    voice_session_html = gr.HTML(
        "<div class='vm-empty'>No voice memo captured yet.</div>",
    )
    voice_reset_btn = gr.Button(
        "Stop recording", elem_classes="secondary",
        visible=False, elem_id="voice-stop",
    )

    def _process_voice(audio_path, session):
        from shopstack.app_context import providers as _providers
        if not audio_path:
            return (
                session,
                "<div class='vm-empty'>No audio captured. Press the mic and try again.</div>",
                gr.update(visible=False),
            )
        stt = None
        try:
            for name in ("whisper", "local_whisper", "sensevoice", "qwen3_asr", "mock_stt"):
                stt = _providers.get(name)
                if stt is not None:
                    break
        except Exception:
            stt = None
        if stt is None:
            return (
                session,
                "<div class='vm-empty'>No voice engine loaded. "
                "Type your command in the box above instead.</div>",
                gr.update(visible=False),
            )
        log: list[dict] = []
        from shopstack.services.voice_memo import make_recording_dispatcher
        _capture_vm(session, audio_path, stt,
                    dispatcher=make_recording_dispatcher(log))
        return (
            session,
            _render_vm(_end_vm(session)),
            gr.update(visible=True),
        )

    def _reset_voice():
        return (
            _start_vm(),
            "<div class='vm-empty'>New session started.</div>",
            gr.update(visible=False),
        )

    voice_process_btn.click(
        _process_voice,
        [voice_record, voice_memo_state],
        [voice_memo_state, voice_session_html, voice_reset_btn],
        api_name="voice_memo_process",
        api_description="Transcribe the latest audio chunk and dispatch commands",
    )
    voice_reset_btn.click(
        _reset_voice,
        outputs=[voice_memo_state, voice_session_html, voice_reset_btn],
        api_name="voice_memo_reset",
        api_description="End the current voice memo session and start a new one",
    )
