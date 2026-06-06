from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.app_context import db, planner, providers, tools
from shopstack.ui import card as ui_card, empty_state
from shopstack.ui.components import render_decision_card
from shopstack.traces.export import create_trace
from shopstack.ui.screens._utils import (
    WORKFLOW_STEPS,
    extract_query_for_action,
)

logger = logging.getLogger(__name__)


def ask_shopstack(question: str) -> str:
    question = (question or "").strip()
    if not question:
        return "<div style='color:var(--text-dim);'>Ask ShopStack anything \u2014 e.g. \u201cDo we have milk?\u201d or \u201cWhat should I buy today?\u201d</div>"

    if planner.available:
        try:
            response = planner.process(question)
            _record_ask_trace(question, response, "ai_planner")
            return _render_planner_response(response)
        except Exception as e:
            logger.warning("AI planner failed, falling back to heuristic: %s", e)

    lowered = question.lower()
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
            cards = "".join(render_decision_card(r["lot"].get("display_name", ""), "buy", "Found in inventory", 1.0, r["lot"].get("quantity"), r["lot"].get("unit")) for r in results)
            response = ui_card("Location match", cards)
        else:
            response = empty_state(f"We looked for {query} but found nothing. Add it to your next list if needed.")

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
            "<div style='margin-top:8px;color:var(--text-dim);'>Try: \u201cDo we have milk?\u201d, \u201cWhat should I buy today?\u201d, or \u201cWhere is toothpaste?\u201d</div>",
        )

    _record_ask_trace(question, response, "ask_shopstack")
    return response


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
        "ShopStack AI",
        rendered
        + "<div style='margin-top:8px;font-size:11px;color:var(--text-dim);'>"
        "Rendered through the same Ask ShopStack HTML boundary as heuristic answers.</div>",
    )
