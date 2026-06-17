"""Command surface sub-builder — the unified input for the Today tab.

**Why this exists (motto_v3 §0.14 product reality):**

The legacy Today tab had two near-duplicate inputs:

* "Quick add" — a small textbox + a primary "Add to my shopping list"
  button that called :func:`shopstack.services.restock_card.add_restock_to_list`.
* "Ask ShopStack" — a textbox + button pair that routed natural-language
  questions through the AI planner.

For the user, these were the same job ("tell ShopStack something").
For us, they were two surfaces to maintain, two event wirings, and
two ways to forget which one does what.

The command surface merges both. One input, one button, one Enter
handler. The :mod:`shopstack.services.command_surface` service parses
the typed text into a :class:`CommandIntent` (deterministic, no
LLM roundtrip for the common cases) and dispatches to the matching
inventory or shopping-list action. If nothing matches, the input
falls through to the Ask ShopStack planner so the user always gets
an answer.

The chip row below the input shows the 10 most common Indian
household staples — clicking a chip prefills the input with
``"add <staple>"`` and focuses it.

**Supersession (motto_v3 §7):**

The Quick-add row in :mod:`shopstack.ui.tabs.today` and the Ask
panel in :mod:`shopstack.ui.tabs.ask_panel` are *not* deleted. They
are deprecated (kept for back-compat) and the new command surface
is wired as the primary input. The chip-row, JS shim, and
"register_handler" pattern are the canonical surface for new code.
"""
from __future__ import annotations

from dataclasses import dataclass

import gradio as gr

from shopstack.services.command_execution import register_default_handlers
from shopstack.services.command_surface import (
    COMMAND_SURFACE_SCRIPT_HTML,
    parse_intent,
    render_command_surface_html,
)
from shopstack.services.intelligence_cards import INTELLIGENCE_CARD_SCRIPT_HTML
from shopstack.ui.tabs.context import TabContext


# ── Sub-builder handles ────────────────────────────────────────────


@dataclass
class CommandSurfaceHandles:
    """Components the parent Today tab references after building.

    Exposed (a) so the legacy Quick-add row in :mod:`shopstack.ui.tabs.today`
    can still be queried for back-compat and (b) so the household-switch
    wiring in ``app.py`` can refresh the surface on household change.
    """

    prompt_html: gr.HTML
    input_textbox: gr.Textbox
    submit_btn: gr.Button
    feedback_html: gr.HTML
    js_shim: gr.HTML


# ── Builder ────────────────────────────────────────────────────────


def build_command_surface(
    blocks: gr.Blocks,
    app: gr.Blocks,
    ctx: TabContext,
) -> CommandSurfaceHandles:
    """Add the unified command surface to the parent ``gr.Blocks`` context.

    Registers handlers for the four inventory actions and the Ask
    fall-through. The chip-row is rendered as part of ``prompt_html``
    (HTML produced by :func:`render_command_surface_html`) so the
    :class:`gr.HTML` for the prompt doubles as the chip container.
    """
    from shopstack.services import command_surface as _cs

    # Register the canonical handlers once so the dispatcher works
    # even when the v1 API is mounted without the Gradio tab.
    register_default_handlers()

    # Description / chip row (HTML)
    prompt_html = gr.HTML(
        render_command_surface_html(),
        elem_classes="command-surface-prompt",
    )

    # JS shim (chip → input fill helper + intelligence card dispatcher)
    js_shim = gr.HTML(
        _cs.COMMAND_SURFACE_SCRIPT_HTML + INTELLIGENCE_CARD_SCRIPT_HTML,
        elem_id="command-surface-shim",
        visible=True,
    )

    # Input + button in a single row (the unified CTA)
    with gr.Row(elem_classes="command-surface-row"):
        input_textbox = gr.Textbox(
            label="",
            placeholder=(
                "Add milk · I bought bread · We finished eggs · Do we have rice?"
            ),
            scale=4,
            elem_id="command-surface-input",
            show_label=False,
        )
        submit_btn = gr.Button("Submit", variant="primary", scale=1)

    feedback_html = gr.HTML("", elem_id="command-surface-feedback")

    def _on_submit(text: str) -> str:
        intent = parse_intent(text or "")
        result = _cs.dispatch(intent)
        return result.to_toast()

    submit_btn.click(_on_submit, inputs=input_textbox, outputs=feedback_html)
    input_textbox.submit(_on_submit, inputs=input_textbox, outputs=feedback_html)

    return CommandSurfaceHandles(
        prompt_html=prompt_html,
        input_textbox=input_textbox,
        submit_btn=submit_btn,
        feedback_html=feedback_html,
        js_shim=js_shim,
    )


__all__ = [
    "CommandSurfaceHandles",
    "build_command_surface",
]
