from __future__ import annotations

import json
import os
import tempfile
from html import escape
from pathlib import Path

from shopstack.app_context import db
from shopstack.portability import export_json, export_csv_inventory, import_json, import_csv

from shopstack.traces.export import _redact_obj, _redact_text


def _resolve_uploaded_file_path(file_path: str | Path | object | None) -> str | None:
    """Gradio's ``gr.File`` returns different types depending on version:
    a string path, a Path, a tempfile._TemporaryFileWrapper, or a dict
    with a ``name`` key. Normalize to a string path or None.

    Returns the path string if resolvable, None if not.
    """
    if not file_path:
        return None
    if isinstance(file_path, (str, Path)):
        return str(file_path)
    if isinstance(file_path, dict):
        name = file_path.get("name") or file_path.get("path")
        if name:
            return str(name)
        return None
    # tempfile._TemporaryFileWrapper or similar — has a .name attribute
    name = getattr(file_path, "name", None)
    if name:
        return str(name)
    return None


def export_data_json() -> str:
    """Export household data to a redacted JSON file.

    Returns the path to the generated file. The caller (Gradio's
    gr.File component) will offer it as a download.
    """
    data = export_json(db)
    redacted_data = _redact_obj(data)
    tmp = os.path.join(tempfile.mkdtemp(), "shopstack_export.json")
    with open(tmp, "w") as f:
        json.dump(redacted_data, f, indent=2, default=str)
    return tmp


def export_data_csv() -> str:
    """Export inventory to a redacted CSV file.

    Returns the path to the generated file. The caller (Gradio's
    gr.File component) will offer it as a download.
    """
    tmp = os.path.join(tempfile.mkdtemp(), "shopstack_inventory.csv")
    csv_text = export_csv_inventory(db)
    redacted_csv = _redact_text(csv_text)
    with open(tmp, "w") as f:
        f.write(redacted_csv)
    return tmp


def import_data_file(file_path: str | Path | object | None) -> str:
    """Import household data from a JSON or CSV upload.

    Handles Gradio's various file upload return types (string path,
    Path, tempfile wrapper, dict) via _resolve_uploaded_file_path.
    """
    from shopstack.ui.errors import safe_render_html
    return safe_render_html(
        lambda: _import_data_file_inner(file_path),
        user_message="Could not import data file",
        help_tab="today",
    )


def _import_data_file_inner(file_path: str | Path | object | None) -> str:
    resolved = _resolve_uploaded_file_path(file_path)
    if not resolved:
        return "<div style='color:var(--text-dim);'>Upload a JSON or CSV file first.</div>"
    path = str(resolved)
    if path.endswith(".csv"):
        with open(path) as f:
            result = import_csv(db, f.read())
    else:
        with open(path) as f:
            data = json.load(f)
        result = import_json(db, data)
    return result.summary_html
