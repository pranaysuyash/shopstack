from __future__ import annotations

import logging
import json
import re
from html import escape
from typing import Any

from shopstack.app_context import APP_NAME, db, planner, providers, tools, current_user_id
from shopstack.ui.components.cards import card as ui_card
from shopstack.ui.components.primitives import empty_state_enhanced, toast
from shopstack.ui.renderers.image_cards import render_decision_card as render_unified_decision_card
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

    uid = current_user_id()

    lowered = question.lower()

    if _is_add_command(lowered):
        response = _handle_add_command(question)
        _record_ask_trace(
            question,
            response,
            "ask_shopstack",
            proposed_tool_calls=[{"tool_name": "add_inventory_item", "args": {"text": question}}],
            user_id=uid,
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
                user_id=uid,
            )
            return response
        except Exception as e:
            logger.warning("AI planner failed, falling back to heuristic: %s", e)

    response: dict[str, Any] = {}

    if any(k in lowered for k in ["do we have", "kya", "hai kya", "where is", "where's", "where"]):
        query = extract_query_for_action(question, "item")
        result = tools.find_item(query, user_id=uid)
        response = {
            "intent": "find_item",
            "query": query,
            "results": result.get("results", [])
        }

    elif any(keyword in lowered for keyword in ["skip", "what can i skip", "can i skip"]):
        lots = db.get_inventory(user_id=uid)
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
        soon = tools.get_use_soon_items(days=7, user_id=uid).get("items", [])
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
        suggestions = tools.get_next_buy_suggestions(user_id=uid).get("suggestions", [])
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
        user_id=uid,
    )
    return response


# ── Action badge colors (synced with decision color tokens) ──────────
# Kept here next to ``render_ask_response`` so the renderer and the
# badge palette it depends on share a single canonical home. The Ask
# panel builder (``shopstack/ui/tabs/ask_panel.py``) re-imports both
# to preserve its historical public surface.
_ACTION_BADGE: dict[str, tuple[str, str]] = {
    "buy": ("badge-green", "Buy"),
    "skip": ("badge-gray", "Skip"),
    "use_soon": ("badge-amber", "Use soon"),
    "optional": ("badge-blue", "Optional"),
    "compare": ("badge-blue", "Compare"),
    "confirm": ("badge-red", "Confirm"),
    "substitute": ("badge-blue", "Substitute"),
}


