"""Scenario corpus for the bounded planner continuation protocol."""
from __future__ import annotations

from typing import Any

from shopstack.eval.agent.schema import ContinuationScenario, FaultSpec


def _lookup_result(substitute: str = "tofu") -> list[dict[str, Any]]:
    return [{
        "substitute": substitute,
        "display": substitute.title(),
        "type": "ingredient_swap",
        "reason": "Seeded continuation candidate",
        "price": 80,
    }]


def _lookup_call() -> dict[str, Any]:
    return {"tool": "find_substitute", "args": {"canonical_name": "paneer"}}


def _list_call() -> dict[str, Any]:
    return {
        "tool": "create_or_update_shopping_list",
        "args": {
            "items": [{
                "canonical_name": {"$from": "step_1.result.0.substitute"},
                "requested_quantity": 1,
                "unit": "unit",
                "priority": "must_buy",
            }],
            "goal": "Replace unavailable paneer",
        },
    }


def build_continuation_scenarios() -> list[ContinuationScenario]:
    """Return the canonical continuation contract corpus."""
    return [
        ContinuationScenario(
            id="CONT-001",
            version=1,
            title="Bound substitute into shopping list",
            request="Find a substitute for unavailable paneer, then add the selected substitute to the shopping list.",
            expected_status="write_completed",
            expected_steps=2,
            expected_tool_sequence=["find_substitute", "create_or_update_shopping_list"],
            expected_binding_references=["step_1.result.0.substitute"],
            expected_list_items=["tofu"],
            fixture_results={"find_substitute": _lookup_result()},
            scripted_responses=[{"tool_calls": [_lookup_call()]}, {"tool_calls": [_list_call()]}],
            tags=["happy_path", "binding", "real_model"],
        ),
        ContinuationScenario(
            id="CONT-002",
            version=1,
            title="Stop on empty substitute result",
            request="Find a substitute for unavailable paneer, then add the selected substitute to the shopping list.",
            expected_status="empty_intermediate",
            expected_steps=1,
            expected_tool_sequence=["find_substitute"],
            fixture_results={"find_substitute": []},
            scripted_responses=[{"tool_calls": [_lookup_call()]}],
            expect_no_mutation=True,
            tags=["empty", "recovery", "real_model"],
        ),
        ContinuationScenario(
            id="CONT-003",
            version=1,
            title="Stop on substitute tool error",
            request="Find a substitute for paneer and add it to my shopping list.",
            expected_status="tool_failed",
            expected_steps=1,
            expected_tool_sequence=["find_substitute"],
            scripted_responses=[{"tool_calls": [_lookup_call()]}],
            faults=[FaultSpec(tool="find_substitute", kind="tool_error", message="substitute service unavailable")],
            expect_no_mutation=True,
            tags=["tool_error", "recovery"],
        ),
        ContinuationScenario(
            id="CONT-004",
            version=1,
            title="Stop on substitute timeout",
            request="Find a substitute for paneer and add it to my shopping list.",
            expected_status="tool_failed",
            expected_steps=1,
            expected_tool_sequence=["find_substitute"],
            scripted_responses=[{"tool_calls": [_lookup_call()]}],
            faults=[FaultSpec(tool="find_substitute", kind="timeout", message="substitute service timed out")],
            expect_no_mutation=True,
            tags=["timeout", "recovery"],
        ),
        ContinuationScenario(
            id="CONT-005",
            version=1,
            title="Stop on stale substitute result",
            request="Find a substitute for paneer and add it to my shopping list.",
            expected_status="stale_intermediate",
            expected_steps=1,
            expected_tool_sequence=["find_substitute"],
            scripted_responses=[{"tool_calls": [_lookup_call()]}],
            faults=[FaultSpec(tool="find_substitute", kind="stale", message="market snapshot is stale")],
            expect_no_mutation=True,
            tags=["stale", "recovery"],
        ),
        ContinuationScenario(
            id="CONT-006",
            version=1,
            title="Reject missing binding path",
            request="Find a substitute for paneer and add it to my shopping list.",
            expected_status="binding_failed",
            expected_steps=2,
            expected_tool_sequence=["find_substitute", "create_or_update_shopping_list"],
            fixture_results={"find_substitute": _lookup_result()},
            scripted_responses=[
                {"tool_calls": [_lookup_call()]},
                {"tool_calls": [{
                    "tool": "create_or_update_shopping_list",
                    "args": {"items": [{"canonical_name": {"$from": "step_1.result.0.missing"}}]},
                }]},
            ],
            expect_no_mutation=True,
            tags=["binding", "malformed"],
        ),
        ContinuationScenario(
            id="CONT-007",
            version=1,
            title="Suppress duplicate lookup",
            request="Find a substitute for paneer, then verify the same lookup again.",
            expected_status="duplicate_action",
            expected_steps=2,
            expected_tool_sequence=["find_substitute", "find_substitute"],
            fixture_results={"find_substitute": _lookup_result()},
            scripted_responses=[
                {"tool_calls": [_lookup_call()]},
                {"tool_calls": [_lookup_call()]},
            ],
            expect_no_mutation=True,
            tags=["duplicate", "recovery"],
        ),
        ContinuationScenario(
            id="CONT-008",
            version=1,
            title="Keep inventory confirmation boundary",
            request="Find a substitute for paneer and add it to inventory.",
            expected_status="tool_failed",
            expected_steps=2,
            expected_tool_sequence=["find_substitute", "add_inventory_item"],
            expected_binding_references=["step_1.result.0.substitute"],
            fixture_results={"find_substitute": _lookup_result()},
            scripted_responses=[
                {"tool_calls": [_lookup_call()]},
                {"tool_calls": [{
                    "tool": "add_inventory_item",
                    "args": {"canonical_name": {"$from": "step_1.result.0.substitute"}},
                }]},
            ],
            expect_no_mutation=True,
            tags=["confirmation", "authority"],
        ),
        ContinuationScenario(
            id="CONT-009",
            version=1,
            title="Truncate batched continuation proposal",
            request="Find a substitute for paneer.",
            expected_status="multiple_calls_truncated",
            expected_steps=1,
            expected_tool_sequence=["find_substitute"],
            fixture_results={"find_substitute": _lookup_result()},
            scripted_responses=[
                {"tool_calls": [_lookup_call(), _lookup_call()]},
            ],
            expect_no_mutation=True,
            tags=["protocol", "boundedness"],
        ),
        ContinuationScenario(
            id="CONT-010",
            version=1,
            title="Reject wrong bound result type without mutation",
            request="Find a substitute for paneer and add it to my shopping list.",
            expected_status="tool_failed",
            expected_steps=2,
            expected_tool_sequence=["find_substitute", "create_or_update_shopping_list"],
            expected_binding_references=["step_1.result.0.substitute"],
            fixture_results={"find_substitute": [{"substitute": ["tofu"]}]},
            scripted_responses=[
                {"tool_calls": [_lookup_call()]},
                {"tool_calls": [{
                    "tool": "create_or_update_shopping_list",
                    "args": {"items": [{"canonical_name": {"$from": "step_1.result.0.substitute"}}]},
                }]},
            ],
            expect_no_mutation=True,
            tags=["binding", "type_safety", "recovery"],
        ),
    ]
