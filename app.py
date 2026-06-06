from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from datetime import date
from html import escape
from typing import Any

import gradio as gr

logger = logging.getLogger(__name__)
import pandas as pd

from shopstack.config import settings
from shopstack.scanner import decode_barcode, infer_product_from_code
from shopstack.planner.engine import PlannerEngine
from shopstack.portability import export_json, export_csv_inventory, import_json, import_csv
from shopstack.model_registry import (
    MAX_ACTIVE_MODEL_PARAMS_B,
    get_active,
    get_registry,
    total_candidate_params,
    total_loaded_params,
    validate_active_model_budget,
)
from shopstack.persistence.database import Database
from shopstack.providers.registry import ProviderRegistry
from shopstack.tools.registry import ToolRegistry
from shopstack.ui import (
    build_price_memory_view,
    badge_html,
    card as ui_card,
    empty_state,
    list_to_table,
    load_field_notes,
    render_decision_card,
    render_grouped_cards,
    render_metric,
    render_workflow_rail,
    save_field_notes,
)
from shopstack.traces.export import (
    create_trace,
    export_trace_by_id,
    trace_payload_for_export,
)

db = Database(settings.db_path)
providers = ProviderRegistry(settings)
tools = ToolRegistry(db)
planner = PlannerEngine(db, tools, providers)
model_registry = get_registry()

CSS = """
:root {
  --bg: #FFF8ED;
  --bg-card: #FFFFFF;
  --bg-warm: #FFF3DA;
  --bg-input: #FFF3DA;
  --border: #E8DCCB;
  --text: #201A14;
  --text-dim: #75685A;
  --accent: #6D5BD0;
  --accent-hover: #5c4bc5;
  --green: #1F8A5B;
  --red: #C94A3A;
  --amber: #D98A1F;
  --blue: #3F6FB5;
  --radius: 20px; --radius-sm: 12px;
}
.gradio-container { background: var(--bg) !important; color: var(--text) !important; font-family: Inter, ui-sans-serif, system-ui, sans-serif; max-width: 1280px !important; margin: 0 auto; }
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
label, .gr-form-label { color: var(--text) !important; font-size: 13px !important; font-weight: 500 !important; letter-spacing: 0.2px !important; }
.gr-dataframe { background: var(--bg-card) !important; border: 1px solid var(--border) !important; border-radius: var(--radius) !important; }
.gr-dataframe table { font-size: 13px !important; }
.gr-dataframe th { background: var(--bg-input) !important; color: var(--text-dim) !important; border-bottom: 1px solid var(--border) !important; padding: 10px 12px !important; }
.gr-dataframe td { border-bottom: 1px solid var(--border) !important; padding: 8px 12px !important; color: var(--text) !important; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 100px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.3px; }
.badge-green { background: rgba(31,138,91,0.12); color: var(--green); }
.badge-red { background: rgba(201,74,58,0.12); color: var(--red); }
.badge-amber { background: rgba(217,138,31,0.12); color: var(--amber); }
.badge-blue { background: rgba(63,111,181,0.12); color: var(--blue); }
.badge-gray { background: rgba(117,104,90,0.12); color: var(--text-dim); }
.home-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; box-shadow: 0 6px 20px rgba(80, 50, 20, 0.06); }
.stat-card { background: var(--bg-warm); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; text-align: center; }
.stat-value { font-size: 34px; font-weight: 700; color: var(--text); line-height: 1; }
.metric-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; text-align: left; }
.stat-label { font-size: 12px; color: var(--text-dim); margin-top: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
.action-row { display: flex; gap: 8px; flex-wrap: wrap; }
.item-row { display: flex; justify-content: space-between; gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--border); align-items: center; }
.item-card { margin-bottom: 10px; }
.chip { display: inline-block; border: 1px solid var(--border); border-radius: 999px; padding: 5px 10px; font-size: 11px; background: #fff; color: var(--text); }
@media (max-width: 768px) {
  .gradio-container { max-width: 100% !important; padding: 0 8px !important; }
  .tab-nav button { font-size: 11px !important; padding: 6px 8px !important; white-space: nowrap; }
  .gr-box, .home-card, .stat-card { border-radius: 12px !important; padding: 12px !important; }
  .gr-text-input, .gr-number-input, input, textarea, select { font-size: 16px !important; }
  .gr-button { padding: 10px 16px !important; font-size: 14px !important; min-height: 44px; }
  .gr-dataframe { font-size: 11px !important; overflow-x: auto !important; display: block !important; }
  .gr-dataframe table { min-width: 600px; }
  .gr-dataframe th, .gr-dataframe td { padding: 6px 8px !important; white-space: nowrap; }
  .stat-value { font-size: 24px !important; }
  div[style*="display:grid"] { grid-template-columns: 1fr !important; }
  .action-row { flex-direction: column !important; }
  .item-row { flex-direction: column !important; align-items: flex-start !important; gap: 4px !important; }
}
@media (max-width: 480px) {
  .tab-nav { display: flex !important; flex-wrap: wrap !important; gap: 2px !important; }
  .tab-nav button { flex: 1 0 auto !important; min-width: 0 !important; padding: 6px 6px !important; font-size: 10px !important; }
  .gr-button { width: 100% !important; }
}
"""



ITEM_ALIASES: dict[str, list[str]] = {
    "tomato": ["tamatar", "tomatoes"],
    "coriander": ["dhania", "cilantro"],
    "curd": ["dahi", "yogurt"],
    "wheat flour": ["atta", "aata"],
    "rice": ["chawal"],
    "lentils": ["dal", "daal"],
    "onion": ["pyaaz", "pyaz"],
    "potato": ["aloo", "alu"],
}


WORKFLOW_STEPS = (
    "Input",
    "Perception/Parsing",
    "Inventory Context",
    "Decision",
    "Proposed Actions",
    "Human Confirmation",
    "Saved Trace",
)
WORKFLOW_ACTION_STEPS = (
    "Input",
    "Perception",
    "Inventory Context",
    "Decision",
    "Proposed Actions",
    "Human Confirmation",
    "Saved Trace",
)
WORKFLOW_NAV = (
    "Plan Today’s Shopping",
    "Market Lens: Should I Buy This?",
    "Add Purchase to Home Memory",
    "Use Soon / Waste Saver",
    "Find an Item at Home",
    "Price Memory Check",
    "Export Redacted Trace",
)


def _workflow_header(steps: tuple[str, ...]) -> str:
    return render_workflow_rail(list(steps), current_step=4)


def _workflow_title_bar(title: str, subtitle: str = "") -> str:
    return (
        "<div class='home-card' style='margin-bottom:10px;'>"
        f"<h2>{escape(title)}</h2>"
        + (f"<div style='color:var(--text-dim);'>{escape(subtitle)}</div>" if subtitle else "")
        + "</div>"
    )


def _safe_trace_id(trace_id: str) -> str:
    return trace_id.strip().split()[0]