def render_ask_response(answer: dict[str, Any] | Any) -> str:
    """Convert an ``ask_shopstack`` response into user-facing HTML.

    Canonical renderer — every caller that surfaces an ``ask_shopstack``
    result to the UI should go through this function so intent-specific
    rendering stays consistent. ``market_lens_process`` previously
    assigned the raw dict straight to ``result_html``; that value then
    flowed into ``create_trace(final_response=...)`` and broke Pydantic
    validation (``final_response`` is typed ``str``), which silently
    dropped the trace and broke audio-only market-lens flows.
    """
    if isinstance(answer, str):
        return f"home_card(body='{answer}', style='text-align:left;')"
    if not isinstance(answer, dict):
        return f"home_card(body='{escape(str(answer))}', style='text-align:left;')"

    # ── Intent: empty ──
    intent = answer.get("intent", "")
    if intent == "empty":
        msg = escape(answer.get("message", ""))
        return (
            f"<div class='home-card' style='text-align:left;color:var(--text-muted);'>{msg}</div>"
        )

    # ── Intent: unknown ──
    if intent == "unknown":
        suggestion = escape(answer.get("suggestion", ""))
        return home_card(
            body=f"<div style='color:var(--text-muted);'>{suggestion}</div>",
            style="text-align:left;",
        )

    # ── Intent: find_item ──
    if intent == "find_item":
        results = answer.get("results", [])
        if not results:
            return (
                f"home_card(body='<div style=\"color:var(--text-dim);\">No matching items found.</div>', style='text-align:left;')"
            )
        rows = []
        for r in results[:6]:
            name = escape(str(r.get("display_name", r.get("canonical_name", ""))).replace("_", " ").title())
            qty = r.get("quantity", r.get("location_name", ""))
            unit = r.get("unit", "")
            location = escape(str(r.get("location_name", "")))
            qty_str = f"{qty} {escape(unit)}" if unit else str(qty)
            match_type = r.get("match_type", "")
            badge = f" <span class='badge badge-green' style='font-size: 0.5625rem;'>{escape(match_type)}</span>" if match_type else ""
            rows.append(
                f"<div class='item-row'><div><div style='font-weight:600;'>{name}{badge}</div>"
                f"<div style='font-size: 0.6875rem;color:var(--text-dim);'>{location}</div></div><span style='font-weight:500;'>{qty_str}</span></div>"
            )
        # Compute the item-count text once to avoid nested single-quote
        # escaping issues inside the f-string. (The original used
        # ``item{\'s\'}`` which is invalid inside an f-string expression
        # — ``\'`` is not allowed inside the ``{}``.)
        item_count_text = (
            f"{len(results)} item{'s' if len(results) != 1 else ''}"
        )
        return (
            f"<div class='home-card' style='text-align:left;'>"
            f"<div style='font-weight:600;margin-bottom:8px;'>Found {item_count_text}</div>"
            f"{''.join(rows)}</div>"
        )

    # ── DecisionSet (buy/skip/use_soon/compare/substitute) ──
    decisions = answer.get("decisions", [])
    if decisions:
        rows = []
        for d in decisions[:8]:
            name = escape(str(d.get("display_name", d.get("canonical_name", ""))).replace("_", " ").title())
            action = d.get("action", "")
            badge_cls, badge_label = _ACTION_BADGE.get(action, ("badge-gray", action.title()))
            reasons = d.get("reasons", [])
            reason_text = escape(str(reasons[0])) if reasons else ""
            rows.append(
                f"<div class='item-row'><div><div style='font-weight:600;'>{name}</div>"
                f"<div style='font-size: 0.6875rem;color:var(--text-dim);'>{reason_text}</div></div><span class='badge {badge_cls}'>{escape(badge_label)}</span></div>"
            )
        return (
            f"home_card(body='<div style='font-weight:600;margin-bottom:8px;'>{len(decisions)} suggestion{'s' if len(decisions) != 1 else ''}', style='text-align:left;')"
            f"{''.join(rows)}</div>"
        )

    # ── AI planner response (tool_calls / outcomes / message) ──
    message = answer.get("message", "")
    outcomes = answer.get("outcomes", [])
    tool_calls = answer.get("tool_calls", [])
    if message or outcomes:
        parts: list[str] = []
        if message:
            safe_msg = escape(str(message))
            parts.append(f"<div style='margin-bottom:8px;'>{safe_msg}</div>")
        if isinstance(outcomes, list) and outcomes:
            for o in outcomes[:5]:
                if isinstance(o, dict):
                    action = escape(str(o.get("action", o.get("tool_name", ""))))
                    status = "✓" if o.get("success", True) else "✗"
                    color = "var(--green)" if o.get("success", True) else "var(--red)"
                    parts.append(
                        f"<div class='item-row'><span style='color:{color};font-weight:700;'>{status}</span>"
                        f"<span style='font-size: 0.75rem;'>{action}</span></div>"
                    )
        if parts:
            return (
                f"home_card(body='{''.join(parts)}', style='text-align:left;')"
            )

    # ── Fallback: render key-value pairs ──
    parts = []
    for key, val in answer.items():
        if key in ("debug", "tool_calls"):
            continue
        if isinstance(val, list) and val:
            val_str = f"{len(val)} items"
        elif isinstance(val, dict):
            val_str = ", ".join(f"{k}: {v}" for k, v in list(val.items())[:3])
        else:
            val_str = str(val)
        parts.append(
            f"<div style='padding:3px 0;border-bottom:1px solid var(--border);'><span style='font-weight:600;font-size: 0.75rem;'>{escape(key.replace('_', ' ').title())}</span> "
            f"<span style='font-size: 0.75rem;color:var(--text-dim);'>{escape(val_str[:200])}</span></div>"
        )
    if parts:
        return f"<div class='home-card' style='text-align:left;'>{''.join(parts)}</div>"
    return (
        f"<div class='home-card' style='text-align:left;'>"
        f"<div style='color:var(--text-dim);'>No answer available.</div>"
        f"</div>"
    )


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
                user_id=current_user_id(),
            )
            return _render_planner_response(_render_structured_ask_summary(response))
        except Exception as exc:
            logger.warning("AI planner failed for voice, falling back: %s", exc)
            _record_ask_trace(
                text,
                {"error": str(exc)},
                "ai_planner_audio_fallback",
                trace_input_type="voice",
                user_id=current_user_id(),
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
    user_id: str = "",
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
            user_id=user_id,
        )
    except Exception as e:
        logger.warning("Failed to record ask trace: %s", e)


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
        f"Tool calls: {len(tool_calls)}; Outcomes: {len(outcomes)}; Parser status: {debug.get('parser', {}).get('status', 'unknown')}"
    )


