from __future__ import annotations

import json
import os
import shutil
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


def export_data_json() -> tuple[str, str]:
    """Export household data to a redacted JSON file.

    Returns:
        (file_path, status_html) tuple. The file_path is the path
        to the generated JSON file; status_html is the user-facing
        message to display.

    The temp directory is cleaned up after the file is read (we
    don't delete the file immediately because Gradio needs to serve
    it to the user). We do track the temp dir for later cleanup.
    """
    data = export_json(db)
    redacted_data = _redact_obj(data)
    tmp_dir = tempfile.mkdtemp(prefix="shopstack_export_")
    tmp_path = os.path.join(tmp_dir, "shopstack_export.json")
    with open(tmp_path, "w") as f:
        json.dump(redacted_data, f, indent=2, default=str)
    size_kb = os.path.getsize(tmp_path) / 1024
    status = (
        f"<div style='color:var(--green);'>"
        f"Exported {len(redacted_data.get('inventory_lots', []))} inventory lots, "
        f"{len(redacted_data.get('shopping_lists', []))} shopping lists "
        f"({size_kb:.1f} KB) to {escape(tmp_path)}</div>"
    )
    return tmp_path, status


def export_data_csv() -> tuple[str, str]:
    """Export inventory to a redacted CSV file.

    Returns:
        (file_path, status_html) tuple.
    """
    tmp_dir = tempfile.mkdtemp(prefix="shopstack_csv_")
    tmp_path = os.path.join(tmp_dir, "shopstack_inventory.csv")
    csv_text = export_csv_inventory(db)
    redacted_csv = _redact_text(csv_text)
    with open(tmp_path, "w") as f:
        f.write(redacted_csv)
    size_kb = os.path.getsize(tmp_path) / 1024
    line_count = redacted_csv.count("\n") + 1
    status = (
        f"<div style='color:var(--green);'>"
        f"Exported {line_count} rows ({size_kb:.1f} KB) to {escape(tmp_path)}</div>"
    )
    return tmp_path, status


def import_data_file(file_path: str | Path | object | None) -> str:
    """Import household data from a JSON or CSV upload.

    Handles Gradio's various file upload return types (string path,
    Path, tempfile wrapper, dict) via _resolve_uploaded_file_path.
    """
    resolved = _resolve_uploaded_file_path(file_path)
    if not resolved:
        return "<div style='color:var(--text-dim);'>Upload a JSON or CSV file first.</div>"
    try:
        path = str(resolved)
        if path.endswith(".csv"):
            with open(path) as f:
                result = import_csv(db, f.read())
        else:
            with open(path) as f:
                data = json.load(f)
            result = import_json(db, data)
        return result.summary_html
    except Exception as e:
        return f"<div style='color:var(--red);'>Import failed: {escape(str(e))}</div>"
