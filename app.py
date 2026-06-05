from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import gradio as gr

from shopstack.config import Settings
from shopstack.model_registry import get_registry
from shopstack.persistence.database import Database
from shopstack.providers.registry import ProviderRegistry
from shopstack.tools.registry import ToolRegistry
from shopstack.traces.export import create_trace

settings = Settings()
db = Database(settings.database_path)
providers = ProviderRegistry(settings)
tools = ToolRegistry(db)
model_registry = get_registry()

CSS = """
:root {
  --bg: #0f0f11; --bg-card: #1a1a1e; --bg-input: #242428;
  --border: #2e2e34; --text: #e4e4e7; --text-dim: #888899;
  --accent: #6c5ce7; --accent-hover: #7c6df7;
  --green: #00b894; --red: #e17055; --amber: #fdcb6e; --blue: #74b9ff;
  --radius: 12px; --radius-sm: 8px;
}
.gradio-container { background: var(--bg) !important; color: var(--text) !important; font-family: 'Inter', -apple-system, system-ui, sans-serif; max-width: 1280px !important; margin: 0 auto; }
.tabs { border: none !important; }
.tab-nav { background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; padding: 4px !important; gap: 2px !important; }
.tab-nav button { background: transparent !important; border: none !important; color: var(--text-dim) !important; font-size: 13px !important; padding: 8px 14px !important; border-radius: var(--radius-sm) !important; transition: all 0.15s; }
.tab-nav button.selected { background: var(--accent) !important; color: #fff !important; }
.tab-nav button:hover { background: var(--bg-input) !important; color: var(--text) !important; }
.gr-box { background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; }
.gr-text-input, .gr-number-input, .gr-dropdown, textarea { background: var(--bg-input) !important; border: 1px solid var(--border) !important; border-radius: var(--radius-sm) !important; color: var(--text) !important; }
.gr-text-input:focus, .gr-number-input:focus, textarea:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 2px rgba(108,92,231,0.2) !important; }
.gr-button { background: var(--accent) !important; border: none !important; border-radius: var(--radius-sm) !important; color: #fff !important; font-weight: 500 !important; padding: 8px 20px !important; transition: all 0.15s !important; }
.gr-button:hover { background: var(--accent-hover) !important; transform: translateY(-1px); }
.gr-button.secondary { background: var(--bg-input) !important; border: 1px solid var(--border) !important; }
.gr-button.secondary:hover { background: var(--border) !important; }
h1, h2, h3 { color: var(--text) !important; font-weight: 600 !important; margin: 0 0 8px 0 !important; }
label, .gr-form-label { color: var(--text-dim) !important; font-size: 12px !important; font-weight: 500 !important; text-transform: uppercase !important; letter-spacing: 0.5px !important; }
.gr-dataframe { background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; }
.gr-dataframe table { font-size: 13px !important; }
.gr-dataframe th { background: var(--bg-input) !important; color: var(--text-dim) !important; border-bottom: 1px solid var(--border) !important; padding: 10px 12px !important; }
.gr-dataframe td { border-bottom: 1px solid var(--border) !important; padding: 8px 12px !important; color: var(--text) !important; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 100px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }
.badge-green { background: rgba(0,184,148,0.15); color: var(--green); }
.badge-red { background: rgba(225,112,85,0.15); color: var(--red); }
.badge-amber { background: rgba(253,203,110,0.15); color: var(--amber); }
.badge-blue { background: rgba(116,185,255,0.15); color: var(--blue); }
.stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; text-align: center; }
.stat-value { font-size: 32px; font-weight: 700; color: var(--text); line-height: 1; }
.stat-label { font-size: 12px; color: var(--text-dim); margin-top: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
.action-row { display: flex; gap: 8px; flex-wrap: wrap; }
"""


def _list_to_table(items: list[dict[str, Any]], cols: list[str] | None = None) -> list[list[str]]:
    if not items:
        return [["No data"]]
    if cols is None:
        cols = list(items[0].keys())
    header = [c.replace("_", " ").title() for c in cols]
    rows = [[str(item.get(c, "")) for c in cols] for item in items]
    return [header] + rows


