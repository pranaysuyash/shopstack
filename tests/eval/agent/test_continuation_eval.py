from __future__ import annotations

from shopstack.eval.agent.continuation_corpus import build_continuation_scenarios
from shopstack.eval.agent.continuation_eval import ContinuationEvalRunner, continuation_summary
from shopstack.eval.agent.schema import EvalModelConfig, EvalStatus
from shopstack.eval.agent.storage import AgentEvalStorage


def test_continuation_corpus_has_unique_contracts_and_expected_fault_families():
    scenarios = build_continuation_scenarios()

    assert len(scenarios) == 10
    assert len({scenario.id for scenario in scenarios}) == len(scenarios)
    assert {scenario.expected_status for scenario in scenarios} == {
        "write_completed",
        "empty_intermediate",
        "tool_failed",
        "stale_intermediate",
        "binding_failed",
        "duplicate_action",
        "multiple_calls_truncated",
    }
    assert {scenario.faults[0].kind for scenario in scenarios if scenario.faults} == {
        "tool_error",
        "timeout",
        "stale",
    }


def test_mock_continuation_suite_passes_and_preserves_contract_statuses(tmp_path):
    db_path = tmp_path / "continuation-eval.db"
    model = EvalModelConfig(
        key="mock",
        requested_model="mock-planner-v1",
        backend="mock",
        provider="mock",
        generation={"temperature": 0.0},
    )

    metadata, results = ContinuationEvalRunner([model], result_db=db_path).run()

    assert metadata.scenario_count == 10
    assert len(results) == 10
    assert all(result.status is EvalStatus.PASSED for result in results)
    assert all(result.task_success for result in results)
    assert {result.planner_outcome for result in results} == {
        "write_completed",
        "empty_intermediate",
        "tool_failed",
        "stale_intermediate",
        "binding_failed",
        "duplicate_action",
        "multiple_calls_truncated",
    }
    assert continuation_summary(results)["models"]["mock"]["success_rate"] == 1.0


def test_continuation_suite_persists_cases_with_trace_and_failure_evidence(tmp_path):
    db_path = tmp_path / "continuation-persistence.db"
    model = EvalModelConfig(key="mock", requested_model="mock-planner-v1", backend="mock", provider="mock")
    metadata, results = ContinuationEvalRunner([model], result_db=db_path).run()

    storage = AgentEvalStorage(db_path)
    try:
        storage.save(metadata, results)
        stored = storage.results(run_id=metadata.run_id)
    finally:
        storage.close()

    assert len(stored) == 10
    assert all(row.trace_id.startswith(f"continuation-eval:{metadata.run_id}:") for row in stored)
    assert next(row for row in stored if row.scenario_id == "CONT-006").failure_codes == []
    assert next(row for row in stored if row.scenario_id == "CONT-010").failure_codes == []


def test_interrupted_continuation_run_resumes_without_reexecuting_completed_cases(tmp_path):
    db_path = tmp_path / "continuation-resume.db"
    model = EvalModelConfig(key="mock", requested_model="mock-planner-v1", backend="mock", provider="mock")
    runner = ContinuationEvalRunner([model], result_db=db_path)

    interrupted_metadata, interrupted_results = runner.run(max_cases=3)
    assert interrupted_metadata.interrupted is True
    assert len(interrupted_results) == 3

    resumed_metadata, resumed_results = ContinuationEvalRunner([model], result_db=db_path).run(
        resume_run_id=interrupted_metadata.run_id,
    )

    assert resumed_metadata.run_id == interrupted_metadata.run_id
    assert resumed_metadata.interrupted is False
    assert len(resumed_results) == 10
    assert [result.scenario_id for result in resumed_results[:3]] == ["CONT-001", "CONT-002", "CONT-003"]
    assert all(result.task_success for result in resumed_results)
    storage = AgentEvalStorage(db_path)
    try:
        assert len(storage.results(run_id=resumed_metadata.run_id)) == 10
        assert storage.completed_keys(resumed_metadata.run_id) == {
            (result.scenario_id, result.model_key) for result in resumed_results
        }
    finally:
        storage.close()


def test_resume_rejects_a_different_evaluation_shape(tmp_path):
    db_path = tmp_path / "continuation-resume-shape.db"
    model = EvalModelConfig(key="mock", requested_model="mock-planner-v1", backend="mock", provider="mock")
    metadata, _ = ContinuationEvalRunner([model], result_db=db_path).run(max_cases=1)

    try:
        ContinuationEvalRunner(
            [EvalModelConfig(key="other", requested_model="other", backend="mock", provider="mock")],
            result_db=db_path,
        ).run(resume_run_id=metadata.run_id)
    except ValueError as exc:
        assert "model configuration" in str(exc)
    else:
        raise AssertionError("resume unexpectedly accepted a different model set")
