"""Run a bounded real-model continuation evaluation with seeded result data.

The lookup result is seeded at the tool boundary so this script evaluates
planner continuation and explicit binding independently of market snapshot
availability. The temporary database is disposable and never uses the app's
configured database path.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shopstack.config import Settings, settings as global_settings
from shopstack.eval.recorder import ModelCallRecorder
from shopstack.eval.storage import JsonlSink, SqliteSink
from shopstack.persistence.database import Database
from shopstack.planner.engine import PlannerEngine
from shopstack.providers.registry import ProviderRegistry
from shopstack.tools.registry import ToolRegistry


def _markdown(report: dict[str, Any]) -> str:
    result = report["result"]
    if report["fixture"] == "empty_substitute_result":
        evidence_text = (
            "The real model selected the substitute lookup, and the seeded empty "
            "result stopped the protocol before any mutation or retry."
        )
    else:
        evidence_text = (
            "The real model selected the continuation steps, but the substitute "
            "lookup was seeded at the local tool boundary."
        )
    return "\n".join([
        "# ShopStack OpenAI continuation evaluation",
        "",
        f"Date: {report['started_at'][:10]}",
        f"Model: `{report['model']}`",
        "Reasoning: `high`",
        "Protocol: `1.0`",
        f"Fixture: {report['fixture']}, disposable SQLite world",
        "",
        "## Result",
        "",
        f"- Status: `{result.get('status')}`",
        f"- Steps executed: {result.get('steps_executed')}",
        f"- Binding resolutions: {sum(len(step.get('binding_resolutions', [])) for step in result.get('steps', []))}",
        f"- Final shopping-list items: {', '.join(item.get('canonical_name', '') for item in report['final_state']['shopping_list_items']) or '(none)' }",
        f"- Contract checks: {sum(1 for check in report['checks'] if check['passed'])}/{len(report['checks'])} passed",
        f"- Estimated cost: `${report['estimated_cost_usd']:.6f}`",
        f"- Provider latency total: {report['provider_latency_ms']:.2f} ms",
        "",
        "## Evidence boundary",
        "",
        evidence_text,
        "This proves the planner, parser,",
        "binder, tool registry, and disposable state transition for this fixture.",
        "It does not prove market-data freshness, production autonomy, or repeated",
        "quality variance. Production confirmation defaults and existing environment",
        "keys were not changed.",
        "",
        "## Contract checks",
        "",
        *[f"- {'PASS' if check['passed'] else 'FAIL'}: {check['name']}" for check in report["checks"]],
        "",
        "## Structured result",
        "",
        "```json",
        json.dumps(result, indent=2, ensure_ascii=False, default=str),
        "```",
        "",
    ])


def _contract_checks(
    fixture: str,
    result: dict[str, Any],
    final_state: dict[str, Any],
) -> list[dict[str, Any]]:
    steps = result.get("steps", [])
    items = final_state.get("shopping_list_items", [])
    if fixture == "empty_substitute_result":
        checks = [
            ("empty_result_stops_protocol", result.get("status") == "empty_intermediate"),
            ("empty_result_uses_one_step", result.get("steps_executed") == 1),
            ("empty_result_has_no_mutation", not items),
            ("empty_result_does_not_retry", len(steps) == 1),
        ]
    else:
        binding = [
            resolution
            for step in steps
            for resolution in step.get("binding_resolutions", [])
        ]
        checks = [
            ("seeded_flow_completes_write", result.get("status") == "write_completed"),
            ("seeded_flow_uses_two_steps", result.get("steps_executed") == 2),
            ("first_step_is_substitute_lookup", steps and steps[0].get("requested_tool_call", {}).get("tool") == "find_substitute"),
            ("second_step_is_shopping_mutation", len(steps) > 1 and steps[1].get("requested_tool_call", {}).get("tool") == "create_or_update_shopping_list"),
            ("second_step_uses_explicit_reference", any(item.get("reference") == "step_1.result.0.substitute" for item in binding)),
            ("reference_resolves_to_tofu", any(item.get("value") == "tofu" for item in binding)),
            ("final_state_contains_tofu", [item.get("canonical_name") for item in items] == ["tofu"]),
            ("no_protocol_violation", not any(step.get("protocol_violation") for step in steps)),
        ]
    return [{"name": name, "passed": bool(passed)} for name, passed in checks]


def run(model: str, output: Path, fixture: str = "seeded_substitute_result") -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    with tempfile.TemporaryDirectory(prefix="shopstack-continuation-") as temp_dir:
        db_path = Path(temp_dir) / "world.db"
        recorder_path = Path(temp_dir) / "model-calls.db"
        db = Database(str(db_path))
        try:
            tools = ToolRegistry(db)
            from shopstack.providers.openai_provider import OpenAIProvider

            provider = OpenAIProvider(
                api_key=os.environ.get("SHOPSTACK_OPENAI_API_KEY")
                or os.environ.get("OPENAI_API_KEY", ""),
                model=model,
            )
            if not provider.available:
                raise RuntimeError(provider.error or "OpenAI provider unavailable")
            registry = ProviderRegistry(
                Settings(_env_file=None, db_path=str(db_path), planner_backend="mock")
            )
            registry.register("planner", provider)

            original_execute = tools.execute

            def execute(tool_name: str, **kwargs: Any) -> dict[str, Any]:
                if tool_name == "find_substitute":
                    seeded_result = [] if fixture == "empty_substitute_result" else [{
                        "substitute": "tofu",
                        "display": "Tofu",
                        "type": "ingredient_swap",
                        "reason": "Seeded evaluation candidate",
                        "price": 80,
                    }]
                    return {
                        "success": True,
                        "result": seeded_result,
                        "tool": tool_name,
                    }
                return original_execute(tool_name, **kwargs)

            tools.execute = execute  # type: ignore[method-assign]
            old_allow_writes = global_settings.planner_allow_writes
            old_recorder = ModelCallRecorder._instance
            global_settings.planner_allow_writes = True
            ModelCallRecorder._instance = ModelCallRecorder(
                jsonl_sink=JsonlSink(recorder_path.with_suffix(".jsonl")),
                sqlite_sink=SqliteSink(recorder_path),
            )
            try:
                engine = PlannerEngine(db, tools, registry, allow_confirmed_writes=True)
                result = engine.process_continuation(
                    "Find a substitute for unavailable paneer, then add the selected substitute to the shopping list.",
                    max_steps=3,
                    generation={"max_tokens": 768, "temperature": 0.0, "reasoning_effort": "high"},
                )
                active_list = db.get_active_shopping_list()
                final_state = {
                    "shopping_list_items": [
                        item.model_dump() for item in (active_list.items if active_list else [])
                    ],
                }
                checks = _contract_checks(fixture, result, final_state)
            finally:
                global_settings.planner_allow_writes = old_allow_writes
                ModelCallRecorder._instance = old_recorder
            provider_latency_ms = sum(
                float(step.get("provider", {}).get("latency_ms") or 0.0)
                for step in result.get("steps", [])
            )
            estimated_cost_usd = sum(
                float(step.get("provider", {}).get("cost_usd") or 0.0)
                for step in result.get("steps", [])
            )
            report = {
                "started_at": started_at,
                "ended_at": datetime.now(UTC).isoformat(),
                "model": model,
                "provider": "openai",
                "fixture": fixture,
                "temporary_database": True,
                "provider_latency_ms": provider_latency_ms,
                "estimated_cost_usd": estimated_cost_usd,
                "final_state": final_state,
                "checks": checks,
                "result": result,
            }
        finally:
            db.force_close_all_connections()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n")
    output.with_suffix(".md").write_text(_markdown(report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument(
        "--fixture",
        choices=("seeded_substitute_result", "empty_substitute_result"),
        default="seeded_substitute_result",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("Docs/evals/openai_continuation_luna_20260826.json"),
    )
    args = parser.parse_args()
    report = run(args.model, args.output, args.fixture)
    print(json.dumps({
        "status": report["result"].get("status"),
        "steps_executed": report["result"].get("steps_executed"),
        "output": str(args.output),
    }))


if __name__ == "__main__":
    run_started = time.monotonic()
    main()
    print(f"elapsed_seconds={time.monotonic() - run_started:.2f}")
