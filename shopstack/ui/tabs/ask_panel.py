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

.. note::
    2026-06-15 supersession (motto_v3 §7): voice memo is no longer
    rendered inside this panel. The canonical voice-memo implementation
    lives in :mod:`shopstack.ui.tabs.voice_memo` and is mounted from
    the Today tab below the command surface. The
    ``build_voice_memo_section`` symbol at the bottom of this file is a
    backward-compat alias kept for any external importer; new code
    should import directly from :mod:`shopstack.ui.tabs.voice_memo`.
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
    gr.Markdown("### Ask about home, shopping, or prices")
    ask_input = gr.Textbox(
        label="Your question",
        placeholder="Do we have milk?  |  What should I buy today?  |  Where is toothpaste?",
        lines=2,
        elem_id="ask-input",
    )
    ask_btn = gr.Button("Ask", elem_id="ask-btn")
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

    # ── Voice memo is intentionally NOT rendered here. ───────────
    # 2026-06-15: voice memo is now a primary nav tab component
    # (rendered in `shopstack/ui/tabs/voice_memo.py::build_voice_memo_section`,
    # mounted from the Today tab below the command surface). Ask
    # ShopStack is a text-first panel; voice input is reachable
    # from the same Today tab. Per `motto_v3` §7 supersession, the
    # inline voice_memo copy that previously lived here has been
    # removed; the canonical implementation is the dedicated
    # module. A `build_voice_memo_section` backward-compat alias
    # remains at the bottom of this file for any external code
    # that imported it from here.
    return AskPanelHandles(ask_input=ask_input, ask_output=ask_output)


def build_voice_memo_section(app: gr.Blocks) -> None:
    """Backward-compat alias for the canonical voice memo builder.

    .. deprecated:: 2026-06-15
        Import :func:`shopstack.ui.tabs.voice_memo.build_voice_memo_section`
        directly. The canonical implementation lives in
        :mod:`shopstack.ui.tabs.voice_memo` (extracted from this file
        per the voice-memo repositioning work). This alias is preserved
        per :ref:`motto_v3 §7 Supersession <motto_v3>` so external
        importers do not break, and will be removed in a future pass
        once no in-tree code references it.
    """
    from shopstack.ui.tabs.voice_memo import build_voice_memo_section as _build
    _build(app)


def _parser_preview_and_reveal(utterance: str) -> str:
    """Render the "what the parser understood" panel."""
    from shopstack.ui.screens.parser_preview import parser_preview_screen
    return parser_preview_screen(utterance or "")
