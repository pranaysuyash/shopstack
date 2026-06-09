#!/usr/bin/env python3
"""Benchmark Phi-4-mini vs Qwen with verbose text descriptions (production format).

Tests both models with raw-text prompt and chat-template formatting to compare
tool-calling accuracy on 10 prompts using the verbose PlannerEngine format.
"""
import base64
import json
import os
import re
import subprocess
import sys
import time

# The 10 prompts from the production benchmark
PROMPTS = [
    ("find_onion", "Find red onions in my inventory"),
    ("consume_rice", "I used 0.5 kg of basmati rice from the kitchen"),
    ("shopping_vegetables", "Add tomatoes, onions, and potatoes to my shopping list"),
    ("compare_eggs", "Check if I already have eggs at home before buying more"),
    ("buy_suggestions", "What should I buy this week? Suggest items based on what's running low"),
    ("add_milk", "I bought 2 liters of milk and put it in the fridge"),
    ("price_tomato", "How much did I pay for tomatoes last time?"),
    ("use_soon_check", "Show me items that are about to expire"),
    ("move_sugar", "Move the sugar from the pantry to the kitchen counter"),
    ("multi_step", "I finished the almond milk. Remove it from inventory and add it to the shopping list"),
]

VERBOSE_TOOLS = (
    "Available tools:\n"
    "  - find_item(query: Search term (item name). Required.)\n"
    "    Search for an item across inventory and storage locations.\n"
    "  - add_inventory_item(canonical_name: Item name in English. Required., quantity: Quantity. Optional, defaults to 1.0., unit: Unit. Optional, defaults to units., purchase_date: YYYY-MM-DD. Optional., expiry_date: YYYY-MM-DD. Optional., price: Price. Optional, defaults to 0., location_id: Storage location. Optional, defaults to Kitchen.)\n"
    "    Add a new item to household inventory.\n"
    "  - consume_inventory_item(lot_id: Lot ID or prefix. Required., quantity: Amount consumed. Optional, defaults to 1.0.)\n"
    "    Record that some amount of an item was used or consumed.\n"
    "  - update_inventory_item(lot_id: Lot ID or prefix. Required., updates: JSON object with fields to update. Required.)\n"
    "    Update details of an existing inventory item.\n"
    "  - move_inventory_item(lot_id: Lot ID or prefix. Required., to_location_id: Destination location. Required.)\n"
    "    Move an item to a different storage location.\n"
    "  - create_or_update_shopping_list(items: JSON array of item dicts. Required., goal: Shopping goal. Optional.)\n"
    "    Create a shopping list or add items to the active list.\n"
    "  - compare_visible_item_to_inventory(canonical_name: Item name. Required., quantity: Amount. Optional, defaults to 1.0., unit: Unit. Optional.)\n"
    "    Check if an item is already available at home.\n"
    "  - get_price_history(canonical_name: Item name. Required., limit: Max records. Optional, defaults to 5.)\n"
    "    Look up past purchase prices for an item.\n"
    "  - list_inventory_use_soon(days: Days to look ahead. Optional, defaults to 7.)\n"
    "    Show items that will expire soon.\n"
    "  - list_inventory_by_location()\n"
    "    List all inventory items grouped by storage location.\n"
    "  - complete_step(step: What the user needs to do next. Required.)\n"
    "    Signal that a step needs user action outside the app."
)

SYSTEM_PROMPT = (
    "You are a helpful household inventory assistant.\n\n"
    "Rules:\n"
    '- Always respond with a JSON array of tool calls.\n'
    '- The first item in the array can be a {"step": "instruction"} if you need the user to do something.\n'
    "- Use multiple tool calls if needed.\n"
    "- If the user asks about something that doesn't match a tool, use complete_step.\n"
    "- Never make up information. If you're not sure, ask.\n"
    "- Do NOT add extra text before or after the JSON. Only output JSON.\n\n"
    + VERBOSE_TOOLS
    + "\n\nCurrent inventory state:\n"
    "- Red onions: 2 kg in Kitchen (purchased 2026-06-01)\n"
    "- Basmati rice: 1 kg in Kitchen (purchased 2026-05-15)\n"
    "- Eggs: 12 units in Fridge (purchased 2026-06-05)\n"
    "- Milk: 1 liter in Fridge (purchased 2026-06-07)\n"
    "- Sugar: 500 g in Pantry (purchased 2026-05-20)\n"
    "- Almond milk: 1 liter in Fridge (expiring 2026-06-09)\n"
    "- Tomatoes: 500 g in Kitchen (purchased 2026-06-03)\n"
    "- Potatoes: 2 kg in Pantry (purchased 2026-05-28)"
)

WORKER_CODE = r"""
import base64, json, os, sys, time
os.environ["SHOPSTACK_OFF_THE_GRID"] = "true"
import psutil
from mlx_lm import load, generate
from mlx_lm.sample_utils import make_sampler

MODEL_NAME = sys.argv[1]
USE_CHAT = sys.argv[2] == "chat"
SYSTEM = base64.b64decode(sys.argv[3]).decode()
QUESTION = base64.b64decode(sys.argv[4]).decode()
MAX_TOKENS = int(sys.argv[5])

model, tokenizer = load(MODEL_NAME)

if USE_CHAT and hasattr(tokenizer, "chat_template") and tokenizer.chat_template:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": QUESTION},
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
else:
    prompt = SYSTEM + "\n\nUser: " + QUESTION

sampler = make_sampler(temp=0.1)
t0 = time.perf_counter()
response = generate(model, tokenizer, prompt=prompt, max_tokens=MAX_TOKENS, sampler=sampler, verbose=False)
elapsed = time.perf_counter() - t0
rss = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
# Base64-encode the response to safely transport multi-line output
encoded = base64.b64encode(response.encode()).decode()
print(f"RSS:{rss:.0f}|LAT:{elapsed*1000:.0f}|OUT:{encoded}", flush=True)
"""


