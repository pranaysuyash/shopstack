"""Fault injection at the real ToolRegistry boundary."""
from __future__ import annotations

from typing import Any

from shopstack.eval.agent.schema import FaultSpec


class FaultInjectingToolRegistry:
    """Transparent wrapper used only inside an isolated eval world."""

    def __init__(self, registry: Any, faults: list[FaultSpec] | None = None):
        self._registry = registry
        normalized = [fault if isinstance(fault, FaultSpec) else FaultSpec.model_validate(fault) for fault in (faults or [])]
        self._faults = {fault.tool: fault for fault in normalized}

    def tool_specs(self) -> list[Any]:
        return self._registry.tool_specs()

    def list_tools(self) -> list[dict[str, Any]]:
        return self._registry.list_tools()

    def format_tool_descriptions(self, compact: bool = False) -> str:
        return self._registry.format_tool_descriptions(compact=compact)

    def execute(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        fault = self._faults.get(tool_name)
        if fault is None:
            return self._registry.execute(tool_name, **kwargs)
        if fault.kind == "timeout":
            raise TimeoutError(fault.message)
        if fault.kind == "empty":
            return {"success": True, "result": [], "tool": tool_name, "fault": fault.kind}
        if fault.kind == "stale":
            return {
                "success": True,
                "result": {"stale": True, "items": [], "message": fault.message},
                "tool": tool_name,
                "fault": fault.kind,
            }
        return {"success": False, "error": fault.message, "tool": tool_name, "fault": fault.kind}

    def __getattr__(self, name: str) -> Any:
        """Preserve the small private compatibility surface used by the engine."""
        return getattr(self._registry, name)
