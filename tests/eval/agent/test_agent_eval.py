from __future__ import annotations

from pathlib import Path

from shopstack.eval.agent.aggregate import summarize
from shopstack.eval.agent.failures import FailureCode
from shopstack.eval.agent.fixtures import IsolatedWorld
from shopstack.eval.agent.faults import FaultInjectingToolRegistry
from shopstack.eval.agent.loader import load_scenarios, validate_suite
from shopstack.eval.agent.recommend import recommend
from shopstack.eval.agent.scorers import score_case
from shopstack.eval.agent.schema import EvalModelConfig
from shopstack.eval.agent.storage import AgentEvalStorage
from shopstack.eval.agent.runner import AgentEvalRunner


def test_committed_corpus_is_exactly_50_and_runtime_complete():
    scenarios = load_scenarios()
    assert len(scenarios) == 50
    assert not validate_suite(scenarios)
    assert len({scenario.id for scenario in scenarios}) == 50


def test_isolated_world_uses_temp_db_and_canonical_seeders():
    with IsolatedWorld({"inventory": [{"canonical_name": "milk", "quantity": 2, "unit": "L", "storage_location_id": "fridge"}]}) as world:
        assert world.db is not None
        assert Path(world.db.db_path).exists()
        assert [lot.canonical_name for lot in world.db.get_inventory(user_id=world.user_id)] == ["milk"]
        assert str(world.db.db_path).startswith("/var/folders/") or "shopstack-agent-eval-" in str(world.db.db_path)


def test_fault_wrapper_intercepts_only_target_tool():
    with IsolatedWorld() as world:
        assert world.tools is not None
        wrapper = FaultInjectingToolRegistry(world.tools, [{"tool": "find_item", "kind": "empty"}])
        empty = wrapper.execute("find_item", query="milk")
        assert empty["fault"] == "empty"
        normal = wrapper.execute("get_next_buy_suggestions")
        assert normal["success"] is True


def test_runner_trace_and_persistence_are_correlated(tmp_path):
    db_path = tmp_path / "eval.db"
    model = EvalModelConfig(key="mock", requested_model="mock-planner-v1", backend="mock", provider="mock")
    runner = AgentEvalRunner([model], result_db=db_path)
    metadata, results = runner.run([load_scenarios()[0]])
    assert len(results) == 1
    result = results[0]
    assert result.trace_id.startswith(f"agent-eval:{metadata.run_id}:ST-001:mock:1")
    storage = AgentEvalStorage(db_path)
    try:
        storage.save(metadata, results)
        stored = storage.results(run_id=metadata.run_id)
        assert len(stored) == 1
        assert stored[0].trace_id == result.trace_id
        assert stored[0].requested_model == "mock-planner-v1"
    finally:
        storage.close()


def test_recommendation_is_eligibility_first_and_advisory():
    scenarios = load_scenarios()
    result = AgentEvalRunner([EvalModelConfig(key="mock", requested_model="mock", backend="mock")], result_db=":memory:")
    _metadata, rows = result.run(scenarios[:1])
    decision = recommend(summarize(rows, scenarios[:1]))
    assert decision["routing_mutated"] is False
    assert decision["decision"] == "NO_WINNER"


def test_failure_codes_are_specific():
    assert FailureCode.INVALID_TOOL.value == "INVALID_TOOL"
    assert FailureCode.ARG_WRONG_VALUE.value != FailureCode.STATE_MISMATCH.value


def test_failed_write_cannot_hide_a_state_change():
    scenario = next(item for item in load_scenarios() if item.id == "IC-006")
    with IsolatedWorld() as world:
        assert world.tools is not None
        before = world.snapshot()
        added = world.tools.execute(
            "add_inventory_item",
            canonical_name="milk",
            display_name="Milk",
            quantity=1,
            unit="L",
            storage_location_id="fridge",
        )
        failed = world.tools.execute(
            "move_inventory_item",
            lot_id="missing",
            to_location_id="pantry",
        )
        result = score_case(
            scenario,
            {
                "tool_calls": [
                    {"tool": "add_inventory_item", "args": {"canonical_name": "milk"}},
                    {"tool": "move_inventory_item", "args": {"lot_id": "missing", "to_location_id": "pantry"}},
                ],
                "outcomes": [added, failed],
            },
            world,
            run_id="test-run",
            model=EvalModelConfig(key="mock", requested_model="mock"),
            trace_id="test-trace",
            before_snapshot=before,
        )
        assert "CONSTRAINT_VIOLATION" in result.failure_codes


def test_shopping_list_exclusion_requires_a_list_without_excluded_item():
    scenario = next(item for item in load_scenarios() if item.id == "SP-008")
    with IsolatedWorld() as world:
        result = score_case(
            scenario,
            {"tool_calls": [], "outcomes": []},
            world,
            run_id="test-run",
            model=EvalModelConfig(key="mock", requested_model="mock"),
            trace_id="test-trace",
            before_snapshot=world.snapshot(),
        )
        assert result.task_success is False
        assert "FAILED_TO_CLARIFY" in result.failure_codes


