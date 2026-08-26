"""Scenario corpus loading and structural validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shopstack.eval.agent.corpus import build_scenarios
from shopstack.eval.agent.tool_semantics import validate_semantics
from shopstack.tools.registry import ToolRegistry

KNOWN_ASSERTIONS = {
    "meaningful", "inventory_contains", "inventory_quantity", "inventory_location",
    "shopping_list_contains", "shopping_list_excludes", "shopping_list_no_duplicates",
    "price_exists", "read_only", "no_mutation", "state_safe", "inventory_restored",
    "correct_entity", "no_fake_state", "no_invalid_state", "clarification", "grounded_action", "expected_fault_contained",
}
KNOWN_FAULTS = {"tool_error", "empty", "timeout", "stale"}


def scenario_dir() -> Path:
    return Path(__file__).resolve().parent


def load_scenarios(path: str | Path | None = None) -> list[Any]:
    if path is None:
        return build_scenarios()
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = payload.get("scenarios", payload) if isinstance(payload, (dict, list)) else []
    from shopstack.eval.agent.schema import Scenario
    return [Scenario.model_validate(row) for row in rows]


def validate_suite(scenarios: list[Any] | None = None, tool_registry: Any | None = None) -> list[str]:
    scenarios = scenarios if scenarios is not None else load_scenarios()
    registry = tool_registry or ToolRegistry.__new__(ToolRegistry)
    if tool_registry is None:
        # Avoid constructing a real app DB just to validate names. ToolSpec is
        # the canonical contract and is also what ToolRegistry exposes.
        from shopstack.tools.spec import build_tool_specs
        runtime_names = {spec.name for spec in build_tool_specs()} | {"respond"}
        semantic_errors = validate_semantics(None)
    else:
        runtime_names = {spec.name for spec in registry.tool_specs()} | {"respond"}
        semantic_errors = validate_semantics(registry)
    errors = list(semantic_errors)
    if len(scenarios) != 50:
        errors.append(f"expected exactly 50 scenarios, found {len(scenarios)}")
    ids = [scenario.id for scenario in scenarios]
    errors.extend(f"duplicate scenario id: {sid}" for sid in sorted({sid for sid in ids if ids.count(sid) > 1}))
    pairs = [(scenario.title.strip().lower(), scenario.request.strip().lower()) for scenario in scenarios]
    errors.extend(f"duplicate title/request: {title}" for title, request in sorted(set(pairs)) if pairs.count((title, request)) > 1)
    for scenario in scenarios:
        for name in set(scenario.required_tools + scenario.allowed_tools + scenario.forbidden_tools):
            if name not in runtime_names:
                errors.append(f"{scenario.id}: unknown tool {name}")
        collisions = set(scenario.required_tools) & set(scenario.forbidden_tools)
        errors.extend(f"{scenario.id}: required and forbidden tool {name}" for name in sorted(collisions))
        if scenario.expected_behavior == "tool_calls" and not (scenario.required_tools or scenario.allowed_tools):
            errors.append(f"{scenario.id}: tool_calls scenario has no tool contract")
        if not (scenario.state_assertions or scenario.required_tools or scenario.constraints):
            errors.append(f"{scenario.id}: no meaningful assertion")
        for assertion in scenario.state_assertions:
            if assertion.kind not in KNOWN_ASSERTIONS:
                errors.append(f"{scenario.id}: unknown assertion {assertion.kind}")
        for fault in scenario.faults:
            if fault.tool not in runtime_names:
                errors.append(f"{scenario.id}: fault targets unknown tool {fault.tool}")
            if fault.kind not in KNOWN_FAULTS:
                errors.append(f"{scenario.id}: unknown fault {fault.kind}")
    return errors


def assert_valid_suite(scenarios: list[Any] | None = None) -> list[Any]:
    scenarios = scenarios if scenarios is not None else load_scenarios()
    errors = validate_suite(scenarios)
    if errors:
        raise ValueError("Invalid agent eval suite:\n" + "\n".join(errors))
    return scenarios