def _find_trace_by_id(trace_id: str):
    if not trace_id:
        traces = db.get_traces(limit=1)
        return traces[0] if traces else None
    target = _safe_trace_id(trace_id)
    for trace in db.get_traces(limit=100):
        if trace.trace_id == target:
            return trace
    return None


def _trace_timeline_html(trace) -> str:
    if not trace:
        return "<div style='color:var(--text-dim);'>No workflow trace selected yet.</div>"
    steps = [
        ("Input", trace.input_type or "unknown"),
        ("Perception", trace.redacted_user_request or str(trace.perception or {})),
        (
            "Inventory Context",
            (str(trace.inventory_context) if trace.inventory_context else "Using live household state"),
        ),
        ("Decision", str(trace.decision) if trace.decision else "Decision not stored"),
        ("Proposed Actions", f"{len(trace.proposed_tool_calls or [])} tool calls suggested"),
        (
            "Human Confirmation",
            trace.human_confirmation or "No confirmation recorded yet",
        ),
        ("Saved Trace", "Yes" if trace.trace_id else "No"),
    ]
    rows = "".join(
        f"<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);'>"
        f"<strong>{label}</strong><span>{escape(str(value))}</span></div>"
        for label, value in steps
    )
    return (
        "<div class='home-card' style='text-align:left;'>"
        "<h3>Workflow evidence timeline</h3>"
        f"{rows}"
        "</div>"
    )


def _format_trace_selector_label(trace) -> str:
    goal = (trace.user_goal or "").strip() or "workflow run"
    return f"{goal[:40]} · {trace.input_type} · {trace.timestamp.strftime('%m-%d %H:%M') if trace.timestamp else 'no time'}"


def agent_trace_choices() -> tuple[list[tuple[str, str]], str]:
    traces = db.get_traces(limit=50)
    if not traces:
        return [("No traces yet", "")], ""
    choices = [(f"{_format_trace_selector_label(t)} | {t.trace_id[:12]}", t.trace_id) for t in traces]
    default = traces[0].trace_id
    return choices, default


def _trace_bundle(trace_id: str) -> tuple[str, str]:
    trace = _find_trace_by_id(trace_id)
    if not trace:
        no_trace = "<div style='color:var(--text-dim);'>No workflow trace selected yet.</div>"
        return no_trace, no_trace
    timeline_html = _trace_timeline_html(trace)
    raw_json = json.dumps(trace_payload_for_export(trace), indent=2, default=str)
    return timeline_html, f"<pre style='font-size:12px;overflow:auto;max-height:400px;background:var(--bg-input);padding:12px;border-radius:var(--radius-sm);'>{raw_json}</pre>"


def agent_trace_bootstrap() -> tuple[list[tuple[str, str]], str, str, str]:
    traces = db.get_traces(limit=50)
    if not traces:
        no_data = "<div style='color:var(--text-dim);'>No workflow traces recorded yet.</div>"
        return [("No traces yet", "")], "", no_data, no_data
    first = traces[0]
    timeline, raw = _trace_bundle(first.trace_id)
    choices = [(f"{_format_trace_selector_label(t)} | {t.trace_id[:12]}", t.trace_id) for t in traces]
    return choices, first.trace_id, timeline, raw


def agent_trace_export_file(trace_id: str) -> str:
    trace = _find_trace_by_id(trace_id)
    if not trace:
        return ""
    fd, out_path = tempfile.mkstemp(suffix=".jsonl")
    try:
        wrote = export_trace_by_id(db, trace.trace_id, out_path, redact=True)
    finally:
        pass
    if not wrote:
        return ""
    return out_path


def _record_workflow_trace(
    input_type: str,
    user_goal: str,
    redacted_user_request: str,
    perception: dict[str, Any],
    inventory_context: dict[str, Any],
    decision: dict[str, Any],
    proposed_tool_calls: list[dict[str, Any]],
    final_response: str,
    human_confirmation: str | None = None,
) -> None:
    try:
        create_trace(
            db,
            input_type=input_type,
            user_goal=user_goal,
            redacted_user_request=redacted_user_request,
            perception=perception,
            inventory_context=inventory_context,
            decision=decision,
            proposed_tool_calls=proposed_tool_calls,
            human_confirmation=human_confirmation,
            final_response=final_response,
        )
    except Exception:
        pass


def _rows_to_html(rows: list[dict[str, Any]], headers: list[str]) -> str:
    if not rows:
        return "<div style='color:var(--text-dim);'>No entries.</div>"

    head_html = "".join(
        f"<th style='text-align:left;border-bottom:1px solid var(--border);padding:6px 8px;'>{header}</th>"
        for header in headers
    )
    body_html = ""
    for row in rows:
        body_html += (
            "<tr>"
            + "".join(
                f"<td style='border-bottom:1px solid var(--border);padding:6px 8px'>{row.get(col, '')}</td>"
                for col in headers
            )
            + "</tr>"
        )
    return (
        "<table style='border-collapse:collapse;width:100%;font-size:12px;'>"
        f"<tr>{head_html}</tr>"
        f"{body_html}"
        "</table>"
    )


def _candidate_model_rows() -> list[dict[str, Any]]:
    return [
        {
            "Provider Group": model.provider_group,
            "Model": model.model_id,
            "Runtime": model.runtime,
            "Params (B)": f"{model.params_b:.2f}",
            "License": model.license_note,
            "Status": model.status,
        }
        for model in get_registry()
        if model.status == "candidate"
    ]


def _active_model_rows() -> list[dict[str, Any]]:
    active = [m for m in get_registry() if m.status == "active"]
    if active:
        return [
            {
                "Provider Group": model.provider_group,
                "Model": model.model_id,
                "Runtime": model.runtime,
                "Params (B)": f"{model.params_b:.2f}",
                "License": model.license_note,
                "Status": model.status,
            }
            for model in active
        ]

    return [
        {
            "Provider Group": "runtime",
            "Model": "Mock providers",
            "Runtime": "mock",
            "Params (B)": "0.00",
            "License": "N/A",
            "Status": "active",
        }
    ]


def model_budget_view() -> str:
    try:
        validate_active_model_budget()
        budget_ok = True
        budget_message = "Active runtime stack is within the 32B cap."
    except ValueError as exc:
        budget_ok = False
        budget_message = str(exc)

    active_rows = _active_model_rows()
    candidate_rows = _candidate_model_rows()
    if not candidate_rows:
        candidate_html = "<div style='color:var(--text-dim);'>No candidate entries yet.</div>"
    else:
        candidate_html = _rows_to_html(
            candidate_rows,
            ["Provider Group", "Model", "Runtime", "Params (B)", "License", "Status"],
        )

    status_badge = badge_html("Under budget", "green") if budget_ok else badge_html("Over budget", "red")
    return (
        f"{_workflow_header(WORKFLOW_STEPS)}"
        + "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:12px 0;'>"
        f"{render_metric('Active / Loaded', f'{total_loaded_params():.2f} B')}"
        f"{render_metric('Candidate Pool', f'{total_candidate_params():.2f} B')}"
        f"{render_metric('Max Budget', f'{MAX_ACTIVE_MODEL_PARAMS_B:.2f} B')}"
        "</div>"
        + ui_card(
            "Selected Runtime Stack",
            f"<div style='margin-bottom:8px;display:flex;gap:8px;align-items:center;'>{status_badge}"
            f"<span style='font-size:12px;color:var(--text-dim);'>{budget_message}</span></div>"
            + _rows_to_html(
                active_rows,
                ["Provider Group", "Model", "Runtime", "Params (B)", "License", "Status"],
            ),
        )
        + ui_card("Candidate Models", candidate_html)
    )