def today_dashboard():
    use_soon = tools.get_use_soon_items(days=3)
    soon_count = use_soon["count"]
    active_list = db.get_active_shopping_list()
    all_inv = db.get_inventory()
    active_inv = [l for l in all_inv if l.status == "active"]
    low_items = [l for l in active_inv if l.quantity <= 0.5 or l.status == "low"]
    purchases = db.get_purchases(limit=5)

    return [
        gr.HTML(f"""
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:20px;">
  <div class="stat-card"><div class="stat-value">{len(active_inv)}</div><div class="stat-label">Active Items</div></div>
  <div class="stat-card"><div class="stat-value">{soon_count}</div><div class="stat-label">Use Soon</div></div>
  <div class="stat-card"><div class="stat-value">{len(low_items)}</div><div class="stat-label">Low Stock</div></div>
  <div class="stat-card"><div class="stat-value">{len(purchases)}</div><div class="stat-label">Recent Purchases</div></div>
</div>"""),
        _render_use_soon(use_soon),
        _render_list_summary(active_list),
        _render_low_stock(low_items),
        _render_recent_purchases(purchases),
    ]


def _render_use_soon(data: dict) -> str:
    items = data.get("items", [])
    if not items:
        return '<div class="stat-card" style="text-align:left;margin-bottom:12px;"><div style="color:var(--green);font-weight:500;">✓ No items need immediate attention</div></div>'
    rows = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--border);">'
        f'<span>{i["display_name"]}</span>'
        f'<span class="badge {"badge-red" if i.get("days_remaining", 99) <= 1 else "badge-amber"}">{i.get("days_remaining", "?")}d left</span>'
        f'</div>'
        for i in items[:5]
    )
    return f'<div class="stat-card" style="text-align:left;margin-bottom:12px;"><h3>⚠ Use Soon</h3>{rows}</div>'


def _render_list_summary(sl) -> str:
    if not sl:
        return '<div class="stat-card" style="text-align:left;margin-bottom:12px;"><h3>Shopping List</h3><div style="color:var(--text-dim);">No active list.</div></div>'
    items = sl.items or []
    if not items:
        return '<div class="stat-card" style="text-align:left;margin-bottom:12px;"><h3>Shopping List</h3><div style="color:var(--text-dim);">List is empty.</div></div>'
    rows = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);">'
        f'<span>{i.canonical_name}</span>'
        f'<span class="badge badge-blue">{i.status}</span>'
        f'</div>'
        for i in items[:8]
    )
    return f'<div class="stat-card" style="text-align:left;margin-bottom:12px;"><h3>Shopping List ({len(items)} items)</h3>{rows}</div>'


def _render_low_stock(items) -> str:
    if not items:
        return ""
    rows = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);">'
        f'<span>{l.display_name}</span>'
        f'<span style="color:var(--red);">{l.quantity} {l.unit}</span>'
        f'</div>'
        for l in items[:5]
    )
    return f'<div class="stat-card" style="text-align:left;margin-bottom:12px;"><h3>Low Stock</h3>{rows}</div>'


def _render_recent_purchases(purchases) -> str:
    if not purchases:
        return ""
    rows = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);">'
        f'<span>{p.canonical_name}</span>'
        f'<span>₹{p.total_price:.0f}</span>'
        f'</div>'
        for p in purchases[:5]
    )
    return f'<div class="stat-card" style="text-align:left;margin-bottom:12px;"><h3>Recent Purchases</h3>{rows}</div>'


def shopping_list_view():
    sl = db.get_active_shopping_list()
    if not sl:
        return "<div class='stat-card' style='text-align:left;'><h3>Shopping List</h3><div style='color:var(--text-dim);'>No active shopping list. Create one below.</div></div>", gr.DataFrame(value=[["No items"]], headers=["Item"]), "", ""

    items = sl.items or []
    tbl = _list_to_table(
        [{"item": i.canonical_name, "qty": i.requested_quantity or 1, "unit": i.unit or "unit", "priority": i.priority, "status": i.status, "reason": i.reason} for i in items],
        ["item", "qty", "unit", "priority", "status", "reason"],
    )
    goal_html = f"<div style='margin-bottom:12px;'><strong>Goal:</strong> {sl.goal}</div>" if sl.goal else ""
    return goal_html, gr.DataFrame(value=tbl, headers=tbl[0] if tbl else []), sl.list_id, sl.goal or ""


def shopping_list_create(goal: str, items_json: str) -> str:
    items = json.loads(items_json) if items_json else []
    result = tools.create_or_update_shopping_list(items=items, goal=goal)
    return f"<div style='color:var(--green);'>Created list: {result.get('list', {}).get('list_id', '')} with {len(items)} items</div>"


