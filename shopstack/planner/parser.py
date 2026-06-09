from __future__ import annotations

import json
import re
from typing import Any


def extract_json(text: str) -> list[dict[str, Any]] | dict[str, Any] | None:
    cleaned = text.strip()

    # Step 1: strip markdown fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    # Step 2: strip <think>...</think> wrappers (Qwen3.5 thinking tags)
    # Chat-based models like Qwen wrap reasoning in <think> blocks before
    # the JSON output. If the think-text contains brackets (e.g.
    # "I should use [find_item]"), the bracket search below would find the
    # wrong delimiter. Stripping think tags first prevents this.
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL)

    # Step 3: try to find a JSON array or object in the text
    first_bracket = cleaned.find("[")
    first_brace = cleaned.find("{")

    if first_bracket == -1 and first_brace == -1:
        return None

    if first_bracket != -1 and (first_brace == -1 or first_bracket < first_brace):
        start = first_bracket
        end = cleaned.rfind("]")
        if end == -1 or end < start:
            return None
    else:
        start = first_brace
        end = cleaned.rfind("}")
        if end == -1 or end < start:
            return None

    candidate = cleaned[start:end + 1]

    # Step 3: try standard JSON parsing
    try:
        result = json.loads(candidate)
        if isinstance(result, (list, dict)):
            return result
        return None
    except json.JSONDecodeError:
        pass

    # Step 4: try common fixes
    fixed = _fix_common_json_errors(candidate)
    try:
        result = json.loads(fixed)
        if isinstance(result, (list, dict)):
            return result
        return None
    except json.JSONDecodeError:
        pass

    # Step 5: try extracting individual fields with regex
    if first_brace != -1:
        try:
            return _extract_single_object(text)
        except (json.JSONDecodeError, ValueError):
            pass

    return None


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
    raw = extract_json(text)

    if raw is None:
        return _error_result("No structured data found in model response")

    if isinstance(raw, dict):
        # Single tool call object: wrap in list
        raw = [raw]

    if not isinstance(raw, list):
        return _error_result(f"Expected a JSON array of tool calls, got {type(raw).__name__}")

    validated: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            validated.append(_error_item(f"Item {i} is not a dict", original=item))
            continue
        tool = item.get("tool")
        if not tool or not isinstance(tool, str):
            validated.append(_error_item(f"Item {i} missing 'tool' field", original=item))
            continue
        args = item.get("args")
        if args is not None and not isinstance(args, dict):
            validated.append(_error_item(
                f"Item {i} 'args' must be a dict", original=item
            ))
            continue
        validated.append({
            "tool": tool,
            "args": args if isinstance(args, dict) else {},
        })

    return validated


def _error_result(message: str) -> list[dict[str, Any]]:
    return [{"tool": "respond", "args": {"message": message}}]


def _error_item(message: str, original: Any = None) -> dict[str, Any]:
    item: dict[str, Any] = {"tool": "respond", "args": {"message": message}}
    if original is not None:
        item["_original"] = original
    return item


def parse_tool_calls_strict(text: str) -> list[dict[str, Any]]:
    result = parse_tool_calls(text)
    if len(result) == 1 and result[0]["tool"] == "respond" and "No structured data" in str(result[0]["args"].get("message", "")):
        return result
    for tc in result:
        if tc["tool"] == "respond" and "_original" in tc:
            return _error_result("Parsing failed: invalid tool call structure")
    return result
