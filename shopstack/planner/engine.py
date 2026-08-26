from __future__ import annotations

import json
import logging
import time
from html import escape
from typing import Any

from shopstack.config import settings
from shopstack.cost_tracker import (
    CostRecord,
    CostTracker,
    estimate_cost_usd,
    estimate_model_tier,
)
from shopstack.eval.recorder import (
    CAP_PLANNER_TOOL_CALLING,
    OUTCOME_EMPTY,
    OUTCOME_EXCEPTION,
    OUTCOME_BLOCKED,
    OUTCOME_PARSE_ERROR,
    OUTCOME_SUCCESS,
    OUTCOME_TOOL_FAILURE,
    SHAPE_TOOL_CALLS,
    record_model_call,
)
from shopstack.persistence.database import Database
from shopstack.planner.parser import parse_tool_calls_with_diagnostics
from shopstack.providers.registry import ProviderRegistry
from shopstack.tools.registry import ToolRegistry


def _stat_card(*args: Any, **kwargs: Any) -> str:
    """Deferred import: shopstack.ui's package __init__ imports shopstack.app_context,
    which imports PlannerEngine from this module — a top-level import here would cycle."""
    from shopstack.ui.components.primitives import stat_card
    return stat_card(*args, **kwargs)

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
    MAX_TOOL_CALLS_PER_RUN = 8
    _LOT_REFERENCE_TOOLS = frozenset({
        "consume_inventory_item",
        "move_inventory_item",
        "update_inventory_item",
        "undo_last_inventory_change",
    })

    def __init__(
        self,
        db: Database,
        tool_registry: ToolRegistry,
        provider_registry: ProviderRegistry,
        *,
        allow_confirmed_writes: bool = False,
    ):
        self._db = db
        self._tools = tool_registry
        self._providers = provider_registry
        self._allow_confirmed_writes = allow_confirmed_writes
        self._cost_tracker = CostTracker(budget_limit=settings.cost_budget_limit)

    @property
    def available(self) -> bool:
        provider = self._providers.planner
        if provider is None:
            return False
        return getattr(provider, "available", False)

    def process(
        self,
        question: str,
        compact_tools: bool | None = None,
        trace_id: str = "",
        generation: dict[str, Any] | None = None,
    ) -> str:
        from shopstack.planner.prompts import build_planner_prompt, build_system_prompt

        provider = self._providers.planner
        if self._cost_guarded():
            return self._budget_blocked_html()
        if provider is None or not getattr(provider, "available", False):
            return _stat_card(body_html=(
                "Planner not available. "
                "Set SHOPSTACK_PLANNER_BACKEND=local to use a local model, "
                "or SHOPSTACK_PLANNER_BACKEND=openai for OpenAI."
            ))

        if compact_tools is None:
            compact_tools = settings.planner_compact_tools
        prompt = build_planner_prompt(question, self._db, tool_registry=self._tools, compact_tools=compact_tools)
        system_prompt = build_system_prompt(self._db, tool_registry=self._tools, compact_tools=compact_tools)
        provider_meta: dict[str, Any] = {}
        parser_meta: dict[str, Any] = {}
        tool_calls: list[dict[str, Any]] = []

        # ── o/p eval: open the per-call record before the provider call.
        # The recorder is best-effort; it never raises into the hot path.
        with record_model_call(
            domain_route="planner",
            capability=CAP_PLANNER_TOOL_CALLING,
            capability_expected_shape=SHAPE_TOOL_CALLS,
            trace_id=trace_id,
        ) as rec:
            rec.set_prompt(prompt)
            try:
                started = time.monotonic()
                if hasattr(provider, "plan"):
                    result = provider.plan({
                        "prompt": prompt,
                        "system": system_prompt,
                        "question": question,
                        **(generation or {}),
                    })
                    planner_call_ms = round((time.monotonic() - started) * 1000, 2)
                    tool_calls, parser_meta = self._parse_tool_calls_from_result(result)
                    parser_meta = self._merge_provider_parser_diagnostics(provider, parser_meta)
                    provider_meta = self._provider_call_meta(
                        provider,
                        result=result,
                        call_latency_ms=planner_call_ms,
                        question=question,
                        prompt=prompt,
                    )
                else:
                    complete_fn = getattr(provider, "complete", None)
                    plan_result = complete_fn(prompt) if callable(complete_fn) else {"text": ""}
                    if isinstance(plan_result, dict):
                        result = plan_result
                        planner_call_ms = round((time.monotonic() - started) * 1000, 2)
                        raw_text = str(plan_result.get("text", ""))
                        self._record_provider_cost(plan_result)
                        provider_meta = self._provider_call_meta(
                            provider,
                            result=plan_result,
                            call_latency_ms=planner_call_ms,
                            question=question,
                            prompt=prompt,
                        )
                        if self._cost_guarded():
                            rec.set_outcome("blocked", "cost_budget_exceeded")
                            rec.set_output(raw_text)
                            rec.set_usage(
                                input_tokens=provider_meta.get("input_tokens", 0),
                                output_tokens=provider_meta.get("output_tokens", 0),
                                cost_usd=provider_meta.get("cost_usd", 0.0),
                                model=provider_meta.get("model", ""),
                                backend=provider_meta.get("backend", ""),
                                provider_name=provider_meta.get("provider", ""),
                            )
                            return self._budget_blocked_html()
                        if not raw_text:
                            provider_meta["outcome"] = "empty_llm_text"
                            rec.set_outcome(OUTCOME_EMPTY, "empty_llm_text")
                            rec.set_output(raw_text)
                            rec.set_usage(
                                input_tokens=provider_meta.get("input_tokens", 0),
                                output_tokens=provider_meta.get("output_tokens", 0),
                                cost_usd=provider_meta.get("cost_usd", 0.0),
                                model=provider_meta.get("model", ""),
                                backend=provider_meta.get("backend", ""),
                                provider_name=provider_meta.get("provider", ""),
                            )
                            return _stat_card(body_html="Planner returned an empty response.")
                        tool_calls, parser_meta = self._parse_tool_calls_from_result(raw_text)
                    else:
                        planner_call_ms = round((time.monotonic() - started) * 1000, 2)
                        tool_calls, parser_meta = self._parse_tool_calls_from_result(str(plan_result))
                        provider_meta = self._provider_call_meta(
                            provider,
                            result=None,
                            raw_output=plan_result,
                            call_latency_ms=planner_call_ms,
                            question=question,
                            prompt=prompt,
                        )

            except Exception as e:
                logger.warning("Planner call failed", exc_info=True)
                rec.set_outcome(OUTCOME_EXCEPTION, str(e))
                return _stat_card(body_html=f"<div style='color:var(--red);'>Planner error: {escape(str(e))}</div>")

            # Feed provider metadata into the o/p eval record.
            rec.set_output(result if "result" in locals() else plan_result)
            rec.set_usage(
                input_tokens=provider_meta.get("input_tokens", 0),
                output_tokens=provider_meta.get("output_tokens", 0),
                cost_usd=provider_meta.get("cost_usd", 0.0),
                model=provider_meta.get("model", ""),
                backend=provider_meta.get("backend", ""),
                provider_name=provider_meta.get("provider", ""),
            )
            parser_failed = self._parser_failed(parser_meta, tool_calls)
            if parser_failed:
                execution_meta = self._parse_failure_execution(tool_calls)
                outcomes = []
                rec.set_execution(execution_meta)
                rec.set_outcome(OUTCOME_PARSE_ERROR, self._parser_error(parser_meta))
            else:
                outcomes, execution_meta = self._execute_tool_calls(tool_calls)
                rec.set_execution(execution_meta)
                self._set_execution_outcome(rec, execution_meta)

        # End of with block — __exit__ persists the record.
        provider_meta["parser"] = parser_meta
        provider_meta["execution"] = execution_meta
        if self._parser_failed(parser_meta, tool_calls):
            return _stat_card(body_html="Planner could not produce a valid action plan. Please rephrase the request.")
        # kept intentionally for UI/debug surfacing through raw trace consumers
        return self._format_outcomes(outcomes, question)

    def process_structured(
        self,
        question: str,
        compact_tools: bool | None = None,
        trace_id: str = "",
        generation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process a question and return a structured dictionary instead of HTML prose."""
        from shopstack.planner.prompts import build_planner_prompt, build_system_prompt

        provider = self._providers.planner
        if provider is None or not getattr(provider, "available", False):
            return {"error": "Planner not available", "type": "error"}

        if compact_tools is None:
            compact_tools = settings.planner_compact_tools
        prompt = build_planner_prompt(question, self._db, tool_registry=self._tools, compact_tools=compact_tools)
        system_prompt = build_system_prompt(self._db, tool_registry=self._tools, compact_tools=compact_tools)
        parser_meta: dict[str, Any] = {}
        provider_meta: dict[str, Any] = {}
        tool_calls: list[dict[str, Any]] = []

        # ── o/p eval: open the per-call record
        with record_model_call(
            domain_route="planner",
            capability=CAP_PLANNER_TOOL_CALLING,
            capability_expected_shape=SHAPE_TOOL_CALLS,
            trace_id=trace_id,
        ) as rec:
            rec.set_prompt(prompt)

            if self._cost_guarded():
                rec.set_outcome("blocked", "cost_budget_exceeded")
                return {"error": "Budget limit reached", "type": "error"}

            try:
                started = time.monotonic()
                if hasattr(provider, "plan"):
                    result = provider.plan({
                        "prompt": prompt,
                        "system": system_prompt,
                        "question": question,
                        **(generation or {}),
                    })
                    planner_call_ms = round((time.monotonic() - started) * 1000, 2)
                    tool_calls, parser_meta = self._parse_tool_calls_from_result(result)
                    parser_meta = self._merge_provider_parser_diagnostics(provider, parser_meta)
                    provider_meta = self._provider_call_meta(
                        provider,
                        result=result,
                        call_latency_ms=planner_call_ms,
                        question=question,
                        prompt=prompt,
                    )
                else:
                    complete_fn = getattr(provider, "complete", None)
                    plan_result = complete_fn(prompt) if callable(complete_fn) else {"text": ""}
                    if isinstance(plan_result, dict):
                        planner_call_ms = round((time.monotonic() - started) * 1000, 2)
                        raw_text = str(plan_result.get("text", ""))
                        self._record_provider_cost(plan_result)
                        provider_meta = self._provider_call_meta(
                            provider,
                            result=plan_result,
                            call_latency_ms=planner_call_ms,
                            question=question,
                            prompt=prompt,
                        )
                        if self._cost_guarded():
                            rec.set_outcome("blocked", "cost_budget_exceeded")
                            rec.set_output(raw_text)
                            rec.set_usage(
                                input_tokens=provider_meta.get("input_tokens", 0),
                                output_tokens=provider_meta.get("output_tokens", 0),
                                cost_usd=provider_meta.get("cost_usd", 0.0),
                                model=provider_meta.get("model", ""),
                                backend=provider_meta.get("backend", ""),
                                provider_name=provider_meta.get("provider", ""),
                            )
                            return {"error": "Budget limit reached", "type": "error"}
                        if not raw_text:
                            rec.set_outcome(OUTCOME_EMPTY, "empty_llm_text")
                            rec.set_output(raw_text)
                            rec.set_usage(
                                input_tokens=provider_meta.get("input_tokens", 0),
                                output_tokens=provider_meta.get("output_tokens", 0),
                                cost_usd=provider_meta.get("cost_usd", 0.0),
                                model=provider_meta.get("model", ""),
                                backend=provider_meta.get("backend", ""),
                                provider_name=provider_meta.get("provider", ""),
                            )
                            return {"error": "Planner returned an empty response.", "type": "error"}
                        tool_calls, parser_meta = self._parse_tool_calls_from_result(raw_text)
                    else:
                        planner_call_ms = round((time.monotonic() - started) * 1000, 2)
                        tool_calls, parser_meta = self._parse_tool_calls_from_result(str(plan_result))
                        provider_meta = self._provider_call_meta(
                            provider,
                            result=None,
                            raw_output=plan_result,
                            call_latency_ms=planner_call_ms,
                            question=question,
                            prompt=prompt,
                        )

            except Exception as e:
                logger.warning("Planner call failed", exc_info=True)
                rec.set_outcome(OUTCOME_EXCEPTION, str(e))
                return {"error": f"Planner error: {e!s}", "type": "error"}

            # Feed provider metadata into the o/p eval record.
            rec.set_output(result if "result" in locals() else plan_result)
            rec.set_usage(
                input_tokens=provider_meta.get("input_tokens", 0),
                output_tokens=provider_meta.get("output_tokens", 0),
                cost_usd=provider_meta.get("cost_usd", 0.0),
                model=provider_meta.get("model", ""),
                backend=provider_meta.get("backend", ""),
                provider_name=provider_meta.get("provider", ""),
            )
            parser_failed = self._parser_failed(parser_meta, tool_calls)
            if parser_failed:
                execution_meta = self._parse_failure_execution(tool_calls)
                outcomes = []
                rec.set_execution(execution_meta)
                rec.set_outcome(OUTCOME_PARSE_ERROR, self._parser_error(parser_meta))
            else:
                outcomes, execution_meta = self._execute_tool_calls(tool_calls)
                rec.set_execution(execution_meta)
                self._set_execution_outcome(rec, execution_meta)

        # End of with block — __exit__ persists the record.
        provider_meta["parser"] = parser_meta
        provider_meta["execution"] = execution_meta

        if self._parser_failed(parser_meta, tool_calls):
            return {
                "error": "Planner could not produce a valid action plan. Please rephrase the request.",
                "type": "error",
                "debug": {
                    "provider": provider_meta,
                    "parser": parser_meta,
                    "execution": execution_meta,
                },
            }

        return {
            "tool_calls": tool_calls,
            "outcomes": outcomes,
            "type": "tool_calls",
            "debug": {
                "provider": provider_meta,
                "parser": parser_meta,
                "execution": execution_meta,
            },
        }

    @staticmethod
    def _parser_failed(parser_meta: dict[str, Any], tool_calls: list[dict[str, Any]]) -> bool:
        if not tool_calls:
            return True
        if parser_meta.get("status") in {
            "fallback_respond",
            "invalid_root_type",
            "invalid_items",
            "empty",
            "unavailable",
        }:
            return True
        return int(parser_meta.get("items_output", 0) or 0) == 0

    @staticmethod
    def _merge_provider_parser_diagnostics(
        provider: Any,
        parser_meta: dict[str, Any],
    ) -> dict[str, Any]:
        provider_diagnostics = getattr(provider, "last_plan_diagnostics", None)
        if not isinstance(provider_diagnostics, dict) or not provider_diagnostics:
            return parser_meta
        merged = dict(parser_meta)
        merged["provider_plan"] = provider_diagnostics
        merged.update(provider_diagnostics)
        merged["source"] = f"{parser_meta.get('source', 'planner')}:provider_diagnostics"
        return merged

    @staticmethod
    def _parser_error(parser_meta: dict[str, Any]) -> str:
        return str(parser_meta.get("error") or parser_meta.get("status") or "no tool calls parsed")

    @staticmethod
    def _parse_failure_execution(tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "status": "parse_failed",
            "tool_calls_requested": len(tool_calls),
            "tool_calls_executed": 0,
            "tool_calls_failed": 0,
            "tool_calls_truncated": 0,
            "tool_runs": [],
            "cost_blocked": False,
        }

    @staticmethod
    def _set_execution_outcome(rec: Any, execution_meta: dict[str, Any]) -> None:
        if execution_meta.get("cost_blocked"):
            rec.set_outcome(OUTCOME_BLOCKED, "cost_budget_exceeded")
        elif execution_meta.get("tool_calls_failed", 0):
            rec.set_outcome(OUTCOME_TOOL_FAILURE, "one or more tool calls failed")
        else:
            rec.set_outcome(OUTCOME_SUCCESS)

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
        if not output_tokens and usage.get("total_tokens"):
            output_tokens = int(usage["total_tokens"])
        latency_ms = result.get("latency_ms")
        if isinstance(latency_ms, (int, float)):
            latency_ms = float(latency_ms)
        elif isinstance(result.get("cost"), dict):
            latency_ms = result["cost"].get("latency_ms")
        if input_tokens or output_tokens:
            self._record_cost(model_key, input_tokens, output_tokens, latency_ms)

    def _provider_call_meta(
        self,
        provider: Any,
        result: Any = None,
        call_latency_ms: float | None = None,
        question: str = "",
        prompt: str = "",
        raw_output: Any = None,
    ) -> dict[str, Any]:
        if result is None:
            result = {}
        result_type = type(raw_output if raw_output is not None else result).__name__
        metadata_result = result
        if not isinstance(metadata_result, dict):
            provider_completion = getattr(provider, "last_completion_meta", None)
            metadata_result = provider_completion if isinstance(provider_completion, dict) else {}
        usage: dict[str, Any] = {}
        if isinstance(metadata_result, dict):
            usage = metadata_result.get("usage") or {}
            if not isinstance(usage, dict):
                usage = {}

        cost_payload = metadata_result.get("cost") if isinstance(metadata_result, dict) else {}
        if not isinstance(cost_payload, dict):
            cost_payload = {}

        input_tokens = 0
        output_tokens = 0
        if usage:
            input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            output_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            if not output_tokens and usage.get("total_tokens"):
                output_tokens = int(usage["total_tokens"])

        model_key = None
        if isinstance(result, dict):
            model_key = result.get("model") or result.get("model_key")
        if not model_key and isinstance(metadata_result, dict):
            model_key = metadata_result.get("model") or metadata_result.get("model_key")
        if not model_key:
            model_key = getattr(provider, "_model", None)
        if not model_key:
            model_key = getattr(provider, "_model_name", None)
        if not model_key:
            model_key = getattr(provider, "model_id", None) or getattr(provider, "name", "unknown")

        latency_ms = call_latency_ms
        if isinstance(cost_payload, dict) and isinstance(cost_payload.get("latency_ms"), (int, float)):
            latency_ms = float(cost_payload["latency_ms"])

        if latency_ms is None:
            latency_ms = (
                getattr(provider, "last_latency_ms", None)
                or getattr(provider, "_last_latency_ms", None)
                or getattr(provider, "latency_ms", None)
                or getattr(provider, "_last_response_latency_ms", None)
            )

        if latency_ms is not None:
            latency_ms = round(float(latency_ms), 2)

        return {
            "provider": getattr(provider, "name", "unknown"),
            "model": str(model_key),
            "backend": (
                getattr(provider, "_backend", None)
                or getattr(provider, "backend", None)
                or ""
            ),
            "latency_ms": latency_ms,
            "prompt_length": len(prompt or ""),
            "question_length": len(question or ""),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "usage": usage,
            "cost_usd": cost_payload.get("usd"),
            "raw_output_type": result_type,
        }

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

    def _contains_suspicious_text(self, value: Any) -> str | None:
        if isinstance(value, str):
            lower_val = value.lower()
            for pattern in self._SUSPICIOUS_ARG_PATTERNS:
                if pattern.lower() in lower_val:
                    return pattern
            return None
        if isinstance(value, list | tuple | set):
            for item in value:
                match = self._contains_suspicious_text(item)
                if match is not None:
                    return match
            return None
        if isinstance(value, dict):
            for item in list(value.keys()) + list(value.values()):
                match = self._contains_suspicious_text(item)
                if match is not None:
                    return match
            return None
        return None

    def _validate_args(self, tool: str, args: dict[str, Any]) -> str | None:
        """Validate tool arguments for injection / path traversal / abuse.
        Returns an error message string if validation fails, or None if clean.
        """
        for key, value in args.items():
            match = self._contains_suspicious_text(value)
            if match is not None:
                return (
                    f"Rejected tool '{tool}' arg '{key}': value contains suspicious pattern '{match}'"
                )
        return None

    def _resolve_planner_lot_args(
        self, tool: str, args: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
        """Resolve a user-visible item name to one unique lot for planner writes.

        The public mutation tools intentionally keep ``lot_id`` as their
        auditable target. The planner has richer context than a form field, so
        it may translate an exact canonical/display name when there is exactly
        one active match. This is deterministic entity resolution, not model
        inference. Ambiguous names are rejected before any write occurs.
        """
        if tool not in self._LOT_REFERENCE_TOOLS or not isinstance(args, dict):
            return args, None, None
        reference = args.get("lot_id")
        if not isinstance(reference, str) or not reference.strip():
            return args, None, None
        reference = reference.strip()

        # Preserve the existing lot-id and prefix contract first.
        lot_ids = self._db.get_inventory_lot_ids(reference)
        if len(lot_ids) == 1:
            if lot_ids[0] == reference:
                return args, None, None
            resolved = {**args, "lot_id": lot_ids[0]}
            return resolved, {"reference": reference, "lot_id": lot_ids[0], "method": "lot_id_prefix"}, None
        if len(lot_ids) > 1:
            return args, None, f"Lot reference '{reference}' is ambiguous, use more characters"

        normalized = reference.casefold()
        active_lots = self._db.get_inventory(status="active")
        matches = [
            lot for lot in active_lots
            if normalized in {
                str(getattr(lot, "canonical_name", "")).casefold(),
                str(getattr(lot, "display_name", "")).casefold(),
            }
        ]
        if len(matches) == 1:
            resolved_id = str(matches[0].lot_id)
            resolved = {**args, "lot_id": resolved_id}
            return resolved, {
                "reference": reference,
                "lot_id": resolved_id,
                "canonical_name": matches[0].canonical_name,
                "method": "unique_active_item_name",
            }, None
        if len(matches) > 1:
            return args, None, f"Item reference '{reference}' matches multiple inventory lots"
        return args, None, None

    def _resolve_planner_location_args(
        self, tool: str, args: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
        """Resolve a natural location phrase to one canonical location ID."""
        if tool != "move_inventory_item" or not isinstance(args, dict):
            return args, None, None
        reference = args.get("to_location_id")
        if not isinstance(reference, str) or not reference.strip():
            return args, None, None

        def normalize(value: str) -> str:
            return " ".join(value.casefold().replace("_", " ").replace("-", " ").split())

        target = normalize(reference)
        locations = self._db.get_locations()
        exact = [
            location for location in locations
            if target in {normalize(location.location_id), normalize(location.name)}
        ]
        candidates = exact or [
            location for location in locations
            if normalize(location.location_id) != "home"
            and normalize(location.name) in target
        ]
        if not candidates:
            return args, None, None
        longest = max(len(normalize(location.name)) for location in candidates)
        matches = [location for location in candidates if len(normalize(location.name)) == longest]
        if len(matches) != 1:
            return args, None, f"Location reference '{reference}' is ambiguous"
        location = matches[0]
        resolved_id = str(location.location_id)
        if resolved_id == reference:
            return args, None, None
        return (
            {**args, "to_location_id": resolved_id},
            {"reference": reference, "location_id": resolved_id, "method": "canonical_location_name" if exact else "location_name_subphrase"},
            None,
        )

    def _parse_tool_calls_from_result(
        self, result: str | list[Any] | dict[str, Any]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if isinstance(result, dict):
            raw_tool_calls = result.get("tool_calls")
            if isinstance(raw_tool_calls, list):
                raw_tool_calls = [c for c in raw_tool_calls if isinstance(c, dict)]
                tool_calls, diagnostics = parse_tool_calls_with_diagnostics(
                    json.dumps(raw_tool_calls, default=str)
                )
                diagnostics["source"] = "planner_plan_tool_calls_key"
                return tool_calls, diagnostics
            tool_name = result.get("tool")
            if tool_name and isinstance(tool_name, str):
                raw = json.dumps([{"tool": tool_name, "args": result.get("args", {})}])
                tool_calls, diagnostics = parse_tool_calls_with_diagnostics(raw)
                diagnostics["source"] = "planner_plan_tool_object"
                return tool_calls, diagnostics

            raw = str(result.get("text", ""))
            tool_calls, diagnostics = parse_tool_calls_with_diagnostics(raw)
            diagnostics["source"] = "planner_plan_text"
            return tool_calls, diagnostics

        if isinstance(result, list):
            try:
                raw = json.dumps(result, default=str)
            except Exception:
                raw = str(result)
            tool_calls, diagnostics = parse_tool_calls_with_diagnostics(raw)
            diagnostics["source"] = "planner_plan_list"
            return tool_calls, diagnostics

        tool_calls, diagnostics = parse_tool_calls_with_diagnostics(str(result or ""))
        diagnostics["source"] = "planner_plan_other"
        return tool_calls, diagnostics

    def _execute_tool_calls(
        self, tool_calls: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if self._cost_guarded():
            return (
                [{
                    "tool": "respond",
                    "success": False,
                    "error": self._cost_blocked_reason(),
                }],
                {
                    "status": "cost_blocked",
                    "tool_calls_requested": len(tool_calls),
                    "tool_calls_executed": 0,
                    "tool_calls_failed": 0,
                    "tool_calls_truncated": 0,
                    "tool_runs": [],
                    "cost_blocked": True,
                },
            )

        results: list[dict[str, Any]] = []
        limited = tool_calls[: self.MAX_TOOL_CALLS_PER_RUN]
        execution: dict[str, Any] = {
            "status": "pending",
            "tool_calls_requested": len(tool_calls),
            "tool_calls_executed": 0,
            "tool_calls_failed": 0,
            "tool_calls_truncated": max(0, len(tool_calls) - self.MAX_TOOL_CALLS_PER_RUN),
            "tool_runs": [],
            "cost_blocked": False,
        }

        if len(tool_calls) > self.MAX_TOOL_CALLS_PER_RUN:
            results.append({
                "tool": "respond",
                "success": True,
                "message": (
                    f"Planner requested {len(tool_calls)} actions; executing first {self.MAX_TOOL_CALLS_PER_RUN} for safety."
                ),
            })

        for tc in limited:
            run = {"tool": tc.get("tool", "respond"), "status": "started"}
            started = time.monotonic()

            tool = tc.get("tool", "respond")
            requested_args = tc.get("args", {})
            args, resolution, resolution_error = self._resolve_planner_lot_args(tool, requested_args)
            args, location_resolution, location_error = self._resolve_planner_location_args(tool, args)
            if resolution is not None:
                run["lot_resolution"] = resolution
            if location_resolution is not None:
                run["location_resolution"] = location_resolution
            resolution_error = resolution_error or location_error
            if resolution_error is not None:
                elapsed_ms = round((time.monotonic() - started) * 1000, 2)
                run["status"] = "lot_resolution_failed"
                run["error"] = resolution_error
                run["latency_ms"] = elapsed_ms
                execution["tool_runs"].append(run)
                execution["tool_calls_executed"] += 1
                execution["tool_calls_failed"] += 1
                results.append({
                    "tool": tool,
                    "success": False,
                    "error": resolution_error,
                    "latency_ms": elapsed_ms,
                })
                continue
            if tool == "respond":
                elapsed_ms = round((time.monotonic() - started) * 1000, 2)
                run["status"] = "respond"
                run["latency_ms"] = elapsed_ms
                execution["tool_runs"].append(run)
                execution["tool_calls_executed"] += 1
                msg = args.get("message", "")
                results.append({
                    "tool": "respond",
                    "success": True,
                    "message": msg,
                })
                continue

            validation_error = self._validate_args(tool, args)
            if validation_error is not None:
                elapsed_ms = round((time.monotonic() - started) * 1000, 2)
                run["status"] = "validation_failed"
                run["error"] = validation_error
                run["latency_ms"] = elapsed_ms
                execution["tool_runs"].append(run)
                execution["tool_calls_failed"] += 1
                execution["tool_calls_executed"] += 1
                results.append({
                    "tool": tool,
                    "success": False,
                    "error": validation_error,
                    "latency_ms": elapsed_ms,
                })
                continue

            tool_spec = self._tools._find_tool_spec(tool)
            if tool_spec is not None and tool_spec.mutability == "write":
                requires_confirmation = bool(tool_spec.needs_confirmation) or (
                    not settings.planner_allow_writes and tool != "create_or_update_shopping_list"
                )
                if requires_confirmation and not self._allow_confirmed_writes:
                    elapsed_ms = round((time.monotonic() - started) * 1000, 2)
                    if tool == "create_or_update_shopping_list":
                        item_count = 0
                        if isinstance(args.get("items"), list):
                            item_count = len(args.get("items", []))
                        summary = f"plan {item_count} shopping list item(s)"
                    elif "canonical_name" in args:
                        summary = f"modify '{args['canonical_name']}'"
                    else:
                        summary = f"apply '{tool}'"

                    reason = (
                        f"Planner write blocked by safety policy: {summary}. "
                        "Review and confirm this action in the relevant screen."
                    )
                    run["status"] = "blocked_by_policy"
                    run["error"] = reason
                    run["latency_ms"] = elapsed_ms
                    execution["tool_runs"].append(run)
                    execution["tool_calls_executed"] += 1
                    execution["tool_calls_failed"] += 1
                    results.append({
                        "tool": tool,
                        "success": False,
                        "error": reason,
                        "latency_ms": elapsed_ms,
                    })
                    continue

            try:
                outcome = self._tools.execute(tool, **args)
                elapsed_ms = round((time.monotonic() - started) * 1000, 2)
                tool_success = outcome.get("success", False)
                result = {
                    "tool": tool,
                    "success": bool(tool_success),
                    "result": outcome.get("result", outcome),
                    "error": outcome.get("error"),
                    "latency_ms": elapsed_ms,
                }
                if outcome.get("fault") is not None:
                    result["fault"] = outcome["fault"]
                execution["tool_calls_executed"] += 1
                if not tool_success:
                    run["status"] = "tool_failed"
                    run["error"] = outcome.get("error")
                    execution["tool_calls_failed"] += 1
                else:
                    run["status"] = "succeeded"
                run["latency_ms"] = elapsed_ms
                run["success"] = bool(tool_success)
                execution["tool_runs"].append(run)
                results.append(result)
            except Exception as e:
                elapsed_ms = round((time.monotonic() - started) * 1000, 2)
                run["status"] = "exception"
                run["error"] = str(e)
                run["latency_ms"] = elapsed_ms
                execution["tool_runs"].append(run)
                execution["tool_calls_executed"] += 1
                execution["tool_calls_failed"] += 1
                results.append({
                    "tool": tool,
                    "success": False,
                    "error": str(e),
                    "latency_ms": elapsed_ms,
                })

            if self._cost_guarded():
                blocked_msg = self._cost_blocked_reason()
                execution["cost_blocked"] = True
                results.append({
                    "tool": "respond",
                    "success": False,
                    "error": blocked_msg,
                })
                execution["tool_runs"].append({
                    "tool": "respond",
                    "status": "cost_blocked",
                    "error": blocked_msg,
                    "latency_ms": 0.0,
                })
                break

        if execution["cost_blocked"]:
            execution["status"] = "cost_blocked"
        elif execution["tool_calls_failed"]:
            execution["status"] = "partial_failure"
        elif execution["tool_calls_truncated"]:
            execution["status"] = "truncated"
        else:
            execution["status"] = "completed"
        return results, execution

    def _cost_guarded(self) -> bool:
        return self._cost_tracker.over_budget

    def _cost_blocked_reason(self) -> str:
        summary = self.session_cost
        return (
            "Cost budget exceeded. "
            f"Budget: ${summary['budget_limit']:.2f}, Spent: ${summary['total_cost']:.2f}."
        )

    def _budget_blocked_html(self) -> str:
        return _stat_card(body_html=(
            f"<div style='font-weight:600;color:var(--red);'>Cost budget blocked</div><div>{escape(self._cost_blocked_reason())}</div>"
        ))

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
                        f"<div style='padding:6px;margin:2px 0;color:var(--text-main);'><span style='color:var(--green);'>&#10003;</span> {action}</div>"
                    )
            else:
                err = outcome.get("error", "Unknown error")
                html_parts.append(
                    f"<div style='padding:6px;margin:2px 0;color:var(--red);'>&#10007; {escape(str(tool))}: {escape(str(err))}</div>"
                )

        if not html_parts:
            return _stat_card(body_html="No actions taken.")

        title = f"{settings.app_name} AI"
        body = "".join(html_parts)
        return _stat_card(body_html=(
            f"<div style='font-weight:600;margin-bottom:8px;'>{title}</div>{body}"
        ))
