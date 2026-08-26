"""Scenario runner attached to the real PlannerEngine path."""
from __future__ import annotations

import os
import platform
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from shopstack.config import Settings, settings as global_settings
from shopstack.eval.agent.failures import FailureCode
from shopstack.eval.agent.fixtures import IsolatedWorld
from shopstack.eval.agent.faults import FaultInjectingToolRegistry
from shopstack.eval.agent.schema import EvalCaseResult, EvalModelConfig, EvalRunMetadata, EvalStatus, Scenario
from shopstack.eval.agent.scorers import score_case
from shopstack.eval.agent.loader import assert_valid_suite
from shopstack.eval.recorder import ModelCallRecorder
from shopstack.eval.storage import JsonlSink, SqliteSink
from shopstack.planner.engine import PlannerEngine
from shopstack.providers.registry import ProviderRegistry


class AgentEvalRunner:
    def __init__(self, models: list[EvalModelConfig], *, result_db: str | Path | None = None):
        self.models = [model for model in models if model.enabled]
        self.result_db = str(result_db) if result_db else None

    def _provider(self, model: EvalModelConfig, db_path: str) -> tuple[ProviderRegistry, Any, str | None]:
        if model.backend == "openai":
            from shopstack.providers.openai_provider import OpenAIProvider
            provider = OpenAIProvider(
                api_key=os.environ.get("SHOPSTACK_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", ""),
                model=model.requested_model,
            )
            if not provider.available:
                return ProviderRegistry(Settings(_env_file=None, db_path=db_path, planner_backend="mock")), provider, provider.error
            registry = ProviderRegistry(Settings(_env_file=None, db_path=db_path, planner_backend="mock"))
            registry.register("planner", provider)
            return registry, provider, None
        local_settings = Settings(
            _env_file=None,
            db_path=db_path,
            planner_backend=model.backend or "mock",
            off_the_grid=True,
            local_auto_download=False,
            planner_allow_writes=True,
        )
        registry = ProviderRegistry(local_settings)
        provider = registry.planner
        rows = {row.get("name"): row for row in registry.list_providers()}
        row = rows.get("planner", {})
        if model.backend not in {"", "mock", "mocked"} and row.get("status") == "fallback":
            return registry, provider, FailureCode.FALLBACK_DETECTED.value
        if not getattr(provider, "available", False):
            return registry, provider, FailureCode.PROVIDER_UNAVAILABLE.value
        return registry, provider, None

    def run_case(self, scenario: Scenario, model: EvalModelConfig, *, run_id: str) -> EvalCaseResult:
        trace_id = f"agent-eval:{run_id}:{scenario.id}:{model.key}:1"
        with IsolatedWorld(scenario.initial_state) as world:
            assert world.db is not None and world.tools is not None
            registry, provider, provider_error = self._provider(model, str(world.db.db_path))
            if provider_error:
                return EvalCaseResult(
                    run_id=run_id, scenario_id=scenario.id, model_key=model.key,
                    requested_model=model.requested_model, actual_model=None,
                    backend=model.backend, provider=model.provider, trace_id=trace_id,
                    status=EvalStatus.UNAVAILABLE,
                    failure_codes=[provider_error], error=provider_error,
                )
            eval_tools = FaultInjectingToolRegistry(world.tools, scenario.faults)
            # Isolated evaluation has explicit authorization to execute the
            # proposed write so final-state assertions can be measured. The
            # production default remains confirmation-gated.
            engine = PlannerEngine(world.db, eval_tools, registry, allow_confirmed_writes=True)
            old_instance = ModelCallRecorder._instance
            old_allow_writes = global_settings.planner_allow_writes
            # The isolated world is the only place where the eval permits
            # writes. The global setting is restored before leaving this case.
            global_settings.planner_allow_writes = True
            recorder_db = self.result_db or str(Path(world.db.db_path).with_name("model-calls.db"))
            ModelCallRecorder._instance = ModelCallRecorder(
                jsonl_sink=JsonlSink(Path(recorder_db).with_suffix(".jsonl")),
                sqlite_sink=SqliteSink(recorder_db),
            )
            try:
                before_snapshot = world.snapshot()
                response = engine.process_structured(
                    scenario.request,
                    compact_tools=model.compact_tools,
                    trace_id=trace_id,
                    generation=model.generation,
                )
                record_rows = SqliteSink(recorder_db).query(trace_id=trace_id, limit=1)
                record = record_rows[0] if record_rows else None
                if record and not (record.get("input_tokens") or record.get("output_tokens")):
                    record = dict(record)
                    record["cost_usd"] = None
                result = score_case(
                    scenario, response, world, run_id=run_id, model=model,
                    trace_id=trace_id, call_record=record,
                    before_snapshot=before_snapshot,
                )
                return result
            except KeyboardInterrupt:
                return EvalCaseResult(
                    run_id=run_id, scenario_id=scenario.id, model_key=model.key,
                    requested_model=model.requested_model, trace_id=trace_id,
                    status=EvalStatus.INTERRUPTED, failure_codes=[FailureCode.INTERNAL_EVAL_ERROR.value],
                )
            except Exception as exc:
                return EvalCaseResult(
                    run_id=run_id, scenario_id=scenario.id, model_key=model.key,
                    requested_model=model.requested_model, trace_id=trace_id,
                    status=EvalStatus.ERROR, failure_codes=[FailureCode.INTERNAL_EVAL_ERROR.value],
                    error=str(exc),
                )
            finally:
                global_settings.planner_allow_writes = old_allow_writes
                ModelCallRecorder._instance = old_instance

    def run(
        self,
        scenarios: list[Scenario] | None = None,
        *,
        run_id: str | None = None,
        on_result: Callable[[EvalCaseResult], None] | None = None,
    ) -> tuple[EvalRunMetadata, list[EvalCaseResult]]:
        scenarios = scenarios if scenarios is not None else assert_valid_suite()
        run_id = run_id or uuid.uuid4().hex
        started = datetime.now(UTC).isoformat()
        metadata = EvalRunMetadata(
            run_id=run_id, suite_version=1, scenario_count=len(scenarios),
            policy_version=1, started_at=started, python_version=platform.python_version(),
            os=platform.platform(), model_configs=self.models,
        )
        results: list[EvalCaseResult] = []
        try:
            for model in self.models:
                for scenario in scenarios:
                    result = self.run_case(scenario, model, run_id=run_id)
                    results.append(result)
                    if on_result:
                        on_result(result)
        except KeyboardInterrupt:
            metadata.interrupted = True
        finally:
            metadata.ended_at = datetime.now(UTC).isoformat()
        return metadata, results