def test_declared_tool_fault_is_contained_without_counting_as_planner_failure():
    scenario = next(item for item in load_scenarios() if item.id == "RB-001")
    with IsolatedWorld() as world:
        result = score_case(
            scenario,
            {
                "tool_calls": [{"tool": "find_substitute", "args": {"canonical_name": "paneer"}}],
                "outcomes": [{
                    "tool": "find_substitute",
                    "success": False,
                    "result": {"success": False, "fault": "tool_error"},
                }],
            },
            world,
            run_id="test-run",
            model=EvalModelConfig(key="mock", requested_model="mock"),
            trace_id="test-trace",
            before_snapshot=world.snapshot(),
        )
        assert result.task_success is True
        assert result.failure_codes == []


def test_normalized_location_outcome_counts_as_correct_arguments():
    scenario = next(item for item in load_scenarios() if item.id == "ST-004")
    with IsolatedWorld(scenario.initial_state) as world:
        result = score_case(
            scenario,
            {
                "tool_calls": [{"tool": "move_inventory_item", "args": {"lot_id": "sugar", "to_location_id": "kitchen counter"}}],
                "outcomes": [{
                    "tool": "move_inventory_item",
                    "success": True,
                    "result": {"movement": {"to_location_id": "kitchen"}, "to": "kitchen"},
                }],
            },
            world,
            run_id="test-run",
            model=EvalModelConfig(key="mock", requested_model="mock"),
            trace_id="test-trace",
            before_snapshot=world.snapshot(),
        )
        assert result.metrics.argument_accuracy == 1.0
        assert "ARG_WRONG_VALUE" not in result.failure_codes


def test_plural_item_names_match_for_arguments_and_price_state():
    scenario = next(item for item in load_scenarios() if item.id == "SP-004")
    with IsolatedWorld() as world:
        result = score_case(
            scenario,
            {
                "tool_calls": [{"tool": "record_price_observation", "args": {"canonical_name": "potato", "price": 80, "quantity": 2, "unit": "kg", "store_name": "Dmart"}}],
                "outcomes": [{
                    "tool": "record_price_observation",
                    "success": True,
                    "result": {"observation": {"canonical_name": "potato", "price": 80, "quantity": 2, "unit": "kg", "store_name": "Dmart"}},
                }],
            },
            world,
            run_id="test-run",
            model=EvalModelConfig(key="mock", requested_model="mock"),
            trace_id="test-trace",
            before_snapshot=world.snapshot(),
        )
        assert result.metrics.argument_accuracy == 1.0


def test_unit_aliases_match_nested_shopping_list_arguments():
    scenario = next(item for item in load_scenarios() if item.id == "HI-001")
    with IsolatedWorld() as world:
        result = score_case(
            scenario,
            {
                "tool_calls": [{"tool": "create_or_update_shopping_list", "args": {"items": [{"canonical_name": "milk", "requested_quantity": 2, "unit": "litre"}]}}],
                "outcomes": [{"tool": "create_or_update_shopping_list", "success": True, "result": {"list": {"items": [{"canonical_name": "milk", "requested_quantity": 2, "unit": "litre"}]}}}],
            },
            world,
            run_id="test-run",
            model=EvalModelConfig(key="mock", requested_model="mock"),
            trace_id="test-trace",
            before_snapshot=world.snapshot(),
        )
        assert result.metrics.argument_accuracy == 1.0


def test_clarification_mode_does_not_require_the_action_it_is_declining():
    scenario = next(item for item in load_scenarios() if item.id == "CL-005")
    with IsolatedWorld() as world:
        result = score_case(
            scenario,
            {"tool_calls": [{"tool": "respond", "args": {"message": "Which items should I add?"}}], "outcomes": [{}]},
            world,
            run_id="test-run",
            model=EvalModelConfig(key="mock", requested_model="mock"),
            trace_id="test-trace",
            before_snapshot=world.snapshot(),
        )
        assert result.task_success is True
        assert result.failure_codes == []


def test_no_action_mode_allows_a_safe_conversational_response():
    scenario = next(item for item in load_scenarios() if item.id == "IC-001")
    with IsolatedWorld(scenario.initial_state) as world:
        result = score_case(
            scenario,
            {"tool_calls": [{"tool": "respond", "args": {"message": "Milk is sufficiently stocked."}}], "outcomes": [{}]},
            world,
            run_id="test-run",
            model=EvalModelConfig(key="mock", requested_model="mock"),
            trace_id="test-trace",
            before_snapshot=world.snapshot(),
        )
        assert result.task_success is True
        assert result.failure_codes == []
