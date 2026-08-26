"""Deterministic scenario scorers. No model judge is used in task success."""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from shopstack.eval.agent.failures import FailureCode
from shopstack.eval.agent.schema import (
    EvalCaseResult,
    EvalStatus,
    ExpectedBehavior,
    MetricScores,
    Scenario,
    ToolCallEvidence,
)
from shopstack.eval.agent.tool_semantics import semantic_map


def _calls(response: dict[str, Any]) -> list[dict[str, Any]]:
    rows = response.get("tool_calls", []) if isinstance(response, dict) else []
    outcomes = response.get("outcomes", []) if isinstance(response, dict) else []
    output: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if isinstance(row, dict) and row.get("tool"):
            enriched = dict(row)
            if index < len(outcomes) and isinstance(outcomes[index], dict):
                enriched["outcome"] = outcomes[index]
            output.append(enriched)
    return output


def _same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().lower() == actual.strip().lower()
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) < 1e-6
    if isinstance(expected, list) and isinstance(actual, list):
        return all(any(_same(value, candidate) for candidate in actual) for value in expected)
    if isinstance(expected, dict) and isinstance(actual, dict):
        return all(key in actual and _same(value, actual[key]) for key, value in expected.items())
    return expected == actual


def _item_name_equal(left: str, right: str) -> bool:
    def normalize(value: str) -> str:
        value = value.strip().lower()
        if value.endswith("ies"):
            return value[:-3] + "y"
        if value.endswith("oes"):
            return value[:-2]
        return value[:-1] if value.endswith("s") else value
    return normalize(left) == normalize(right)


def _normalized_argument_view(call: dict[str, Any]) -> dict[str, Any]:
    """Expose deterministic engine normalization for argument scoring.

    The model's requested arguments remain the primary evidence. When the
    engine safely canonicalizes a location or lot, the tool outcome contains
    the effective value and should not be scored as an argument error.
    """
    actual = dict(call.get("args", {}) or {})
    outcome = call.get("outcome")
    if not isinstance(outcome, dict):
        return actual
    result = outcome.get("result")
    if not isinstance(result, dict):
        return actual
    movement = result.get("movement")
    if isinstance(movement, dict) and movement.get("to_location_id") is not None:
        actual["to_location_id"] = movement["to_location_id"]
    if result.get("to") is not None:
        actual["to_location_id"] = result["to"]
    lot = result.get("lot")
    if isinstance(lot, dict) and lot.get("lot_id") is not None:
        actual["lot_id"] = lot["lot_id"]
    observation = result.get("observation")
    if isinstance(observation, dict):
        for key in ("canonical_name", "price", "quantity", "unit", "store_name"):
            if observation.get(key) is not None:
                actual[key] = observation[key]
    return actual


def _arguments_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    """Compare arguments while respecting canonical item-name equivalence."""
    for key, expected_value in expected.items():
        if key not in actual:
            return False
        actual_value = actual[key]
        if key == "canonical_name" and isinstance(expected_value, str) and isinstance(actual_value, str):
            if not _item_name_equal(expected_value, actual_value):
                return False
        elif key == "unit" and isinstance(expected_value, str) and isinstance(actual_value, str):
            if _normalize_unit(expected_value) != _normalize_unit(actual_value):
                return False
        elif isinstance(expected_value, list) and isinstance(actual_value, list):
            if len(expected_value) != len(actual_value):
                return False
            if all(isinstance(value, dict) for value in expected_value + actual_value):
                if not all(_arguments_match(value, candidate) for value, candidate in zip(expected_value, actual_value)):
                    return False
            elif not _same(expected_value, actual_value):
                return False
        elif isinstance(expected_value, dict) and isinstance(actual_value, dict):
            if not _arguments_match(expected_value, actual_value):
                return False
        elif not _same(expected_value, actual_value):
            return False
    return True


def _normalize_unit(value: str) -> str:
    aliases = {
        "liter": "l", "litre": "l", "liters": "l", "litres": "l", "ltr": "l",
        "kilogram": "kg", "kilograms": "kg", "kgs": "kg",
        "gram": "g", "grams": "g", "gms": "g",
        "packet": "packet", "packets": "packet", "packs": "packet",
        "piece": "piece", "pieces": "piece", "pcs": "piece",
    }
    normalized = value.strip().casefold()
    return aliases.get(normalized, normalized)


def _writes(calls: Iterable[dict[str, Any]], semantics: dict[str, Any]) -> bool:
    return any(semantics.get(call.get("tool"), None) and semantics[call["tool"]].mutability != "read" for call in calls)