def _market_lens_process(image_path: str | None, audio_path: str | None) -> tuple:
    result_html = "<div style='color:var(--text-dim);'>No input provided.</div>"
    items_found = []
    analysis = ""

    if image_path:
        detections = providers.object_detection.detect(image_path)
        ocr_result = providers.ocr.extract(image_path)
        items_found = [d["label"] for d in detections if d["confidence"] > 0.3]
        analysis_html = "<div style='margin:12px 0;'>"
        for d in detections[:8]:
            comparison = tools.compare_visible_item_to_inventory(d["label"], d.get("quantity", 1.0), "unit")
            badge = "badge-green" if comparison["decision"] == "skip" else "badge-red" if comparison["decision"] == "buy" else "badge-amber"
            analysis_html += f"<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);'>"
            analysis_html += f"<span>{d['label']} ({d['confidence']:.0%})</span>"
            analysis_html += f"<span><span class='badge {badge}'>{comparison['decision']}</span> {comparison.get('reason','')[:50]}</span>"
            analysis_html += f"</div>"
        analysis_html += "</div>"
        result_html = analysis_html
        analysis = analysis_html

    if audio_path:
        transcript = providers.stt.transcribe(audio_path)
        result_html += f"<div style='margin-top:12px;'><strong>Heard:</strong> {transcript}</div>"

    return result_html, str(items_found), analysis


def add_purchase_form(
    name: str, qty: float, unit: str, price: float, store: str, location: str, purchase_date_str: str, category: str
) -> str:
    add_result = tools.add_inventory_item(
        canonical_name=name.strip().lower(),
        display_name=name.strip(),
        quantity=qty,
        unit=unit,
        storage_location_id=location or "kitchen",
        purchase_date=purchase_date_str or date.today().isoformat(),
        category=category,
    )
    lot_id = add_result.get("lot_id", "")
    if price > 0 and store:
        tools.record_price_observation(
            canonical_name=name.strip().lower(),
            price=price,
            quantity=qty,
            unit=unit,
            store_name=store,
        )
    return f"<div style='color:var(--green);'>Added {name} (lot {lot_id})</div>"


def inventory_view(search: str = "") -> list[list[str]]:
    items = db.get_inventory()
    if search:
        q = search.lower()
        items = [l for l in items if q in l.canonical_name.lower() or q in l.display_name.lower()]
    tbl = _list_to_table(
        [
            {
                "name": l.display_name,
                "qty": l.quantity,
                "unit": l.unit,
                "location": db.get_location(l.storage_location_id).name if l.storage_location_id and db.get_location(l.storage_location_id) else l.storage_location_id,
                "status": l.status,
                "purchased": l.purchase_date.isoformat() if l.purchase_date else "",
                "expires": (l.label_expiry_date or l.estimated_use_by_date or "").isoformat() if (l.label_expiry_date or l.estimated_use_by_date) else "",
                "lot_id": l.lot_id[:8],
            }
            for l in items
        ],
        ["name", "qty", "unit", "location", "status", "purchased", "expires", "lot_id"],
    )
    return tbl


def consume_item(lot_id: str, qty: float) -> str:
    result = tools.consume_inventory_item(lot_id, qty)
    if "error" in result:
        return f"<div style='color:var(--red);'>Error: {result['error']}</div>"
    return f"<div style='color:var(--green);'>Consumed {qty}. Remaining: {result.get('remaining', 0)}</div>"


def use_soon_view(days: int = 3) -> list[list[str]]:
    data = tools.get_use_soon_items(days=days)
    items = data.get("items", [])
    tbl = _list_to_table(
        [
            {
                "name": i.get("display_name", i.get("canonical_name", "")),
                "qty": i.get("quantity", 0),
                "unit": i.get("unit", ""),
                "expires": i.get("expiry_date", i.get("purchase_date", "")),
                "days": i.get("days_remaining", i.get("days_since_purchase", 0)),
                "reason": i.get("reason", i.get("expiry_type", "")),
            }
            for i in items
        ],
        ["name", "qty", "unit", "expires", "days", "reason"],
    )
    return tbl


def price_memory_view(item_name: str = "") -> list[list[str]]:
    if not item_name:
        return [["Enter an item name to see price history"]]
    history = db.get_price_history(item_name)
    tbl = _list_to_table(
        [
            {
                "store": p.store_name or "Unknown",
                "price": f"₹{p.price:.2f}",
                "qty": p.quantity,
                "unit": p.unit,
                "date": p.observation_date.isoformat(),
                "notes": p.notes or "",
            }
            for p in history
        ],
        ["store", "price", "qty", "unit", "date", "notes"],
    )
    return tbl


