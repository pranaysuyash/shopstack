from __future__ import annotations

import json
import os
import tempfile
from html import escape

from shopstack.app_context import db
from shopstack.portability import export_json, export_csv_inventory, import_json, import_csv

from shopstack.traces.export import _redact_obj, _redact_text


def export_data_json() -> str:
    data = export_json(db)
    redacted_data = _redact_obj(data)
    tmp = os.path.join(tempfile.mkdtemp(), "shopstack_export.json")
    with open(tmp, "w") as f:
        json.dump(redacted_data, f, indent=2, default=str)
    return tmp


def export_data_csv() -> str:
    tmp = os.path.join(tempfile.mkdtemp(), "shopstack_inventory.csv")
    csv_text = export_csv_inventory(db)
    redacted_csv = _redact_text(csv_text)
    with open(tmp, "w") as f:
        f.write(redacted_csv)
    return tmp


def import_data_file(file_path: str | None) -> str:
    if not file_path:
        return "<div style='color:var(--text-dim);'>Upload a JSON or CSV file first.</div>"
    try:
        path = str(file_path)
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
