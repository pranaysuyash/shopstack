from __future__ import annotations

import json
import logging
from html import escape
from datetime import date
from typing import Any
from urllib.parse import quote

from shopstack.app_context import db, tools
from shopstack.ui import list_to_table
from shopstack.ui.components import render_grouped_cards
from shopstack.traces.export import create_trace
from shopstack.ui.screens._utils import (
    WORKFLOW_STEPS,
    normalize_item_name,
    parse_shopping_text,
)

logger = logging.getLogger(__name__)

_ITEM_ALIASES_LOCAL: dict[str, list[str]] = {
    "tomato": ["tamatar", "tomatoes"],
    "coriander": ["dhania", "cilantro"],
    "curd": ["dahi", "yogurt"],
    "wheat flour": ["atta", "aata"],
    "rice": ["chawal"],
    "lentils": ["dal", "daal"],
    "onion": ["pyaaz", "pyaz"],
    "potato": ["aloo", "alu"],
}


def shopping_list_view():
    goal_html, tbl, list_id, list_goal, _cards, _share = _shopping_list_payload()
    return goal_html, tbl, list_id, list_goal


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
            items, plan_note = _parse_shopping_items_from_text(goal, items_json)
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
        _record_shopping_trace(goal, items_json, items, must_buy, optional, skipped, use_soon, plan_note)
    else:
        plan_note = "<div style='color:var(--text-dim);'>Created an empty active list. Add more items anytime.</div>"
    result = tools.create_or_update_shopping_list(items=items, goal=goal)
    safe_list_id = escape(str(result.get("list", {}).get("list_id", "")))
    return (
        f"<div style='color:var(--green);'>Created list: {safe_list_id} with {len(items)} items</div>"
        f"{plan_note}"
    )


def _parse_shopping_items_from_text(goal: str, raw: str) -> tuple[list[dict[str, Any]], str]:
    raw = (raw or "").strip()
    parsed = parse_shopping_text(raw)
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


