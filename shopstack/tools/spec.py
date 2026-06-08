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
        if not self.args:
            return f"  - {self.name}(no arguments)\n    {self.description}"
        args_fmt = ", ".join(
            f"{a.name}: {a.description}" for a in self.args
        )
        return f"  - {self.name}({args_fmt})\n    {self.description}"

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
            name="find_item",
            description="Search for an item across inventory and storage locations. Use when the user asks where something is or whether they have something.",
            args=[
                ArgSpec("query", "Search term (item name). Required."),
            ],
            mutability="read",
            category="inventory",
        ),
        ToolSpec(
            name="add_inventory_item",
            description="Add a new item to household inventory. Use when the user wants to record something they bought or received.",
            args=[
                ArgSpec("canonical_name", "Item name in English. Required."),
                ArgSpec("display_name", "Display name (defaults to canonical_name). Optional.", required=False, default=""),
                ArgSpec("quantity", "Amount as a number (e.g., 2.0). Optional, defaults to 1.0.", required=False, default="1.0"),
                ArgSpec("unit", "Unit like kg, L, pieces, packets. Optional, defaults to 'unit'.", required=False, default="unit"),
                ArgSpec("storage_location_id", "Where to store it: kitchen, pantry, fridge, freezer, bathroom, etc. Optional, defaults to 'kitchen'.", required=False, default="kitchen"),
                ArgSpec("category", "Item category. Optional.", required=False, default=""),
            ],
            mutability="write",
            needs_confirmation=False,
            category="inventory",
        ),
        ToolSpec(
            name="consume_inventory_item",
            description="Record that some amount of an item was used or consumed.",
            args=[
                ArgSpec("lot_id", "The lot ID of the item to consume. Can be a prefix. Required."),
                ArgSpec("quantity", "Amount consumed. Optional, defaults to 1.0.", required=False, default="1.0"),
            ],
            mutability="write",
            needs_confirmation=True,
            category="inventory",
        ),
        ToolSpec(
            name="update_inventory_item",
            description="Update details of an existing inventory item like quantity, location, or expiry.",
            args=[
                ArgSpec("lot_id", "The lot ID or prefix to update. Required."),
                ArgSpec("updates", 'A JSON object of fields to update (e.g., {"quantity": 3.0, "storage_location_id": "pantry"}). Required.'),
            ],
            mutability="write",
            needs_confirmation=False,
            category="inventory",
        ),
        ToolSpec(
            name="move_inventory_item",
            description="Move an item to a different storage location.",
            args=[
                ArgSpec("lot_id", "The lot ID or prefix to move. Required."),
                ArgSpec("to_location_id", "Destination location name. Required."),
            ],
            mutability="write",
            needs_confirmation=False,
            category="inventory",
        ),
        ToolSpec(
            name="create_or_update_shopping_list",
            description="Create a shopping list or add items to the active list.",
            args=[
                ArgSpec("items", 'A JSON array of item dicts, each with canonical_name (required), requested_quantity, unit, priority (must_buy/optional/avoid_buying), reason.', required=False, default=""),
                ArgSpec("goal", "A short description of the shopping goal. Optional.", required=False, default=""),
            ],
            mutability="write",
            needs_confirmation=False,
            category="shopping",
        ),
        ToolSpec(
            name="compare_visible_item_to_inventory",
            description="Check if an item the user sees (in a store) is already available at home. Returns buy/skip/maybe decision.",
            args=[
                ArgSpec("canonical_name", "Item name. Required."),
                ArgSpec("quantity", "Amount being considered. Optional, defaults to 1.0.", required=False, default="1.0"),
                ArgSpec("unit", "Unit. Optional.", required=False, default="unit"),
            ],
            mutability="read",
            category="shopping",
        ),
        ToolSpec(
            name="record_price_observation",
            description="Record the price of an item at a store for price memory and trend tracking.",
            args=[
                ArgSpec("canonical_name", "Item name. Required."),
                ArgSpec("price", "Price as a number. Required."),
                ArgSpec("quantity", "Quantity for this price. Optional, defaults to 1.0.", required=False, default="1.0"),
                ArgSpec("unit", "Unit. Optional.", required=False, default="unit"),
                ArgSpec("store_name", "Store name. Optional.", required=False, default=""),
            ],
            mutability="write",
            needs_confirmation=False,
            category="price_memory",
        ),
        ToolSpec(
            name="get_use_soon_items",
            description="Get items that need to be used soon because they are expiring or old.",
            args=[
                ArgSpec("days", "Number of days to look ahead. Optional, defaults to 3.", required=False, default="3"),
            ],
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
    ]


def format_tool_descriptions(specs: list[ToolSpec] | None = None) -> str:
    """Generate planner-readable tool descriptions from ToolSpec objects."""
    if specs is None:
        specs = build_tool_specs()
    lines: list[str] = []
    for spec in specs:
        lines.append(spec.format_for_prompt())
    return "\n".join(lines)
