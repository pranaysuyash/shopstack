"""Production-accurate tool-calling accuracy benchmark for Qwen3.5-4B-4bit.

Uses the REAL PlannerEngine prompt format:
  - Verbose tool descriptions from ToolSpec (11 tools)
  - Full system prompt with rules, safety, inventory context
  - Chat template formatting (fix #1)
  - max_tokens=512 (fix #2)
  - Think-tag stripping in parser (fix #3)

This gives the production-accurate ceiling for Qwen3.5-4B-4bit.

Run standalone:
    uv run python benchmarks/bench_planner_tool_calling.py
"""

# ── Environment (must be set before any shopstack imports) ──────────
import os
os.environ["SHOPSTACK_OFF_THE_GRID"] = "true"
os.environ["SHOPSTACK_LOCAL_AUTO_DOWNLOAD"] = "false"

import re
import sys
import time
from typing import Any

from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler

from shopstack.planner.parser import extract_json
from shopstack.planner.prompts import build_planner_prompt, build_system_prompt

MODEL_NAME = "mlx-community/Qwen3.5-4B-4bit"

# ─── Benchmark prompts ──────────────────────────────────────────────

TOOL_PROMPTS: list[tuple[str, str]] = [
    ("add_milk",            "I bought 2 liters of milk. Record it in my inventory in the fridge."),
    ("find_onion",          "Do I have any onions at home?"),
    ("consume_rice",        "I used 0.5 kg of basmati rice from my pantry."),
    ("shopping_vegetables", "Create a shopping list for tomatoes, onions, and potatoes. I need 1 kg of each."),
    ("compare_eggs",        "I'm at the store and see eggs for $3.99. Should I buy them?"),
    ("price_tomato",        "I saw tomatoes at $2.49 per kg at Dmart. Record this price."),
    ("use_soon_check",      "What items in my fridge need to be used soon?"),
    ("buy_suggestions",     "What should I buy next time I go shopping?"),
    ("move_sugar",          "I moved the sugar from the pantry to the kitchen counter."),
    ("multi_step",          "I bought 3 kg of apples and 1 kg of carrots. Record both in the fridge, then check if I need to buy onions."),
]

# Build a quick lookup for re-runs in the analysis section
_PROMPT_MAP: dict[str, str] = dict(TOOL_PROMPTS)


# ─── Parser (matches production extract_json + validation) ──────────

def parse_tool_calls_from_text(text: str) -> list[dict[str, Any]]:
    """Parse tool calls from raw model output, matching production parser."""
    raw = extract_json(text)
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []

    validated: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        tool = item.get("tool")
        if not tool or not isinstance(tool, str):
            continue
        args = item.get("args", {})
        if not isinstance(args, dict):
            continue
        validated.append({"tool": tool, "args": args})
    return validated