def _classify_shopping_items(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    must_buy: list[dict[str, Any]] = []
    optional: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    use_soon: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        name = item["canonical_name"]
        normalized = normalize_item_name(name)
        if normalized in seen:
            continue
        seen.add(normalized)
        try:
            qty = float(item.get("requested_quantity", 1.0) or 1.0)
        except (TypeError, ValueError):
            qty = 1.0
        unit = item.get("unit", "unit") or "unit"
        comparison = tools.compare_visible_item_to_inventory(name, qty, unit)
        decision = comparison.get("decision", "maybe")
        total_have = comparison.get("total_quantity_at_home", 0)
        if comparison.get("is_use_soon", False) and decision != "skip":
            decision = "use_soon"
        if decision == "skip":
            conf = min(0.95, 0.82 + (total_have / (qty * 4)) * 0.13) if total_have > 0 else 0.82
        elif decision == "use_soon":
            conf = 0.85
        elif decision == "optional":
            conf = 0.72
        elif total_have > 0:
            conf = 0.62
        else:
            conf = 0.52
        enriched = {
            "canonical_name": normalized.title(),
            "decision": decision,
            "smart_decision": decision,
            "reason": comparison.get("reason", ""),
            "confidence": round(conf, 2),
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


def _record_shopping_trace(
    goal: str | None,
    items_json: str,
    items: list[dict[str, Any]],
    must_buy: list[dict[str, Any]],
    optional: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    use_soon: list[dict[str, Any]],
    plan_note: str,
) -> None:
    try:
        create_trace(
            db,
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
    except Exception as exc:
        logger.debug("Failed to record shopping trace: %s", exc)


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
        suffix = f" \u2014 {qty} {unit}"
        if reason:
            suffix += f" ({reason})"
        if decision == "skip":
            skipped.append(f"\u2022 {name}{suffix}")
        elif decision == "optional":
            optional.append(f"\u2022 {name}{suffix}")
        elif decision == "use_soon":
            use_soon.append(f"\u2022 {name}{suffix}")
        else:
            must_buy.append(f"\u2022 {name}{suffix}")

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


def _shopping_list_share_html(share_text: str) -> str:
    safe_text = escape(share_text)
    encoded = quote(share_text)
    whatsapp_url = f"https://wa.me/?text={encoded}"
    share_link = f"https://shopstack.local/share/list?text={encoded}"
    return (
        "<div style='margin-top:8px;'>"
        "<strong>Copy for WhatsApp</strong>"
        "<div style='display:flex;gap:8px;margin-top:6px;'>"
        "<textarea readonly rows='6' id='sl-share-text' "
        "style='flex:1;background:var(--bg-input);border:1px solid var(--border);"
        "border-radius:var(--radius-sm);padding:8px;font-size:12px;color:var(--text);"
        "resize:none;'"
        f">{safe_text}</textarea>"
        "</div>"
        "<button onclick=\"var t=document.getElementById('sl-share-text');"
        "t.select();navigator.clipboard.writeText(t.value);"
        "this.textContent='Copied!';setTimeout(function(){this.textContent='Copy'}.bind(this),1500);"
        "\" class='gr-button' style='margin-top:6px;font-size:12px;'>Copy</button>"
        f"<a class='gr-button' style='margin-top:6px;display:inline-block;text-decoration:none;' href='{whatsapp_url}' target='_blank'>Open WhatsApp</a>"
        f"<a class='gr-button' style='margin-top:6px;display:inline-block;text-decoration:none;' href='{share_link}' target='_blank'>Shareable Link</a>"
        "</div>"
    )


def _shopping_list_payload() -> tuple[str, list[list[str]], str, str, str, str]:
    sl = db.get_active_shopping_list()
    if not sl:
        return (
            "<div class='stat-card' style='text-align:left;margin-bottom:12px;'><h3>Shopping List</h3><div style='color:var(--text-dim);'>No active shopping list. Create one with your goal or rough text.</div></div>",
            [["No items"]],
            "",
            "",
            "",
            _shopping_list_share_html(_shopping_list_share_text([])),
        )

    rows = [
        {
            "list_item_id": lot.list_item_id,
            "canonical_name": lot.canonical_name,
            "requested_quantity": lot.requested_quantity or 1.0,
            "unit": lot.unit or "unit",
            "priority": lot.priority,
            "reason": lot.reason or "",
        }
        for lot in (sl.items or [])
        if lot.status != "bought" and lot.status != "skipped"
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
    goal_html = f"<div style='margin-bottom:12px;'><strong>Goal:</strong> {escape(str(sl.goal))}</div>" if sl.goal else ""
    share_text = _shopping_list_share_text(rows)
    share_html = _shopping_list_share_html(share_text)
    return goal_html, tbl, sl.list_id, sl.goal or "", cards, share_html


def _shopping_list_view_with_cards() -> tuple[str, str, list[list[str]], str, str, str]:
    goal_html, tbl, list_id, list_goal, cards, share = _shopping_list_payload()
    empty_cards = "<div style='color:var(--text-dim);'>No items classified for display yet.</div>"
    card_wrap = "<div class='home-card' style='text-align:left;'>" + "<h3>Shopping List</h3>" + (cards or empty_cards) + "</div>"
    return card_wrap, goal_html, tbl, list_id, list_goal, share


def shopping_list_item_choices() -> list[list[str]]:
    sl = db.get_active_shopping_list()
    if not sl or not sl.items:
        return [["No items"]]
    items = [i for i in sl.items if i.status != "bought" and i.status != "skipped"]
    if not items:
        return [["All items purchased"]]
    return [[i.canonical_name, str(i.requested_quantity or 1.0), i.unit or "unit", i.list_item_id] for i in items]


def mark_items_purchased(item_ids_json: str) -> str:
    if not item_ids_json or item_ids_json == "[]":
        return "<div style='color:var(--text-dim);'>No items selected.</div>"
    try:
        selected = json.loads(item_ids_json)
    except (json.JSONDecodeError, TypeError):
        return "<div style='color:var(--red);'>Could not parse selection.</div>"
    if not selected:
        return "<div style='color:var(--text-dim);'>No items selected.</div>"

    sl = db.get_active_shopping_list()
    if not sl or not sl.items:
        return "<div style='color:var(--text-dim);'>No active shopping list.</div>"

    added = []
    matched_ids = set(selected)
    for item in sl.items:
        if item.list_item_id in matched_ids:
            qty = item.requested_quantity or 1.0
            result = tools.add_inventory_item(
                canonical_name=item.canonical_name.lower().strip(),
                display_name=item.canonical_name.strip(),
                quantity=qty,
                unit=item.unit or "unit",
                storage_location_id="kitchen",
            )
            lot_id = result.get("lot_id", "")
            db.update_list_item(item.list_item_id, {"status": "bought"})
            added.append(f"{item.canonical_name} (lot {lot_id[:8]})")

    if not added:
        return "<div style='color:var(--text-dim);'>No valid items found to mark as purchased.</div>"
    return f"<div style='color:var(--green);'>Marked {len(added)} item(s) as purchased and added to inventory: {', '.join(escape(a) for a in added)}</div>"


def complete_shopping_list(list_id: str) -> str:
    if not list_id:
        return "<div style='color:var(--text-dim);'>No active shopping list to complete.</div>"
    sl = db.get_active_shopping_list()
    if not sl or sl.list_id != list_id:
        return "<div style='color:var(--text-dim);'>Active list not found or already completed.</div>"
    items = sl.items or []
    if not items:
        db.mark_list_complete(list_id)
        return "<div style='color:var(--green);'>Empty list marked complete.</div>"

    added = []
    for item in items:
        priority = item.priority or "optional"
        if priority == "avoid_buying":
            continue
        qty = item.requested_quantity or 1.0
        if priority == "optional":
            qty = max(qty * 0.5, 0.5)
        result = tools.add_inventory_item(
            canonical_name=item.canonical_name.lower().strip(),
            display_name=item.canonical_name.strip(),
            quantity=qty,
            unit=item.unit or "unit",
            storage_location_id="kitchen",
        )
        lot_id = result.get("lot_id", "")
        added.append(f"{item.canonical_name} (lot {lot_id[:8]})")

    db.mark_list_complete(list_id)
    try:
        create_trace(
            db,
            input_type="form",
            user_goal="complete_shopping_list",
            redacted_user_request=f"completed list: {sl.goal or ''}",
            perception={"goal": sl.goal or "", "item_count": len(items), "added_count": len(added)},
            inventory_context={"added_items": added},
            decision={"action": "mark_list_complete"},
            proposed_tool_calls=[],
            final_response=f"Completed list with {len(added)} items added to inventory",
            human_confirmation="auto-confirmed",
        )
    except Exception as exc:
        logger.debug("Failed to record complete list trace: %s", exc)
    summary = ", ".join(added)
    return (
        f"<div style='color:var(--green);'>List completed! Added {len(added)} items to inventory: {escape(summary)}</div>"
    )


def _build_shopping_list_and_refresh(
    goal: str, items_text: str
) -> tuple[str, str, str, list[list[str]], str, str, str]:
    create_result = shopping_list_create(goal, items_text)
    cards, goal_html, tbl, list_id, list_goal, share = _shopping_list_view_with_cards()
    return create_result, cards, goal_html, tbl, list_id, list_goal, share
