from __future__ import annotations

import logging
import re
from html import escape

from shopstack.app_context import APP_NAME, db, planner, providers, tools
from shopstack.ui import card as ui_card
from shopstack.ui.components import render_decision_card
from shopstack.ui.components.primitives import empty_state_enhanced, item_row, toast
from shopstack.traces.export import create_trace
from shopstack.ui.screens._utils import (
    extract_query_for_action,
    normalize_item_name,
    safe_render,
)

logger = logging.getLogger(__name__)


@safe_render
def ask_shopstack(question: str) -> str:
    question = (question or "").strip()
    if not question:
        return empty_state_enhanced(
            "Ask ShopStack anything \u2014 e.g. \u201cDo we have milk?\u201d or \u201cWhat should I buy today?\u201d",
            icon="💬",
        )

    lowered = question.lower()

    if _is_add_command(lowered):
        response = _handle_add_command(question)
        _record_ask_trace(question, response, "ask_shopstack")
        return response

    if planner.available:
        try:
            response = planner.process(question)
            _record_ask_trace(question, response, "ai_planner")
            return _render_planner_response(response)
        except Exception as e:
            logger.warning("AI planner failed, falling back to heuristic: %s", e)

    response: str

    if any(k in lowered for k in ["do we have", "kya", "hai kya", "where is", "where's", "where"]):
        query = extract_query_for_action(question, "item")
        result = tools.find_item(query)
        results = result.get("results", [])
        lines = [
            f"<li>{r['lot'].get('canonical_name', '')} \xb7 {r['lot'].get('quantity', 0)} {r['lot'].get('unit', '')} @ {r.get('location_name', 'Unknown')}</li>"
            for r in results
        ]
        if lines:
            rows = "".join(
                item_row(
                    name=r["lot"].get("display_name", ""),
                    quantity=r["lot"].get("quantity", 0),
                    unit=r["lot"].get("unit", "unit"),
                    location=r.get("location_name", "Unknown"),
                )
                for r in results
            )
            response = ui_card("Location match", rows)
        else:
            response = empty_state_enhanced(f"We looked for {query} but found nothing. Add it to your next list if needed.", icon="🔍")

    elif any(keyword in lowered for keyword in ["skip", "what can i skip", "can i skip"]):
        lots = db.get_inventory()
        stock = [lot for lot in lots if lot.quantity > 0 and lot.status == "active"]
        if not stock:
            response = empty_state_enhanced("No obvious skip candidates right now.", icon="✅")
        else:
            ranked = sorted(stock, key=lambda lot: lot.quantity, reverse=True)[:8]
            rows = "".join(
                item_row(
                    name=lot.display_name,
                    quantity=lot.quantity,
                    unit=lot.unit,
                    status="active",
                    decision="skip",
                )
                for lot in ranked
            )
            if not rows:
                response = empty_state_enhanced("No obvious skip candidates right now.", icon="✅")
            else:
                response = ui_card("Likely skip today", rows)

    elif any(k in lowered for k in ["expiring", "expires", "use soon", "urgent"]):
        soon = tools.get_use_soon_items(days=7).get("items", [])
        if not soon:
            response = empty_state_enhanced("No urgent expiry items. You can hold steady today.", icon="🧊")
        else:
            rows = "".join(
                item_row(
                    name=item.get("display_name", item.get("canonical_name", "")),
                    quantity=item.get("quantity", 0),
                    unit=item.get("unit", "unit"),
                    status="active",
                    decision="use_soon",
                    extra=escape(str(item.get("reason", "Use soon"))),
                )
                for item in soon[:6]
            )
            response = ui_card("Use-Soon Items", rows)

    elif _is_add_command(lowered):
        response = _handle_add_command(question)

    elif "should i buy" in lowered or "what should i buy" in lowered or "what do i need" in lowered:
        suggestions = tools.get_next_buy_suggestions().get("suggestions", [])
        if not suggestions:
            response = empty_state_enhanced("No clear buy suggestions right now.", icon="🛍️")
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
            empty_state_enhanced(
                f"Question understood: {question}",
                icon="🤔",
                secondary_text="Try: \u201cDo we have milk?\u201d, \u201cWhat should I buy today?\u201d, or \u201cWhere is toothpaste?\u201d",
            ),
        )

    _record_ask_trace(question, response, "ask_shopstack")
    return response


