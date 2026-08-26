"""Planner model benchmark — tool-calling accuracy and latency.

Benchmarks all registered planner candidates on Modal GPU.
Tests tool-calling accuracy, latency, and output quality.
"""

from __future__ import annotations

import json
import time
from typing import Any

import modal

from shopstack.modal.shared import (
    A10G,
    A100_40G,
    A100_80G,
    BENCH_TIMEOUT,
    PLANNER_PROMPTS,
    BenchResult,
    base_image,
)

# ── Model Registry ───────────────────────────────────────────────────────────

PLANNER_MODELS: list[dict[str, Any]] = [
    # Active default
    {
        "id": "ministral-8b-instruct-2410",
        "hf": "mistralai/Ministral-8B-Instruct-2410",
        "gpu": A10G,
        "precision": "int4",
        "runtime": "transformers",
        "status": "active",
    },
    # Best mid-2026 candidate
    {
        "id": "ministral-3-8b-reasoning-2512",
        "hf": "mistralai/Ministral-3-8B-Reasoning-2512",
        "gpu": A10G,
        "precision": "int4",
        "runtime": "transformers",
        "status": "candidate",
    },
    # Best 3B option
    {
        "id": "ministral-3-3b-instruct-2512",
        "hf": "mistralai/Ministral-3-3B-Instruct-2512",
        "gpu": A10G,
        "precision": "int4",
        "runtime": "transformers",
        "status": "candidate",
    },
    # Fastest candidate
    {
        "id": "qwen2.5-7b-instruct",
        "hf": "Qwen/Qwen2.5-7B-Instruct",
        "gpu": A10G,
        "precision": "int4",
        "runtime": "transformers",
        "status": "candidate",
    },
    # Larger candidates (need A100)
    {
        "id": "qwen3.6-27b-fp8",
        "hf": "Qwen/Qwen3.6-27B-FP8",
        "gpu": A100_80G,
        "precision": "fp8",
        "runtime": "transformers-fp8",
        "status": "candidate",
    },
    {
        "id": "gemma-4-31b-qat",
        "hf": "google/gemma-4-31B-it-qat-q4_0-unquantized-assistant",
        "gpu": A100_80G,
        "precision": "q4_0",
        "runtime": "transformers-q4",
        "status": "candidate",
    },
    {
        "id": "qwen3-coder-next",
        "hf": "Qwen/Qwen3-Coder-Next",
        "gpu": A100_80G,
        "precision": "int4",
        "runtime": "transformers-int4",
        "status": "candidate",
    },
    # Local models (for comparison)
    {
        "id": "llama-3.2-3b-gguf",
        "hf": "unsloth/Llama-3.2-3B-Instruct-GGUF",
        "gpu": "cpu",
        "precision": "q4_k_m",
        "runtime": "gguf",
        "status": "candidate",
    },
    {
        "id": "qwen3.5-4b",
        "hf": "Qwen/Qwen3.5-4B",
        "gpu": A10G,
        "precision": "bf16",
        "runtime": "mlx",
        "status": "candidate",
    },
    # Previously benchmarked (re-bench for current data)
    {
        "id": "ministral-3-8b-instruct-2512",
        "hf": "mistralai/Ministral-3-8B-Instruct-2512",
        "gpu": A10G,
        "precision": "int4",
        "runtime": "transformers",
        "status": "candidate",
    },
    {
        "id": "qwen3.5-9b",
        "hf": "Qwen/Qwen3.5-9B",
        "gpu": A10G,
        "precision": "int4",
        "runtime": "transformers",
        "status": "candidate",
    },
    {
        "id": "gemma-3-4b-it-4bit",
        "hf": "mlx-community/gemma-3-4b-it-4bit",
        "gpu": A10G,
        "precision": "int4",
        "runtime": "mlx",
        "status": "candidate",
    },
    {
        "id": "deepseek-r1-distill-qwen-7b-4bit",
        "hf": "mlx-community/DeepSeek-R1-Distill-Qwen-7B-abliterated-4bit",
        "gpu": A10G,
        "precision": "int4",
        "runtime": "mlx",
        "status": "candidate",
    },
    {
        "id": "ministral-3-14b-instruct-2512",
        "hf": "mistralai/Ministral-3-14B-Instruct-2512-BF16",
        "gpu": A100_40G,
        "precision": "int4",
        "runtime": "transformers",
        "status": "candidate",
    },
]

# ── Tool-Calling Eval Set ────────────────────────────────────────────────────

