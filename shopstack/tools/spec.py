"""ToolSpec — typed tool definitions for the planner and tool registry.

Every tool in ShopStack has a canonical ToolSpec that defines its name,
description, argument schema, mutability, confirmation needs, and cost.
The planner prompt is generated from these specs instead of hand-written
TOOL_DESCRIPTIONS, eliminating the duplication that caused the P0 priority
mismatch in prompts.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

DEFAULT_STORAGE_LOCATION = "kitchen"


def _compact_arg_str(a: ArgSpec) -> str:
    """Format an arg in compact type-shorthand: 'name: type?' for optional."""
    type_map = {
        "string": "string",
        "number": "number",
        "integer": "int",
        "boolean": "bool",
        "array": "array",
        "object": "obj",
    }
    t = type_map.get(a.type_name, a.type_name)
    return f"{a.name}: {t}?" if not a.required and a.default is not None else f"{a.name}: {t}"


@dataclass
class ArgSpec:
    name: str
    description: str
    type_name: str = "string"
    required: bool = True
    default: Any = None
    enum_values: list[str] | None = None


@dataclass
class ToolSpec:
    name: str
    description: str
    args: list[ArgSpec] = field(default_factory=list)
    mutability: str = "read"  # "read" | "write" | "delete"
    needs_confirmation: bool = False
    cost_tier: str = "free"  # "free" | "local" | "api" | "expensive"
    category: str = "inventory"

    def format_for_prompt(self) -> str:
        """Verbose format with full English prose descriptions."""
        if not self.args:
            return f"  - {self.name}(no arguments)\n    {self.description}"
        args_fmt = ", ".join(
            f"{a.name}: {a.description}" for a in self.args
        )
        return f"  - {self.name}({args_fmt})\n    {self.description}"

    def format_compact(self) -> str:
        """Compact format — type-shorthand args, one-line description.

        Produces output like:
          - add_inventory_item(canonical_name: string, quantity: number?)
            Add item to home inventory

        This format achieves ~90% planner accuracy vs ~50% for verbose prose
        (benchmarked with Qwen3.5-4B-4bit, chat template, 512 max_tokens).
        """
        if not self.args:
            return f"  - {self.name}()\n    {self.description.split('.')[0]}"
        args_fmt = ", ".join(
            _compact_arg_str(a) for a in self.args
        )
        short_desc = self.description.split('.')[0]  # first sentence only
        return f"  - {self.name}({args_fmt})\n    {short_desc}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "args": [
                {
                    "name": a.name,
                    "description": a.description,
                    "type": a.type_name,
                    "required": a.required,
                    "default": a.default,
                    "enum_values": a.enum_values,
                }
                for a in self.args
            ],
            "mutability": self.mutability,
            "needs_confirmation": self.needs_confirmation,
            "cost_tier": self.cost_tier,
            "category": self.category,
        }


def build_tool_specs() -> list[ToolSpec]:
    """Canonical ToolSpec definitions for all 11 tools.

    This is the single source of truth. prompts.py generates planner
    descriptions from these specs. Any new tool must be added here.
    """
    return [
        ToolSpec(
            name="semantic_find_item",
            description="Search for an item using exact, prefix, and semantic embedding search with match quality scores. Falls back to prefix search when the embedding model is unavailable. Preferred over find_item when embedding model is loaded.",
            args=[ArgSpec("query", "Search term (item name). Required.", type_name="string")],
            mutability="read",
            category="inventory",
        ),
        ToolSpec(
            name="find_item",
            description="Search for an item across inventory and storage locations using exact match and prefix matching. Use this when the user asks where something is or whether they have something.",
            args=[ArgSpec("query", "Search term (item name). Required.", type_name="string")],
            mutability="read",
            category="inventory",
        ),
        ToolSpec(
            name="add_inventory_item",
            description="Add a new item to household inventory. Use when the user wants to record something they bought or received.",
            args=[
                ArgSpec("canonical_name", "Item name in English. Required.", type_name="string"),
                ArgSpec("display_name", "Display name (defaults to canonical_name). Optional.", type_name="string", required=False, default=""),
                ArgSpec("quantity", "Amount as a number (e.g., 2.0). Optional, defaults to 1.0.", type_name="number", required=False, default=1.0),
                ArgSpec("unit", "Unit like kg, L, pieces, packets. Optional, defaults to 'unit'.", type_name="string", required=False, default="unit"),
                ArgSpec("storage_location_id", "Where to store it: kitchen, pantry, fridge, freezer, bathroom, etc. Optional, defaults to 'kitchen'.", type_name="string", required=False, default=DEFAULT_STORAGE_LOCATION),
                ArgSpec("category", "Item category. Optional.", type_name="string", required=False, default=""),
                ArgSpec("purchase_date", "Purchase date in YYYY-MM-DD format. Optional.", type_name="string", required=False, default=None),
                ArgSpec("estimated_use_by_date", "Estimated use-by date in YYYY-MM-DD format. Optional.", type_name="string", required=False, default=None),
                ArgSpec("label_expiry_date", "Labeled expiry date in YYYY-MM-DD format. Optional.", type_name="string", required=False, default=None),
                ArgSpec("price_paid", "Price paid for the purchase. Optional.", type_name="number", required=False, default=0.0),
                ArgSpec("source_event_id", "Optional source event id.", type_name="string", required=False, default=""),
                ArgSpec("confidence", "Model/vision confidence for this lot. Optional.", type_name="number", required=False, default=1.0),
            ],
            mutability="write",
            needs_confirmation=False,
            category="inventory",
        ),
        ToolSpec(
            name="consume_inventory_item",
            description="Record that some amount of an item was used or consumed.",
            args=[
                ArgSpec("lot_id", "The lot ID of the item to consume. Can be a prefix. Required.", type_name="string"),
                ArgSpec("quantity", "Amount consumed. Optional, defaults to 1.0.", type_name="number", required=False, default=1.0),
            ],
            mutability="write",
            needs_confirmation=True,
            category="inventory",
        ),
        ToolSpec(
            name="update_inventory_item",
            description="Update details of an existing inventory item like quantity, location, or expiry.",
            args=[
                ArgSpec("lot_id", "The lot ID or prefix to update. Required.", type_name="string"),
                ArgSpec("updates", 'A JSON object of fields to update (e.g., {"quantity": 3.0, "storage_location_id": "pantry"}). Required.', type_name="object"),
            ],
            mutability="write",
            needs_confirmation=False,
            category="inventory",
        ),
        ToolSpec(
            name="move_inventory_item",
            description="Move an item to a different storage location.",
            args=[
                ArgSpec("lot_id", "The lot ID or prefix to move. Required.", type_name="string"),
                ArgSpec("to_location_id", "Destination location name. Required.", type_name="string"),
            ],
            mutability="write",
            needs_confirmation=False,
            category="inventory",
        ),
        ToolSpec(
            name="create_or_update_shopping_list",
            description="Create a shopping list or add items to the active list.",
            args=[
                ArgSpec("items", 'A JSON array of item dicts, each with canonical_name (required), requested_quantity, unit, priority (must_buy/optional/avoid_buying), reason.', type_name="array", required=False, default=[]),
                ArgSpec("goal", "A short description of the shopping goal. Optional.", type_name="string", required=False, default=""),
            ],
            mutability="write",
            needs_confirmation=False,
            category="shopping",
        ),
        ToolSpec(
            name="compare_visible_item_to_inventory",
            description="Check if an item the user sees (in a store) is already available at home. Returns inventory quantity and shortfall data.",
            args=[
                ArgSpec("canonical_name", "Item name. Required.", type_name="string"),
                ArgSpec("quantity", "Amount being considered. Optional, defaults to 1.0.", type_name="number", required=False, default=1.0),
                ArgSpec("unit", "Unit. Optional.", type_name="string", required=False, default="unit"),
            ],
            mutability="read",
            category="shopping",
        ),
        ToolSpec(
            name="record_price_observation",
            description="Record the price of an item at a store for price memory and trend tracking.",
            args=[
                ArgSpec("canonical_name", "Item name. Required.", type_name="string"),
                ArgSpec("price", "Price as a number. Required.", type_name="number"),
                ArgSpec("quantity", "Quantity for this price. Optional, defaults to 1.0.", type_name="number", required=False, default=1.0),
                ArgSpec("unit", "Unit. Optional.", type_name="string", required=False, default="unit"),
                ArgSpec("store_name", "Store name. Optional.", type_name="string", required=False, default=""),
            ],
            mutability="write",
            needs_confirmation=False,
            category="price_memory",
        ),
        ToolSpec(
            name="get_use_soon_items",
            description="Get items that need to be used soon because they are expiring or old.",
            args=[ArgSpec("days", "Number of days to look ahead. Optional, defaults to 3.", type_name="number", required=False, default=3)],
            mutability="read",
            category="inventory",
        ),
        ToolSpec(
            name="get_next_buy_suggestions",
            description="Get suggestions for what to buy next based on depleted or low inventory.",
            args=[],
            mutability="read",
            category="shopping",
        ),
        ToolSpec(
            name="export_anonymized_trace",
            description="Export a recently recorded trace with privacy redactions applied.",
            args=[ArgSpec("trace_id", "Trace identifier to export. Required.", type_name="string")],
            mutability="read",
            category="observability",
        ),
    ]


def format_tool_descriptions(specs: list[ToolSpec] | None = None, compact: bool = False) -> str:
    """Generate planner-readable tool descriptions from ToolSpec objects.

    Args:
        specs: ToolSpec list (defaults to all tools).
        compact: If True, use compact type-shorthand format (achieves ~90%
                 planner accuracy vs ~50% for verbose prose). Default False.
    """
    if specs is None:
        specs = build_tool_specs()
    lines: list[str] = []
    for spec in specs:
        if compact:
            lines.append(spec.format_compact())
        else:
            lines.append(spec.format_for_prompt())
    return "\n".join(lines)
