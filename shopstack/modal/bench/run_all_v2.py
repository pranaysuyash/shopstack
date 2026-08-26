"""ShopStack Model Benchmarks v2 — per-category functions at module level.

Each category has its own Modal function with the correct image and GPU.
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

# ── Per-category images ──────────────────────────────────────────────────────

planner_img = base_image(["bitsandbytes", "scipy", "einops", "sentencepiece", "accelerate>=1.5.0"])
vision_img = base_image(["torchvision>=0.22.0", "pillow>=11.0.0", "accelerate>=1.5.0", "einops"])
ocr_img = base_image(["torchvision>=0.22.0", "pillow>=11.0.0", "accelerate>=1.5.0", "einops"])
stt_img = base_image(["soundfile", "librosa", "torchaudio", "accelerate>=1.5.0"])
tts_img = base_image(["soundfile", "torchaudio", "accelerate>=1.5.0"])
embeddings_img = base_image(["sentence-transformers>=3.4.0", "accelerate>=1.5.0"])
segmentation_img = base_image(["torchvision>=0.22.0", "pillow>=11.0.0", "accelerate>=1.5.0"])

app = modal.App("shopstack-model-bench-v2")

# ── Model Registry ────────────────────────────────────────────────────────────

ALL_MODELS: list[dict[str, Any]] = [
    {"id": "ministral-8b-instruct-2410", "hf": "mistralai/Ministral-8B-Instruct-2410", "gpu": A10G, "precision": "int4", "category": "planner"},
    {"id": "ministral-3-8b-reasoning-2512", "hf": "mistralai/Ministral-3-8B-Reasoning-2512", "gpu": A10G, "precision": "int4", "category": "planner"},
    {"id": "ministral-3-3b-instruct-2512", "hf": "mistralai/Ministral-3-3B-Instruct-2512", "gpu": A10G, "precision": "int4", "category": "planner"},
    {"id": "qwen2.5-7b-instruct", "hf": "Qwen/Qwen2.5-7B-Instruct", "gpu": A10G, "precision": "int4", "category": "planner"},
    {"id": "qwen3.5-4b", "hf": "Qwen/Qwen3.5-4B", "gpu": A10G, "precision": "bf16", "category": "planner"},
    {"id": "gemma-3-4b-it-4bit", "hf": "mlx-community/gemma-3-4b-it-4bit", "gpu": A10G, "precision": "int4", "category": "planner"},
    {"id": "deepseek-r1-distill-qwen-7b-4bit", "hf": "mlx-community/DeepSeek-R1-Distill-Qwen-7B-abliterated-4bit", "gpu": A10G, "precision": "int4", "category": "planner"},
    {"id": "ministral-3-14b-instruct-2512", "hf": "mistralai/Ministral-3-14B-Instruct-2512-BF16", "gpu": A100_40G, "precision": "int4", "category": "planner"},
    {"id": "qwen3.6-27b-fp8", "hf": "Qwen/Qwen3.6-27B-FP8", "gpu": A100_80G, "precision": "fp8", "category": "planner"},
    {"id": "gemma-4-31b-qat", "hf": "google/gemma-4-31B-it-qat-q4_0-unquantized-assistant", "gpu": A100_80G, "precision": "q4_0", "category": "planner"},
    {"id": "qwen3-coder-next", "hf": "Qwen/Qwen3-Coder-Next", "gpu": A100_80G, "precision": "int4", "category": "planner"},
    {"id": "qwen3-vl-8b", "hf": "Qwen/Qwen3-VL-8B-Instruct", "gpu": A10G, "precision": "int4", "category": "vision"},
    {"id": "qwen2.5-vl-7b", "hf": "Qwen/Qwen2.5-VL-7B-Instruct", "gpu": A10G, "precision": "int4", "category": "vision"},
    {"id": "minicpm-v-4.6", "hf": "openbmb/MiniCPM-V-4.6", "gpu": A10G, "precision": "int4", "category": "vision"},
    {"id": "molmo2-8b", "hf": "allenai/Molmo2-8B", "gpu": A10G, "precision": "int4", "category": "vision"},
    {"id": "kimi-vl-a3b-thinking", "hf": "moonshotai/Kimi-VL-A3B-Thinking", "gpu": A10G, "precision": "int4", "category": "vision"},
    {"id": "minicpm-v-8b", "hf": "openbmb/MiniCPM-V-2_6", "gpu": A10G, "precision": "int4", "category": "vision"},
    {"id": "glm-ocr-0.9b", "hf": "zai-org/GLM-OCR", "gpu": A10G, "precision": "fp16", "category": "ocr"},
    {"id": "deepseek-ocr-2", "hf": "deepseek-ai/DeepSeek-OCR-2", "gpu": A10G, "precision": "int4", "category": "ocr"},
    {"id": "paddleocr-vl-1.6", "hf": "PaddlePaddle/PaddleOCR-VL-1.6", "gpu": A10G, "precision": "fp16", "category": "ocr"},
    {"id": "dots-ocr", "hf": "rednote-hilab/dots.ocr", "gpu": A10G, "precision": "int4", "category": "ocr"},
    {"id": "nuextract3-4b", "hf": "nuance/NuExtract3-4B", "gpu": A10G, "precision": "int4", "category": "ocr"},
    {"id": "sense-voice-small", "hf": "iic/SenseVoiceSmall", "gpu": A10G, "precision": "fp16", "category": "stt"},
    {"id": "voxtral-mini-4b-realtime", "hf": "mistralai/Voxtral-Mini-4B-Realtime-2602", "gpu": A10G, "precision": "int4", "category": "stt"},
    {"id": "parakeet-tdt-0.6b-v3", "hf": "nvidia/parakeet-tdt-0.6b-v3", "gpu": A10G, "precision": "fp16", "category": "stt"},
    {"id": "fun-asr-nano-2512", "hf": "FunAudioLLM/Fun-ASR-Nano-2512", "gpu": A10G, "precision": "fp16", "category": "stt"},
    {"id": "qwen3-asr-1.7b", "hf": "Qwen/Qwen3-ASR-1.7B", "gpu": A10G, "precision": "int4", "category": "stt"},
    {"id": "qwen3-asr-0.6b", "hf": "Qwen/Qwen3-ASR-0.6B", "gpu": A10G, "precision": "int4", "category": "stt"},
    {"id": "qwen3-tts-1.7b-customvoice", "hf": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", "gpu": A10G, "precision": "fp16", "category": "tts"},
    {"id": "qwen3-tts-0.6b", "hf": "Qwen/Qwen3-TTS-12Hz-0.6B-Base", "gpu": A10G, "precision": "fp16", "category": "tts"},
    {"id": "qwen3-tts-1.7b-voicedesign", "hf": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", "gpu": A10G, "precision": "fp16", "category": "tts"},
    {"id": "fun-cosyvoice3-0.5b-2512", "hf": "FunAudioLLM/Fun-CosyVoice3-0.5B-2512", "gpu": A10G, "precision": "fp16", "category": "tts"},
    {"id": "nomic-embed-text-v1.5", "hf": "nomic-ai/nomic-embed-text-v1.5", "gpu": A10G, "precision": "fp16", "category": "embeddings"},
    {"id": "bge-m3", "hf": "BAAI/bge-m3", "gpu": A10G, "precision": "fp16", "category": "embeddings"},
    {"id": "qwen3-embedding-0.6b", "hf": "Qwen/Qwen3-Embedding-0.6B", "gpu": A10G, "precision": "fp16", "category": "embeddings"},
    {"id": "mxbai-embed-large", "hf": "mixedbread-ai/mxbai-embed-large-v1", "gpu": A10G, "precision": "fp16", "category": "embeddings"},
    {"id": "jina-embeddings-v5-text-nano", "hf": "jinaai/jina-embeddings-v5-text-nano", "gpu": A10G, "precision": "fp16", "category": "embeddings"},
    {"id": "birefnet", "hf": "ZhengPeng7/BiRefNet", "gpu": A10G, "precision": "fp16", "category": "segmentation"},
    {"id": "rmbg-2.0", "hf": "briaai/RMBG-2.0", "gpu": A10G, "precision": "fp16", "category": "segmentation"},
]


def _setup_env():
    import os
    os.environ["HF_HOME"] = os.path.join(MODEL_CACHE_PATH, "hf")
    os.environ["TRANSFORMERS_CACHE"] = os.path.join(MODEL_CACHE_PATH, "transformers")
    os.makedirs(os.environ["HF_HOME"], exist_ok=True)
    os.makedirs(os.environ["TRANSFORMERS_CACHE"], exist_ok=True)


def _bench_planner(model_cfg: dict, result: BenchResult):
    import json
    import re

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    hf, prec = model_cfg["hf"], model_cfg["precision"]
    kwargs = {"trust_remote_code": True, "device_map": "auto"}
    if "int4" in prec:
        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4")
        kwargs["torch_dtype"] = torch.float16
    elif "fp8" in prec:
        kwargs["torch_dtype"] = torch.bfloat16
    else:
        kwargs["torch_dtype"] = torch.float16
    model = AutoModelForCausalLM.from_pretrained(hf, **kwargs)
    tokenizer = AutoTokenizer.from_pretrained(hf, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    eval_set = [{"p": "Add 2 kg of rice to the pantry", "t": "add_inventory_item"},
                {"p": "Create a shopping list for milk, bread, and eggs", "t": "create_or_update_shopping_list"},
                {"p": "Find items that are about to expire", "t": "get_use_soon_items"},
                {"p": "How much milk have I bought this month?", "t": "get_price_history"},
                {"p": "Mark 1 kg of onions as consumed", "t": "consume_inventory_item"},
                {"p": "What's running low in my pantry?", "t": "find_low_stock_items"},
                {"p": "Compare prices for basmati rice across stores", "t": "compare_prices"},
                {"p": "Move the milk from fridge to pantry", "t": "move_inventory_item"},
                {"p": "What's the price trend for potatoes?", "t": "get_price_history"},
                {"p": "Add 500g of paneer to my shopping list", "t": "create_or_update_shopping_list"}]
    correct, latencies = 0, []
    for item in eval_set:
        msgs = [{"role": "system", "content": "You are a shopping assistant. Respond with JSON tool calls."},
                {"role": "user", "content": item["p"]}]
        inputs = tokenizer.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt").to(model.device)
        start = time.perf_counter()
        with torch.no_grad():
            outputs = model.generate(inputs, max_new_tokens=128, temperature=0.1, do_sample=False)
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)
        resp = tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True)
        jm = re.search(r'\{[^{}]*\}', resp, re.DOTALL)
        if jm:
            try:
                parsed = json.loads(jm.group())
                tool = parsed.get("tool", parsed.get("name", ""))
                if item["t"].lower() in tool.lower():
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
    hf = model_cfg["hf"]
    try:
        resp = requests.get("https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/transformers/tasks/car.jpg", timeout=30)
        img = Image.open(BytesIO(resp.content))
    except Exception:
        img = Image.new("RGB", (224, 224), color="red")
    from transformers import AutoModelForImageTextToText, AutoProcessor
    try:
        processor = AutoProcessor.from_pretrained(hf, trust_remote_code=True)
        model = AutoModelForImageTextToText.from_pretrained(hf, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True)
        prompts = ["Describe this image", "What objects can you see?"]
        latencies = []
        for p in prompts:
            inputs = processor(images=img, text=p, return_tensors="pt").to(model.device, dtype=torch.float16)
            start = time.perf_counter()
            with torch.no_grad():
                model.generate(**inputs, max_new_tokens=100)
            latencies.append(time.perf_counter() - start)
        result.metrics["mean_latency_s"] = round(sum(latencies) / len(latencies), 3)
    except Exception as e:
        result.errors.append(f"Vision failed: {e}")


def _bench_ocr(model_cfg: dict, result: BenchResult):
    from io import BytesIO

    import requests
    import torch
    from PIL import Image
    hf = model_cfg["hf"]
    try:
        resp = requests.get("https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/blog/vision-langchain/ocr_example.png", timeout=30)
        img = Image.open(BytesIO(resp.content))
    except Exception:
        img = Image.new("RGB", (224, 224), color="white")
    from transformers import AutoModelForImageTextToText, AutoProcessor
    try:
        processor = AutoProcessor.from_pretrained(hf, trust_remote_code=True)
        model = AutoModelForImageTextToText.from_pretrained(hf, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True)
        prompts = ["Extract all text from this image", "Read the text in this receipt"]
        latencies = []
        for p in prompts:
            inputs = processor(images=img, text=p, return_tensors="pt").to(model.device, dtype=torch.float16)
            start = time.perf_counter()
            with torch.no_grad():
                model.generate(**inputs, max_new_tokens=200)
            latencies.append(time.perf_counter() - start)
        result.metrics["mean_latency_s"] = round(sum(latencies) / len(latencies), 3)
    except Exception as e:
        result.errors.append(f"OCR failed: {e}")


def _bench_stt(model_cfg: dict, result: BenchResult):
    import numpy as np
    import torch
    hf = model_cfg["hf"]
    sr = 16000
    audio = (np.sin(2 * np.pi * 440 * np.linspace(0, 1.0, sr)) * 0.1).astype(np.float32)
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor
    try:
        processor = AutoProcessor.from_pretrained(hf, trust_remote_code=True)
        model = AutoModelForSpeechSeq2Seq.from_pretrained(hf, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True)
        inputs = processor(audio, sampling_rate=sr, return_tensors="pt").input_features.to(model.device, dtype=torch.float16)
        start = time.perf_counter()
        with torch.no_grad():
            model.generate(inputs, max_new_tokens=50)
        elapsed = time.perf_counter() - start
        result.metrics["latency_s"] = round(elapsed, 3)
        result.metrics["real_time_factor"] = round(elapsed / 1.0, 2)
    except Exception as e:
        result.errors.append(f"STT failed: {e}")


def _bench_tts(model_cfg: dict, result: BenchResult):
    import torch
    hf = model_cfg["hf"]
    from transformers import AutoModelForTextToWaveform, AutoProcessor
    try:
        processor = AutoProcessor.from_pretrained(hf, trust_remote_code=True)
        model = AutoModelForTextToWaveform.from_pretrained(hf, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True)
        texts = ["Your shopping list has 5 items.", "Don't forget the tomatoes."]
        latencies = []
        for t in texts:
            inputs = processor(text=t, return_tensors="pt").to(model.device, dtype=torch.float16)
            start = time.perf_counter()
            with torch.no_grad():
                model.generate(**inputs, max_new_tokens=500)
            latencies.append(time.perf_counter() - start)
        result.metrics["mean_latency_s"] = round(sum(latencies) / len(latencies), 3)
    except Exception as e:
        result.errors.append(f"TTS failed: {e}")


def _bench_embeddings(model_cfg: dict, result: BenchResult):
    import numpy as np
    import torch
    from sentence_transformers import SentenceTransformer
    hf = model_cfg["hf"]
    try:
        model = SentenceTransformer(hf, device="cuda" if torch.cuda.is_available() else "cpu")
        texts = ["milk", "doodh", "whole milk", "rice", "chawal", "basmati rice",
                 "tomato", "tamatar", "onion", "pyaaz", "potato", "aloo",
                 "eggs", "ande", "bread", "butter", "cheese", "paneer",
                 "yogurt", "dahi", "chicken", "mutton", "fish", "apple"]
        start = time.perf_counter()
        embs = model.encode(texts, show_progress_bar=False)
        elapsed = time.perf_counter() - start
        result.metrics["num_texts"] = len(texts)
        result.metrics["total_time_s"] = round(elapsed, 3)
        result.metrics["mean_time_per_text_s"] = round(elapsed / len(texts), 4)
        result.metrics["embedding_dim"] = len(embs[0]) if len(embs) > 0 else 0
        if "doodh" in texts and "milk" in texts:
            mi, di = texts.index("milk"), texts.index("doodh")
            sim = float(np.dot(embs[mi], embs[di]) / (np.linalg.norm(embs[mi]) * np.linalg.norm(embs[di])))
            result.metrics["hindi_english_similarity"] = round(sim, 4)
    except Exception as e:
        result.errors.append(f"Embeddings failed: {e}")


def _bench_segmentation(model_cfg: dict, result: BenchResult):
    from io import BytesIO

    import requests
    import torch
    from PIL import Image
    hf = model_cfg["hf"]
    try:
        resp = requests.get("https://huggingface.co/datasets/huggingface/documentation-images/resolve/main/transformers/tasks/car.jpg", timeout=30)
        img = Image.open(BytesIO(resp.content))
    except Exception:
        img = Image.new("RGB", (224, 224), color="red")
    from transformers import AutoImageProcessor, AutoModelForImageSegmentation
    try:
        processor = AutoImageProcessor.from_pretrained(hf, trust_remote_code=True)
        model = AutoModelForImageSegmentation.from_pretrained(hf, torch_dtype=torch.float16, device_map="auto", trust_remote_code=True)
        inputs = processor(images=img, return_tensors="pt").to(model.device, dtype=torch.float16)
        start = time.perf_counter()
        with torch.no_grad():
            model(**inputs)
        elapsed = time.perf_counter() - start
        result.metrics["latency_s"] = round(elapsed, 3)
    except Exception as e:
        result.errors.append(f"Segmentation failed: {e}")


def _run_bench(model_cfg: dict) -> dict[str, Any]:
    _setup_env()
    import torch
    result = BenchResult(model_id=model_cfg["id"], category=model_cfg["category"], gpu=model_cfg["gpu"], precision=model_cfg["precision"])
    try:
        cat = model_cfg["category"]
        if cat == "planner":
            _bench_planner(model_cfg, result)
        elif cat == "vision":
            _bench_vision(model_cfg, result)
        elif cat == "ocr":
            _bench_ocr(model_cfg, result)
        elif cat == "stt":
            _bench_stt(model_cfg, result)
        elif cat == "tts":
            _bench_tts(model_cfg, result)
        elif cat == "embeddings":
            _bench_embeddings(model_cfg, result)
        elif cat == "segmentation":
            _bench_segmentation(model_cfg, result)
    except Exception as e:
        import traceback
        result.errors.append(f"Benchmark failed: {e}")
        result.errors.append(traceback.format_exc()[:500])
    if torch.cuda.is_available():
        result.metrics["gpu_memory_gb"] = round(torch.cuda.max_memory_allocated() / 1e9, 2)
        torch.cuda.empty_cache()
    return result.to_dict()


# ── Per-category Modal functions ──────────────────────────────────────────────

@app.function(image=planner_img, gpu=A10G, timeout=BENCH_TIMEOUT, volumes={MODEL_CACHE_PATH: MODEL_CACHE_VOLUME})
def bench_planner(model_cfg: dict) -> dict[str, Any]:
    return _run_bench(model_cfg)

@app.function(image=vision_img, gpu=A10G, timeout=BENCH_TIMEOUT, volumes={MODEL_CACHE_PATH: MODEL_CACHE_VOLUME})
def bench_vision(model_cfg: dict) -> dict[str, Any]:
    return _run_bench(model_cfg)

@app.function(image=ocr_img, gpu=A10G, timeout=BENCH_TIMEOUT, volumes={MODEL_CACHE_PATH: MODEL_CACHE_VOLUME})
def bench_ocr(model_cfg: dict) -> dict[str, Any]:
    return _run_bench(model_cfg)

@app.function(image=stt_img, gpu=A10G, timeout=BENCH_TIMEOUT, volumes={MODEL_CACHE_PATH: MODEL_CACHE_VOLUME})
def bench_stt(model_cfg: dict) -> dict[str, Any]:
    return _run_bench(model_cfg)

@app.function(image=tts_img, gpu=A10G, timeout=BENCH_TIMEOUT, volumes={MODEL_CACHE_PATH: MODEL_CACHE_VOLUME})
def bench_tts(model_cfg: dict) -> dict[str, Any]:
    return _run_bench(model_cfg)

@app.function(image=embeddings_img, gpu=A10G, timeout=BENCH_TIMEOUT, volumes={MODEL_CACHE_PATH: MODEL_CACHE_VOLUME})
def bench_embeddings(model_cfg: dict) -> dict[str, Any]:
    return _run_bench(model_cfg)

@app.function(image=segmentation_img, gpu=A10G, timeout=BENCH_TIMEOUT, volumes={MODEL_CACHE_PATH: MODEL_CACHE_VOLUME})
def bench_segmentation(model_cfg: dict) -> dict[str, Any]:
    return _run_bench(model_cfg)

@app.function(gpu=A100_80G, timeout=BENCH_TIMEOUT, volumes={MODEL_CACHE_PATH: MODEL_CACHE_VOLUME})
def bench_planner_large(model_cfg: dict) -> dict[str, Any]:
    return _run_bench(model_cfg)


# ── Orchestrator ──────────────────────────────────────────────────────────────

CATEGORY_FUNCTIONS = {
    "planner": bench_planner,
    "vision": bench_vision,
    "ocr": bench_ocr,
    "stt": bench_stt,
    "tts": bench_tts,
    "embeddings": bench_embeddings,
    "segmentation": bench_segmentation,
}

LARGE_MODELS = {A100_80G, A100_40G}


@app.function(timeout=BENCH_TIMEOUT * 2)
def run_category(category: str) -> list[dict[str, Any]]:
    models = [m for m in ALL_MODELS if m["category"] == category]
    results = []
    fn = CATEGORY_FUNCTIONS[category]
    print(f"\nBenchmarking {category} ({len(models)} models)")
    for mc in models:
        print(f"  {mc['id']} on {mc['gpu']}...")
        try:
            if mc["gpu"] in LARGE_MODELS:
                result = bench_planner_large.remote(mc)
            else:
                result = fn.remote(mc)
            results.append(result)
            br = BenchResult(**result)
            print(f"    {br.summary()}")
        except Exception as e:
            er = BenchResult(model_id=mc["id"], category=category, gpu=mc["gpu"], precision=mc["precision"], errors=[str(e)])
            results.append(er.to_dict())
            print(f"    FAILED: {e}")
    return results


@app.function(timeout=BENCH_TIMEOUT * 3)
def run_all() -> dict[str, list[dict[str, Any]]]:
    cats = list(CATEGORY_FUNCTIONS.keys())
    return {c: run_category.remote(c) for c in cats}


@app.local_entrypoint()
def main():
    import time as tmod
    print("=" * 60)
    print("ShopStack Model Benchmarks v2")
    print(f"Total models: {len(ALL_MODELS)}")
    print("=" * 60)
    start = tmod.time()
    all_results = run_all.remote()
    total = tmod.time() - start
    output = {"benchmark": "comprehensive-v2", "date": tmod.strftime("%Y-%m-%d %H:%M UTC", tmod.gmtime()),
              "total_models": len(ALL_MODELS), "total_time_minutes": round(total / 60, 1), "results": all_results}
    with open("/tmp/shopstack_bench_v2_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nTotal time: {round(total/60, 1)} min")
    for cat, results in all_results.items():
        print(f"\n{'─'*50}\nCategory: {cat}")
        print(f"{'Model':<35} {'Metric':<25} {'Errors':<10}")
        print("-" * 70)
        for r in results:
            m = r.get("metrics", {})
            err = "YES" if r.get("errors") else ""
            if cat == "planner":
                metric = f"{m.get('tool_calling_accuracy_pct', 'N/A')}% acc, {m.get('mean_latency_s', 'N/A')}s"
            elif cat == "embeddings":
                metric = f"{m.get('mean_time_per_text_s', 'N/A')}s/text, sim={m.get('hindi_english_similarity', 'N/A')}"
            else:
                metric = f"{m.get('mean_latency_s', m.get('latency_s', 'N/A'))}s"
            print(f"{r['model_id']:<35} {metric:<25} {err:<10}")
