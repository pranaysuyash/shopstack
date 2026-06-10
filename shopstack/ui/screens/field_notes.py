from __future__ import annotations

from shopstack.app_context import db
from shopstack.ui.views import load_field_notes, save_field_notes
from shopstack.ui.screens._utils import safe_render


@safe_render
def field_notes_view():
    view = load_field_notes(db)
    return view.editor_value, view.preview_value, view.status_html


@safe_render
def field_notes_save(note_text: str):
    view = save_field_notes(db, note_text)
    return view.editor_value, view.preview_value, view.status_html