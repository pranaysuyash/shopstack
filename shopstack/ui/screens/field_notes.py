from __future__ import annotations

from shopstack.app_context import db
from shopstack.ui.views import load_field_notes, save_field_notes
from shopstack.ui.errors import safe_render_html


def field_notes_view():
    try:
        return _field_notes_view_inner()
    except Exception:
        err = safe_render_html(
            lambda: "",
            user_message="Couldn't load field notes",
            help_tab="memory",
        )
        return err, err, err


def _field_notes_view_inner():
    view = load_field_notes(db)
    return view.editor_value, view.preview_value, view.status_html


def field_notes_save(note_text: str):
    try:
        return _field_notes_save_inner(note_text)
    except Exception:
        err = safe_render_html(
            lambda: "",
            user_message="Couldn't save field notes",
            help_tab="memory",
        )
        return err, err, err


def _field_notes_save_inner(note_text: str):
    view = save_field_notes(db, note_text)
    return view.editor_value, view.preview_value, view.status_html