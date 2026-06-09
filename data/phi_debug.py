#!/usr/bin/env python3
"""Debug: check raw model output for one prompt to understand scoring failures."""
import json, os, re, subprocess, sys

VERBOSE_TOOLS = r"""Available tools:
  - find_item(query: Search term (item name). Required.)
    Search for an item across inventory and storage locations. Returns matching items with their location, quantity, unit, purchase date, and expiry date.

  - add_inventory_item(canonical_name: Item name in English. Required., display_name: Display name shown in UI. Optional., quantity: Quantity of item to add. Optional, defaults to 1.0., unit: Unit of measurement. Optional, defaults to units., purchase_date: Purchase date in YYYY-MM-DD format. Optional., expiry_date: Expiry date in YYYY-MM-DD format. Optional., price: Price paid. Optional, defaults to 0., location_id: Where the item is stored (e.g. Kitchen, Fridge, Pantry). Optional, defaults to Kitchen.)
    Add a new item to household inventory. Use when the user wants to record something they bought or received.

  - consume_inventory_item(lot_id: The lot ID or prefix to identify the item. Required., quantity: Amount consumed. Optional, defaults to 1.0.)
    Record that some amount of an item was used or consumed. Reduces the remaining quantity of that inventory lot.

  - update_inventory_item(lot_id: The lot ID or prefix to update. Required., updates: A JSON object with fields to update. Required.)
    Update details of an existing inventory item. Fields you can update: quantity, unit, display_name, expiry_date, price.

  - move_inventory_item(lot_id: The lot ID or prefix to move. Required., to_location_id: Destination location name. Required.)
    Move an item to a different storage location.

  - create_or_update_shopping_list(items: A JSON array of item dicts with canonical_name, quantity, unit. Required., goal: A short description of the shopping goal. Optional.)
    Create a shopping list or add items to the active list. Merges with any existing list instead of replacing it.

  - compare_visible_item_to_inventory(canonical_name: Item name. Required., quantity: Amount of the visible item. Optional, defaults to 1.0., unit: Unit of measurement. Optional.)
    Check if an item the user sees is already available at home. Returns whether you have it and where.

  - get_price_history(canonical_name: Item name. Required., limit: Max records to return. Optional, defaults to 5.)
    Look up past purchase prices for an item. Returns date and price per record.

  - list_inventory_use_soon(days: How many days to look ahead for expiry. Optional, defaults to 7.)
    Show items that will expire soon. Returns items expiring within the specified number of days.

  - list_inventory_by_location()
    List all inventory items grouped by their storage location. Shows what you have and where.

  - complete_step(step: What the user needs to do next. Required.)
    Signal that a step needs user action outside the app. The step description will be shown to the user."""

SYSTEM = f"""You are a helpful household inventory assistant.

Rules:
- Always respond with a JSON array of tool calls.
- The first item in the array can be a {"{"}"step": "<natural language instruction for the user>"{"}"} if you need the user to do something.
- Use multiple tool calls if needed.
- If the user asks about something that doesn't match a tool, use complete_step to tell them what to do.
- Never make up information. If you're not sure, ask.
- Do NOT add extra text before or after the JSON. Only output JSON.

{VERBOSE_TOOLS}

Current inventory state:
- Red onions: 2 kg in Kitchen (purchased 2026-06-01)
- Basmati rice: 1 kg in Kitchen (purchased 2026-05-15)
- Eggs: 12 units in Fridge (purchased 2026-06-05)
- Milk: 1 liter in Fridge (purchased 2026-06-07)
- Sugar: 500 g in Pantry (purchased 2026-05-20)
- Almond milk: 1 liter in Fridge (purchased 2026-05-25, expiring 2026-06-09)
- Tomatoes: 500 g in Kitchen (purchased 2026-06-03)
- Potatoes: 2 kg in Pantry (purchased 2026-05-28)
"""

def run(model: str, use_chat: bool, question: str):
    from mlx_lm import load, generate
    from mlx_lm.sample_utils import make_sampler
    model_obj, tokenizer = load(model)
    if use_chat and hasattr(tokenizer, "chat_template") and tokenizer.chat_template:
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    else:
        prompt = SYSTEM + "\n\nUser: " + question
    sampler = make_sampler(temp=0.1)
    response = generate(model_obj, tokenizer, prompt=prompt, max_tokens=512, sampler=sampler, verbose=False)
    return response

if __name__ == "__main__":
    question = sys.argv[3] if len(sys.argv) > 3 else "Find red onions in my inventory"
    use_chat = sys.argv[2] == "chat"
    model = sys.argv[1]
    
    output = run(model, use_chat, question)
    print("=" * 60)
    print("RAW OUTPUT:")
    print("=" * 60)
    print(output)
    print("=" * 60)
    
    # Try extraction
    cleaned = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL)
    cleaned = re.sub(r"```(?:json)?\s*", "", cleaned)
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start >= 0 and end > start:
        candidate = cleaned[start:end+1]
        print("\nEXTRACTED JSON CANDIDATE:")
        print(candidate[:500])
        try:
            data = json.loads(candidate)
            print(f"\nVALID JSON: {type(data).__name__}")
            print(json.dumps(data, indent=2)[:500])
        except json.JSONDecodeError as e:
            print(f"\nJSON PARSE ERROR: {e}")
    else:
        print("\nNO JSON BRACKETS FOUND")
        # Check for other patterns
        if "```" in cleaned:
            print("Found markdown fences")
        if "[" in cleaned:
            print(f"Found '[' at position {cleaned.find('[')}")
        if "]" in cleaned:
            print(f"Found ']' at position {cleaned.rfind(']')}")