def ask_shopstack_from_audio(audio_path: str | None) -> str:
    if not audio_path:
        return ask_shopstack("")
    try:
        transcript = providers.stt.transcribe(audio_path)
        if isinstance(transcript, dict):
            text = str(transcript.get("text", "")).strip()
        else:
            text = str(transcript).strip()
    except Exception as exc:
        return toast(f"Could not transcribe audio: {escape(str(exc))}", kind="error")

    if not text:
        return ask_shopstack("")
    if planner.available:
        try:
            response = planner.process(text)
            _record_ask_trace(text, response, "ai_planner")
            return _render_planner_response(response)
        except Exception as exc:
            logger.warning("AI planner failed for voice, falling back: %s", exc)

    return ask_shopstack(text)


def _record_ask_trace(question: str, response: str, mode: str) -> None:
    try:
        create_trace(
            db,
            input_type="text",
            user_goal="ask_shopstack",
            redacted_user_request=question,
            perception={"query": question},
            inventory_context={},
            decision={"response_type": mode},
            proposed_tool_calls=[{"tool_name": mode, "args": {"question": question}}],
            final_response=response,
            human_confirmation="responded",
        )
    except Exception as e:
        logger.debug("Failed to record ask trace: %s", e)


def _render_planner_response(response: str) -> str:
    response_text = response or ""
    rendered = response_text if response_text.lstrip().startswith("<") else escape(response_text)
    return ui_card(
        f"{APP_NAME} AI",
        rendered
        + "<div style='margin-top:8px;font-size:11px;color:var(--text-dim);'>"
        "Rendered through the same Ask ShopStack HTML boundary as heuristic answers.</div>",
    )


_ADD_PATTERNS = [
    re.compile(r"^\s*(?:add|added|put)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^\s*(?:i|we)\s+(?:bought|purchased|got)\s+(.+)$", re.IGNORECASE),
    re.compile(r"^\s*(?:bought|purchased)\s+(.+)$", re.IGNORECASE),
]

_QTY_UNIT_PATTERN = re.compile(
    r"^(\d+(?:\.\d+)?)\s*"
    r"(kg|g|l|ml|liter|litre|liters|litres|piece|pieces|pc|pcs|pack|packs|bar|bars|"
    r"bunch|bunches|tube|tubes|loaf|loaves|pack|packet|box)\s+"
    r"(.+)$",
    re.IGNORECASE,
)

_QTY_ONLY_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)\s+(.+)$")

_UNIT_MAP: dict[str, str] = {
    "kg": "kg", "g": "g", "l": "L", "liter": "L", "litre": "L", "liters": "L", "litres": "L",
    "ml": "mL", "piece": "pieces", "pieces": "pieces", "pc": "pieces", "pcs": "pieces",
    "pack": "pack", "packs": "pack", "packet": "pack",
    "bar": "bar", "bars": "bar", "bunch": "bunch", "bunches": "bunch",
    "tube": "tube", "tubes": "tube", "loaf": "loaf", "loaves": "loaf", "box": "box",
}