def write_worker() -> str:
    path = "/tmp/phi_qwen_worker.py"
    with open(path, "w") as f:
        f.write(WORKER_CODE)
    return path


def run_worker(model: str, use_chat: bool, system: str, question: str, max_tokens: int = 512) -> dict:
    worker_path = write_worker()
    sys_b64 = base64.b64encode(system.encode()).decode()
    q_b64 = base64.b64encode(question.encode()).decode()
    cmd = [sys.executable, worker_path, model, "chat" if use_chat else "raw", sys_b64, q_b64, str(max_tokens)]
    t0 = time.perf_counter()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    wall = time.perf_counter() - t0
    parsed = {"latency": None, "rss": None, "output": None, "wall": wall, "stderr": result.stderr[:200]}
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if "|OUT:" in line:
            parts = line.split("|OUT:", 1)
            prefix = parts[0]
            encoded = parts[1].strip()
            try:
                parsed["output"] = base64.b64decode(encoded).decode()
            except Exception:
                parsed["output"] = encoded  # fallback if not base64
            for part in prefix.split("|"):
                if part.startswith("RSS:"):
                    parsed["rss"] = float(part[4:])
                elif part.startswith("LAT:"):
                    parsed["latency"] = float(part[4:])
    return parsed


def extract_tool_calls(text: str) -> list:
    if not text:
        return []
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"</?think>", "", text, flags=re.DOTALL)
    text = re.sub(r"```(?:json)?\s*", "", text)
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    candidate = text[start:end+1]
    try:
        data = json.loads(candidate)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return []


def score_response(output: str) -> bool:
    if not output:
        return False
    calls = extract_tool_calls(output)
    if not calls:
        return False
    for call in calls:
        if isinstance(call, dict):
            if "tool" in call or "step" in call:
                return True
    return False


def run_comparison(label: str, model_name: str, use_chat: bool) -> dict:
    results = []
    passed = 0
    latencies = []
    rss_val = None
    for name, question in PROMPTS:
        result = run_worker(model_name, use_chat, SYSTEM_PROMPT, question, max_tokens=512)
        output = result.get("output", "")
        is_correct = score_response(output)
        results.append({"prompt": name, "correct": is_correct, "latency_ms": result.get("latency"), "rss": result.get("rss")})
        if is_correct:
            passed += 1
        if result.get("latency"):
            latencies.append(result["latency"])
        if result.get("rss") and rss_val is None:
            rss_val = result["rss"]
    return {"label": label, "passed": passed, "total": len(PROMPTS), "results": results, "latencies": latencies, "rss": rss_val}


def report(configs: list[dict]):
    print("\n" + "=" * 78)
    print(f"{'Config':<42} {'Accuracy':<10} {'RSS':<10} {'Latency':<12}")
    print("-" * 78)
    for c in configs:
        acc = f"{c['passed']}/{c['total']}"
        rss = f"{c['rss']:.0f}MB" if c.get('rss') else "N/A"
        lat = f"{c['latencies'][0]:.0f}ms" if c.get('latencies') else "N/A"
        print(f"{c['label']:<42} {acc:<10} {rss:<10} {lat:<12}")
    print("=" * 78)

    print("\nPer-prompt breakdown:\n")
    print(f"{'Prompt':<25} {'Qwen-raw':<12} {'Qwen-chat':<12} {'Phi-raw':<12} {'Phi-chat':<12}")
    print("-" * 73)
    for i, (name, _) in enumerate(PROMPTS):
        row = [name[:24]]
        for c in configs:
            r = c["results"][i]
            row.append(("PASS" if r["correct"] else "FAIL").ljust(12))
        print("  ".join(row))

    # Summary
    print("\nSummary:")
    for c in configs:
        avg_lat = f"{sum(c['latencies'])/len(c['latencies']):.0f}ms" if c.get('latencies') else "N/A"
        print(f"  {c['label']}: {c['passed']}/{c['total']}, RSS={c['rss']:.0f}MB" if c.get('rss') else f"  {c['label']}: {c['passed']}/{c['total']}")
        print(f"    Avg latency: {avg_lat}")


if __name__ == "__main__":
    QWEN = "mlx-community/Qwen3.5-4B-4bit"
    PHI = "mlx-community/Phi-4-mini-instruct-4bit"

    configs = [
        run_comparison("Qwen raw-text", QWEN, False),
        run_comparison("Qwen chat-templ", QWEN, True),
        run_comparison("Phi-4-mini raw-text", PHI, False),
        run_comparison("Phi-4-mini chat-templ", PHI, True),
    ]
    report(configs)

    # Cleanup
    if os.path.exists("/tmp/phi_qwen_worker.py"):
        os.remove("/tmp/phi_qwen_worker.py")