TOOL_CALLING_EVAL = [
    {
        "prompt": "Add 2 kg of rice to the pantry",
        "expected_tool": "add_inventory_item",
        "expected_params": {"canonical_name": "rice", "quantity": 2.0, "unit": "kg"},
    },
    {
        "prompt": "Create a shopping list for milk, bread, and eggs",
        "expected_tool": "create_or_update_shopping_list",
        "expected_params_contains": ["milk", "bread", "eggs"],
    },
    {
        "prompt": "Find items that are about to expire",
        "expected_tool": "get_use_soon_items",
        "expected_params": {},
    },
    {
        "prompt": "How much milk have I bought this month?",
        "expected_tool": "get_price_history",
        "expected_params_contains": ["milk"],
    },
    {
        "prompt": "Mark 1 kg of onions as consumed",
        "expected_tool": "consume_inventory_item",
        "expected_params": {"canonical_name": "onions", "quantity": 1.0},
    },
    {
        "prompt": "What's running low in my pantry?",
        "expected_tool": "find_low_stock_items",
        "expected_params": {},
    },
    {
        "prompt": "Compare prices for basmati rice across stores",
        "expected_tool": "compare_prices",
        "expected_params_contains": ["rice", "basmati"],
    },
    {
        "prompt": "Move the milk from fridge to pantry",
        "expected_tool": "move_inventory_item",
        "expected_params_contains": ["milk"],
    },
    {
        "prompt": "What's the price trend for potatoes?",
        "expected_tool": "get_price_history",
        "expected_params_contains": ["potato"],
    },
    {
        "prompt": "Add 500g of paneer to my shopping list",
        "expected_tool": "create_or_update_shopping_list",
        "expected_params_contains": ["paneer"],
    },
]


# ── Modal App ─────────────────────────────────────────────────────────────────

image = base_image(extra_packages=["bitsandbytes", "scipy", "einops", "sentencepiece"])

app = modal.App("shopstack-planner-bench", image=image)


def load_model(hf_model: str, precision: str, runtime: str):
    """Load a planner model with the appropriate runtime."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if "int4" in precision or "q4" in precision:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        model = AutoModelForCausalLM.from_pretrained(
            hf_model,
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.float16,
            trust_remote_code=True,
        )
    elif "fp8" in precision:
        model = AutoModelForCausalLM.from_pretrained(
            hf_model,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            trust_remote_code=True,
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(
            hf_model,
            device_map="auto",
            torch_dtype=torch.float16,
            trust_remote_code=True,
        )

    tokenizer = AutoTokenizer.from_pretrained(hf_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    return model, tokenizer


def run_inference(model, tokenizer, prompt: str, max_tokens: int = 256) -> dict[str, Any]:
    """Run a single inference and return timing + output."""
    import torch

    messages = [
        {"role": "system", "content": "You are a helpful shopping assistant. Respond with tool calls in JSON format."},
        {"role": "user", "content": prompt},
    ]

    inputs = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt",
    ).to(model.device)

    start = time.perf_counter()
    with torch.no_grad():
        outputs = model.generate(
            inputs,
            max_new_tokens=max_tokens,
            temperature=0.1,
            do_sample=False,
        )
    elapsed = time.perf_counter() - start

    response = tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True)
    tokens_generated = outputs.shape[1] - inputs.shape[1]

    return {
        "response": response.strip(),
        "latency": round(elapsed, 4),
        "tokens": tokens_generated,
        "tokens_per_sec": round(tokens_generated / elapsed, 2) if elapsed > 0 else 0,
    }


def evaluate_tool_calling(response: str, expected: dict) -> dict[str, Any]:
    """Evaluate if the model's response contains the expected tool call."""
    import json
    import re

    result = {"correct": False, "details": {}}

    # Try to extract JSON from response
    json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
    if not json_match:
        result["details"] = {"error": "No JSON found in response"}
        return result

    try:
        parsed = json.loads(json_match.group())
    except json.JSONDecodeError:
        result["details"] = {"error": "Invalid JSON in response"}
        return result

    # Check tool name
    tool_name = parsed.get("tool", parsed.get("name", parsed.get("action", "")))
    expected_tool = expected.get("expected_tool", "")
    tool_match = expected_tool.lower() in tool_name.lower() or tool_name.lower() in expected_tool.lower()

    # Check params
    expected_params = expected.get("expected_params", {})
    expected_contains = expected.get("expected_params_contains", [])
    params = parsed.get("parameters", parsed.get("params", parsed.get("arguments", {})))

    param_match = True
    for k, v in expected_params.items():
        if str(params.get(k, "")).lower() != str(v).lower():
            param_match = False

    contains_match = all(
        any(c.lower() in str(pv).lower() for pv in params.values())
        for c in expected_contains
    ) if expected_contains else True

    result["correct"] = tool_match and param_match and contains_match
    result["details"] = {
        "tool_name": tool_name,
        "expected_tool": expected_tool,
        "tool_match": tool_match,
        "param_match": param_match,
        "contains_match": contains_match,
    }
    return result


