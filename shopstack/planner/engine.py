from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.config import settings
from shopstack.cost_tracker import CostTracker, CostRecord, estimate_cost_usd, estimate_model_tier
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
        self._cost_tracker = CostTracker(budget_limit=settings.cost_budget_limit)

    @property
    def available(self) -> bool:
        provider = self._providers.planner
        if provider is None:
            return False
        return getattr(provider, "available", False)

    def process(self, question: str) -> str:
        from shopstack.planner.prompts import build_planner_prompt, build_system_prompt

        provider = self._providers.planner
        if provider is None or not getattr(provider, "available", False):
            return "<div class='stat-card'>Planner not available. Set SHOPSTACK_PLANNER_BACKEND=local to use a local model, or SHOPSTACK_PLANNER_BACKEND=openai for OpenAI.</div>"

        prompt = build_planner_prompt(question, self._db)
        system_prompt = build_system_prompt(self._db)

        try:
            if hasattr(provider, "plan"):
                result = provider.plan({
                    "prompt": prompt,
                    "system": system_prompt,
                    "question": question,
                })
                # Interface contract: plan() may return a list of tool calls directly
                if isinstance(result, list):
                    outcomes = self._execute_tool_calls(result)
                    return self._format_outcomes(outcomes, question)
                raw_text = str(result.get("text", ""))
                self._record_provider_cost(result)
            else:
                complete_fn = getattr(provider, "complete", None)
                plan_result = complete_fn(prompt) if callable(complete_fn) else {"text": ""}
                if isinstance(plan_result, dict):
                    raw_text = str(plan_result.get("text", ""))
                    self._record_provider_cost(plan_result)
                else:
                    raw_text = str(plan_result) if plan_result else ""
        except Exception as e:
            logger.warning("Planner call failed", exc_info=True)
            return f"<div class='stat-card'><div style='color:var(--red);'>Planner error: {escape(str(e))}</div></div>"

        if not raw_text:
            return "<div class='stat-card'>Planner returned an empty response.</div>"

        tool_calls = parse_tool_calls(raw_text)
        outcomes = self._execute_tool_calls(tool_calls)
        return self._format_outcomes(outcomes, question)

    @property
    def session_cost(self) -> dict[str, Any]:
        """Return the current session cost summary."""
        return self._cost_tracker.summary()

    def _record_provider_cost(self, result: dict[str, Any]) -> None:
        """Extract usage/cost from a provider result dict and record it."""
        model_key = str(result.get("model") or result.get("model_key") or "unknown")
        usage = result.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        latency_ms = result.get("latency_ms")
        if isinstance(latency_ms, (int, float)):
            latency_ms = float(latency_ms)
        elif isinstance(result.get("cost"), dict):
            latency_ms = result["cost"].get("latency_ms")
        if input_tokens or output_tokens:
            self._record_cost(model_key, input_tokens, output_tokens, latency_ms)

    def _record_cost(self, model_key: str, input_tokens: int, output_tokens: int, latency_ms: float | None = None) -> None:
        """Record a cost entry from a provider call."""
        cost = estimate_cost_usd(model_key, input_tokens, output_tokens)
        tier = estimate_model_tier(input_tokens, item_count=0)
        record = CostRecord(
            model=model_key,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            tier=tier,
            latency_ms=latency_ms,
        )
        self._cost_tracker = self._cost_tracker.add(record)

    # Patterns that indicate potential injection or path traversal in tool args
    _SUSPICIOUS_ARG_PATTERNS = (
        "../", "..\\", "/etc/", "C:\\", "|", ";", "&&", "||", "`", "$(",
        "__import__", "eval(", "exec(", "open(", "os.", "subprocess",
    )

    def _validate_args(self, tool: str, args: dict[str, Any]) -> str | None:
        """Validate tool arguments for injection / path traversal / abuse.
        Returns an error message string if validation fails, or None if clean.
        """
        for key, value in args.items():
            if not isinstance(value, str):
                continue
            lower_val = value.lower()
            for pattern in self._SUSPICIOUS_ARG_PATTERNS:
                if pattern.lower() in lower_val:
                    return (
                        f"Rejected tool '{tool}' arg '{key}': "
                        f"value contains suspicious pattern '{pattern}'"
                    )
        return None

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
            # Validate args before execution
            validation_error = self._validate_args(tool, args)
            if validation_error is not None:
                logger.warning("Tool arg validation failed: %s", validation_error)
                results.append({
                    "tool": tool,
                    "success": False,
                    "error": validation_error,
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
            _result_data = outcome.get("result") or outcome.get("error", "")
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

        title = f"{settings.app_name} AI"
        body = "".join(html_parts)
        return (
            f"<div class='stat-card'>"
            f"<div style='font-weight:600;margin-bottom:8px;'>{title}</div>"
            f"{body}"
            f"</div>"
        )
