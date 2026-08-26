"""Deterministic binding helpers for bounded planner continuations."""
from __future__ import annotations

import json
import re
from typing import Any


CONTINUATION_PROTOCOL_VERSION = "1.0"
_REFERENCE_PATTERN = re.compile(r"^step_(\d+)\.result(?:\.(.+))?$")


class BindingError(ValueError):
    """Raised when a model-supplied result reference cannot be resolved."""


def resolve_result_references(
    value: Any,
    step_results: dict[str, dict[str, Any]],
) -> tuple[Any, list[dict[str, Any]]]:
    """Resolve explicit ``{"$from": "step_1.result.0.name"}`` objects.

    The resolver is intentionally structural. Ordinary strings are never
    interpreted as references, and partial reference objects are rejected.
    """
    resolutions: list[dict[str, Any]] = []

    def visit(current: Any) -> Any:
        if isinstance(current, dict):
            if "$from" in current:
                if set(current) != {"$from"} or not isinstance(current["$from"], str):
                    raise BindingError("result reference must contain only a string '$from' field")
                reference = current["$from"]
                resolved = _resolve_reference(reference, step_results)
                resolutions.append({"reference": reference, "value": resolved})
                return resolved
            return {key: visit(item) for key, item in current.items()}
        if isinstance(current, list):
            return [visit(item) for item in current]
        return current

    return visit(value), resolutions


def _resolve_reference(
    reference: str,
    step_results: dict[str, dict[str, Any]],
) -> Any:
    match = _REFERENCE_PATTERN.fullmatch(reference.strip())
    if match is None:
        raise BindingError(f"unsupported result reference '{reference}'")

    step_id = f"step_{match.group(1)}"
    step = step_results.get(step_id)
    if step is None:
        raise BindingError(f"result reference points to unknown step '{step_id}'")

    current: Any = step.get("result")
    path = match.group(2)
    if path is None:
        return current

    for segment in path.split("."):
        if isinstance(current, list):
            if not segment.isdigit():
                raise BindingError(
                    f"result reference '{reference}' uses non-numeric list segment '{segment}'"
                )
            index = int(segment)
            if index >= len(current):
                raise BindingError(f"result reference '{reference}' is out of range")
            current = current[index]
        elif isinstance(current, dict):
            if segment not in current:
                raise BindingError(f"result reference '{reference}' has no key '{segment}'")
            current = current[segment]
        else:
            raise BindingError(f"result reference '{reference}' traverses a scalar value")
    return current


def action_fingerprint(tool: str, args: dict[str, Any]) -> str:
    """Return a stable fingerprint after reference resolution."""
    return json.dumps({"tool": tool, "args": args}, sort_keys=True, default=str)


def is_empty_result(value: Any) -> bool:
    """Treat structurally empty successful tool output as a stop condition."""
    if value is None or value == "" or value == [] or value == {}:
        return True
    if isinstance(value, dict):
        for collection_key in ("results", "items", "suggestions", "matches"):
            if collection_key in value and value[collection_key] == []:
                return True
    return False
