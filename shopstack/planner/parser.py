from __future__ import annotations

import json
import re
from typing import Any

PARSER_VERSION = "1.2"


def extract_json(text: str) -> list[dict[str, Any]] | dict[str, Any] | None:
    parsed, _ = extract_json_with_diagnostics(text)
    return parsed


def extract_json_with_diagnostics(
    text: str,
) -> tuple[list[dict[str, Any]] | dict[str, Any] | None, dict[str, Any]]:
    cleaned = _strip_wrappers(text.strip())
    diagnostics: dict[str, Any] = {
        "parser_version": PARSER_VERSION,
        "repair_steps": [],
        "candidate_count": 0,
        "raw_text_length": len(text or ""),
        "json_candidate_found": False,
    }

    candidates = _extract_json_candidates(cleaned)
    diagnostics["candidate_count"] = len(candidates)
    for candidate in candidates:
        parsed = _parse_json_candidate_with_diagnostics(candidate, diagnostics)
        if parsed is not None:
            return parsed, diagnostics

    # Legacy fallback for malformed single-object payloads.
    # This preserves historical tolerance used by model output tests.
    try:
        return _extract_single_object(cleaned), diagnostics
    except (json.JSONDecodeError, ValueError):
        diagnostics["error"] = "no_parseable_json"
        return None, diagnostics


def _fix_common_json_errors(text: str) -> str:
    result = text
    # Replace single quotes with double quotes (but not inside existing strings)
    result = re.sub(r"(?<!\\)'", '"', result)
    # Remove trailing commas before closing brackets
    result = re.sub(r",\s*}", "}", result)
    result = re.sub(r",\s*]", "]", result)
    # Remove trailing commas at end of lines within JSON
    result = re.sub(r",\s*(\n|\r)", r"\1", result)
    # Try to fix unquoted keys (only simple alphanumeric keys)
    result = re.sub(r'(?<!["\w])(\w+)(?=\s*:)', r'"\1"', result)
    return result


def _extract_single_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found")
    candidate = text[start:end + 1]
    return json.loads(_fix_common_json_errors(candidate))


def parse_tool_calls(text: str) -> list[dict[str, Any]]:
    parsed, _ = parse_tool_calls_with_diagnostics(text)
    return parsed


def parse_tool_calls_with_diagnostics(
    text: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw, diagnostics = extract_json_with_diagnostics(text)

    if raw is None:
        diagnostics["status"] = "fallback_respond"
        diagnostics["items_output"] = 0
        return _error_result("No structured data found in model response"), diagnostics

    if isinstance(raw, dict):
        # Single tool call object: wrap in list
        raw = [raw]

    if not isinstance(raw, list):
        diagnostics["status"] = "invalid_root_type"
        diagnostics["items_output"] = 0
        return _error_result(f"Expected a JSON array of tool calls, got {type(raw).__name__}"), diagnostics

    validated: list[dict[str, Any]] = []
    diagnostics["raw_count"] = len(raw)
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            validated.append(_error_item(f"Item {i} is not a dict", original=item))
            diagnostics["errors"] = diagnostics.get("errors", 0) + 1
            continue
        tool = item.get("tool")
        if not tool or not isinstance(tool, str):
            validated.append(_error_item(f"Item {i} missing 'tool' field", original=item))
            diagnostics["errors"] = diagnostics.get("errors", 0) + 1
            continue
        args = item.get("args")
        if args is not None and not isinstance(args, dict):
            validated.append(_error_item(
                f"Item {i} 'args' must be a dict", original=item
            ))
            diagnostics["errors"] = diagnostics.get("errors", 0) + 1
            continue
        validated.append({
            "tool": tool,
            "args": args if isinstance(args, dict) else {},
        })
        diagnostics["items_output"] = diagnostics.get("items_output", 0) + 1

    diagnostics["status"] = "parsed"
    if diagnostics.get("repair_steps"):
        diagnostics["status"] = "recovered"
    if not diagnostics.get("items_output") and not diagnostics.get("errors"):
        diagnostics["status"] = "empty"

    return validated, diagnostics


def _error_result(message: str) -> list[dict[str, Any]]:
    return [{"tool": "respond", "args": {"message": message}}]


def _error_item(message: str, original: Any = None) -> dict[str, Any]:
    item: dict[str, Any] = {"tool": "respond", "args": {"message": message}}
    if original is not None:
        item["_original"] = original
    return item


def parse_tool_calls_strict(text: str) -> list[dict[str, Any]]:
    result = parse_tool_calls(text)
    if len(result) == 1 and result[0]["tool"] == "respond":
        message = str(result[0]["args"].get("message", ""))
        if "No structured data found" in message:
            return result
    if len(result) == 1 and result[0]["tool"] == "respond" and "No structured data" in str(result[0]["args"].get("message", "")):
        return result
    for tc in result:
        if tc["tool"] == "respond" and "_original" in tc:
            return _error_result("Parsing failed: invalid tool call structure")
    return result


def _strip_wrappers(text: str) -> str:
    # Remove markdown fences first.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```\s*$", "", text)
    # Remove Qwen-style `<think>...</think>` reasoning blocks.
    text = re.sub(r"<think>.*?</think>", "", text, flags= re.DOTALL)
    return text.strip()


def _extract_json_candidates(text: str) -> list[str]:
    """Extract balanced JSON candidate snippets from noisy model output."""
    candidates: list[str] = []
    start_stack: list[tuple[str, int]] = []
    in_string = False
    escaped = False

    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{" or ch == "[":
            start_stack.append((ch, i))
            continue

        if not start_stack:
            continue

        opener, start = start_stack[-1]
        if ch == "}" and opener == "{":
            start_stack.pop()
            if not start_stack:
                candidates.append(text[start : i + 1])
        elif ch == "]" and opener == "[":
            start_stack.pop()
            if not start_stack:
                candidates.append(text[start : i + 1])

    return candidates


def _parse_json_candidate(candidate: str) -> dict[str, Any] | list[dict[str, Any]] | None:
    for value in (candidate, _fix_common_json_errors(candidate)):
        parsed = _parse_json_candidate_core(value)
        if parsed is not None:
            return parsed
    return None


def _parse_json_candidate_core(value: str) -> dict[str, Any] | list[dict[str, Any]] | None:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)] or parsed
    return None


def _parse_json_candidate_with_diagnostics(
    candidate: str, diagnostics: dict[str, Any]
) -> dict[str, Any] | list[dict[str, Any]] | None:
    parsed = _parse_json_candidate_core(candidate)
    if parsed is not None:
        diagnostics["json_candidate_found"] = True
        return parsed

    fixed = _fix_common_json_errors(candidate)
    if fixed != candidate:
        parsed = _parse_json_candidate_core(fixed)
        if parsed is not None:
            diagnostics["repair_steps"].append("common_json_fixes")
            diagnostics["json_candidate_found"] = True
            return parsed

    return None
