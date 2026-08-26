"""Reusable scenario runner and scorer for planner continuations."""
from __future__ import annotations

import os
import platform
import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shopstack.config import Settings, settings as global_settings
from shopstack.eval.agent.continuation_corpus import build_continuation_scenarios
from shopstack.eval.agent.faults import FaultInjectingToolRegistry
from shopstack.eval.agent.fixtures import IsolatedWorld
from shopstack.eval.agent.schema import (
    ContinuationScenario,
    EvalCaseResult,
    EvalModelConfig,
    EvalRunMetadata,
    EvalStatus,
    MetricScores,
    ToolCallEvidence,
)
from shopstack.eval.recorder import ModelCallRecorder
from shopstack.eval.storage import JsonlSink, SqliteSink
from shopstack.eval.agent.storage import AgentEvalStorage
from shopstack.planner.engine import PlannerEngine
from shopstack.providers.registry import ProviderRegistry


class _ScriptedPlanner:
    available = True
    name = "scripted-continuation"
    backend = "mock"
    model_id = "scripted-continuation"

    def __init__(self, responses: list[Any]):
        self._responses = iter(responses)

    def plan(self, _payload: dict[str, Any]) -> Any:
        try:
            return next(self._responses)
        except StopIteration:
            return {"tool_calls": [{"tool": "respond", "args": {"message": "no scripted response"}}]}


