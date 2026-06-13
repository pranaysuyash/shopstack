"""Memory tab — Remember (Field Notes) sub-builder.

Extracted from ``build_memory_tab`` so the field-notes editor
(free-form household notes with live markdown preview, reload, and
save) is independently testable and reusable.
"""
from __future__ import annotations

import gradio as gr

from shopstack.ui.components.primitives import loading_skeleton
from shopstack.ui.screens import field_notes_save, field_notes_view
from shopstack.ui.tabs.context import TabContext


def build_memory_notes(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Remember (Field Notes) sub-tab inside the Memory tab.

    Adds a Markdown header, an editable Textbox, a live markdown
    preview, a status HTML, and Reload/Save buttons. Wires:
    - ``notes_reload.click`` → ``field_notes_view``
    - ``notes_save.click`` → ``field_notes_save``
    - ``notes_editor.change`` → live preview (echo of the text)
    - ``app.load`` → ``field_notes_view`` (initial population)

    Args:
        app: The root gr.Blocks instance — needed for ``app.load(...)``.
        ctx: Shared dependencies (unused in this sub-tab, kept for
            uniform signature).

    Returns:
        None. No cross-sub-tab references.
    """
    gr.Markdown("### Household notes")
    gr.Markdown(
        "Capture household notes, shopping decisions, price changes, "
        "and things to remember next time."
    )
    notes_editor = gr.Textbox(
        label="Editable Draft",
        lines=16,
        placeholder="# Household Notes\n\nWrite what we learned...",
    )
    notes_preview = gr.Markdown()
    notes_status = gr.HTML(loading_skeleton("text"))
    with gr.Row():
        notes_reload = gr.Button("Reload draft", elem_classes="secondary")
        notes_save = gr.Button("Save notes")
    notes_reload.click(
        field_notes_view,
        outputs=[notes_editor, notes_preview, notes_status],
        api_name="notes_reload",
        api_description="Reload persisted field notes and preview",
    )
    notes_save.click(
        field_notes_save,
        notes_editor,
        outputs=[notes_editor, notes_preview, notes_status],
        api_name="notes_save",
        api_description="Save field notes draft",
    )
    notes_editor.change(
        lambda text: text,
        notes_editor,
        notes_preview,
        api_name="notes_live_preview",
        api_description="Update markdown preview while typing notes",
    )
    app.load(field_notes_view, outputs=[notes_editor, notes_preview, notes_status])
