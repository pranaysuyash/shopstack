from __future__ import annotations

from html import escape

import gradio as gr
import pandas as pd

from shopstack.app_context import db
from shopstack.ui import build_price_memory_view, load_field_notes, save_field_notes


def price_memory_view(item_name: str = ""):
    view = build_price_memory_view(db, item_name)
    has_data = view.observation_count > 0
    unit_plot_df = view.df[["date", "unit_price"]].dropna() if has_data else pd.DataFrame(columns=["date", "unit_price"])
    return (
        view.summary_html,
        gr.update(value=view.df, visible=has_data),
        gr.update(value=unit_plot_df, visible=len(unit_plot_df) > 0),
        view.table,
    )


def household_map_view() -> str:
    locations = db.get_locations()
    inventory = db.get_inventory()
    loc_counts: dict[str, int] = {}
    loc_items: dict[str, list[str]] = {}
    for l in inventory:
        lid = l.storage_location_id or "unknown"
        loc_counts[lid] = loc_counts.get(lid, 0) + 1
        loc_items.setdefault(lid, []).append(f"{l.display_name} ({l.quantity} {l.unit})")

    cards = ""
    for loc in locations:
        count = loc_counts.get(loc.location_id, 0)
        parent = loc.parent_location_id or ""
        item_list = loc_items.get(loc.location_id, [])
        item_details = item_list[:8]
        if len(item_list) > 8:
            item_details.append(f"... and {len(item_list) - 8} more")
        item_details_html = (
            "<div style='margin-top:8px;font-size:11px;color:var(--text-dim);'>"
            + "".join(f"<div>{escape(str(item))}</div>" for item in item_details)
            + "</div>"
            if item_details
            else "<div style='margin-top:8px;font-size:11px;color:var(--text-dim);'>No items stored here yet.</div>"
        )
        safe_name = escape(str(loc.name))
        safe_type = escape(str(loc.location_type))
        safe_parent = escape(str(parent))
        cards += f"""
<div class="stat-card" style="text-align:left;margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div>
      <div style="font-weight:600;color:var(--text);">{safe_name}</div>
      <div style="font-size:11px;color:var(--text-dim);">{safe_type}{' \u2192 '+safe_parent if parent else ''}</div>
    </div>
    <div class="stat-value" style="font-size:24px;">{count}</div>
  </div>
  {item_details_html}
</div>"""
    return f"<h3>Household Storage Map</h3><div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;'>{cards}</div>"


def field_notes_view():
    view = load_field_notes(db)
    return view.editor_value, view.preview_value, view.status_html


def field_notes_save(note_text: str):
    view = save_field_notes(db, note_text)
    return view.editor_value, view.preview_value, view.status_html