@app.function(gpu=A10G, timeout=BENCH_TIMEOUT)
def bench_planner(model_cfg: dict[str, Any]) -> dict[str, Any]:
    """Benchmark a single planner model."""
    import torch

    hf_model = model_cfg["hf"]
    model_id = model_cfg["id"]
    gpu = model_cfg["gpu"]
    precision = model_cfg["precision"]
    runtime = model_cfg["runtime"]

    result = BenchResult(
        model_id=model_id,
        category="planner",
        gpu=gpu,
        precision=precision,
    )

    # Load model
    load_start = time.perf_counter()
    try:
        model, tokenizer = load_model(hf_model, precision, runtime)
        load_time = time.perf_counter() - load_start
        result.metrics["load_time_s"] = round(load_time, 2)
    except Exception as e:
        result.errors.append(f"Model load failed: {e}")
        return result.to_dict()

    # Run tool-calling eval
    correct = 0
    total = len(TOOL_CALLING_EVAL)
    latencies = []
    tokens_per_sec_list = []

    for eval_item in TOOL_CALLING_EVAL:
        prompt = eval_item["prompt"]
        try:
            output = run_inference(model, tokenizer, prompt)
            latencies.append(output["latency"])
            tokens_per_sec_list.append(output["tokens_per_sec"])

            eval_result = evaluate_tool_calling(output["response"], eval_item)
            if eval_result["correct"]:
                correct += 1
        except Exception as e:
            result.errors.append(f"Eval failed for '{prompt[:30]}...': {e}")

    # Run general prompts
    general_latencies = []
    for prompt in PLANNER_PROMPTS[:5]:
        try:
            output = run_inference(model, tokenizer, prompt)
            general_latencies.append(output["latency"])
        except Exception as e:
            result.errors.append(f"Prompt failed: {e}")

    # Compile metrics
    result.metrics["tool_calling_accuracy_pct"] = round(correct / total * 100, 1) if total > 0 else 0
    result.metrics["tool_calling_correct"] = correct
    result.metrics["tool_calling_total"] = total
    result.metrics["mean_latency_s"] = round(sum(latencies) / len(latencies), 3) if latencies else -1
    result.metrics["median_latency_s"] = round(sorted(latencies)[len(latencies) // 2], 3) if latencies else -1
    result.metrics["min_latency_s"] = round(min(latencies), 3) if latencies else -1
    result.metrics["max_latency_s"] = round(max(latencies), 3) if latencies else -1
    result.metrics["mean_tokens_per_sec"] = round(sum(tokens_per_sec_list) / len(tokens_per_sec_list), 1) if tokens_per_sec_list else 0
    result.metrics["gpu_memory_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 2) if torch.cuda.is_available() else 0

    # Cleanup
    del model
    del tokenizer
    torch.cuda.empty_cache()

    return result.to_dict()


@app.function(gpu=A100_80G, timeout=BENCH_TIMEOUT)
def bench_planner_large(model_cfg: dict[str, Any]) -> dict[str, Any]:
    """Benchmark large planner models that need A100 80GB."""
    return bench_planner.remote(model_cfg)


@app.function(timeout=BENCH_TIMEOUT)
def run_all() -> list[dict[str, Any]]:
    """Run all planner benchmarks sequentially."""
    results = []
    for model_cfg in PLANNER_MODELS:
        print(f"\n{'='*60}")
        print(f"Benchmarking: {model_cfg['id']} on {model_cfg['gpu']}")
        print(f"{'='*60}")

        try:
            if model_cfg["gpu"] in (A100_80G,):
                result = bench_planner_large.remote(model_cfg)
            else:
                result = bench_planner.remote(model_cfg)
            results.append(result)
            br = BenchResult(**result)
            print(br.summary())
        except Exception as e:
            error_result = BenchResult(
                model_id=model_cfg["id"],
                category="planner",
                gpu=model_cfg["gpu"],
                precision=model_cfg["precision"],
                errors=[f"Benchmark failed: {e}"],
            )
            results.append(error_result.to_dict())
            print(f"  FAILED: {e}")

    return results


@app.local_entrypoint()
def main():
    """Entry point: run all planner benchmarks."""
    print("Starting ShopStack Planner Benchmarks")
    print(f"Models to benchmark: {len(PLANNER_MODELS)}")
    print(f"Tool-calling eval items: {len(TOOL_CALLING_EVAL)}")
    print()

    results = run_all.remote()

    # Save results
    output = {
        "benchmark": "planner",
        "date": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()),
        "models": PLANNER_MODELS,
        "eval_set": TOOL_CALLING_EVAL,
        "results": results,
    }

    with open("/tmp/planner_bench_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print("BENCHMARK COMPLETE")
    print(f"{'='*60}")
    print("Results saved to /tmp/planner_bench_results.json")

    # Print summary table
    print(f"\n{'Model':<35} {'Accuracy':<10} {'Latency':<10} {'Tokens/s':<10}")
    print("-" * 65)
    for r in results:
        m = r.get("metrics", {})
        acc = f"{m.get('tool_calling_accuracy_pct', 'N/A')}%"
        lat = f"{m.get('mean_latency_s', 'N/A')}s"
        tps = f"{m.get('mean_tokens_per_sec', 'N/A')}"
        err = " [ERROR]" if r.get("errors") else ""
        print(f"{r['model_id']:<35} {acc:<10} {lat:<10} {tps:<10}{err}")