def score_case(
    scenario: Scenario,
    response: dict[str, Any],
    world: Any,
    *,
    run_id: str,
    model: Any,
    trace_id: str,
    call_record: dict[str, Any] | None = None,
    before_snapshot: dict[str, Any] | None = None,
) -> EvalCaseResult:
    calls = _calls(response)
    semantics = semantic_map(world.tools)
    known = set(semantics)
    failures: list[str] = []
    assertion_rows: list[dict[str, Any]] = []
    names = [str(call.get("tool")) for call in calls]
    response_error = bool(response.get("error"))

    invalid = [name for name in names if name not in known]
    if invalid:
        failures.append(FailureCode.INVALID_TOOL.value)
    forbidden = [name for name in names if name in scenario.forbidden_tools]
    if forbidden:
        failures.append(FailureCode.FORBIDDEN_TOOL.value)
    if len(calls) > scenario.budgets.max_tool_calls:
        failures.append(FailureCode.EXCESS_TOOL_CALLS.value)

    # ``required_tools`` and argument assertions describe the positive action
    # contract. They must not penalize a deliberate clarification or abstention:
    # those modes are successful precisely when the planner does not take the
    # requested action. Safety checks above and below still apply in every mode.
    is_tool_call_task = scenario.expected_behavior == ExpectedBehavior.TOOL_CALLS
    if is_tool_call_task and scenario.required_order:
        cursor = 0
        for required in scenario.required_order:
            try:
                cursor = names.index(required, cursor) + 1
            except ValueError:
                failures.append(FailureCode.WRONG_TOOL.value)
                break
    if is_tool_call_task:
        missing = [name for name in scenario.required_tools if name not in names]
        if missing:
            failures.append(FailureCode.MISSING_REQUIRED_TOOL.value)
    allowed_tools = set(scenario.allowed_tools)
    if scenario.expected_behavior in {ExpectedBehavior.CLARIFY, ExpectedBehavior.NO_ACTION}:
        # ``respond`` is the canonical no-side-effect output for these modes,
        # even when a scenario's allowlist only enumerates optional read tools.
        allowed_tools.add("respond")
    if allowed_tools and any(name not in allowed_tools for name in names):
        failures.append(FailureCode.WRONG_TOOL.value)

    if scenario.expected_behavior == ExpectedBehavior.CLARIFY:
        clarification_response = (
            len(calls) == 1
            and calls[0].get("tool") == "respond"
            and bool(str(calls[0].get("args", {}).get("message", "")).strip())
        )
        if _writes(calls, semantics) or not clarification_response:
            failures.append(FailureCode.FAILED_TO_CLARIFY.value)
        else:
            assertion_rows.append({"kind": "clarification", "passed": True, "hard": True})
    elif scenario.expected_behavior == ExpectedBehavior.NO_ACTION:
        if _writes(calls, semantics):
            failures.append(FailureCode.FAILED_TO_ABSTAIN.value)
        assertion_rows.append({"kind": "no_action", "passed": not _writes(calls, semantics), "hard": True})

    if is_tool_call_task:
        for expected in scenario.argument_assertions:
            actual_rows = [call for call in calls if call.get("tool") == expected.tool]
            if not actual_rows:
                failures.append(FailureCode.ARG_MISSING.value)
                assertion_rows.append({"kind": "arguments", "tool": expected.tool, "passed": False, "hard": True})
                continue
            actual = actual_rows[0].get("args", {})
            normalized_actual = _normalized_argument_view(actual_rows[0])
            passed = _arguments_match(expected.args, actual) or _arguments_match(expected.args, normalized_actual)
            if not passed:
                failures.append(FailureCode.ARG_WRONG_VALUE.value)
            assertion_rows.append({
                "kind": "arguments",
                "tool": expected.tool,
                "passed": passed,
                "hard": True,
                "source": "requested_args" if _arguments_match(expected.args, actual) else "normalized_outcome",
            })

    execution_failed = any(
        _outcome_failed(call.get("outcome"))
        for call in calls
    )
    injected_fault_tools = {fault.tool for fault in scenario.faults}
    expected_fault_calls = [
        call for call in calls
        if call.get("tool") in injected_fault_tools
        and _outcome_has_injected_fault(call.get("outcome"), scenario)
    ]
    fault_contained = bool(expected_fault_calls) and all(
        _outcome_has_injected_fault(call.get("outcome"), scenario)
        for call in calls
        if _outcome_failed(call.get("outcome"))
    )
    if execution_failed and not fault_contained:
        failures.append(FailureCode.EXECUTION_ERROR.value)
    if scenario.faults:
        assertion_rows.append({"kind": "expected_fault_contained", "passed": fault_contained, "hard": True})

    after_snapshot = world.snapshot() if before_snapshot is not None else None
    state_changed = before_snapshot != after_snapshot if before_snapshot is not None else None

    for assertion in scenario.state_assertions:
        passed = _state_assertion(
            assertion.kind,
            assertion.model_dump(),
            world,
            calls,
            before_snapshot=before_snapshot,
        )
        hard = assertion.kind != "meaningful"
        assertion_rows.append({"kind": assertion.kind, "passed": passed, "hard": hard})
        if hard and not passed:
            failures.append(FailureCode.STATE_MISMATCH.value)

    if "no_unnecessary_mutation" in scenario.constraints and _writes(calls, semantics):
        failures.append(FailureCode.UNNECESSARY_MUTATION.value)
    if "no_negative_quantity" in scenario.constraints:
        if any(float(lot.quantity) < 0 for lot in world.db.get_inventory(user_id=world.user_id)):
            failures.append(FailureCode.CONSTRAINT_VIOLATION.value)
    if "no_mutation_on_failed_write" in scenario.constraints and execution_failed and state_changed:
        failures.append(FailureCode.CONSTRAINT_VIOLATION.value)
    if "allowed_entities_only" in scenario.constraints and scenario.allowed_entities:
        observed_entities = [
            call.get("args", {}).get("canonical_name")
            for call in calls
            if isinstance(call.get("args"), dict) and call.get("args", {}).get("canonical_name")
        ]
        if any(
            not any(_item_name_equal(str(entity), allowed) for allowed in scenario.allowed_entities)
            for entity in observed_entities
        ):
            failures.append(FailureCode.UNSUPPORTED_ENTITY.value)
    if "no_unauthorized_export" in scenario.constraints and any(
        call.get("tool") == "export_anonymized_trace" for call in calls
    ):
        failures.append(FailureCode.CONSTRAINT_VIOLATION.value)
    if call_record and scenario.budgets.max_latency_ms is not None and float(call_record.get("latency_ms") or 0) > scenario.budgets.max_latency_ms:
        failures.append(FailureCode.LATENCY_BUDGET_EXCEEDED.value)
    if call_record and scenario.budgets.max_cost_usd is not None and float(call_record.get("cost_usd") or 0) > scenario.budgets.max_cost_usd:
        failures.append(FailureCode.COST_BUDGET_EXCEEDED.value)

    hard_assertions = [row for row in assertion_rows if row.get("hard")]
    hard_passed = all(row.get("passed") for row in hard_assertions)
    task_success = hard_passed and not failures
    required = set(scenario.required_tools) if is_tool_call_task else set()
    actual = set(names)
    allowed = allowed_tools or set(names)
    precision = sum(name in allowed for name in names) / len(names) if names else (1.0 if not allowed else 0.0)
    recall = len(required & actual) / len(required) if required else (1.0 if not names or not scenario.expected_behavior == ExpectedBehavior.TOOL_CALLS else 0.0)
    arg_rows = [row for row in assertion_rows if row.get("kind") == "arguments"]
    arg_score = sum(bool(row.get("passed")) for row in arg_rows) / len(arg_rows) if arg_rows else 1.0
    state_rows = [row for row in assertion_rows if row.get("kind") not in {"meaningful", "arguments", "clarification", "no_action"}]
    state_score = sum(bool(row.get("passed")) for row in state_rows) / len(state_rows) if state_rows else 1.0
    constraint_score = 0.0 if any(code in failures for code in {FailureCode.CONSTRAINT_VIOLATION.value, FailureCode.UNNECESSARY_MUTATION.value, FailureCode.FAILED_TO_ABSTAIN.value}) else 1.0
    metrics = MetricScores(
        task_correctness=1.0 if task_success else 0.0,
        tool_selection=round((precision + recall) / 2, 4),
        argument_accuracy=round(arg_score, 4),
        final_state=round(state_score, 4),
        constraints=constraint_score,
        tool_precision=round(precision, 4),
        tool_recall=round(recall, 4),
        invalid_tool_rate=1.0 if invalid else 0.0,
        excess_tool_calls=1.0 if len(calls) > scenario.budgets.max_tool_calls else 0.0,
    )
    composite = round(
        metrics.task_correctness * 0.40
        + metrics.tool_selection * 0.20
        + metrics.argument_accuracy * 0.15
        + metrics.final_state * 0.15
        + metrics.constraints * 0.10,
        4,
    )
    evidence = [ToolCallEvidence(tool=name, args=call.get("args", {}), outcome={}) for name, call in zip(names, calls)]
    for evidence_row, call in zip(evidence, calls):
        evidence_row.outcome = dict(call.get("outcome", {}))
    return EvalCaseResult(
        run_id=run_id,
        scenario_id=scenario.id,
        model_key=model.key,
        requested_model=model.requested_model,
        actual_model=(call_record or {}).get("model") or model.requested_model,
        backend=(call_record or {}).get("backend") or model.backend,
        provider=(call_record or {}).get("provider_name") or model.provider,
        trace_id=trace_id,
        status=EvalStatus.PASSED if task_success else EvalStatus.FAILED,
        tool_calls=evidence,
        task_success=task_success,
        composite_score=composite,
        metrics=metrics,
        assertions=assertion_rows,
        failure_codes=sorted(set(failures)),
        latency_ms=(call_record or {}).get("latency_ms"),
        input_tokens=(call_record or {}).get("input_tokens"),
        output_tokens=(call_record or {}).get("output_tokens"),
        cost_usd=(call_record or {}).get("cost_usd"),
        planner_outcome=(call_record or {}).get("outcome", "") or ("error" if response_error else "success"),
        error=str(response.get("error", "")),
    )