def normalize_item_name(name: str) -> str:
    normal = re.sub(r"[^\w\s]", " ", name.lower()).strip()
    for canonical, aliases in ITEM_ALIASES.items():
        if normal == canonical or normal in aliases:
            return canonical
    return normal


def _parse_shopping_text(items_text: str) -> list[str]:
    if not items_text:
        return []
    normalized = re.sub(r"\b(and|&)\b", ",", items_text.lower(), flags=re.IGNORECASE)
    chunks = [t.strip() for t in re.split(r"[,;\n]", normalized) if t.strip()]
    parsed: list[str] = []
    for chunk in chunks:
        candidate = chunk.strip()
        m = re.match(r"^\s*([a-z].*?)\s+\d", candidate)
        if m:
            candidate = m.group(1)
        if candidate:
            parsed.append(normalize_item_name(candidate))
    return parsed


def _extract_query_for_action(question: str, keyword: str) -> str:
    q = question.lower()
    for stop in ("do we have", "kya", "hai", "kharidna", "should i buy", "what about", "where is", "where's", "where are", "kahan hai", "kahan"):
        q = q.replace(stop, " ")
    q = re.sub(r"\b(what|should|do|need|today|today's|for|can|you|tell|me)\b", " ", q)
    q = re.sub(r"[^\w\s]", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    if not q and keyword:
        return keyword
    return q or keyword


def _shopping_list_items_from_text(goal: str, raw: str) -> tuple[list[dict[str, Any]], str]:
    raw = (raw or "").strip()
    parsed = _parse_shopping_text(raw)
    if parsed:
        items = []
        for item in parsed:
            if not item:
                continue
            items.append({
                "canonical_name": item,
                "requested_quantity": 1.0,
                "unit": "unit",
                "priority": "must_buy",
            })
        return items, raw

    if raw:
        # If this is not parseable as a list, treat it as a goal phrase and use
        # suggestions from next-buy intelligence.
        suggestions = tools.get_next_buy_suggestions().get("suggestions", [])
        fallback_items = []
        for s in suggestions[:5]:
            fallback_items.append({
                "canonical_name": s["canonical_name"],
                "requested_quantity": s.get("suggested_quantity", 1),
                "unit": "unit",
                "priority": s.get("priority", "optional"),
                "reason": s.get("reason", ""),
            })
        if fallback_items:
            return fallback_items, f"Suggested from home memory: {goal}"

    return [], "No clear items were detected. Share a rough list like `milk, bread, tomato`."


def today_dashboard():
    use_soon = tools.get_use_soon_items(days=3)
    soon_count = use_soon["count"]
    active_list = db.get_active_shopping_list()
    all_inv = db.get_inventory()
    active_inv = [l for l in all_inv if l.status == "active"]
    low_items = [l for l in active_inv if l.quantity <= 0.5 or l.status == "low"]
    purchases = db.get_purchase_events(limit=5)

    hero = (
        "<div class='home-card' style='margin-bottom:10px;'>"
        "<h2>Good day. What should your home remember today?</h2>"
        "<div style='color:var(--text-dim);'>Use what you've got, buy what you need, and skip what you already have.</div>"
        "</div>"
    )
    workflow_preview = (
        "<div class='home-card' style='text-align:left;margin-bottom:12px;'>"
        "<div style='font-size:12px;text-transform:uppercase;letter-spacing:0.4px;color:var(--text-dim);margin-bottom:8px;'>"
        "Workflow previews</div>"
        + "".join(
            f"<div style='padding:7px 0;border-bottom:1px solid var(--border);'><strong>{name}</strong> <span style='color:var(--text-dim);'>— task-first household workflow</span></div>"
            for name in WORKFLOW_NAV
        )
        + "</div>"
    )
    quick_actions = (
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:12px 0 16px 0;'>"
        f"{render_metric('Active items', str(len(active_inv)))}"
        f"{render_metric('Use soon', str(soon_count))}"
        f"{render_metric('Low stock', str(len(low_items)))}"
        f"{render_metric('Recent purchases', str(len(purchases)))}"
        "</div>"
    )

    return [
        f"{hero}{workflow_preview}{quick_actions}",
        _render_home_advice(active_inv, low_items, use_soon["items"][:3]),
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


def _render_home_advice(active_inv: list, low_items: list, use_soon_items: list[dict[str, Any]]) -> str:
    buy = []
    skip = []
    use_soon_names = {item.get("canonical_name", "") for item in use_soon_items}
    for lot in active_inv:
        if lot.status == "low" or lot.quantity <= 0.4:
            buy.append(f"Buy {lot.display_name}")
        if lot.quantity > 0.7 and lot.canonical_name not in use_soon_names:
            skip.append(f"You already have {lot.display_name}")
    for item in use_soon_items[:2]:
        buy.append(f"Use {item.get('display_name', item.get('canonical_name', ''))} before buying more")
    if not buy and not skip:
        return ui_card("Today's note", "Your pantry looks healthy. No immediate action needed.")
    body = ""
    if buy:
        body += "<div style='margin-bottom:10px;'><strong>Buy</strong><ul>" + "".join(
            f"<li>{line}</li>" for line in buy[:3]
        ) + "</ul></div>"
    if skip:
        body += "<div><strong>Skip</strong><ul>" + "".join(
            f"<li>{line}</li>" for line in skip[:3]
        ) + "</ul></div>"
    return ui_card("Today’s Shopping Advice", body)


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
    goal_html, tbl, list_id, list_goal, _cards, _share = _shopping_list_payload()
    return goal_html, gr.DataFrame(value=tbl, headers=tbl[0] if tbl else []), list_id, list_goal


def shopping_list_create(goal: str, items_json: str) -> str:
    if not items_json:
        items = []
        plan_note = "No items specified yet."
    else:
        try:
            parsed_json = json.loads(items_json)
            if isinstance(parsed_json, list):
                items = parsed_json
                plan_note = None
            elif isinstance(parsed_json, dict):
                items = [parsed_json]
                plan_note = None
            else:
                return "<div style='color:var(--red);'>Input must be a list (or one item).</div>"
        except json.JSONDecodeError:
            stripped = items_json.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                return "<div style='color:var(--red);'>Invalid JSON input.</div>"
            items, plan_note = _shopping_list_items_from_text(goal, items_json)
            if not items:
                return f"<div style='color:var(--amber);'>{plan_note}</div>"
        except TypeError:
            return "<div style='color:var(--red);'>Unable to parse input.</div>"

    if not items:
        items = []
    for item in items:
        if not item.get("canonical_name"):
            item["canonical_name"] = normalize_item_name(str(item.get("name", "")))
            item["canonical_name"] = item["canonical_name"] or "unknown"
    items = [
        {
            "canonical_name": normalize_item_name(item.get("canonical_name") or item.get("item", "")),
            "requested_quantity": item.get("requested_quantity") or 1.0,
            "unit": item.get("unit", "unit"),
            "priority": item.get("priority", "must_buy"),
            "reason": item.get("reason", ""),
        }
        for item in items if isinstance(item, dict)
    ]
    if items:
        must_buy, optional, skipped, use_soon = _classify_shopping_items(items)
        plan_note = _render_shopping_plan_html(must_buy, optional, skipped, use_soon)
        _record_workflow_trace(
            input_type="text",
            user_goal=(goal or "").strip() or "Plan shopping list",
            redacted_user_request=goal or "",
            perception={"goal": goal or "", "items_text": items_json},
            inventory_context={
                "must_buy": len(must_buy),
                "optional": len(optional),
                "skip": len(skipped),
                "use_soon": len(use_soon),
            },
            decision={"workflow": "plan_shopping", "items": [i["canonical_name"] for i in items]},
            proposed_tool_calls=[
                {
                    "tool_name": "create_or_update_shopping_list",
                    "args": {"goal": goal or "", "items": items},
                    "confirmed": True,
                }
            ],
            final_response=plan_note,
            human_confirmation="auto-summarized",
        )
    else:
        plan_note = "<div style='color:var(--text-dim);'>Created an empty active list. Add more items anytime.</div>"
    result = tools.create_or_update_shopping_list(items=items, goal=goal)
    return (
        f"<div style='color:var(--green);'>Created list: {result.get('list', {}).get('list_id', '')} with {len(items)} items</div>"
        f"{plan_note}"
    )


def _classify_shopping_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    must_buy: list[dict[str, Any]] = []
    optional: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    use_soon: list[dict[str, Any]] = []
    for item in items:
        name = item["canonical_name"]
        try:
            qty = float(item.get("requested_quantity", 1.0) or 1.0)
        except (TypeError, ValueError):
            qty = 1.0
        unit = item.get("unit", "unit") or "unit"
        comparison = tools.compare_visible_item_to_inventory(name, qty, unit)
        decision = comparison.get("decision", "maybe")
        if comparison.get("is_use_soon", False) and decision != "skip":
            decision = "use_soon"
        enriched = {
            "canonical_name": name.title(),
            "decision": decision,
            "smart_decision": decision,
            "reason": comparison.get("reason", ""),
            "confidence": 1.0,
            "requested_quantity": qty,
            "unit": unit,
        }
        if decision == "skip":
            enriched["priority"] = "avoid_buying"
            skipped.append(enriched)
        elif decision == "use_soon":
            enriched["priority"] = "must_buy"
            use_soon.append(enriched)
        elif decision == "optional":
            enriched["priority"] = "optional"
            optional.append(enriched)
        else:
            enriched["priority"] = "must_buy"
            must_buy.append(enriched)
        item["reason"] = enriched["reason"]
        item["priority"] = enriched["priority"]
        item["smart_decision"] = enriched["smart_decision"]
    return must_buy, optional, skipped, use_soon


def _render_shopping_plan_html(
    must_buy: list[dict[str, Any]], optional: list[dict[str, Any]], skipped: list[dict[str, Any]], use_soon: list[dict[str, Any]]
) -> str:
    return (
        "<div style='margin-top:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;'>"
        f"{render_grouped_cards('Must buy', must_buy)}"
        f"{render_grouped_cards('Optional', optional)}"
        f"{render_grouped_cards('Use Soon', use_soon)}"
        f"{render_grouped_cards('Skip', skipped)}"
        "</div>"
    )


def _shopping_list_share_text(items: list[dict[str, Any]]) -> str:
    if not items:
        return "ShopStack list for today\nNo items in list."
    must_buy: list[str] = []
    optional: list[str] = []
    skipped: list[str] = []
    use_soon: list[str] = []
    for item in items:
        decision = item.get("smart_decision") or item.get("priority") or "must_buy"
        name = item.get("canonical_name", "")
        qty = item.get("requested_quantity")
        unit = item.get("unit", "unit") or "unit"
        reason = (item.get("reason") or "").strip()
        suffix = f" — {qty} {unit}"
        if reason:
            suffix += f" ({reason})"
        if decision == "skip":
            skipped.append(f"• {name}{suffix}")
        elif decision == "optional":
            optional.append(f"• {name}{suffix}")
        elif decision == "use_soon":
            use_soon.append(f"• {name}{suffix}")
        else:
            must_buy.append(f"• {name}{suffix}")

    sections: list[str] = ["ShopStack list for today"]
    if must_buy:
        sections.append("\nMust Buy:\n" + "\n".join(must_buy))
    if optional:
        sections.append("\nOptional:\n" + "\n".join(optional))
    if skipped:
        sections.append("\nSkip:\n" + "\n".join(skipped))
    if use_soon:
        sections.append("\nUse Soon:\n" + "\n".join(use_soon))
    return "\n".join(sections)


def _shopping_list_payload() -> tuple[str, list[list[str]], str, str, str, str]:
    sl = db.get_active_shopping_list()
    if not sl:
        return (
            "<div class='stat-card' style='text-align:left;margin-bottom:12px;'><h3>Shopping List</h3><div style='color:var(--text-dim);'>No active shopping list. Create one with your goal or rough text.</div></div>",
            [["No items"]],
            "",
            "",
            "",
            _shopping_list_share_text([]),
        )

    rows = [
        {
            "canonical_name": lot.canonical_name,
            "requested_quantity": lot.requested_quantity or 1.0,
            "unit": lot.unit or "unit",
            "priority": lot.priority,
            "reason": lot.reason or "",
        }
        for lot in (sl.items or [])
    ]
    _classify_shopping_items(rows)
    must_buy = [i for i in rows if i.get("priority") == "must_buy"]
    optional = [i for i in rows if i.get("priority") == "optional"]
    skipped = [i for i in rows if i.get("priority") == "avoid_buying"]
    use_soon = [i for i in rows if i.get("smart_decision") == "use_soon"]

    cards = _render_shopping_plan_html(must_buy, optional, skipped, use_soon)

    table_rows = [
        {
            "item": item.get("canonical_name", ""),
            "qty": item.get("requested_quantity", 1.0),
            "unit": item.get("unit", "unit"),
            "priority": item.get("priority", "optional"),
            "status": "saved",
            "reason": item.get("reason", ""),
        }
        for item in rows
    ]
    tbl = list_to_table(
        table_rows,
        ["item", "qty", "unit", "priority", "status", "reason"],
    )
    goal_html = f"<div style='margin-bottom:12px;'><strong>Goal:</strong> {sl.goal}</div>" if sl.goal else ""
    share_text = _shopping_list_share_text(rows)
    return goal_html, tbl, sl.list_id, sl.goal or "", cards, share_text


def _shopping_list_view_with_cards() -> tuple[str, str, list[list[str]], str, str, str]:
    goal_html, tbl, list_id, list_goal, cards, share = _shopping_list_payload()
    empty_cards = "<div style='color:var(--text-dim);'>No items classified for display yet.</div>"
    card_wrap = "<div class='home-card' style='text-align:left;'>" + "<h3>Shopping List</h3>" + (cards or empty_cards) + "</div>"
    return card_wrap, goal_html, tbl, list_id, list_goal, share


def _build_shopping_list_and_refresh(
    goal: str, items_text: str
) -> tuple[str, str, str, list[list[str]], str, str, str]:
    create_result = shopping_list_create(goal, items_text)
    cards, goal_html, tbl, list_id, list_goal, share = _shopping_list_view_with_cards()
    return create_result, cards, goal_html, tbl, list_id, list_goal, share


def ask_shopstack(question: str) -> str:
    question = (question or "").strip()
    if not question:
        return "<div style='color:var(--text-dim);'>Ask ShopStack anything — e.g. “Do we have milk?” or “What should I buy today?”</div>"

    # Use AI planner when a real provider is available
    if planner.available:
        try:
            response = planner.process(question)
            _record_workflow_trace(
                input_type="text",
                user_goal="ask_shopstack",
                redacted_user_request=question,
                perception={"query": question, "mode": "ai_planner"},
                inventory_context={},
                decision={"response_type": "planner"},
                proposed_tool_calls=[{"tool_name": "planner", "args": {"question": question}}],
                final_response=response,
                human_confirmation="responded",
            )
            return response
        except Exception as e:
            logger.warning("AI planner failed, falling back to heuristic: %s", e)

    lowered = question.lower()
    response: str

    if any(k in lowered for k in ["do we have", "kya", "hai kya", "where is", "where's", "where"]):
        query = _extract_query_for_action(question, "item")
        result = tools.find_item(query)
        results = result.get("results", [])
        lines = [
            f"<li>{r['lot'].get('canonical_name', '')} · {r['lot'].get('quantity', 0)} {r['lot'].get('unit', '')} @ {r.get('location_name', 'Unknown')}</li>"
            for r in results
        ]
        if lines:
            cards = "".join(render_decision_card(r["lot"].get("display_name", ""), "buy", "Found in inventory", 1.0, r["lot"].get("quantity"), r["lot"].get("unit")) for r in results)
            response = ui_card("Location match", cards)
        else:
            response = empty_state(f"We looked for <strong>{query}</strong> but found nothing. Add it to your next list if needed.")

    elif any(keyword in lowered for keyword in ["skip", "what can i skip", "can i skip"]):
        lots = db.get_inventory()
        stock = [lot for lot in lots if lot.quantity > 0 and lot.status == "active"]
        if not stock:
            response = empty_state("No obvious skip candidates right now.")
        else:
            ranked = sorted(stock, key=lambda lot: lot.quantity, reverse=True)[:8]
            cards = "".join(
                render_decision_card(
                    lot.display_name,
                    "skip",
                    f"You already have {lot.quantity} {lot.unit}.",
                    0.85,
                    lot.quantity,
                    lot.unit,
                    False,
                )
                for lot in ranked
            )
            if not cards:
                response = empty_state("No obvious skip candidates right now.")
            else:
                response = ui_card("Likely skip today", cards)

    elif any(k in lowered for k in ["expiring", "expires", "use soon", "urgent"]):
        soon = tools.get_use_soon_items(days=7).get("items", [])
        if not soon:
            response = empty_state("No urgent expiry items. You can hold steady today.")
        else:
            body = "".join(
                f"{render_decision_card(item.get('display_name', item.get('canonical_name', '')), 'use_soon', item.get('reason', 'Use soon'), 0.92, item.get('quantity'), item.get('unit', 'unit'), False)}"
                for item in soon[:6]
            )
            response = ui_card("Use-Soon Items", body)

    elif "should i buy" in lowered or "what should i buy" in lowered or "what do i need" in lowered:
        suggestions = tools.get_next_buy_suggestions().get("suggestions", [])
        if not suggestions:
            response = empty_state("No clear buy suggestions right now.")
        else:
            items = [
                {
                    "canonical_name": s.get("canonical_name", ""),
                    "reason": s.get("reason", ""),
                    "decision": "buy",
                    "confidence": 0.91,
                }
                for s in suggestions[:8]
            ]
            response = ui_card("Today's shopping suggestions", "".join(
                render_decision_card(i["canonical_name"], i["decision"], i["reason"], i["confidence"], None, show_actions=False)
                for i in items
            ))

    else:
        response = ui_card(
            "Quick answer",
            f"{empty_state(f'Question understood: {question}')}"
            "<div style='margin-top:8px;color:var(--text-dim);'>Try: “Do we have milk?”, “What should I buy today?”, or “Where is toothpaste?”</div>",
        )

    _record_workflow_trace(
        input_type="text",
        user_goal="ask_shopstack",
        redacted_user_request=question,
        perception={"query": question},
        inventory_context={"matched_text": lowered},
        decision={"response_type": "ask_shopstack"},
        proposed_tool_calls=[{"tool_name": "ask_shopstack", "args": {"question": question}}],
        final_response=response,
        human_confirmation="responded",
    )
    return response


def market_lens_barcode(image_path: str | None) -> str:
    if not image_path:
        return "<div style='color:var(--text-dim);'>Upload or capture an image with a barcode first.</div>"
    codes = decode_barcode(image_path)
    if not codes:
        return (
            "<div class='stat-card'>"
            "<div style='font-weight:600;'>No barcode detected</div>"
            "<div style='font-size:12px;color:var(--text-dim);'>Try a clearer image or enter the product name manually.</div>"
            "</div>"
        )
    parts = []
    for code in codes:
        info = infer_product_from_code(code["data"])
        parts.append(
            f"<div class='stat-card' style='margin-bottom:8px;'>"
            f"<div style='font-weight:600;'>{escape(info['label'])}</div>"
            f"<div style='font-size:11px;color:var(--text-dim);'>Type: {code['type']} | Code: {escape(code['data'])}</div>"
            f"<div style='margin-top:6px;display:flex;gap:6px;'>"
            f"<button class='gr-button lg primary' onclick=\"alert('Barcode: {escape(code['data'])}')\">Add to Inventory</button>"
            f"</div>"
            f"</div>"
        )
    return "".join(parts)


def market_lens_process(image_path: str | None, audio_path: str | None) -> tuple:
    result_html = "<div style='color:var(--text-dim);'>No input provided.</div>"
    items_found = []
    analysis = ""
    trace_decisions: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []
    final_text = ""

    if image_path:
        detections = providers.object_detection.detect(image_path)
        ocr_result = providers.ocr.extract(image_path)
        if isinstance(ocr_result, dict):
            raw_product = ocr_result.get("product_name", "")
        else:
            raw_product = ""
        decisions: list[dict[str, Any]] = []
        for d in detections[:8]:
            item_name = normalize_item_name(str(d.get("label", "")))
            comparison = tools.compare_visible_item_to_inventory(item_name, d.get("quantity", 1.0), "unit")
            decisions.append(
                {
                    "canonical_name": item_name.title(),
                    "decision": comparison.get("decision", "maybe"),
                    "reason": comparison.get("reason", ""),
                    "confidence": float(d.get("confidence", 0.0)),
                    "unit": "unit",
                    "quantity": d.get("quantity", 1.0),
                    "suggested_quantity": max(0.0, d.get("quantity", 1.0)),
                    "source": raw_product,
                }
            )
            items_found.append(item_name.title())
        trace_decisions.extend(decisions)

        buys = [d for d in decisions if d["decision"] == "buy"]
        skips = [d for d in decisions if d["decision"] == "skip"]
        maybes = [d for d in decisions if d["decision"] in ("optional", "maybe")]
        analysis = (
            "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;'>"
            f"{render_grouped_cards('BUY', buys)}"
            f"{render_grouped_cards('SKIP', skips)}"
            f"{render_grouped_cards('MAYBE', maybes)}"
            "</div>"
        )
        result_html = (
            "<div class='home-card'>"
            f"<h3>Market Lens</h3>{analysis}"
            "</div>"
            "<div style='margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;'>"
            "<span class='chip'>Confirm selected BUY</span>"
            "<span class='chip'>Skip selected</span>"
            "<span class='chip'>Save trace</span>"
            "</div>"
        )
        analysis = json.dumps({"items": decisions}, indent=2)
        tool_calls.append(
            {
                "tool_name": "compare_visible_item_to_inventory",
                "args": {"items": [d.get("canonical_name", "") for d in decisions]},
            }
        )

    if audio_path:
        transcript = providers.stt.transcribe(audio_path)
        if isinstance(transcript, dict):
            transcript_text = transcript.get("text", "")
        else:
            transcript_text = str(transcript)
        result_html += f"<div style='margin-top:12px;'><strong>Heard:</strong> {transcript_text}</div>"
        if not image_path and transcript_text:
            result_html = ask_shopstack(transcript_text)
            analysis = json.dumps({"audio_query": transcript_text}, indent=2)
            tool_calls.append(
                {
                    "tool_name": "ask_shopstack",
                    "args": {"question": transcript_text},
                }
            )
            trace_decisions.append({"canonical_name": "", "decision": "text_query", "reason": transcript_text})
        else:
            result_html += f"<div style='margin-top:8px;color:var(--text-dim);'>Spoken note processed for context.</div>"
            tool_calls.append(
                {
                    "tool_name": "stt.transcribe",
                    "args": {"audio_path": audio_path or ""},
                }
            )

    if image_path or audio_path:
        final_text = result_html
        _record_workflow_trace(
            input_type="vision" if image_path else "audio",
            user_goal="market_lens",
            redacted_user_request=analysis,
            perception={"items_detected": items_found, "audio": bool(audio_path), "image": bool(image_path)},
            inventory_context={"decision_count": len(trace_decisions)},
            decision={"steps": WORKFLOW_STEPS, "items": trace_decisions[:6]},
            proposed_tool_calls=tool_calls,
            final_response=final_text,
            human_confirmation="uncommitted",
        )
    return result_html, str(items_found), analysis


def add_purchase_form(
    name: str, qty: float, unit: str, price: float, store: str, location: str, purchase_date_str: str, category: str
) -> str:
    if qty < 0:
        return "<div style='color:var(--red);'>Quantity must be 0 or more.</div>"
    if price < 0:
        return "<div style='color:var(--red);'>Price must be 0 or more.</div>"
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
    result = f"<div style='color:var(--green);'>Added {name} (lot {lot_id})</div>"
    _record_workflow_trace(
        input_type="form",
        user_goal="add_purchase",
        redacted_user_request=f"add purchase: {name}",
        perception={"item": name, "quantity": qty, "unit": unit, "store": store},
        inventory_context={"storage_location": location, "category": category},
        decision={"action": "add_inventory_item", "lot_id": lot_id},
        proposed_tool_calls=[
            {"tool_name": "add_inventory_item", "args": {"name": name, "quantity": qty, "unit": unit}},
            {"tool_name": "record_price_observation", "args": {"price": price, "store": store}},
        ],
        final_response=result,
        human_confirmation="confirmed-by-user",
    )
    return result


def inventory_view(search: str = "") -> list[list[str]]:
    items = db.get_inventory()
    if search:
        q = search.lower()
        items = [l for l in items if q in l.canonical_name.lower() or q in l.display_name.lower()]
    tbl = list_to_table(
        [
            {
                "name": l.display_name,
                "qty": l.quantity,
                "unit": l.unit,
                "location": db.get_location(l.storage_location_id).name if l.storage_location_id and db.get_location(l.storage_location_id) else l.storage_location_id,
                "status": l.status,
                "purchased": l.purchase_date.isoformat() if l.purchase_date else "",
                "expires": (l.label_expiry_date or l.estimated_use_by_date or "").isoformat() if (l.label_expiry_date or l.estimated_use_by_date) else "",
                "lot_id": l.lot_id,
            }
            for l in items
        ],
        ["name", "qty", "unit", "location", "status", "purchased", "expires", "lot_id"],
    )
    return tbl


def inventory_cards_view(search: str = "") -> str:
    items = db.get_inventory()
    if search:
        q = search.lower()
        items = [l for l in items if q in l.canonical_name.lower() or q in l.display_name.lower()]
    locations = {loc.location_id: loc.name for loc in db.get_locations()}
    if not items:
        return empty_state("Your inventory is empty. Add one item in Add Purchase to start.")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for lot in items:
        loc = locations.get(lot.storage_location_id, lot.storage_location_id or "Unknown")
        grouped.setdefault(loc, []).append(
            {
                "name": lot.display_name,
                "qty": lot.quantity,
                "unit": lot.unit,
                "status": lot.status,
                "reason": f"Added {lot.purchase_date.isoformat() if lot.purchase_date else 'today'}",
                "expiry": (lot.label_expiry_date.isoformat() if lot.label_expiry_date else ""),
            }
        )

    cards = ""
    for loc_name, lots in grouped.items():
        body = "<div style='margin-bottom:8px;'>"
        for lot in lots:
            body += "<div class='item-row'>"
            body += f"<div><strong>{lot['name']}</strong><div style='font-size:11px;color:var(--text-dim)'>{lot['reason']}</div></div>"
            body += f"<div style='text-align:right'>{lot['qty']} {lot['unit']}</div>"
            body += "</div>"
        body += "</div>"
        cards += (
            "<div class='home-card' style='margin-bottom:10px;'>"
            f"<h4>{loc_name}</h4>{body}</div>"
        )
    return cards


def consume_item(lot_id: str, qty: float) -> str:
    result = tools.consume_inventory_item(lot_id, qty)
    if "error" in result:
        return f"<div style='color:var(--red);'>Error: {result['error']}</div>"
    return f"<div style='color:var(--green);'>Consumed {qty}. Remaining: {result.get('remaining', 0)}</div>"


def use_soon_view(days: int = 3) -> list[list[str]]:
    data = tools.get_use_soon_items(days=days)
    items = data.get("items", [])
    tbl = list_to_table(
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
    for l in inventory:
        lid = l.storage_location_id or "unknown"
        loc_counts[lid] = loc_counts.get(lid, 0) + 1

    cards = ""
    for loc in locations:
        count = loc_counts.get(loc.location_id, 0)
        parent = loc.parent_location_id or ""
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
    tbl = list_to_table(
        [
            {
                "trace_id": t.trace_id[:12],
                "type": t.input_type,
                "time": t.timestamp.strftime("%Y-%m-%d %H:%M") if t.timestamp else "",
                "goal": (t.user_goal or "")[:40],
                "tool_calls": len(t.proposed_tool_calls or []),
            }
            for t in traces
        ],
        ["trace_id", "type", "time", "goal", "tool_calls"],
    )
    return tbl, traces[0].trace_id if traces else ""


def agent_trace_detail(trace_id: str) -> str:
    trace = _find_trace_by_id(trace_id)
    if not trace:
        return "<div style='color:var(--text-dim);'>Trace not found.</div>"
    timeline = _trace_timeline_html(trace)
    raw = json.dumps(trace_payload_for_export(trace), indent=2, default=str)
    return timeline + (
        "<div class='home-card' style='text-align:left;margin-top:12px;'>"
        "<h3>Redacted trace payload</h3>"
        f"<pre style='font-size:12px;overflow:auto;max-height:400px;background:var(--bg-input);padding:12px;border-radius:var(--radius-sm);'>{raw}</pre>"
        "</div>"
    )


def field_notes_view():
    view = load_field_notes(db)
    return view.editor_value, view.preview_value, view.status_html


def field_notes_save(note_text: str):
    view = save_field_notes(db, note_text)
    return view.editor_value, view.preview_value, view.status_html


def export_data_json() -> str:
    data = export_json(db)
    tmp = os.path.join(tempfile.mkdtemp(), "shopstack_export.json")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return tmp


def export_data_csv() -> str:
    tmp = os.path.join(tempfile.mkdtemp(), "shopstack_inventory.csv")
    csv_text = export_csv_inventory(db)
    with open(tmp, "w") as f:
        f.write(csv_text)
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


def provider_status_badge() -> str:
    all_mock = all(
        getattr(providers.get(name), "available", True) or name == "tool_call_parser"
        for name in ("stt", "tts", "vision", "object_detection", "ocr", "planner", "embeddings")
    )
    status = "Mock" if all_mock else "AI"
    cls = "badge-amber" if all_mock else "badge-green"
    types = providers.list_providers()
    caps = sorted({c for p in types for c in p.get("capabilities", "").split(", ") if c})
    title = f"Backend: {', '.join(caps) if caps else 'mock'}"
    return f'<span class="badge {cls}" title="{title}">{status}</span>'


def build_app() -> gr.Blocks:
    with gr.Blocks(title="ShopStack") as app:
        provider_badge = gr.HTML(provider_status_badge(), visible=False)
        gr.HTML(f"""
<div style="display:flex;justify-content:space-between;align-items:center;padding:16px 0;border-bottom:1px solid var(--border);margin-bottom:20px;">
  <div>
    <h1 style="font-size:22px;margin:0;">ShopStack</h1>
    <div style="font-size:12px;color:var(--text-dim);">Your home's shopping memory.</div>
  </div>
    <div style="text-align:right;font-size:11px;color:var(--text-dim);">
      <div>v0.1.0</div>
      <div id="provider-badge">{provider_status_badge()}</div>
    </div>
  </div>""", padding=True)

        with gr.Tabs(elem_classes="tabs") as tabs:
            with gr.Tab("Plan Today's Shopping", id="today"):
                gr.HTML(_workflow_header(WORKFLOW_STEPS))
                today_stats = gr.HTML("")
                today_soon = gr.HTML("")
                today_list = gr.HTML("")
                today_low = gr.HTML("")
                today_recent = gr.HTML("")
                app.load(today_dashboard, outputs=[today_stats, today_soon, today_list, today_low, today_recent])

            with gr.Tab("Ask ShopStack", id="ask"):
                gr.HTML(_workflow_header(WORKFLOW_STEPS))
                ask_input = gr.Textbox(
                    label="Ask ShopStack",
                    placeholder="Do we have milk?  |  What should I buy today?  |  Where is toothpaste?",
                    lines=2,
                )
                ask_btn = gr.Button("Ask")
                ask_output = gr.HTML("")
                ask_btn.click(ask_shopstack, ask_input, ask_output)
                ask_input.submit(ask_shopstack, ask_input, ask_output)

            with gr.Tab("Shopping List", id="shopping"):
                gr.HTML(_workflow_header(WORKFLOW_STEPS))
                sl_cards = gr.HTML("")
                sl_display = gr.HTML("")
                sl_table = gr.DataFrame(label="Items")
                sl_list_id = gr.State("")
                sl_goal = gr.State("")
                with gr.Row():
                    goal_input = gr.Textbox(label="List Goal (e.g. Weekly Groceries)", placeholder="What's this list for?")
                    items_input = gr.Textbox(
                        label="Shopping list",
                        placeholder='milk, bread, tomato, onion  (or JSON for power users)',
                        lines=3,
                    )
                sl_share = gr.Textbox(
                    label="Copy for WhatsApp",
                    lines=8,
                    interactive=False,
                )
                with gr.Row():
                    create_btn = gr.Button("Build Shopping Plan")
                    refresh_btn = gr.Button("Refresh", elem_classes="secondary")
                create_output = gr.HTML("")
                create_btn.click(
                    _build_shopping_list_and_refresh,
                    [goal_input, items_input],
                    [create_output, sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share],
                )
                refresh_btn.click(_shopping_list_view_with_cards, outputs=[sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share])
                app.load(_shopping_list_view_with_cards, outputs=[sl_cards, sl_display, sl_table, sl_list_id, sl_goal, sl_share])

            with gr.Tab("Market Lens: Should I Buy This?", id="market"):
                gr.HTML(_workflow_header(WORKFLOW_STEPS))
                gr.Markdown("### Point your camera or upload a photo — or speak what you see")
                with gr.Row():
                    image_input = gr.Image(type="filepath", label="Camera / Photo")
                    audio_input = gr.Audio(type="filepath", label="Voice Note")
                with gr.Row():
                    scan_btn = gr.Button("Scan & Compare to Inventory", variant="primary")
                    barcode_btn = gr.Button("Detect Barcode")
                ml_results = gr.HTML("")
                ml_barcode = gr.HTML("")
                ml_items = gr.Textbox(label="Detected Items", visible=False)
                ml_analysis = gr.Textbox(visible=False)
                scan_btn.click(market_lens_process, [image_input, audio_input], [ml_results, ml_items, ml_analysis])
                barcode_btn.click(market_lens_barcode, image_input, ml_barcode)
                app.load(lambda: "", outputs=ml_barcode)

            with gr.Tab("Add Purchase", id="purchase"):
                gr.HTML(_workflow_header(WORKFLOW_STEPS))
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

            with gr.Tab("Find Item at Home", id="inventory"):
                gr.HTML(_workflow_header(WORKFLOW_STEPS))
                with gr.Row():
                    inv_search = gr.Textbox(label="Search Inventory", placeholder="Type to filter...")
                    inv_refresh = gr.Button("Refresh", elem_classes="secondary")
                inv_table = gr.DataFrame(label="All Inventory Items")
                with gr.Row():
                    cons_lot = gr.Textbox(label="Lot ID (full or prefix)", placeholder="abcdef123456")
                    cons_qty = gr.Number(label="Quantity to Consume", value=1.0)
                    cons_btn = gr.Button("Consume")
                cons_result = gr.HTML("")
                inv_cards = gr.HTML("")
                inv_search.change(inventory_view, inv_search, inv_table)
                inv_search.change(inventory_cards_view, inv_search, inv_cards)
                inv_refresh.click(inventory_view, outputs=inv_table)
                inv_refresh.click(inventory_cards_view, outputs=inv_cards)
                cons_btn.click(consume_item, [cons_lot, cons_qty], cons_result)
                app.load(inventory_view, outputs=inv_table)
                app.load(inventory_cards_view, outputs=inv_cards)

            with gr.Tab("Use Soon / Waste Saver", id="usesoon"):
                gr.HTML(_workflow_header(WORKFLOW_STEPS))
                with gr.Row():
                    use_days = gr.Slider(1, 30, value=3, step=1, label="Days threshold")
                    use_refresh = gr.Button("Refresh", elem_classes="secondary")
                use_table = gr.DataFrame(label="Items to Use Soon")
                use_refresh.click(use_soon_view, use_days, use_table)
                app.load(use_soon_view, inputs=use_days, outputs=use_table)

            with gr.Tab("Price Memory Check", id="prices"):
                gr.HTML(_workflow_header(WORKFLOW_STEPS))
                with gr.Row():
                    price_item = gr.Textbox(label="Item Name", placeholder="e.g. basmati rice")
                    price_search = gr.Button("Search")
                price_summary = gr.HTML("")
                with gr.Row():
                    price_plot = gr.LinePlot(
                        label="Price Trend",
                        x="date",
                        y="price",
                        title="Price over time",
                        x_title="Date",
                        y_title="Price (₹)",
                        height=300,
                    )
                    unit_price_plot = gr.LinePlot(
                        label="Unit Price Trend",
                        x="date",
                        y="unit_price",
                        title="Unit price over time",
                        x_title="Date",
                        y_title="Unit Price (₹)",
                        height=300,
                    )
                price_table = gr.DataFrame(label="Price History")
                price_search.click(price_memory_view, price_item, [price_summary, price_plot, unit_price_plot, price_table])
                app.load(price_memory_view, inputs=price_item, outputs=[price_summary, price_plot, unit_price_plot, price_table])

            with gr.Tab("Find Item Location", id="map"):
                gr.HTML(_workflow_header(WORKFLOW_STEPS))
                map_html = gr.HTML("")
                app.load(household_map_view, outputs=map_html)

            with gr.Tab("Model Stack", id="modelstack"):
                model_stack_html = gr.HTML("")
                app.load(model_budget_view, outputs=model_stack_html)

            with gr.Tab("Export Redacted Trace", id="trace"):
                gr.HTML(_workflow_title_bar(
                    "Export Redacted Trace",
                    "Pick a workflow run, inspect the timeline, then download a redacted trace artifact.",
                ))
                gr.HTML(_workflow_header(WORKFLOW_STEPS))
                trace_table = gr.DataFrame(label="Recent Traces")
                with gr.Row():
                    trace_selector = gr.Dropdown(label="Select a trace", choices=[], allow_custom_value=False)
                    trace_refresh = gr.Button("Refresh Trace Views", elem_classes="secondary")
                trace_timeline = gr.HTML("")
                trace_raw = gr.HTML("")
                with gr.Row():
                    trace_export = gr.Button("Export trace JSONL")
                    trace_file = gr.File(file_count="single", visible=True, label="Download redacted JSONL")
                trace_bootstrap_state = gr.State("")

                trace_selector.change(_trace_bundle, trace_selector, [trace_timeline, trace_raw])
                trace_refresh.click(
                    agent_trace_bootstrap,
                    outputs=[trace_selector, trace_timeline, trace_raw, trace_bootstrap_state],
                )
                trace_export.click(agent_trace_export_file, trace_selector, trace_file)
                app.load(lambda: agent_trace_view()[0], outputs=trace_table)
                app.load(agent_trace_bootstrap, outputs=[trace_selector, trace_timeline, trace_raw, trace_bootstrap_state])

            with gr.Tab("Export / Import", id="portability"):
                gr.HTML(_workflow_header(WORKFLOW_STEPS))
                with gr.Tab("Export"):
                    export_json_btn = gr.Button("Export Inventory as JSON")
                    export_csv_btn = gr.Button("Export Inventory as CSV")
                    export_file = gr.File(label="Download", visible=False)
                    export_json_btn.click(export_data_json, outputs=export_file)
                    export_csv_btn.click(export_data_csv, outputs=export_file)
                with gr.Tab("Import"):
                    import_file = gr.File(label="Upload JSON or CSV", file_count="single")
                    import_btn = gr.Button("Import Data")
                    import_result = gr.HTML("")
                    import_btn.click(import_data_file, import_file, import_result)

            with gr.Tab("Field Notes", id="notes"):
                gr.HTML(_workflow_header(WORKFLOW_STEPS))
                gr.Markdown("### Field Notes")
                gr.Markdown("Use this area to capture the story behind the build, the failures, and what changed after real testing.")
                notes_editor = gr.Textbox(label="Editable Draft", lines=16, placeholder="# Field Notes\n\nWrite what we learned...")
                notes_preview = gr.Markdown()
                notes_status = gr.HTML("")
                with gr.Row():
                    notes_reload = gr.Button("Reload Draft", elem_classes="secondary")
                    notes_save = gr.Button("Save Notes")
                notes_reload.click(field_notes_view, outputs=[notes_editor, notes_preview, notes_status])
                notes_save.click(field_notes_save, notes_editor, outputs=[notes_editor, notes_preview, notes_status])
                notes_editor.change(lambda text: text, notes_editor, notes_preview)
                app.load(field_notes_view, outputs=[notes_editor, notes_preview, notes_status])

    return app


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--share", action="store_true")
    args = parser.parse_args()

    app = build_app()
    app.launch(server_port=args.port, share=args.share, theme=gr.themes.Base(), css=CSS)
