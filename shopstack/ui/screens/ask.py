from __future__ import annotations

import logging
import json
import re
from html import escape
from typing import Any

from shopstack.app_context import APP_NAME, db, planner, providers, tools
from shopstack.ui.components.cards import card as ui_card
from shopstack.ui.components.primitives import toast
from shopstack.traces.export import create_trace
from shopstack.ui.screens._utils import (
    extract_query_for_action,
    normalize_item_name,
)

logger = logging.getLogger(__name__)


def ask_shopstack(question: str) -> dict[str, Any]:
    question = (question or "").strip()
    if not question:
        return {
            "intent": "empty",
            "message": "Ask ShopStack anything \u2014 e.g. 'Do we have milk?' or 'What should I buy today?'"
        }

    lowered = question.lower()

    if _is_add_command(lowered):
        response = _handle_add_command(question)
        _record_ask_trace(
            question,
            response,
            "ask_shopstack",
            proposed_tool_calls=[{"tool_name": "add_inventory_item", "args": {"text": question}}],
        )
        return response

    if planner.available:
        try:
            response = planner.process_structured(question)
            _record_ask_trace(
                question,
                response,
                mode="ai_planner",
                proposed_tool_calls=response.get("tool_calls") if isinstance(response, dict) else None,
                debug=response.get("debug") if isinstance(response, dict) else None,
            )
            return response
        except Exception as e:
            logger.warning("AI planner failed, falling back to heuristic: %s", e)

    response: dict[str, Any] = {}

    if any(k in lowered for k in ["do we have", "kya", "hai kya", "where is", "where's", "where"]):
        query = extract_query_for_action(question, "item")
        result = tools.find_item(query)
        response = {
            "intent": "find_item",
            "query": query,
            "results": result.get("results", [])
        }

    elif any(keyword in lowered for keyword in ["skip", "what can i skip", "can i skip"]):
        lots = db.get_inventory()
        stock = [lot for lot in lots if lot.quantity > 0 and lot.status == "active"]
        ranked = sorted(stock, key=lambda lot: lot.quantity, reverse=True)[:8]
        from shopstack.schemas.models import DecisionSet, DecisionResult
        ds = DecisionSet(decisions=[])
        for lot in ranked:
            ds.decisions.append(DecisionResult(
                canonical_name=lot.canonical_name,
                display_name=lot.display_name,
                action="skip",
                confidence=0.8,
                reasons=[f"You have {lot.quantity} {lot.unit} remaining"]
            ))
        response = ds.model_dump()

    elif any(k in lowered for k in ["expiring", "expires", "use soon", "urgent"]):
        soon = tools.get_use_soon_items(days=7).get("items", [])
        from shopstack.schemas.models import DecisionSet, DecisionResult
        ds = DecisionSet(decisions=[])
        for item in soon[:6]:
            ds.decisions.append(DecisionResult(
                canonical_name=item.get("canonical_name", ""),
                display_name=item.get("display_name", item.get("canonical_name", "")),
                action="use_soon",
                confidence=0.9,
                reasons=[item.get("reason", "Use soon")]
            ))
        response = ds.model_dump()

    elif _is_add_command(lowered):
        _response_html = _handle_add_command(question)
        response = {"intent": "add_command", "html": _response_html}

    elif "should i buy" in lowered or "what should i buy" in lowered or "what do i need" in lowered:
        suggestions = tools.get_next_buy_suggestions().get("suggestions", [])
        from shopstack.schemas.models import DecisionSet, DecisionResult
        ds = DecisionSet(decisions=[])
        for s in suggestions[:8]:
            ds.decisions.append(DecisionResult(
                canonical_name=s.get("canonical_name", ""),
                display_name=s.get("canonical_name", "").title(),
                action="buy",
                confidence=0.91,
                reasons=[s.get("reason", "")]
            ))
        response = ds.model_dump()

    else:
        response = {"intent": "unknown", "question": question, "suggestion": "Try: 'Do we have milk?', 'What should I buy today?', or 'Where is toothpaste?'"}

    _record_ask_trace(
        question,
        response,
        "ask_shopstack",
        proposed_tool_calls=response.get("tool_calls") if isinstance(response, dict) else None,
    )
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
            response = planner.process_structured(text)
            _record_ask_trace(
                text,
                response,
                "ai_planner_audio",
                proposed_tool_calls=response.get("tool_calls") if isinstance(response, dict) else None,
                debug=response.get("debug") if isinstance(response, dict) else None,
                trace_input_type="voice",
            )
            return _render_planner_response(_render_structured_ask_summary(response))
        except Exception as exc:
            logger.warning("AI planner failed for voice, falling back: %s", exc)
            _record_ask_trace(
                text,
                {"error": str(exc)},
                "ai_planner_audio_fallback",
                trace_input_type="voice",
            )
            return ask_shopstack(text)

    return ask_shopstack(text)


def _record_ask_trace(
    question: str,
    response: str | dict[str, Any],
    mode: str,
    *,
    proposed_tool_calls: list[dict[str, Any]] | None = None,
    debug: dict[str, Any] | None = None,
    trace_input_type: str = "text",
) -> None:
    try:
        final_response = response if isinstance(response, str) else json.dumps(response, default=str)
        normalized_mode = mode
        if isinstance(response, dict):
            normalized_mode = str(response.get("type", mode))
            if proposed_tool_calls is None:
                candidate = response.get("tool_calls")
                if isinstance(candidate, list):
                    proposed_tool_calls = candidate
        create_trace(
            db,
            input_type=trace_input_type,
            user_goal="ask_shopstack",
            redacted_user_request=question,
            perception={"query": question, "mode": mode},
            inventory_context={},
            decision={
                "response_type": normalized_mode,
                "mode": mode,
                "planner_debug": debug or {},
            },
            proposed_tool_calls=proposed_tool_calls or [{"tool_name": mode, "args": {"question": question}}],
            final_response=final_response,
            human_confirmation="responded",
        )
    except Exception as e:
        logger.debug("Failed to record ask trace: %s", e)


def _render_structured_ask_summary(response: dict[str, Any]) -> str:
    if not isinstance(response, dict):
        return str(response or "")
    debug = response.get("debug", {})
    if not isinstance(debug, dict):
        debug = {}
    tool_calls = response.get("tool_calls", [])
    outcomes = response.get("outcomes", [])
    if not isinstance(tool_calls, list):
        tool_calls = []
    if not isinstance(outcomes, list):
        outcomes = []
    return (
        f"Tool calls: {len(tool_calls)}; Outcomes: {len(outcomes)}; "
        f"Parser status: {debug.get('parser', {}).get('status', 'unknown')}"
    )


def _render_planner_response(response: str) -> str:
    response_text = response or ""
    rendered = response_text if response_text.lstrip().startswith("<") else escape(response_text)
    return ui_card(
        f"{APP_NAME} AI",
        rendered
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