_DEFAULT_LOCATIONS: dict[str, str] = {
    "milk": "fridge", "curd": "fridge", "dahi": "fridge", "yogurt": "fridge",
    "cheese": "fridge", "butter": "fridge", "eggs": "fridge_top",
    "tomato": "fridge_drawer", "tomatoes": "fridge_drawer", "tamatar": "fridge_drawer",
    "coriander": "fridge_drawer", "dhania": "fridge_drawer", "cilantro": "fridge_drawer",
    "ginger": "fridge_drawer", "green chili": "fridge_drawer", "green chilies": "fridge_drawer",
    "bread": "fridge_top", "lemon": "fridge_drawer",
    "rice": "pantry_mid", "chawal": "pantry_mid",
    "wheat flour": "pantry_mid", "atta": "pantry_mid", "aata": "pantry_mid",
    "dal": "pantry_top", "toor dal": "pantry_top", "moong dal": "pantry_top",
    "lentils": "pantry_top",
    "onion": "pantry_mid", "pyaaz": "pantry_mid", "onions": "pantry_mid",
    "potato": "pantry_mid", "aloo": "pantry_mid", "potatoes": "pantry_mid",
    "garlic": "pantry",
    "oil": "pantry_mid", "cooking oil": "pantry_mid",
    "salt": "pantry_top", "sugar": "pantry_top", "tea": "pantry_top", "tea leaves": "pantry_top",
    "biscuit": "pantry", "biscuits": "pantry",
    "turmeric": "spice_box", "turmeric powder": "spice_box", "haldi": "spice_box",
    "chili powder": "spice_box", "red chili": "spice_box", "lal mirch": "spice_box",
    "garam masala": "spice_box",
    "mustard seeds": "spice_box", "rai": "spice_box",
    "cumin seeds": "spice_box", "jeera": "spice_box",
    "toothpaste": "bathroom_cabinet", "soap": "bathroom_cabinet", "shampoo": "bathroom_cabinet",
}


def _is_add_command(text: str) -> bool:
    for pat in _ADD_PATTERNS:
        if pat.match(text):
            return True
    return False


def _parse_add_payload(raw: str) -> tuple[str, float, str] | None:
    stripped = raw.strip().rstrip(".")
    for prefix in ("to inventory", "to home", "to pantry", "to fridge", "to kitchen"):
        if stripped.lower().endswith(prefix):
            stripped = stripped[: -len(prefix)].strip()
    m = _QTY_UNIT_PATTERN.match(stripped)
    if m:
        qty = float(m.group(1))
        unit_raw = m.group(2).lower()
        unit = _UNIT_MAP.get(unit_raw, unit_raw)
        name = normalize_item_name(m.group(3).strip())
        return name, qty, unit
    m = _QTY_ONLY_PATTERN.match(stripped)
    if m:
        qty = float(m.group(1))
        name = normalize_item_name(m.group(2).strip())
        return name, qty, "unit"
    name = normalize_item_name(stripped)
    if name:
        return name, 1.0, "unit"
    return None


def _handle_add_command(question: str) -> str:
    for pat in _ADD_PATTERNS:
        m = pat.match(question.strip())
        if m:
            raw_item = m.group(1)
            parsed = _parse_add_payload(raw_item)
            if not parsed:
                break
            name, qty, unit = parsed
            if not name:
                break
            location = _DEFAULT_LOCATIONS.get(name, "kitchen")
            result = tools.add_inventory_item(
                canonical_name=name,
                display_name=name.replace("_", " ").title(),
                quantity=qty,
                unit=unit,
                storage_location_id=location,
            )
            lot_id = result.get("lot_id", "")
            try:
                create_trace(
                    db,
                    input_type="voice",
                    user_goal="voice_add_item",
                    redacted_user_request=f"add {name}",
                    perception={"item": name, "quantity": qty, "unit": unit},
                    inventory_context={"location": location},
                    decision={"action": "add_inventory_item", "lot_id": lot_id},
                    proposed_tool_calls=[
                        {"tool_name": "add_inventory_item", "args": {"name": name, "quantity": qty}},
                    ],
                    final_response=f"Added {name} to inventory",
                    human_confirmation="auto-confirmed",
                )
            except Exception:
                logger.debug("Failed to record voice add trace", exc_info=True)
            return toast(
                f"Added {escape(name)} ({escape(str(qty))} {escape(unit)}) to inventory. Lot: {escape(lot_id[:12])}",
                kind="success",
            )
    return toast("Could not understand what to add. Try: 'add milk' or 'add 2 kg rice'", kind="warning")