def is_valid_tool_call(calls: list[dict[str, Any]]) -> bool:
    if not calls:
        return False
    for call in calls:
        if not isinstance(call, dict) or "tool" not in call or not isinstance(call["tool"], str):
            return False
    return True


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    t0 = time.perf_counter()
    print(f"Loading {MODEL_NAME} ...")
    model, tokenizer = load(MODEL_NAME)
    print(f"Loaded in {time.perf_counter() - t0:.1f}s\n")
    sys.stdout.flush()

    sampler = make_sampler(temp=0.0)

    # Mock database so build_system_prompt() works
    class MockDB:
        def get_inventory(self, status: Any = None) -> list[Any]:
            return []
        def __bool__(self) -> bool:
            return True

    mock_db = MockDB()
    system_prompt = build_system_prompt(mock_db)

    print(f"System prompt length: {len(system_prompt)} chars")
    print(f"Has chat_template: {getattr(tokenizer, 'chat_template', False) is not None}")
    print()
    sys.stdout.flush()

    # ── Production pipeline benchmark ──────────────────────────────
    print("=" * 70)
    print("PRODUCTION-ACCURATE BENCHMARK")
    print("(verbose ToolSpec descriptions + chat template + 512 tok + think-tag strip)")
    print("=" * 70)
    print()

    correct = 0
    total = len(TOOL_PROMPTS)
    details: list[tuple[str, str, bool, int, float, str, str]] = []
    total_prompt_chars = 0

    for pname, question_text in TOOL_PROMPTS:
        # Step 1: Build the raw prompt the way PlannerEngine does
        prompt = build_planner_prompt(question_text, mock_db)

        # Step 2: Apply chat template (matching LocalProvider.plan())
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"USER REQUEST: {question_text}\n\nJSON tool calls:"},
        ]
        try:
            formatted_prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
        except Exception as exc:
            print(f"  [{pname}] CHAT TEMPLATE FAILED: {exc}")
            formatted_prompt = prompt  # fallback

        total_prompt_chars += len(formatted_prompt)

        # Step 3: Generate (max_tokens=512 matching the fix)
        t_gen = time.perf_counter()
        resp = generate(model, tokenizer, prompt=formatted_prompt, max_tokens=512, sampler=sampler)
        elapsed = time.perf_counter() - t_gen

        # Step 4: Parse with think-tag stripping (matching parser fix)
        calls = parse_tool_calls_from_text(resp)
        valid = is_valid_tool_call(calls)

        # Determine failure reason
        fail_reason = ""
        if not valid:
            stripped_think = re.sub(r"<think>.*?</think>", "", resp, flags=re.DOTALL)
            if "[" not in stripped_think:
                fail_reason = " (no JSON found)"
            elif resp.strip().endswith("}") or resp.strip().endswith("]"):
                fail_reason = " (truncated)"
            else:
                fail_reason = " (struct invalid)"

        if valid:
            correct += 1
            status = "✓"
        else:
            status = "✗"

        # Show first tool call for debugging
        call_preview = ""
        if valid and calls:
            first = calls[0]
            call_preview = (
                f" → {first['tool']}("
                + ", ".join(f"{k}={v}" for k, v in first["args"].items())
                + ")"
            )

        details.append((pname, status, valid, len(calls), elapsed, fail_reason, call_preview))
        print(
            f"  [{status}] {pname}: {elapsed*1000:.0f}ms"
            f" | calls={len(calls)} | valid={valid}{fail_reason}{call_preview}"
        )
        sys.stdout.flush()

    accuracy = correct / total * 100
    print(f"\n  Accuracy: {correct}/{total} = {accuracy:.1f}%")
    print(f"  Avg prompt length: {total_prompt_chars // total:,} chars")

    # ── Comparison table ───────────────────────────────────────────
    print()
    print("=" * 70)
    print("COMPARISON WITH EARLIER RESULTS")
    print("=" * 70)
    best = "Best so far" if accuracy >= 90 else "Below compact config"
    verdict = (
        "The verbose descriptions do NOT significantly degrade accuracy."
        if accuracy >= 85
        else "The verbose descriptions DO degrade accuracy vs compact format."
    )
    print(f"""
  Config                                        Accuracy   Notes
  ────────────────────────────────────────────   ────────   ─────────────────────
  Raw prompt + verbose tools + 64-256 tok       0%         Stuck in <think>
  Raw prompt + verbose tools + 512 tok          10%        Conversation repetition
  Raw prompt + compact tools + 256-512 tok      0%         Parser failed on repeats
  Chat template + compact tools + 256 tok       60%        Some truncation
  Chat template + compact tools + 512 tok       90%        Best compact config
  ────────────────────────────────────────────   ────────   ─────────────────────
  ★ PRODUCTION: verbose + chat + 512 tok        {accuracy:.0f}%        {best}

  Verdict: {verdict}
""")

    # ── Raw output analysis (first 3 prompts) ──────────────────────
    print()
    print("=" * 70)
    print("RAW OUTPUT ANALYSIS (first 3 prompts)")
    print("=" * 70)
    for pname, _, _, _, _, _, _ in details[:3]:
        question_text = _PROMPT_MAP.get(pname, pname)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"USER REQUEST: {question_text}\n\nJSON tool calls:"},
        ]
        formatted_prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        resp = generate(model, tokenizer, prompt=formatted_prompt, max_tokens=512, sampler=sampler)

        has_think = "think" in resp.lower()
        has_json = "[" in resp
        think_end = resp.rfind("</think>")
        after_think = resp[think_end + 8:] if think_end >= 0 else resp

        print(f"\n  [{pname}]")
        print(f"    Has <think>: {has_think} | Has JSON: {has_json}")
        print(f"    Response length: {len(resp)} chars")
        if has_think and "</think>" in resp:
            think_start = resp.find("<think>")
            think_close = resp.find("</think>") + 8
            print(f"    Think content: {resp[think_start:think_close]}")
        print(f'    After think tag: "{after_think.strip()[:200]}"')
        sys.stdout.flush()


if __name__ == "__main__":
    main()