def household_map_view() -> str:
    locations = db.get_locations()
    inventory = db.get_inventory()
    loc_counts: dict[str, int] = {}
    for l in inventory:
        lid = l.storage_location_id or "unknown"
        loc_counts[lid] = loc_counts.get(lid, 0) + 1

    cards = ""
    for loc in locations:
        count = loc_counts.get(loc.location_id, 0)
        parent = loc.parent_id or ""
        cards += f"""
<div class="stat-card" style="text-align:left;margin-bottom:8px;cursor:pointer;"
     onclick="alert('Location: {loc.name}\\nItems: {count}\\nType: {loc.location_type}')">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div>
      <div style="font-weight:600;color:var(--text);">{loc.name}</div>
      <div style="font-size:11px;color:var(--text-dim);">{loc.location_type}{' → '+parent if parent else ''}</div>
    </div>
    <div class="stat-value" style="font-size:24px;">{count}</div>
  </div>
</div>"""
    return f"<h3>Household Storage Map</h3><div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;'>{cards}</div>"


def agent_trace_view() -> tuple:
    traces = db.get_traces(limit=50)
    if not traces:
        return [["No traces yet"]], ""
    tbl = _list_to_table(
        [
            {
                "trace_id": t.trace_id[:12],
                "type": t.input_type,
                "time": t.timestamp.split(".")[0] if t.timestamp else "",
                "goal": (t.user_goal or "")[:40],
                "tool_calls": len(t.proposed_tool_calls or []),
            }
            for t in traces
        ],
        ["trace_id", "type", "time", "goal", "tool_calls"],
    )
    return tbl, traces[0].trace_id if traces else ""


def agent_trace_detail(trace_id: str) -> str:
    traces = db.get_traces(limit=100)
    for t in traces:
        if t.trace_id == trace_id:
            return f"<pre style='font-size:12px;overflow:auto;max-height:400px;background:var(--bg-input);padding:12px;border-radius:var(--radius-sm);'>{json.dumps(t.model_dump(), indent=2, default=str)}</pre>"
    return "<div style='color:var(--text-dim);'>Trace not found.</div>"


def field_notes_view() -> str:
    traces = db.get_traces(limit=20)
    if not traces:
        return "<div style='color:var(--text-dim);'>No agent sessions recorded yet.</div>"
    entries = ""
    for t in reversed(traces):
        decision = t.decision or {}
        perception = t.perception or {}
        entries += f"""
<div class="stat-card" style="text-align:left;margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--text-dim);margin-bottom:6px;">
    <span>{t.input_type}</span>
    <span>{t.timestamp[:19]}</span>
  </div>
  <div style="margin-bottom:4px;"><strong>Goal:</strong> {t.user_goal or '—'}</div>
  <div style="margin-bottom:4px;"><strong>Decision:</strong> {json.dumps(decision, default=str)[:200]}</div>
  <div style="font-size:11px;color:var(--text-dim);">
    <strong>Perception:</strong> {json.dumps(perception, default=str)[:100]}
    | <strong>Tools:</strong> {len(t.proposed_tool_calls or [])}
    | <strong>Response:</strong> {(t.final_response or '')[:80]}
  </div>
</div>"""
    return entries


