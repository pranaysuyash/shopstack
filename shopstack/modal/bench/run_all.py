"""Comprehensive ShopStack model benchmark — runs all categories on Modal.

This is the main entry point for running all model benchmarks.
It deploys and runs benchmarks for: planner, vision, OCR, STT, TTS, embeddings, segmentation.
Results are saved to a shared Modal Volume for persistence.
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
    MODEL_CACHE_PATH,
    MODEL_CACHE_VOLUME,
    BenchResult,
    base_image,
)

# ── Base Image with all dependencies ──────────────────────────────────────────

ALL_DEPS = [
    "bitsandbytes",
    "scipy",
    "einops",
    "sentencepiece",
    "accelerate",
    "huggingface-hub",
    "soundfile",
    "librosa",
    "torchaudio",
    "sentence-transformers",
    "pillow",
    "requests",
    "tqdm",
]

image = base_image(extra_packages=ALL_DEPS)

app = modal.App("shopstack-model-bench", image=image)

# ── Model Registry (all categories) ──────────────────────────────────────────

ALL_MODELS: list[dict[str, Any]] = [
    # ── Planner ──
    {"id": "ministral-8b-instruct-2410", "hf": "mistralai/Ministral-8B-Instruct-2410", "gpu": A10G, "precision": "int4", "category": "planner", "runtime": "transformers"},
    {"id": "ministral-3-8b-reasoning-2512", "hf": "mistralai/Ministral-3-8B-Reasoning-2512", "gpu": A10G, "precision": "int4", "category": "planner", "runtime": "transformers"},
    {"id": "ministral-3-3b-instruct-2512", "hf": "mistralai/Ministral-3-3B-Instruct-2512", "gpu": A10G, "precision": "int4", "category": "planner", "runtime": "transformers"},
    {"id": "qwen2.5-7b-instruct", "hf": "Qwen/Qwen2.5-7B-Instruct", "gpu": A10G, "precision": "int4", "category": "planner", "runtime": "transformers"},
    {"id": "qwen3.5-4b", "hf": "Qwen/Qwen3.5-4B", "gpu": A10G, "precision": "bf16", "category": "planner", "runtime": "transformers"},
    {"id": "gemma-3-4b-it-4bit", "hf": "mlx-community/gemma-3-4b-it-4bit", "gpu": A10G, "precision": "int4", "category": "planner", "runtime": "transformers"},
    {"id": "deepseek-r1-distill-qwen-7b-4bit", "hf": "mlx-community/DeepSeek-R1-Distill-Qwen-7B-abliterated-4bit", "gpu": A10G, "precision": "int4", "category": "planner", "runtime": "transformers"},
    {"id": "ministral-3-14b-instruct-2512", "hf": "mistralai/Ministral-3-14B-Instruct-2512-BF16", "gpu": A100_40G, "precision": "int4", "category": "planner", "runtime": "transformers"},
    {"id": "qwen3.6-27b-fp8", "hf": "Qwen/Qwen3.6-27B-FP8", "gpu": A100_80G, "precision": "fp8", "category": "planner", "runtime": "transformers-fp8"},
    {"id": "gemma-4-31b-qat", "hf": "google/gemma-4-31B-it-qat-q4_0-unquantized-assistant", "gpu": A100_80G, "precision": "q4_0", "category": "planner", "runtime": "transformers-q4"},
    {"id": "qwen3-coder-next", "hf": "Qwen/Qwen3-Coder-Next", "gpu": A100_80G, "precision": "int4", "category": "planner", "runtime": "transformers-int4"},
    # ── Vision / VLM ──
    {"id": "qwen3-vl-8b", "hf": "Qwen/Qwen3-VL-8B-Instruct", "gpu": A10G, "precision": "int4", "category": "vision", "runtime": "transformers"},
    {"id": "qwen2.5-vl-7b", "hf": "Qwen/Qwen2.5-VL-7B-Instruct", "gpu": A10G, "precision": "int4", "category": "vision", "runtime": "transformers"},
    {"id": "minicpm-v-4.6", "hf": "openbmb/MiniCPM-V-4.6", "gpu": A10G, "precision": "int4", "category": "vision", "runtime": "transformers"},
    {"id": "molmo2-8b", "hf": "allenai/Molmo2-8B", "gpu": A10G, "precision": "int4", "category": "vision", "runtime": "transformers"},
    {"id": "kimi-vl-a3b-thinking", "hf": "moonshotai/Kimi-VL-A3B-Thinking", "gpu": A10G, "precision": "int4", "category": "vision", "runtime": "transformers"},
    {"id": "minicpm-v-8b", "hf": "openbmb/MiniCPM-V-2_6", "gpu": A10G, "precision": "int4", "category": "vision", "runtime": "transformers"},
    # ── OCR ──
    {"id": "glm-ocr-0.9b", "hf": "zai-org/GLM-OCR", "gpu": A10G, "precision": "fp16", "category": "ocr", "runtime": "transformers"},
    {"id": "deepseek-ocr-2", "hf": "deepseek-ai/DeepSeek-OCR-2", "gpu": A10G, "precision": "int4", "category": "ocr", "runtime": "transformers"},
    {"id": "paddleocr-vl-1.6", "hf": "PaddlePaddle/PaddleOCR-VL-1.6", "gpu": A10G, "precision": "fp16", "category": "ocr", "runtime": "transformers"},
    {"id": "dots-ocr", "hf": "rednote-hilab/dots.ocr", "gpu": A10G, "precision": "int4", "category": "ocr", "runtime": "transformers"},
    {"id": "nuextract3-4b", "hf": "nuance/NuExtract3-4B", "gpu": A10G, "precision": "int4", "category": "ocr", "runtime": "transformers"},
    # ── STT ──
    {"id": "sense-voice-small", "hf": "iic/SenseVoiceSmall", "gpu": A10G, "precision": "fp16", "category": "stt", "runtime": "transformers"},
    {"id": "voxtral-mini-4b-realtime", "hf": "mistralai/Voxtral-Mini-4B-Realtime-2602", "gpu": A10G, "precision": "int4", "category": "stt", "runtime": "transformers"},
    {"id": "parakeet-tdt-0.6b-v3", "hf": "nvidia/parakeet-tdt-0.6b-v3", "gpu": A10G, "precision": "fp16", "category": "stt", "runtime": "transformers"},
    {"id": "fun-asr-nano-2512", "hf": "FunAudioLLM/Fun-ASR-Nano-2512", "gpu": A10G, "precision": "fp16", "category": "stt", "runtime": "transformers"},
    {"id": "qwen3-asr-1.7b", "hf": "Qwen/Qwen3-ASR-1.7B", "gpu": A10G, "precision": "int4", "category": "stt", "runtime": "transformers"},
    {"id": "qwen3-asr-0.6b", "hf": "Qwen/Qwen3-ASR-0.6B", "gpu": A10G, "precision": "int4", "category": "stt", "runtime": "transformers"},
    # ── TTS ──
    {"id": "qwen3-tts-1.7b-customvoice", "hf": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", "gpu": A10G, "precision": "fp16", "category": "tts", "runtime": "custom"},
    {"id": "qwen3-tts-0.6b", "hf": "Qwen/Qwen3-TTS-12Hz-0.6B-Base", "gpu": A10G, "precision": "fp16", "category": "tts", "runtime": "custom"},
    {"id": "qwen3-tts-1.7b-voicedesign", "hf": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", "gpu": A10G, "precision": "fp16", "category": "tts", "runtime": "transformers"},
    {"id": "fun-cosyvoice3-0.5b-2512", "hf": "FunAudioLLM/Fun-CosyVoice3-0.5B-2512", "gpu": A10G, "precision": "fp16", "category": "tts", "runtime": "custom"},
    # ── Embeddings ──
    {"id": "nomic-embed-text-v1.5", "hf": "nomic-ai/nomic-embed-text-v1.5", "gpu": A10G, "precision": "fp16", "category": "embeddings", "runtime": "transformers"},
    {"id": "bge-m3", "hf": "BAAI/bge-m3", "gpu": A10G, "precision": "fp16", "category": "embeddings", "runtime": "transformers"},
    {"id": "qwen3-embedding-0.6b", "hf": "Qwen/Qwen3-Embedding-0.6B", "gpu": A10G, "precision": "fp16", "category": "embeddings", "runtime": "transformers"},
    {"id": "mxbai-embed-large", "hf": "mixedbread-ai/mxbai-embed-large-v1", "gpu": A10G, "precision": "fp16", "category": "embeddings", "runtime": "transformers"},
    {"id": "jina-embeddings-v5-text-nano", "hf": "jinaai/jina-embeddings-v5-text-nano", "gpu": A10G, "precision": "fp16", "category": "embeddings", "runtime": "transformers"},
    # ── Segmentation ──
    {"id": "birefnet", "hf": "ZhengPeng7/BiRefNet", "gpu": A10G, "precision": "fp16", "category": "segmentation", "runtime": "transformers"},
    {"id": "rmbg-2.0", "hf": "briaai/RMBG-2.0", "gpu": A10G, "precision": "fp16", "category": "segmentation", "runtime": "transformers"},
]


# ── Benchmark Functions ──────────────────────────────────────────────────────

@app.function(gpu=A10G, timeout=BENCH_TIMEOUT, volumes={MODEL_CACHE_PATH: MODEL_CACHE_VOLUME})
def bench_model(model_cfg: dict[str, Any]) -> dict[str, Any]:
    """Benchmark a single model across any category."""
    import os

    import torch

    model_id = model_cfg["id"]
    gpu = model_cfg["gpu"]
    precision = model_cfg["precision"]
    category = model_cfg["category"]

    result = BenchResult(model_id=model_id, category=category, gpu=gpu, precision=precision)

    # Set HF cache to our volume
    os.environ["HF_HOME"] = os.path.join(MODEL_CACHE_PATH, "hf")
    os.environ["TRANSFORMERS_CACHE"] = os.path.join(MODEL_CACHE_PATH, "transformers")
    os.makedirs(os.environ["HF_HOME"], exist_ok=True)
    os.makedirs(os.environ["TRANSFORMERS_CACHE"], exist_ok=True)

    try:
        if category == "planner":
            _bench_planner(model_cfg, result)
        elif category == "vision":
            _bench_vision(model_cfg, result)
        elif category == "ocr":
            _bench_ocr(model_cfg, result)
        elif category == "stt":
            _bench_stt(model_cfg, result)
        elif category == "tts":
            _bench_tts(model_cfg, result)
        elif category == "embeddings":
            _bench_embeddings(model_cfg, result)
        elif category == "segmentation":
            _bench_segmentation(model_cfg, result)
    except Exception as e:
        result.errors.append(f"Benchmark failed: {e}")
        import traceback
        result.errors.append(traceback.format_exc()[:500])

    if torch.cuda.is_available():
        result.metrics["gpu_memory_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)
        torch.cuda.empty_cache()

    return result.to_dict()


@app.function(gpu=A100_80G, timeout=BENCH_TIMEOUT, volumes={MODEL_CACHE_PATH: MODEL_CACHE_VOLUME})
def bench_model_large(model_cfg: dict[str, Any]) -> dict[str, Any]:
    """Benchmark large models that need A100 80GB."""
    return bench_model.remote(model_cfg)


# ── Category-Specific Benchmarks ──────────────────────────────────────────────

def _load_transformers_model(hf_model: str, precision: str):
    """Load a model with transformers, handling quantization."""
    import torch
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
    )

    kwargs = {"trust_remote_code": True, "device_map": "auto"}

    if "int4" in precision or "q4" in precision:
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        kwargs["torch_dtype"] = torch.float16
    elif "fp8" in precision:
        kwargs["torch_dtype"] = torch.bfloat16
    else:
        kwargs["torch_dtype"] = torch.float16

    model = AutoModelForCausalLM.from_pretrained(hf_model, **kwargs)
    tokenizer = AutoTokenizer.from_pretrained(hf_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    return model, tokenizer


def _bench_planner(model_cfg: dict, result: BenchResult):
    import json
    import re

    import torch

    hf_model = model_cfg["hf"]
    model, tokenizer = _load_transformers_model(hf_model, model_cfg["precision"])

    eval_set = [
        {"prompt": "Add 2 kg of rice to the pantry", "expected_tool": "add_inventory_item"},
        {"prompt": "Create a shopping list for milk, bread, and eggs", "expected_tool": "create_or_update_shopping_list"},
        {"prompt": "Find items that are about to expire", "expected_tool": "get_use_soon_items"},
        {"prompt": "How much milk have I bought this month?", "expected_tool": "get_price_history"},
        {"prompt": "Mark 1 kg of onions as consumed", "expected_tool": "consume_inventory_item"},
        {"prompt": "What's running low in my pantry?", "expected_tool": "find_low_stock_items"},
        {"prompt": "Compare prices for basmati rice across stores", "expected_tool": "compare_prices"},
        {"prompt": "Move the milk from fridge to pantry", "expected_tool": "move_inventory_item"},
        {"prompt": "What's the price trend for potatoes?", "expected_tool": "get_price_history"},
        {"prompt": "Add 500g of paneer to my shopping list", "expected_tool": "create_or_update_shopping_list"},
    ]

    correct = 0
    latencies = []
    for item in eval_set:
        messages = [
            {"role": "system", "content": "You are a shopping assistant. Respond with JSON tool calls."},
            {"role": "user", "content": item["prompt"]},
        ]
        inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(model.device)

        start = time.perf_counter()
        with torch.no_grad():
            outputs = model.generate(inputs, max_new_tokens=128, temperature=0.1, do_sample=False)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

        response = tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True)
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                tool = parsed.get("tool", parsed.get("name", ""))
                if item["expected_tool"].lower() in tool.lower():
                    correct += 1
            except json.JSONDecodeError:
                pass

    result.metrics["tool_calling_accuracy_pct"] = round(correct / len(eval_set) * 100, 1)
    result.metrics["tool_calling_correct"] = correct
    result.metrics["tool_calling_total"] = len(eval_set)
    result.metrics["mean_latency_s"] = round(sum(latencies) / len(latencies), 3)
    result.metrics["median_latency_s"] = round(sorted(latencies)[len(latencies) // 2], 3)
    result.metrics["min_latency_s"] = round(min(latencies), 3)
    result.metrics["max_latency_s"] = round(max(latencies), 3)


def _bench_vision(model_cfg: dict, result: BenchResult):
    from io import BytesIO

    import requests
    import torch
    from PIL import Image

    hf_model = model_cfg["hf"]

    # Use a test image from the web
    try:
        resp = requests.get("https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/transformers/tasks/car.jpg", timeout=30)
        test_image = Image.open(BytesIO(resp.content))
    except Exception:
        test_image = Image.new("RGB", (224, 224), color="red")

    # Load model
    from transformers import AutoModelForImageTextToText, AutoProcessor

    processor = AutoProcessor.from_pretrained(hf_model, trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        hf_model, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True
    )

    prompts = [
        "Describe this image in detail",
        "What objects can you see?",
        "Is there a vehicle in this image?",
    ]

    latencies = []
    for prompt in prompts:
        inputs = processor(images=test_image, text=prompt, return_tensors="pt").to(model.device, dtype=torch.float16)

        start = time.perf_counter()
        with torch.no_grad():
            model.generate(**inputs, max_new_tokens=100)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

    result.metrics["mean_latency_s"] = round(sum(latencies) / len(latencies), 3)
    result.metrics["prompts_tested"] = len(prompts)


def _bench_ocr(model_cfg: dict, result: BenchResult):
    from io import BytesIO

    import requests
    import torch
    from PIL import Image

    hf_model = model_cfg["hf"]

    # Use a test receipt image
    try:
        resp = requests.get("https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/blog/vision-langchain/ocr_example.png", timeout=30)
        test_image = Image.open(BytesIO(resp.content))
    except Exception:
        test_image = Image.new("RGB", (224, 224), color="white")

    from transformers import AutoModelForImageTextToText, AutoProcessor

    try:
        processor = AutoProcessor.from_pretrained(hf_model, trust_remote_code=True)
        model = AutoModelForImageTextToText.from_pretrained(
            hf_model, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True
        )

        prompts = ["Extract all text from this image", "Read the text in this receipt"]
        latencies = []
        for prompt in prompts:
            inputs = processor(images=test_image, text=prompt, return_tensors="pt").to(model.device, dtype=torch.float16)
            start = time.perf_counter()
            with torch.no_grad():
                model.generate(**inputs, max_new_tokens=200)
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)

        result.metrics["mean_latency_s"] = round(sum(latencies) / len(latencies), 3)
    except Exception as e:
        result.errors.append(f"OCR load/run failed: {e}")


def _bench_stt(model_cfg: dict, result: BenchResult):
    import numpy as np
    import torch

    hf_model = model_cfg["hf"]

    # Generate a simple test audio (1 second of silence + tone)
    sample_rate = 16000
    t = np.linspace(0, 1.0, sample_rate)
    test_audio = (np.sin(2 * np.pi * 440 * t) * 0.1).astype(np.float32)

    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

    try:
        processor = AutoProcessor.from_pretrained(hf_model, trust_remote_code=True)
        model = AutoModelForSpeechSeq2Seq.from_pretrained(
            hf_model, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True
        )

        inputs = processor(test_audio, sampling_rate=sample_rate, return_tensors="pt").input_features.to(model.device, dtype=torch.float16)

        start = time.perf_counter()
        with torch.no_grad():
            model.generate(inputs, max_new_tokens=50)
        elapsed = time.perf_counter() - start

        result.metrics["latency_s"] = round(elapsed, 3)
        result.metrics["audio_duration_s"] = 1.0
        result.metrics["real_time_factor"] = round(elapsed / 1.0, 2)
    except Exception as e:
        result.errors.append(f"STT load/run failed: {e}")


def _bench_tts(model_cfg: dict, result: BenchResult):
    import torch

    hf_model = model_cfg["hf"]

    from transformers import AutoModelForTextToWaveform, AutoProcessor

    try:
        processor = AutoProcessor.from_pretrained(hf_model, trust_remote_code=True)
        model = AutoModelForTextToWaveform.from_pretrained(
            hf_model, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True
        )

        texts = [
            "Your shopping list has 5 items. The estimated total is 350 rupees.",
            "Don't forget to use the tomatoes before they expire in 2 days.",
            "I found basmati rice at 45 rupees per kg at Swiggy.",
        ]

        latencies = []
        for text in texts:
            inputs = processor(text=text, return_tensors="pt").to(model.device, dtype=torch.float16)
            start = time.perf_counter()
            with torch.no_grad():
                outputs = model.generate(**inputs, max_new_tokens=500)
            elapsed = time.perf_counter() - start
            latencies.append(elapsed)
            if hasattr(outputs, "audio"):
                result.metrics["audio_length_s"] = round(len(outputs.audio[0]) / 24000, 2)

        result.metrics["mean_latency_s"] = round(sum(latencies) / len(latencies), 3)
    except Exception as e:
        result.errors.append(f"TTS load/run failed: {e}")


def _bench_embeddings(model_cfg: dict, result: BenchResult):
    import torch
    from sentence_transformers import SentenceTransformer

    hf_model = model_cfg["hf"]

    try:
        model = SentenceTransformer(hf_model, device="cuda" if torch.cuda.is_available() else "cpu")

        texts = [
            "milk", "doodh", "whole milk", "rice", "chawal", "basmati rice",
            "tomato", "tamatar", "onion", "pyaaz", "potato", "aloo",
            "eggs", "ande", "bread", "butter", "cheese", "paneer",
            "yogurt", "dahi", "chicken", "mutton", "fish", "apple",
        ]

        start = time.perf_counter()
        embeddings = model.encode(texts, show_progress_bar=False)
        elapsed = time.perf_counter() - start

        result.metrics["num_texts"] = len(texts)
        result.metrics["total_time_s"] = round(elapsed, 3)
        result.metrics["mean_time_per_text_s"] = round(elapsed / len(texts), 4)
        result.metrics["embedding_dim"] = len(embeddings[0]) if len(embeddings) > 0 else 0

        # Cross-language similarity test
        if "doodh" in texts and "milk" in texts:
            import numpy as np
            milk_idx = texts.index("milk")
            doodh_idx = texts.index("doodh")
            milk_emb = embeddings[milk_idx]
            doodh_emb = embeddings[doodh_idx]
            sim = np.dot(milk_emb, doodh_emb) / (np.linalg.norm(milk_emb) * np.linalg.norm(doodh_emb))
            result.metrics["hindi_english_similarity"] = round(float(sim), 4)
    except Exception as e:
        result.errors.append(f"Embeddings load/run failed: {e}")


def _bench_segmentation(model_cfg: dict, result: BenchResult):
    from io import BytesIO

    import requests
    import torch
    from PIL import Image

    hf_model = model_cfg["hf"]

    try:
        resp = requests.get("https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/transformers/tasks/car.jpg", timeout=30)
        test_image = Image.open(BytesIO(resp.content))
    except Exception:
        test_image = Image.new("RGB", (224, 224), color="red")

    from transformers import AutoImageProcessor, AutoModelForImageSegmentation

    try:
        processor = AutoImageProcessor.from_pretrained(hf_model, trust_remote_code=True)
        model = AutoModelForImageSegmentation.from_pretrained(
            hf_model, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True
        )

        inputs = processor(images=test_image, return_tensors="pt").to(model.device, dtype=torch.float16)

        start = time.perf_counter()
        with torch.no_grad():
            outputs = model(**inputs)
        elapsed = time.perf_counter() - start

        result.metrics["latency_s"] = round(elapsed, 3)
        if hasattr(outputs, "pred_masks"):
            result.metrics["mask_shape"] = str(list(outputs.pred_masks.shape))
    except Exception as e:
        result.errors.append(f"Segmentation load/run failed: {e}")


# ── Orchestrator ─────────────────────────────────────────────────────────────

@app.function(timeout=BENCH_TIMEOUT * 2)
def run_category(category: str) -> list[dict[str, Any]]:
    """Run all benchmarks for a single category."""
    models = [m for m in ALL_MODELS if m["category"] == category]
    results = []

    print(f"\n{'='*60}")
    print(f"Benchmarking category: {category} ({len(models)} models)")
    print(f"{'='*60}")

    for model_cfg in models:
        print(f"\n  Model: {model_cfg['id']} on {model_cfg['gpu']}")
        try:
            if model_cfg["gpu"] in (A100_80G,):
                result = bench_model_large.remote(model_cfg)
            else:
                result = bench_model.remote(model_cfg)
            results.append(result)
            br = BenchResult(**result)
            print(f"  {br.summary()}")
        except Exception as e:
            error_result = BenchResult(
                model_id=model_cfg["id"],
                category=category,
                gpu=model_cfg["gpu"],
                precision=model_cfg["precision"],
                errors=[f"Benchmark failed: {e}"],
            )
            results.append(error_result.to_dict())
            print(f"  FAILED: {e}")

    return results


@app.function(timeout=BENCH_TIMEOUT * 3)
def run_all() -> dict[str, list[dict[str, Any]]]:
    """Run all benchmarks across all categories."""
    categories = ["planner", "vision", "ocr", "stt", "tts", "embeddings", "segmentation"]
    all_results = {}

    for cat in categories:
        all_results[cat] = run_category.remote(cat)

    return all_results


@app.local_entrypoint()
def main():
    """Entry point: run all benchmarks."""
    import time as tmod

    print("=" * 60)
    print("ShopStack Comprehensive Model Benchmarks")
    print("=" * 60)
    print(f"Total models: {len(ALL_MODELS)}")
    print(f"Categories: {sorted(set(m['category'] for m in ALL_MODELS))}")
    print()

    start_time = tmod.time()
    all_results = run_all.remote()
    total_time = tmod.time() - start_time

    # Save results
    output = {
        "benchmark": "comprehensive",
        "date": tmod.strftime("%Y-%m-%d %H:%M UTC", tmod.gmtime()),
        "total_models": len(ALL_MODELS),
        "total_time_minutes": round(total_time / 60, 1),
        "results": all_results,
    }

    with open("/tmp/shopstack_bench_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n{'='*60}")
    print("BENCHMARK COMPLETE")
    print(f"{'='*60}")
    print(f"Total time: {round(total_time / 60, 1)} minutes")
    print("Results saved to /tmp/shopstack_bench_results.json")

    # Print summary
    for category, results in all_results.items():
        print(f"\n{'─'*50}")
        print(f"Category: {category}")
        print(f"{'─'*50}")
        print(f"{'Model':<35} {'Key Metric':<20} {'Errors':<10}")
        print("-" * 65)
        for r in results:
            m = r.get("metrics", {})
            err = "YES" if r.get("errors") else ""
            if category == "planner":
                metric = f"{m.get('tool_calling_accuracy_pct', 'N/A')}% acc, {m.get('mean_latency_s', 'N/A')}s"
            elif category == "embeddings":
                metric = f"{m.get('mean_time_per_text_s', 'N/A')}s/text, sim={m.get('hindi_english_similarity', 'N/A')}"
            else:
                metric = f"{m.get('mean_latency_s', m.get('latency_s', 'N/A'))}s"
            print(f"{r['model_id']:<35} {metric:<20} {err:<10}")
