from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import gradio as gr

from shopstack.config import Settings
from shopstack.model_registry import get_registry
from shopstack.persistence.database import Database
from shopstack.providers.registry import ProviderRegistry
from shopstack.tools.registry import ToolRegistry
from shopstack.ui_support import build_price_memory_view, load_field_notes, save_field_notes
from shopstack.ui.components.cards import (
    card as ui_card,
    empty_state,
    render_decision_card,
    render_grouped_cards,
    render_metric,
)
from shopstack.traces.export import create_trace

settings = Settings()
db = Database(settings.db_path)
providers = ProviderRegistry(settings)
tools = ToolRegistry(db)
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
"""


def _list_to_table(items: list[dict[str, Any]], cols: list[str] | None = None) -> list[list[str]]:
    if not items:
        return [["No data"]]
    if cols is None:
        cols = list(items[0].keys())
    header = [c.replace("_", " ").title() for c in cols]
    rows = [[str(item.get(c, "")) for c in cols] for item in items]
    return [header] + rows


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


def normalize_item_name(name: str) -> str:
    normal = re.sub(r"[^\w\s]", " ", name.lower()).strip()
    for canonical, aliases in ITEM_ALIASES.items():
        if normal == canonical or normal in aliases:
            return canonical
    return normal


def _parse_shopping_text(items_text: str) -> list[str]:
    if not items_text:
        return []
    chunks = [t.strip() for t in re.split(r"[,;\n]", items_text) if t.strip()]
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
    quick_actions = (
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:12px 0 16px 0;'>"
        f"{render_metric('Active items', str(len(active_inv)))}"
        f"{render_metric('Use soon', str(soon_count))}"
        f"{render_metric('Low stock', str(len(low_items)))}"
        f"{render_metric('Recent purchases', str(len(purchases)))}"
        "</div>"
    )

    return [
        f"{hero}{quick_actions}",
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
    for lot in active_inv:
        if lot.status == "low" or lot.quantity <= 0.4:
            buy.append(f"Buy {lot.display_name}")
        if lot.quantity > 0.7 and lot.canonical_name not in use_soon_items:
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
        must_buy, optional, skipped = _classify_shopping_items(items)
        plan_note = _render_shopping_plan_html(must_buy, optional, skipped)
    else:
        plan_note = "<div style='color:var(--text-dim);'>Created an empty active list. Add more items anytime.</div>"
    result = tools.create_or_update_shopping_list(items=items, goal=goal)
    return (
        f"<div style='color:var(--green);'>Created list: {result.get('list', {}).get('list_id', '')} with {len(items)} items</div>"
        f"{plan_note}"
    )


def _classify_shopping_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    must_buy: list[dict[str, Any]] = []
    optional: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in items:
        name = item["canonical_name"]
        qty = float(item.get("requested_quantity", 1.0) or 1.0)
        unit = item.get("unit", "unit") or "unit"
        comparison = tools.compare_visible_item_to_inventory(name, qty, unit)
        decision = comparison.get("decision", "maybe")
        enriched = {
            "canonical_name": name.title(),
            "decision": decision,
            "reason": comparison.get("reason", ""),
            "confidence": 1.0,
            "requested_quantity": qty,
            "unit": unit,
        }
        if decision == "skip":
            skipped.append(enriched)
        elif decision == "optional":
            optional.append(enriched)
        else:
            must_buy.append(enriched)
    return must_buy, optional, skipped


def _render_shopping_plan_html(
    must_buy: list[dict[str, Any]], optional: list[dict[str, Any]], skipped: list[dict[str, Any]]
) -> str:
    return (
        "<div style='margin-top:12px;display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;'>"
        f"{render_grouped_cards('Must buy', must_buy)}"
        f"{render_grouped_cards('Optional', optional)}"
        f"{render_grouped_cards('Skip', skipped)}"
        "</div>"
    )


def ask_shopstack(question: str) -> str:
    question = (question or "").strip()
    if not question:
        return "<div style='color:var(--text-dim);'>Ask ShopStack anything — e.g. “Do we have milk?” or “What should I buy today?”</div>"

    lowered = question.lower()

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
            return ui_card("Location match", cards)
        return empty_state(f"We looked for <strong>{query}</strong> but found nothing. Add it to your next list if needed.")

    if any(k in lowered for k in ["expiring", "expires", "use soon", "use soon", "urgent", "skip"]):
        soon = tools.get_use_soon_items(days=7).get("items", [])
        if not soon:
            return empty_state("No urgent expiry items. You can hold steady today.")
        body = "".join(
            f"{render_decision_card(item.get('display_name', item.get('canonical_name', '')), 'use_soon', item.get('reason', 'Use soon'), 0.92, item.get('quantity'), item.get('unit', 'unit'), False)}"
            for item in soon[:6]
        )
        return ui_card("Use-Soon Items", body)

    if "should i buy" in lowered or "what should i buy" in lowered or "what do i need" in lowered:
        suggestions = tools.get_next_buy_suggestions().get("suggestions", [])
        if not suggestions:
            return empty_state("No clear buy suggestions right now.")
        items = [
            {
                "canonical_name": s.get("canonical_name", ""),
                "reason": s.get("reason", ""),
                "decision": "buy",
                "confidence": 0.91,
            }
            for s in suggestions[:8]
        ]
        return ui_card("Today’s shopping suggestions", "".join(
            render_decision_card(i["canonical_name"], i["decision"], i["reason"], i["confidence"], None, show_actions=False)
            for i in items
        ))

    return ui_card(
        "Quick answer",
        f"{empty_state(f'Question understood: {question}')}"
        "<div style='margin-top:8px;color:var(--text-dim);'>Try: “Do we have milk?”, “What should I buy today?”, or “Where is toothpaste?”</div>",
    )


def _market_lens_process(image_path: str | None, audio_path: str | None) -> tuple:
    result_html = "<div style='color:var(--text-dim);'>No input provided.</div>"
    items_found = []
    analysis = ""

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
        else:
            result_html += f"<div style='margin-top:8px;color:var(--text-dim);'>Spoken note processed for context.</div>"

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
                "reason": f"Last seen: {lot.storage_location_id or 'Unknown'}",
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


def price_memory_view(item_name: str = ""):
    view = build_price_memory_view(db, item_name)
    return view.summary_html, view.df, view.table


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
    tbl = _list_to_table(
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
    traces = db.get_traces(limit=100)
    for t in traces:
        if t.trace_id == trace_id:
            return f"<pre style='font-size:12px;overflow:auto;max-height:400px;background:var(--bg-input);padding:12px;border-radius:var(--radius-sm);'>{json.dumps(t.model_dump(), indent=2, default=str)}</pre>"
    return "<div style='color:var(--text-dim);'>Trace not found.</div>"


def field_notes_view():
    view = load_field_notes(db)
    return view.editor_value, view.preview_value, view.status_html


def field_notes_save(note_text: str):
    view = save_field_notes(db, note_text)
    return view.editor_value, view.preview_value, view.status_html


def build_app() -> gr.Blocks:
    with gr.Blocks(title="ShopStack") as app:
        gr.HTML("""