def build_app() -> gr.Blocks:
    with gr.Blocks(title="ShopStack", css=CSS, theme=gr.themes.Base()) as app:
        gr.HTML("""
<div style="display:flex;justify-content:space-between;align-items:center;padding:16px 0;border-bottom:1px solid var(--border);margin-bottom:20px;">
  <div>
    <h1 style="font-size:22px;margin:0;">ShopStack</h1>
    <div style="font-size:12px;color:var(--text-dim);">Off the Grid · Local-First Household Inventory</div>
  </div>
  <div style="text-align:right;font-size:11px;color:var(--text-dim);">
    Off the Grid · Mock Providers
  </div>
</div>""")

        with gr.Tabs(elem_classes="tabs") as tabs:
            with gr.Tab("Today", id="today"):
                today_stats = gr.HTML("")
                today_soon = gr.HTML("")
                today_list = gr.HTML("")
                today_low = gr.HTML("")
                today_recent = gr.HTML("")
                app.load(today_dashboard, outputs=[today_stats, today_soon, today_list, today_low, today_recent])

            with gr.Tab("Shopping List", id="shopping"):
                sl_display = gr.HTML("")
                sl_table = gr.DataFrame(label="Items")
                sl_list_id = gr.State("")
                sl_goal = gr.State("")
                with gr.Row():
                    goal_input = gr.Textbox(label="List Goal (e.g. Weekly Groceries)", placeholder="What's this list for?")
                    items_input = gr.Textbox(label="Items JSON (optional)", placeholder='[{"canonical_name":"milk","requested_quantity":2}]', lines=2)
                with gr.Row():
                    create_btn = gr.Button("Create / Update List")
                    refresh_btn = gr.Button("Refresh", elem_classes="secondary")
                create_output = gr.HTML("")
                create_btn.click(shopping_list_create, [goal_input, items_input], create_output)
                refresh_btn.click(shopping_list_view, outputs=[sl_display, sl_table, sl_list_id, sl_goal])
                app.load(shopping_list_view, outputs=[sl_display, sl_table, sl_list_id, sl_goal])

            with gr.Tab("Market Lens", id="market"):
                gr.Markdown("### Point your camera or upload a photo — or speak what you see")
                with gr.Row():
                    image_input = gr.Image(type="filepath", label="Camera / Photo")
                    audio_input = gr.Audio(type="filepath", label="Voice Note")
                scan_btn = gr.Button("Scan & Compare to Inventory")
                ml_results = gr.HTML("")
                ml_items = gr.Textbox(label="Detected Items", visible=False)
                ml_analysis = gr.HTML("")
                scan_btn.click(_market_lens_process, [image_input, audio_input], [ml_results, ml_items, ml_analysis])

            with gr.Tab("Add Purchase", id="purchase"):
                gr.Markdown("### Record a Purchase")
                with gr.Row():
                    p_name = gr.Textbox(label="Item Name", placeholder="e.g. Milk, Atta, Rice")
                    p_qty = gr.Number(label="Quantity", value=1.0)
                    p_unit = gr.Textbox(label="Unit", value="unit", placeholder="kg, L, pieces")
                with gr.Row():
                    p_price = gr.Number(label="Price (₹)", value=0.0)
                    p_store = gr.Textbox(label="Store", placeholder="e.g. Big Bazaar, Local Kirana")
                    p_location = gr.Dropdown(label="Storage Location", choices=[(l.name, l.location_id) for l in db.get_locations()], value="pantry")
                with gr.Row():
                    p_date = gr.Textbox(label="Purchase Date (YYYY-MM-DD)", placeholder=date.today().isoformat())
                    p_category = gr.Textbox(label="Category", placeholder="e.g. Dairy, Grains, Vegetables")
                p_submit = gr.Button("Add to Inventory")
                p_result = gr.HTML("")
                p_submit.click(add_purchase_form, [p_name, p_qty, p_unit, p_price, p_store, p_location, p_date, p_category], p_result)

            with gr.Tab("Inventory", id="inventory"):
                with gr.Row():
                    inv_search = gr.Textbox(label="Search Inventory", placeholder="Type to filter...")
                    inv_refresh = gr.Button("Refresh", elem_classes="secondary")
                inv_table = gr.DataFrame(label="All Inventory Items")
                with gr.Row():
                    cons_lot = gr.Textbox(label="Lot ID (first 8 chars)", placeholder="abcdef12")
                    cons_qty = gr.Number(label="Quantity to Consume", value=1.0)
                    cons_btn = gr.Button("Consume")
                cons_result = gr.HTML("")
                inv_search.change(inventory_view, inv_search, inv_table)
                inv_refresh.click(inventory_view, outputs=inv_table)
                cons_btn.click(consume_item, [cons_lot, cons_qty], cons_result)
                app.load(inventory_view, outputs=inv_table)

            with gr.Tab("Use Soon", id="usesoon"):
                with gr.Row():
                    use_days = gr.Slider(1, 30, value=3, step=1, label="Days threshold")
                    use_refresh = gr.Button("Refresh", elem_classes="secondary")
                use_table = gr.DataFrame(label="Items to Use Soon")
                use_refresh.click(use_soon_view, use_days, use_table)
                app.load(use_soon_view, inputs=use_days, outputs=use_table)

            with gr.Tab("Price Memory", id="prices"):
                with gr.Row():
                    price_item = gr.Textbox(label="Item Name", placeholder="e.g. basmati rice")
                    price_search = gr.Button("Search")
                price_table = gr.DataFrame(label="Price History")
                price_search.click(price_memory_view, price_item, price_table)

            with gr.Tab("Household Map", id="map"):
                map_html = gr.HTML("")
                app.load(household_map_view, outputs=map_html)

            with gr.Tab("Agent Trace", id="trace"):
                trace_table = gr.DataFrame(label="Agent Traces")
                with gr.Row():
                    trace_detail_btn = gr.Button("View Selected Detail")
                    first_trace = gr.State("")
                trace_detail = gr.HTML("")
                trace_detail_btn.click(agent_trace_detail, first_trace, trace_detail)
                app.load(agent_trace_view, outputs=[trace_table, first_trace])

            with gr.Tab("Field Notes", id="notes"):
                notes_html = gr.HTML("")
                app.load(field_notes_view, outputs=notes_html)

    return app


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    app = build_app()
    app.launch(server_port=args.port, share=args.share)