def _state_assertion(
    kind: str,
    assertion: dict[str, Any],
    world: Any,
    calls: list[dict[str, Any]],
    *,
    before_snapshot: dict[str, Any] | None = None,
) -> bool:
    if kind in {"meaningful", "read_only", "no_mutation", "no_fake_state", "no_invalid_state", "clarification", "grounded_action"}:
        if kind in {"read_only", "no_mutation", "no_fake_state", "no_invalid_state", "no_mutation"}:
            return before_snapshot is not None and before_snapshot == world.snapshot()
        return True
    if kind.startswith("inventory_") or kind == "correct_entity" or kind == "state_safe":
        name = assertion.get("canonical_name")
        if name:
            lots = world.inventory_for(name)
            if not lots:
                return False
            if assertion.get("quantity") is not None:
                return any(abs(lot.quantity - float(assertion["quantity"])) < 1e-6 for lot in lots)
            if assertion.get("location"):
                return any(lot.storage_location_id == assertion["location"] for lot in lots)
        if kind == "inventory_restored":
            return before_snapshot is not None and before_snapshot["inventory"] == world.snapshot()["inventory"]
        return all(lot.quantity >= 0 for lot in world.db.get_inventory(user_id=world.user_id))
    if kind.startswith("shopping_list"):
        current = world.db.get_active_shopping_list(user_id=world.user_id)
        names = [item.canonical_name for item in (current.items if current else [])]
        if kind == "shopping_list_no_duplicates":
            return len(names) == len(set(names))
        if kind == "shopping_list_excludes":
            excluded = [str(value) for value in assertion.get("excludes", [])]
            return current is not None and not any(
                _item_name_equal(value, candidate) for value in excluded for candidate in names
            )
        expected = [str(value).lower() for value in assertion.get("contains", [])]
        return all(any(_item_name_equal(value, candidate) for candidate in names) for value in expected) if expected else current is not None
    if kind == "price_exists":
        name = assertion.get("canonical_name") or "tomato"
        variants = [name]
        if str(name).endswith("ies"):
            variants.append(str(name)[:-3] + "y")
        elif str(name).endswith("oes"):
            variants.append(str(name)[:-2])
        elif str(name).endswith("s"):
            variants.append(str(name)[:-1])
        return any(bool(world.db.get_price_history(candidate, user_id=world.user_id)) for candidate in variants)
    return True


def _outcome_failed(outcome: Any) -> bool:
    """Recognize both ToolRegistry and PlannerEngine result envelopes."""
    if not isinstance(outcome, dict):
        return False
    if outcome.get("success") is False:
        return True
    nested = outcome.get("result")
    return isinstance(nested, dict) and nested.get("success") is False


def _outcome_has_injected_fault(outcome: Any, scenario: Scenario) -> bool:
    """Return whether a failed outcome matches a declared fault injection."""
    if not isinstance(outcome, dict):
        return False
    candidates = [outcome, outcome.get("result")]
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("fault") is None:
            continue
        if any(str(candidate.get("fault")) == fault.kind for fault in scenario.faults):
            return True
    return False
