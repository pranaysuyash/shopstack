from __future__ import annotations

from typing import Any

from shopstack.config import settings
from shopstack.tools.registry import ToolRegistry

SYSTEM_PROMPT = f"""You are {settings.app_name}'s household inventory assistant. You help users manage their kitchen and home inventory, shopping lists, purchases, and price tracking.

You have access to these tools. Use them to answer questions and perform actions:

{{tool_descriptions}}

RULES:
1. Return a JSON array of tool calls.
2. Each tool call must be an object with "tool" (the tool name) and "args" (an object of arguments).
3. Do NOT include arguments that are not listed for that tool.
4. If the user asks a question that has no matching tool, use find_item or get_next_buy_suggestions to look up information.
5. If multiple steps are needed, list them in order in the array.
6. If you cannot handle the request, return a single tool call with tool "respond" and args {{"message": "explanation"}}.
7. Do NOT make up information. Only use what is available in inventory context.

OUTPUT FORMAT:
Return ONLY a JSON array. No markdown fences, no explanatory text, no code blocks.
[
  {{"tool": "tool_name", "args": {{"arg1": "value1", "arg2": "value2"}}}},
  ...
]

INVENTORY CONTEXT:
{{inventory_context}}
"""

TOOL_DESCRIPTIONS: list[dict[str, Any]] = [
    {
        "name": "find_item",
        "description": "Search for an item across inventory and storage locations. Use this when the user asks where something is or whether they have something.",
        "args": {
            "query": "Search term (item name). Required."
        },
    },
    {
        "name": "add_inventory_item",
        "description": "Add a new item to household inventory. Use this when the user wants to record something they bought or received.",
        "args": {
            "canonical_name": "Item name in English. Required.",
            "display_name": "Display name (defaults to canonical_name). Optional.",
            "quantity": "Amount as a number (e.g., 2.0). Optional, defaults to 1.0.",
            "unit": "Unit like kg, L, pieces, packets. Optional, defaults to 'unit'.",
            "storage_location_id": "Where to store it: kitchen, pantry, fridge, freezer, bathroom, etc. Optional, defaults to 'kitchen'.",
            "category": "Item category. Optional.",
        },
    },
    {
        "name": "consume_inventory_item",
        "description": "Record that some amount of an item was used or consumed.",
        "args": {
            "lot_id": "The lot ID of the item to consume. Can be a prefix. Required.",
            "quantity": "Amount consumed. Optional, defaults to 1.0.",
        },
    },
    {
        "name": "update_inventory_item",
        "description": "Update details of an existing inventory item like quantity, location, or expiry.",
        "args": {
            "lot_id": "The lot ID or prefix to update. Required.",
            "updates": "A JSON object of fields to update (e.g., {\"quantity\": 3.0, \"storage_location_id\": \"pantry\"}). Required.",
        },
    },
    {
        "name": "move_inventory_item",
        "description": "Move an item to a different storage location.",
        "args": {
            "lot_id": "The lot ID or prefix to move. Required.",
            "to_location_id": "Destination location name. Required.",
        },
    },
    {
        "name": "create_or_update_shopping_list",
        "description": "Create a shopping list or add items to the active list.",
        "args": {
            "items": "A JSON array of item dicts, each with canonical_name (required), requested_quantity, unit, priority (must_buy/optional/avoid_buying), reason.",
            "goal": "A short description of the shopping goal. Optional.",
        },
    },
    {
        "name": "compare_visible_item_to_inventory",
        "description": "Check if an item the user sees (in a store) is already available at home. Returns buy/skip/maybe decision.",
        "args": {
            "canonical_name": "Item name. Required.",
            "quantity": "Amount being considered. Optional, defaults to 1.0.",
            "unit": "Unit. Optional.",
        },
    },
    {
        "name": "record_price_observation",
        "description": "Record the price of an item at a store for price memory and trend tracking.",
        "args": {
            "canonical_name": "Item name. Required.",
            "price": "Price as a number. Required.",
            "quantity": "Quantity for this price. Optional, defaults to 1.0.",
            "unit": "Unit. Optional.",
            "store_name": "Store name. Optional.",
        },
    },
    {
        "name": "get_use_soon_items",
        "description": "Get items that need to be used soon because they are expiring or old.",
        "args": {
            "days": "Number of days to look ahead. Optional, defaults to 3.",
        },
    },
    {
        "name": "get_next_buy_suggestions",
        "description": "Get suggestions for what to buy next based on depleted or low inventory.",
        "args": {},
    },
]


def _format_tool_descriptions(tools: ToolRegistry | None = None) -> str:
    """Format tool descriptions, preferring ToolSpec when available."""
    if tools is not None and hasattr(tools, "format_tool_descriptions"):
        try:
            return tools.format_tool_descriptions()
        except Exception:
            pass
    # Fallback to legacy TOOL_DESCRIPTIONS
    lines: list[str] = []
    for t in TOOL_DESCRIPTIONS:
        args_fmt = ", ".join(
            f"{k}: {v}" for k, v in t["args"].items()
        ) if t["args"] else "None"
        lines.append(f"  - {t['name']}({args_fmt})")
        lines.append(f"    {t['description']}")
    return "\n".join(lines)


def format_inventory_context(db: Any) -> str:
    lots = db.get_inventory(status="active") if hasattr(db, "get_inventory") else []
    if not lots:
        return "Inventory is empty."
    lines: list[str] = []
    for lot in lots[:20]:
        loc = getattr(lot, "storage_location_id", "unknown")
        qty = getattr(lot, "quantity", 0)
        unit = getattr(lot, "unit", "unit")
        name = getattr(lot, "canonical_name", getattr(lot, "display_name", "unknown"))
        lines.append(f"  - {name}: {qty} {unit} (in {loc})")
    if len(lots) > 20:
        lines.append(f"  ... and {len(lots) - 20} more items")
    return "\n".join(lines)


def build_planner_prompt(question: str, db: Any) -> str:
    inventory_context = format_inventory_context(db)
    tool_descriptions = _format_tool_descriptions()
    prompt = (
        f"You are {settings.app_name}'s household inventory assistant. You help users manage their "
        f"kitchen and home inventory, shopping lists, purchases, and price tracking.\n\n"
        f"You have access to these tools. Use them to answer questions and perform actions:\n\n"
        f"{tool_descriptions}\n\n"
        f"RULES:\n"
        f"1. Return a JSON array of tool calls.\n"
        f"2. Each tool call must be an object with \"tool\" (the tool name) and \"args\" (an object of arguments).\n"
        f"3. Do NOT include arguments that are not listed for that tool.\n"
        f"4. If the user asks a question that has no matching tool, use find_item or get_next_buy_suggestions.\n"
        f"5. If multiple steps are needed, list them in order in the array.\n"
        f"6. If you cannot handle the request, return: {{\"tool\": \"respond\", \"args\": {{\"message\": \"explanation\"}}}}\n"
        f"7. Do NOT make up information.\n\n"
        f"OUTPUT FORMAT:\n"
        f"Return ONLY a JSON array. No markdown fences, no explanatory text, no code blocks.\n"
        f"[{{\"tool\": \"tool_name\", \"args\": {{\"arg1\": \"value1\"}}}}, ...]\n\n"
        f"CURRENT INVENTORY:\n{inventory_context}\n\n"
        f"USER: {question}\n\n"
        f"JSON tool calls:"
    )
    return prompt
