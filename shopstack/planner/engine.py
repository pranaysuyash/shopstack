from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.persistence.database import Database
from shopstack.planner.parser import parse_tool_calls
from shopstack.providers.registry import ProviderRegistry
from shopstack.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

TOOL_ACTIONS_HELP: dict[str, str] = {
    "add_inventory_item": "Added {canonical_name} to inventory.",
    "consume_inventory_item": "Consumed {quantity} of lot {lot_id}.",
    "update_inventory_item": "Updated lot {lot_id}.",
    "move_inventory_item": "Moved lot {lot_id} to {to_location_id}.",
    "find_item": "",
    "create_or_update_shopping_list": "Updated shopping list.",
    "compare_visible_item_to_inventory": "",
    "record_price_observation": "Recorded price for {canonical_name}.",
    "get_use_soon_items": "",
    "get_next_buy_suggestions": "",
    "respond": "",
}


class PlannerEngine:
    def __init__(
        self,
        db: Database,
        tool_registry: ToolRegistry,
        provider_registry: ProviderRegistry,
    ):
        self._db = db
        self._tools = tool_registry
        self._providers = provider_registry

    @property
    def available(self) -> bool:
        provider = self._providers.planner
        if provider is None:
            return False
        return getattr(provider, "available", False)

    def process(self, question: str) -> str:
        from shopstack.planner.prompts import build_planner_prompt

        provider = self._providers.planner
        if provider is None or not getattr(provider, "available", False):
            return "<div class='stat-card'>Planner not available. Set SHOPSTACK_PLANNER_BACKEND=local to use a local model, or SHOPSTACK_PLANNER_BACKEND=openai for OpenAI.</div>"

        prompt = build_planner_prompt(question, self._db)

        try:
            if hasattr(provider, "plan"):
                result = provider.plan({"prompt": prompt, "question": question})
                raw_text = str(result.get("text", ""))
            else:
                result = provider.complete(prompt)
                raw_text = str(result.get("text", ""))
        except Exception as e:
            logger.warning("Planner call failed", exc_info=True)
            return f"<div class='stat-card'><div style='color:var(--red);'>Planner error: {escape(str(e))}</div></div>"

        if not raw_text:
            return "<div class='stat-card'>Planner returned an empty response.</div>"

        tool_calls = parse_tool_calls(raw_text)
        outcomes = self._execute_tool_calls(tool_calls)
        return self._format_outcomes(outcomes, question)

    def _execute_tool_calls(
        self, tool_calls: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for tc in tool_calls:
            tool = tc.get("tool", "respond")
            args = tc.get("args", {})
            if tool == "respond":
                msg = args.get("message", "")
                results.append({
                    "tool": "respond",
                    "success": True,
                    "message": msg,
                })
                continue
            outcome = self._tools.execute(tool, **args)
            results.append({
                "tool": tool,
                "success": outcome.get("success", False),
                "result": outcome.get("result", outcome),
                "error": outcome.get("error"),
            })
        return results

    def _format_outcomes(
        self, outcomes: list[dict[str, Any]], original_question: str
    ) -> str:
        html_parts: list[str] = []
        for outcome in outcomes:
            tool = outcome["tool"]
            success = outcome["success"]
            if tool == "respond":
                msg = outcome.get("message", "")
                if msg:
                    html_parts.append(
                        f"<div style='padding:8px;margin:4px 0;border-left:3px solid var(--accent);'>{escape(str(msg))}</div>"
                    )
                continue
            action = TOOL_ACTIONS_HELP.get(tool, f"Ran {tool}.")
            result_data = outcome.get("result") or outcome.get("error", "")
            if success:
                if action:
                    html_parts.append(
                        f"<div style='padding:6px;margin:2px 0;color:var(--text-main);'>"
                        f"<span style='color:var(--green);'>&#10003;</span> {action}</div>"
                    )
            else:
                err = outcome.get("error", "Unknown error")
                html_parts.append(
                    f"<div style='padding:6px;margin:2px 0;color:var(--red);'>"
                    f"&#10007; {escape(str(tool))}: {escape(str(err))}</div>"
                )

        if not html_parts:
            return "<div class='stat-card'>No actions taken.</div>"

        title = "ShopStack AI"
        body = "".join(html_parts)
        return (
            f"<div class='stat-card'>"
            f"<div style='font-weight:600;margin-bottom:8px;'>{title}</div>"
            f"{body}"
            f"</div>"
        )