class _FixtureToolRegistry:
    """Add deterministic result fixtures above the normal fault wrapper."""

    def __init__(self, registry: Any, fixture_results: dict[str, Any], faults: list[Any]):
        self._registry = FaultInjectingToolRegistry(registry, faults)
        self._fixture_results = fixture_results

    def execute(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        if tool_name in self._fixture_results:
            return {
                "success": True,
                "result": self._fixture_results[tool_name],
                "tool": tool_name,
            }
        return self._registry.execute(tool_name, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._registry, name)


def _check(
    assertions: list[dict[str, Any]],
    name: str,
    passed: bool,
    failure_code: str,
) -> None:
    assertions.append({"kind": name, "passed": bool(passed)})
    if not passed:
        assertions[-1]["failure_code"] = failure_code


def score_continuation(
    scenario: ContinuationScenario,
    response: dict[str, Any],
    before_snapshot: dict[str, Any],
    after_snapshot: dict[str, Any],
    *,
    run_id: str,
    model: EvalModelConfig,
    trace_id: str,
) -> EvalCaseResult:
    """Score a continuation response against its typed contract."""
    assertions: list[dict[str, Any]] = []
    steps = response.get("steps") if isinstance(response.get("steps"), list) else []
    actual_tools = [
        step.get("requested_tool_call", {}).get("tool")
        for step in steps
        if isinstance(step.get("requested_tool_call"), dict)
    ]
    bindings = [
        resolution.get("reference")
        for step in steps
        for resolution in step.get("binding_resolutions", [])
        if isinstance(resolution, dict)
    ]
    final_items = [
        item.get("canonical_name")
        for item in (after_snapshot.get("shopping_list") or {}).get("items", [])
        if isinstance(item, dict)
    ]

    _check(assertions, "status", response.get("status") == scenario.expected_status, "EXECUTION_ERROR")
    _check(assertions, "step_count", response.get("steps_executed") == scenario.expected_steps, "STATE_MISMATCH")
    _check(assertions, "tool_sequence", actual_tools == scenario.expected_tool_sequence, "WRONG_TOOL")
    _check(
        assertions,
        "binding_references",
        all(reference in bindings for reference in scenario.expected_binding_references),
        "ARG_WRONG_VALUE",
    )
    _check(
        assertions,
        "final_list_items",
        final_items == scenario.expected_list_items,
        "STATE_MISMATCH",
    )
    if scenario.expect_no_mutation:
        _check(assertions, "no_mutation", before_snapshot == after_snapshot, "UNNECESSARY_MUTATION")

    failed = [assertion for assertion in assertions if not assertion["passed"]]
    failure_codes = sorted({assertion["failure_code"] for assertion in failed})
    actual_model = next(
        (
            step.get("provider", {}).get("model")
            for step in steps
            if step.get("provider", {}).get("model")
        ),
        None,
    )
    tool_evidence = [
        ToolCallEvidence(
            tool=str(step.get("requested_tool_call", {}).get("tool", "")),
            args=step.get("requested_tool_call", {}).get("args", {}),
            outcome=(step.get("outcomes") or [{}])[0],
        )
        for step in steps
        if isinstance(step.get("requested_tool_call"), dict)
    ]
    provider_rows = [step.get("provider", {}) for step in steps]
    latency_values = [float(row.get("latency_ms")) for row in provider_rows if row.get("latency_ms") is not None]
    cost_values = [float(row.get("cost_usd")) for row in provider_rows if row.get("cost_usd") is not None]
    passed_count = len(assertions) - len(failed)
    score = passed_count / len(assertions) if assertions else 0.0
    status = EvalStatus.PASSED if not failed else EvalStatus.FAILED
    return EvalCaseResult(
        run_id=run_id,
        scenario_id=scenario.id,
        model_key=model.key,
        requested_model=model.requested_model,
        actual_model=actual_model,
        backend=model.backend,
        provider=model.provider,
        trace_id=trace_id,
        status=status,
        tool_calls=tool_evidence,
        task_success=not failed,
        composite_score=round(score, 4),
        metrics=MetricScores(
            task_correctness=score,
            tool_selection=float("tool_sequence" not in {row["kind"] for row in failed}),
            argument_accuracy=float("binding_references" not in {row["kind"] for row in failed}),
            final_state=float("final_list_items" not in {row["kind"] for row in failed}),
            constraints=float("no_mutation" not in {row["kind"] for row in failed}),
        ),
        assertions=assertions,
        failure_codes=failure_codes,
        latency_ms=round(sum(latency_values), 2) if latency_values else None,
        input_tokens=sum(int(row.get("input_tokens") or 0) for row in provider_rows),
        output_tokens=sum(int(row.get("output_tokens") or 0) for row in provider_rows),
        cost_usd=round(sum(cost_values), 6) if cost_values else None,
        planner_outcome=str(response.get("status", "")),
        error="; ".join(f"{row['kind']} failed" for row in failed),
    )


class ContinuationEvalRunner:
    """Run continuation scenarios using real or scripted planner models."""

    def __init__(self, models: list[EvalModelConfig], *, result_db: str | Path | None = None):
        self.models = [model for model in models if model.enabled]
        self.result_db = str(result_db) if result_db else None

    def _provider(
        self,
        scenario: ContinuationScenario,
        model: EvalModelConfig,
        db_path: str,
    ) -> tuple[ProviderRegistry, Any, str | None]:
        if model.backend == "openai":
            from shopstack.providers.openai_provider import OpenAIProvider

            provider = OpenAIProvider(
                api_key=os.environ.get("SHOPSTACK_OPENAI_API_KEY")
                or os.environ.get("OPENAI_API_KEY", ""),
                model=model.requested_model,
            )
            if not provider.available:
                return ProviderRegistry(Settings(_env_file=None, db_path=db_path, planner_backend="mock")), provider, "PROVIDER_UNAVAILABLE"
        else:
            provider = _ScriptedPlanner(scenario.scripted_responses)
        registry = ProviderRegistry(Settings(_env_file=None, db_path=db_path, planner_backend="mock"))
        registry.register("planner", provider)
        return registry, provider, None

    def run_case(
        self,
        scenario: ContinuationScenario,
        model: EvalModelConfig,
        *,
        run_id: str,
    ) -> EvalCaseResult:
        trace_id = f"continuation-eval:{run_id}:{scenario.id}:{model.key}:1"
        with IsolatedWorld(scenario.initial_state) as world:
            assert world.db is not None and world.tools is not None
            registry, provider, provider_error = self._provider(scenario, model, str(world.db.db_path))
            if provider_error:
                return EvalCaseResult(
                    run_id=run_id,
                    scenario_id=scenario.id,
                    model_key=model.key,
                    requested_model=model.requested_model,
                    backend=model.backend,
                    provider=model.provider,
                    trace_id=trace_id,
                    status=EvalStatus.UNAVAILABLE,
                    failure_codes=[provider_error],
                    error=provider_error,
                )
            fixture_tools = _FixtureToolRegistry(world.tools, scenario.fixture_results, scenario.faults)
            old_allow_writes = global_settings.planner_allow_writes
            old_recorder = ModelCallRecorder._instance
            recorder_db = self.result_db or str(Path(world.db.db_path).with_name("model-calls.db"))
            ModelCallRecorder._instance = ModelCallRecorder(
                jsonl_sink=JsonlSink(Path(recorder_db).with_suffix(".jsonl")),
                sqlite_sink=SqliteSink(recorder_db),
            )
            global_settings.planner_allow_writes = False
            try:
                before_snapshot = world.snapshot()
                engine = PlannerEngine(world.db, fixture_tools, registry)
                response = engine.process_continuation(
                    scenario.request,
                    max_steps=3,
                    generation=model.generation,
                    trace_id=trace_id,
                )
                after_snapshot = world.snapshot()
                return score_continuation(
                    scenario,
                    response,
                    before_snapshot,
                    after_snapshot,
                    run_id=run_id,
                    model=model,
                    trace_id=trace_id,
                )
            except Exception as exc:
                return EvalCaseResult(
                    run_id=run_id,
                    scenario_id=scenario.id,
                    model_key=model.key,
                    requested_model=model.requested_model,
                    backend=model.backend,
                    provider=model.provider,
                    trace_id=trace_id,
                    status=EvalStatus.ERROR,
                    failure_codes=["INTERNAL_EVAL_ERROR"],
                    error=str(exc),
                )
            finally:
                global_settings.planner_allow_writes = old_allow_writes
                ModelCallRecorder._instance = old_recorder

    def run(
        self,
        scenarios: Iterable[ContinuationScenario] | None = None,
        *,
        run_id: str | None = None,
        resume_run_id: str | None = None,
        max_cases: int | None = None,
        on_result: Callable[[EvalCaseResult], None] | None = None,
    ) -> tuple[EvalRunMetadata, list[EvalCaseResult]]:
        selected = list(scenarios or build_continuation_scenarios())
        run_id = resume_run_id or run_id or uuid.uuid4().hex
        storage = None if not self.result_db or self.result_db == ":memory:" else AgentEvalStorage(self.result_db)
        existing: dict[tuple[str, str], EvalCaseResult] = {}
        if resume_run_id:
            if storage is None:
                raise ValueError("resume requires a file-backed result database")
            prior_metadata = storage.run_metadata(resume_run_id)
            if prior_metadata is None:
                raise ValueError(f"cannot resume unknown run: {resume_run_id}")
            prior_model_keys = {model.key for model in prior_metadata.model_configs}
            current_model_keys = {model.key for model in self.models}
            if prior_model_keys != current_model_keys:
                raise ValueError("resume model configuration does not match the existing run")
            if prior_metadata.scenario_count != len(selected):
                raise ValueError("resume scenario count does not match the existing run")
            existing = {
                (result.scenario_id, result.model_key): result
                for result in storage.results(run_id=resume_run_id)
            }
            metadata = prior_metadata
            metadata.scenario_count = len(selected)
            metadata.ended_at = None
            metadata.interrupted = False
            metadata.model_configs = self.models
        else:
            metadata = EvalRunMetadata(
                run_id=run_id,
                suite_version=1,
                scenario_count=len(selected),
                policy_version=1,
                started_at=datetime.now(UTC).isoformat(),
                python_version=platform.python_version(),
                os=platform.platform(),
                model_configs=self.models,
            )
        if storage is not None:
            storage.save_run(metadata)

        results: list[EvalCaseResult] = []
        executed = 0
        try:
            for model in self.models:
                for scenario in selected:
                    key = (scenario.id, model.key)
                    if key in existing:
                        results.append(existing[key])
                        continue
                    if max_cases is not None and executed >= max_cases:
                        metadata.interrupted = True
                        break
                    result = self.run_case(scenario, model, run_id=run_id)
                    results.append(result)
                    existing[key] = result
                    executed += 1
                    if storage is not None:
                        storage.save_case(result)
                    if on_result is not None:
                        on_result(result)
                if metadata.interrupted:
                    break
        finally:
            metadata.ended_at = datetime.now(UTC).isoformat()
            if storage is not None:
                storage.save_run(metadata)
                storage.close()
        return metadata, results


def continuation_summary(results: list[EvalCaseResult]) -> dict[str, Any]:
    """Aggregate continuation cases without conflating them with one-shot cases."""
    by_model: dict[str, list[EvalCaseResult]] = {}
    for result in results:
        by_model.setdefault(result.model_key, []).append(result)
    return {
        "cases": len(results),
        "models": {
            model: {
                "cases": len(rows),
                "passed": sum(row.task_success for row in rows),
                "success_rate": round(sum(row.task_success for row in rows) / len(rows), 4),
                "mean_composite": round(sum(row.composite_score for row in rows) / len(rows), 4),
                "total_cost_usd": round(sum(row.cost_usd or 0.0 for row in rows), 6),
                "mean_latency_ms": round(
                    sum(row.latency_ms or 0.0 for row in rows) / len(rows), 2
                ),
                "failures": {
                    code: sum(code in row.failure_codes for row in rows)
                    for code in sorted({code for row in rows for code in row.failure_codes})
                },
            }
            for model, rows in by_model.items()
        },
    }