<div style="display:flex;justify-content:space-between;align-items:center;padding:16px 0;border-bottom:1px solid var(--border);margin-bottom:20px;">
  <div>
    <h1 style="font-size:22px;margin:0;">ShopStack</h1>
    <div style="font-size:12px;color:var(--text-dim);">Your home’s shopping memory.</div>
  </div>
  <div style="text-align:right;font-size:11px;color:var(--text-dim);">
    <div>v0.1.0</div>
  </div>
</div>""", padding=True)

        with gr.Tabs(elem_classes="tabs") as tabs:
            with gr.Tab("Today", id="today"):
                today_stats = gr.HTML("")
                today_soon = gr.HTML("")
                today_list = gr.HTML("")
                today_low = gr.HTML("")
                today_recent = gr.HTML("")
                app.load(today_dashboard, outputs=[today_stats, today_soon, today_list, today_low, today_recent])

            with gr.Tab("Ask ShopStack", id="ask"):
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
                sl_display = gr.HTML("")
                sl_plan = gr.HTML("")
                sl_table = gr.DataFrame(label="Items")
                sl_list_id = gr.State("")
                sl_goal = gr.State("")
                with gr.Row():
                    goal_input = gr.Textbox(label="List Goal (e.g. Weekly Groceries)", placeholder="What's this list for?")
                    items_input = gr.Textbox(
                        label="Shopping list",
                        placeholder='milk, bread, tomato (natural)  |  [{"canonical_name":"milk","requested_quantity":2}]',
                        lines=3,
                    )
                with gr.Row():
                    create_btn = gr.Button("Build Shopping Plan")
                    refresh_btn = gr.Button("Refresh", elem_classes="secondary")
                create_output = gr.HTML("")
                create_btn.click(shopping_list_create, [goal_input, items_input], [create_output, sl_plan])
                sl_plan = gr.HTML("", visible=True)
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
                    cons_lot = gr.Textbox(label="Lot ID (full or first 8 chars)", placeholder="abcdef123456")
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
                price_summary = gr.HTML("")
                price_plot = gr.LinePlot(
                    label="Price Trend",
                    x="date",
                    y="price",
                    title="Price trend over time",
                    x_title="Date",
                    y_title="Price (₹)",
                    height=300,
                )
                price_table = gr.DataFrame(label="Price History")
                price_search.click(price_memory_view, price_item, [price_summary, price_plot, price_table])
                app.load(price_memory_view, inputs=price_item, outputs=[price_summary, price_plot, price_table])

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