def _render_ask_answer_html(response: Any) -> str:
    """Render an ``ask_shopstack`` response as a consumer-friendly HTML answer.

    Surfaces the user-facing intent, message, and (when present) decision
    cards. Internal implementation details (trace_id, debug payloads) are
    hidden so the Ask panel reads like an answer, not a JSON tree.

    Args:
        response: The raw dict/string returned by :func:`ask_shopstack` or
            a related handler.

    Returns:
        HTML snippet suitable for ``gr.HTML``.
    """
    if response is None:
        return empty_state_enhanced(
            "Ask a question to see an answer here.",
            icon="💬",
        )

    if isinstance(response, str):
        # Bare string answer — wrap as a card.
        safe = escape(response)
        return (
            f"<div class='home-card' style='text-align:left;'>"
            f"<div style='font-size: 0.875rem;line-height:1.5;'>{safe}</div>"
            f"</div>"
        )

    if not isinstance(response, dict):
        safe = escape(str(response))
        return (
            f"<div class='home-card' style='text-align:left;'>"
            f"<div>{safe}</div>"
            f"</div>"
        )

    # Direct message wins (intent=empty, planner message, etc.).
    msg = response.get("message") or response.get("answer") or response.get("response")
    intent = response.get("intent", "")

    if msg and not response.get("decisions"):
        return (
            f"<div class='home-card' style='text-align:left;'>"
            f"<div style='font-size: 0.875rem;line-height:1.5;'>{escape(str(msg))}</div>"
            + (f"<div class='muted' style='margin-top:6px;font-size: 0.6875rem;'>Intent: {escape(str(intent))}</div>" if intent else "")
            + "</div>"
        )

    # Decision-set style: render via the existing card renderer.
    decisions = response.get("decisions")
    if isinstance(decisions, list) and decisions:
        cards = []
        for d in decisions[:6]:
            try:
                from shopstack.schemas.models import DecisionResult
                dr = DecisionResult(**d) if not isinstance(d, DecisionResult) else d
                cards.append(render_unified_decision_card(dr))
            except Exception:
                continue
        if cards:
            body = "".join(cards)
            return (
                f"<div class='home-card' style='text-align:left;'>"
                f"<h3>What I found</h3>{body}</div>"
            )

    # Find-item results: show top hits as a small list.
    results = response.get("results")
    if isinstance(results, list) and results:
        rows = "".join(
            "<div class='item-row'>"
            f"<div>{escape(str(r.get('display_name', r.get('canonical_name', ''))))}</div><div style='color:var(--text-muted);font-size: 0.75rem;'>"
            f"{r.get('quantity', '')} {escape(str(r.get('unit', '')))}{' &middot; ' + escape(str(r.get('storage_location_id', ''))) if r.get('storage_location_id') else ''}"
            "</div></div>"
            for r in results[:6]
        )
        if rows:
            return (
                f"<div class='home-card' style='text-align:left;'>"
                f"<h3>What I found</h3>{rows}</div>"
            )

    # Fall back to a friendly message rather than dumping raw JSON.
    if msg:
        return (
            f"<div class='home-card' style='text-align:left;'>"
            f"<div style='font-size: 0.875rem;line-height:1.5;'>{escape(str(msg))}</div>"
        )
    return empty_state_enhanced(
        "I didn't get a clear answer. Try rephrasing the question.",
        icon="🤔",
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
    clean = text.strip().lower()
    if clean in ("add", "added", "put", "bought", "purchased", "got"):
        return True
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
    uid = current_user_id()
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
                user_id=uid,
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
                    user_id=uid,
                )
            except Exception as exc:
                logger.warning("Failed to record voice add trace: %s", exc)
            return toast(
                f"Added {escape(name)} ({escape(str(qty))} {escape(unit)}) to inventory. Lot: {escape(lot_id[:12])}",
                kind="success",
            )
    return toast("Could not understand what to add. Try: 'add milk' or 'add 2 kg rice'", kind="warning")
