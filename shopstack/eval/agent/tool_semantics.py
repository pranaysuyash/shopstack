"""Executable-tool semantics derived from the canonical ToolSpec registry."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shopstack.tools.spec import ToolSpec, build_tool_specs


@dataclass(frozen=True)
class ToolSemantics:
    name: str
    mutability: str
    category: str
    needs_confirmation: bool
    entity_args: tuple[str, ...] = ()


# The registry remains the source of truth for argument shape. This table adds
# evaluation meaning only, and is deliberately checked for exhaustive parity.
_SEMANTICS: dict[str, ToolSemantics] = {
    "semantic_find_item": ToolSemantics("semantic_find_item", "read", "inventory", False, ("query",)),
    "find_item": ToolSemantics("find_item", "read", "inventory", False, ("query",)),
    "add_inventory_item": ToolSemantics("add_inventory_item", "write", "inventory", False, ("canonical_name",)),
    "consume_inventory_item": ToolSemantics("consume_inventory_item", "write", "inventory", True, ("lot_id",)),
    "update_inventory_item": ToolSemantics("update_inventory_item", "write", "inventory", False, ("lot_id",)),
    "move_inventory_item": ToolSemantics("move_inventory_item", "write", "inventory", False, ("lot_id", "to_location_id")),
    "undo_last_inventory_change": ToolSemantics("undo_last_inventory_change", "write", "inventory", True, ("lot_id",)),
    "create_or_update_shopping_list": ToolSemantics("create_or_update_shopping_list", "write", "shopping", False, ("items",)),
    "compare_visible_item_to_inventory": ToolSemantics("compare_visible_item_to_inventory", "read", "shopping", False, ("canonical_name",)),
    "record_price_observation": ToolSemantics("record_price_observation", "write", "price_memory", False, ("canonical_name",)),
    "get_use_soon_items": ToolSemantics("get_use_soon_items", "read", "inventory", False),
    "get_next_buy_suggestions": ToolSemantics("get_next_buy_suggestions", "read", "shopping", False),
    "export_anonymized_trace": ToolSemantics("export_anonymized_trace", "read", "observability", False, ("trace_id",)),
    "calculate_nutrition": ToolSemantics("calculate_nutrition", "read", "nutrition", False, ("name",)),
    "check_price_drop": ToolSemantics("check_price_drop", "read", "price_memory", False),
    "find_substitute": ToolSemantics("find_substitute", "read", "shopping", False, ("canonical_name",)),
    "get_weather_recommendation": ToolSemantics("get_weather_recommendation", "read", "planning", False, ("city",)),
    "respond": ToolSemantics("respond", "read", "conversation", False),
}


def runtime_tool_specs(tool_registry: Any | None = None) -> list[ToolSpec]:
    if tool_registry is not None:
        return list(tool_registry.tool_specs())
    return list(build_tool_specs())


def semantics_for(name: str) -> ToolSemantics | None:
    return _SEMANTICS.get(name)


def semantic_map(tool_registry: Any | None = None) -> dict[str, ToolSemantics]:
    """Return only semantics for executable runtime tools, including respond."""
    # ``respond`` is the planner's built-in conversational action and is not
    # registered as a database tool, but it is still a valid parsed action.
    names = {spec.name for spec in runtime_tool_specs(tool_registry)} | {"respond"}
    return {name: _SEMANTICS[name] for name in names if name in _SEMANTICS}


def validate_semantics(tool_registry: Any | None = None) -> list[str]:
    """Return parity errors instead of silently accepting an incomplete map."""
    specs = runtime_tool_specs(tool_registry)
    runtime_names = {spec.name for spec in specs}
    known_names = set(_SEMANTICS)
    errors = [f"missing semantics: {name}" for name in sorted(runtime_names - known_names)]
    errors.extend(f"stale semantics: {name}" for name in sorted(known_names - runtime_names - {"respond"}))
    for spec in specs:
        sem = _SEMANTICS.get(spec.name)
        if sem and (sem.mutability != spec.mutability or sem.category != spec.category):
            errors.append(f"metadata mismatch: {spec.name}")
    return errors
