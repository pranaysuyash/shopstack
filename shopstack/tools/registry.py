from __future__ import annotations

from copy import deepcopy
import json
from typing import Any, Callable

from shopstack.persistence.database import Database
from shopstack.schemas.models import PriceObservation
from shopstack.repos.inventory import InventoryRepo
from shopstack.repos.shopping_list import ShoppingListRepo
from shopstack.tools.spec import ArgSpec, ToolSpec, build_tool_specs

ToolFunc = Callable[..., dict[str, Any]]

# Re-export for backward compatibility — services that import this constant
# from tools.registry should keep working.
from shopstack.tools.spec import DEFAULT_STORAGE_LOCATION  # noqa: F401


class ToolRegistry:
    """LLM tool interface adapter.

    Composes focused domain repos (InventoryRepo, ShoppingListRepo) and
    exposes them through a tool-registration + execute interface consumed
    by the planner engine.  The repo instances are public attributes so
    services can depend on the narrow interface they need instead of the
    full adapter.
    """

    def __init__(self, db: Database, embedding_provider: Any = None):
        self.db = db
        self.inventory = InventoryRepo(db, embedding_provider)
        self.shopping_list = ShoppingListRepo(db)
        self._embedding_provider = embedding_provider
        self._tools: dict[str, tuple[ToolFunc, str, list[str]]] = {}
        self._tool_specs = {s.name: s for s in build_tool_specs()}
        self._register_all()

    # ── Tool registration / execution ──────────────────────────────

    def _register(
        self, name: str, fn: ToolFunc, description: str, arg_names: list[str]
    ) -> None:
        self._tools[name] = (fn, description, arg_names)

    def _register_all(self) -> None:
        inv = self.inventory
        sl = self.shopping_list

        self._register("add_inventory_item", inv.add_item,
                       "Add a new item to household inventory",
                       ["canonical_name", "display_name", "quantity", "unit", "storage_location_id"])
        self._register("update_inventory_item", inv.update_item,
                       "Update details of an existing inventory item",
                       ["lot_id", "updates"])
        self._register("consume_inventory_item", inv.consume_item,
                       "Record consumption of an inventory item",
                       ["lot_id", "quantity"])
        self._register("move_inventory_item", inv.move_item,
                       "Move an item to a different storage location",
                       ["lot_id", "to_location_id"])
        self._register("find_item", inv.find,
                       "Search for an item across inventory and locations",
                       ["query"])
        self._register("semantic_find_item", inv.semantic_find,
                       "Search for an item using exact, prefix, and semantic embedding search with match quality scores",
                       ["query"])
        self._register("create_or_update_shopping_list", sl.create_or_update,
                       "Create or update the active shopping list",
                       ["items", "goal"])
        self._register("compare_visible_item_to_inventory", inv.compare_visible,
                       "Compare a detected visible item against current inventory",
                       ["canonical_name", "quantity", "unit"])
        self._register("record_price_observation", self._record_price_observation,
                       "Record a price observation for an item",
                       ["canonical_name", "price", "quantity", "unit", "store_name"])
        self._register("get_use_soon_items", inv.get_use_soon,
                       "Get items that need to be used soon (expiring or old)",
                       ["days"])
        self._register("get_next_buy_suggestions", inv.get_buy_suggestions,
                       "Get suggestions for what to buy next",
                       [])
        self._register("export_anonymized_trace", self._export_anonymized_trace,
                       "Export an anonymized agent trace",
                       ["trace_id"])

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {"name": name, "description": desc, "arg_names": args}
            for name, (_, desc, args) in self._tools.items()
        ]

    def tool_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for name, (_, desc, arg_names) in self._tools.items():
            canonical_spec = self._tool_specs.get(name)
            if canonical_spec is not None:
                specs.append(canonical_spec)
            else:
                specs.append(ToolSpec(
                    name=name,
                    description=desc,
                    args=[ArgSpec(name=a, description=a) for a in arg_names],
                ))
        return specs

    def format_tool_descriptions(self) -> str:
        from shopstack.tools.spec import format_tool_descriptions
        return format_tool_descriptions(self.tool_specs())

    def execute(self, tool_name: str, **kwargs) -> dict[str, Any]:
        entry = self._tools.get(tool_name)
        if not entry:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
        fn, _, _ = entry
        try:
            spec = self._find_tool_spec(tool_name)
            if spec is None:
                normalized_kwargs = kwargs
            else:
                normalized_kwargs, validation_error = self._normalize_tool_args(spec, kwargs)
                if validation_error is not None:
                    return {
                        "success": False,
                        "error": validation_error,
                        "tool": tool_name,
                    }
            result = fn(**normalized_kwargs)
            return {"success": True, "result": result, "tool": tool_name}
        except TypeError as exc:
            return {
                "success": False,
                "error": f"Invalid tool signature for '{tool_name}': {exc}",
                "tool": tool_name,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "tool": tool_name}

    def _find_tool_spec(self, tool_name: str) -> ToolSpec | None:
        """Return canonical ToolSpec for tool name, if defined."""
        return self._tool_specs.get(tool_name)

    def _normalize_tool_args(
        self, spec: ToolSpec, kwargs: dict[str, Any]
    ) -> tuple[dict[str, Any], str | None]:
        """Validate and coerce caller args against ToolSpec.

        Returns:
            normalized args, and an error message if validation fails.
        """
        arg_specs = {a.name: a for a in spec.args}
        normalized: dict[str, Any] = {}

        unknown_args = [name for name in kwargs if name not in arg_specs]
        if unknown_args:
            return {}, f"Tool '{spec.name}' received unexpected args: {', '.join(sorted(unknown_args))}"

        for arg in spec.args:
            if arg.name not in kwargs:
                if arg.required:
                    return {}, f"Missing required argument '{arg.name}' for tool '{spec.name}'"
                if arg.default is not None or arg.type_name in {"string", "number", "array", "object", "boolean", "bool"}:
                    value = deepcopy(arg.default)
                else:
                    value = None
            else:
                value = kwargs[arg.name]
                if arg.required and value is None:
                    return {}, f"Required argument '{arg.name}' for tool '{spec.name}' cannot be null"

            if value is None and not arg.required:
                normalized[arg.name] = None
                continue

            normalized_value, err = self._coerce_arg_value(arg, value)
            if err is not None:
                return {}, err
            normalized[arg.name] = normalized_value

        return normalized, None

    @staticmethod
    def _coerce_arg_value(arg: ArgSpec, value: Any) -> tuple[Any, str | None]:
        """Convert incoming tool args into expected ToolSpec runtime types."""
        type_name = arg.type_name.lower()
        name = arg.name

        if type_name == "string":
            if isinstance(value, str):
                return value, None
            return str(value), None

        if type_name == "number":
            if isinstance(value, bool):
                return None, (
                    f"Argument '{name}' must be a number, not a boolean"
                )
            if isinstance(value, (int, float)):
                return float(value), None
            if isinstance(value, str):
                try:
                    return float(value), None
                except ValueError:
                    return None, f"Argument '{name}' must be a number, got {value!r}"
            return None, f"Argument '{name}' must be a number, got {type(value).__name__}"

        if type_name in {"array", "list"}:
            if isinstance(value, list):
                return list(value), None
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    return None, f"Argument '{name}' must be a JSON array string or array"
                if isinstance(parsed, list):
                    return parsed, None
                return None, f"Argument '{name}' must be a JSON array, got {type(parsed).__name__}"

            return None, f"Argument '{name}' must be an array, got {type(value).__name__}"

        if type_name in {"object", "dict"}:
            if isinstance(value, dict):
                return dict(value), None
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    return None, f"Argument '{name}' must be a JSON object string or object"
                if isinstance(parsed, dict):
                    return parsed, None
                return None, f"Argument '{name}' must be a JSON object, got {type(parsed).__name__}"

            return None, f"Argument '{name}' must be an object, got {type(value).__name__}"

        if type_name in {"boolean", "bool"}:
            if isinstance(value, bool):
                return value, None
            if isinstance(value, str):
                lowered = value.strip().lower()
                if lowered in {"1", "true", "yes", "y"}:
                    return True, None
                if lowered in {"0", "false", "no", "n"}:
                    return False, None
            return None, f"Argument '{name}' must be a boolean"

        return value, None

    # ── Price observation (single method, stays here) ──────────────

    def _record_price_observation(
        self,
        canonical_name: str,
        price: float,
        quantity: float = 1.0,
        unit: str = "unit",
        store_name: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        from datetime import date
        obs = PriceObservation(
            canonical_name=canonical_name,
            price=price,
            quantity=quantity,
            unit=unit,
            store_name=store_name,
            observation_date=date.today(),
            notes=notes,
        )
        self.db.record_price(obs)
        history = self.db.get_price_history(canonical_name)
        last_price = history[1].price if len(history) > 1 else None
        return {
            "observation": obs.model_dump(),
            "last_price": last_price,
            "change": round(price - last_price, 2) if last_price else None,
        }

    # ── Trace export (single method, stays here) ──────────────────

    def _export_anonymized_trace(self, trace_id: str) -> dict[str, Any]:
        traces = self.db.get_traces(limit=100)
        for t in traces:
            if t.trace_id == trace_id:
                return {"trace": _redact_trace(t.model_dump())}
        return {"success": False, "error": f"Trace {trace_id} not found"}

    # ── Backward-compatible delegation methods ─────────────────────
    # These one-liners keep existing callers working during migration.
    # New code should use self.inventory / self.shopping_list directly.

    def add_inventory_item(self, *a, **kw): return self.inventory.add_item(*a, **kw)
    def update_inventory_item(self, *a, **kw): return self.inventory.update_item(*a, **kw)
    def consume_inventory_item(self, *a, **kw): return self.inventory.consume_item(*a, **kw)
    def move_inventory_item(self, *a, **kw): return self.inventory.move_item(*a, **kw)
    def find_item(self, *a, **kw): return self.inventory.find(*a, **kw)
    def semantic_find_item(self, *a, **kw): return self.inventory.semantic_find(*a, **kw)
    def compare_visible_item_to_inventory(self, *a, **kw): return self.inventory.compare_visible(*a, **kw)
    def get_use_soon_items(self, *a, **kw): return self.inventory.get_use_soon(*a, **kw)
    def get_next_buy_suggestions(self, *a, **kw): return self.inventory.get_buy_suggestions(*a, **kw)
    def create_or_update_shopping_list(self, *a, **kw): return self.shopping_list.create_or_update(*a, **kw)
    def record_price_observation(self, *a, **kw): return self._record_price_observation(*a, **kw)
    def export_anonymized_trace(self, *a, **kw): return self._export_anonymized_trace(*a, **kw)


def _redact_trace(t: dict) -> dict:
    if "redacted_user_request" in t:
        t["user_goal"] = "[REDACTED]"
    tool_calls = t.get("proposed_tool_calls", [])
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if isinstance(tc, dict):
                args = tc.get("args", {})
                for sensitive_key in ["address", "phone", "email", "name"]:
                    if sensitive_key in args:
                        args[sensitive_key] = "[REDACTED]"
    t.pop("_private", None)
    return t
