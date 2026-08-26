"""Shared Modal image and utilities for ShopStack model benchmarks.

This module provides:
- A base Modal Image with common dependencies (torch, transformers, etc.)
- Utility functions for benchmark reporting
- Shared constants (GPU types, timeouts, etc.)
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

import modal

# ── GPU Types ────────────────────────────────────────────────────────────────
A10G = "A10G"       # 24GB VRAM — good for most 7-8B models
A100_40G = "A100"   # 40GB VRAM — for larger models
A100_80G = "A100-80GB"  # 80GB VRAM — for 27B+ models
H100 = "H100"       # 80GB VRAM — fastest
T4 = "T4"           # 16GB VRAM — budget option

# ── Timeouts ────────────────────────────────────────────────────────────────
BENCH_TIMEOUT = 1800       # 30 min per benchmark run (includes model download)
MODEL_LOAD_TIMEOUT = 900   # 15 min for model download/load
INFERENCE_TIMEOUT = 120   # 2 min per inference call

# ── Model Cache Volume ─────────────────────────────────────────────────────────
# Persists downloaded model weights across benchmark runs
MODEL_CACHE_VOLUME = modal.Volume.from_name("shopstack-model-cache", create_if_missing=True)
MODEL_CACHE_PATH = "/models"

# ── Base Image ────────────────────────────────────────────────────────────────

def base_image(extra_packages: list[str] | None = None) -> modal.Image:
    """Create a base Modal image with common ML dependencies.

    Args:
        extra_packages: Additional pip packages for specific model categories.

    Returns:
        A Modal Image ready for deployment.
    """
    packages = [
        "torch>=2.5.0",
        "transformers>=4.55.0",
        "accelerate>=1.5.0",
        "sentencepiece>=0.2.0",
        "huggingface-hub>=0.30.0",
        "numpy>=2.0.0",
        "pillow>=11.0.0",
        "requests>=2.32.0",
        "tqdm>=4.67.0",
    ]
    if extra_packages:
        packages.extend(extra_packages)

    return (
        modal.Image.debian_slim(python_version="3.12")
        .pip_install(*packages)
        .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
    )


# ── Benchmark Result ─────────────────────────────────────────────────────────

@dataclass
class BenchResult:
    """Structured result from a single benchmark run."""
    model_id: str
    category: str
    gpu: str
    precision: str
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        parts = [f"[{self.category}] {self.model_id} on {self.gpu} ({self.precision})"]
        for k, v in self.metrics.items():
            parts.append(f"  {k}: {v}")
        if self.errors:
            parts.append(f"  ERRORS: {len(self.errors)}")
            for e in self.errors[:3]:
                parts.append(f"    - {e}")
        return "\n".join(parts)


# ── Benchmark Runner ──────────────────────────────────────────────────────────

class BenchRunner:
    """Base class for model category benchmark runners."""

    def __init__(self, model_id: str, gpu: str = A10G, precision: str = "int4"):
        self.model_id = model_id
        self.gpu = gpu
        self.precision = precision
        self.results: list[BenchResult] = []

    def measure(self, name: str, fn, **kwargs) -> float:
        """Time a function call and return seconds."""
        start = time.perf_counter()
        try:
            fn(**kwargs)
            elapsed = time.perf_counter() - start
            return round(elapsed, 4)
        except Exception as e:
            self.results[-1].errors.append(f"{name}: {e}")
            return -1.0

    def report(self) -> BenchResult:
        """Compile and return the final result."""
        r = self.results[-1]
        r.timestamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
        return r


# ── Prompt Sets ──────────────────────────────────────────────────────────────

PLANNER_PROMPTS = [
    "Add 2 kg of rice to the pantry",
    "What should I cook with tomatoes, onions, and eggs?",
    "Create a shopping list for milk, bread, and eggs",
    "Find items that are about to expire",
    "Compare prices for basmati rice across stores",
    "How much milk have I bought this month?",
    "What's the best price for tomatoes right now?",
    "Mark 1 kg of onions as consumed",
    "Show me items I need to buy this week",
    "What did I pay for rice last time?",
    "Move the milk from fridge to pantry",
    "How many eggs do I have left?",
    "What's running low in my pantry?",
    "Find recipes that use chicken and rice",
    "Add 500g of paneer to my shopping list",
    "What's the price trend for potatoes?",
    "Show me items I bought last week",
    "Which store has the cheapest dal?",
    "How much did I spend on groceries this month?",
    "Remind me to buy spices next week",
]

VISION_PROMPTS = [
    "What products are visible in this image?",
    "Identify all food items and their brands",
    "Read the expiration date on this package",
    "Count how many items are in this shelf photo",
    "What's the price on this label?",
    "Describe the contents of this refrigerator",
    "Is this product organic?",
    "What's the weight/quantity on this package?",
    "Identify the store name on this receipt",
    "Are there any damaged items in this image?",
]

OCR_PROMPTS = [
    "Extract all text from this receipt image",
    "Read the product name and price from this label",
    "Extract the MRP, expiry date, and batch number",
    "Read the Hindi text on this package",
    "Extract itemized list from this grocery bill",
]

STT_AUDIOS = [
    "Add two kilograms of rice to the pantry",
    "What should I cook for dinner tonight?",
    "Create a shopping list for milk and eggs",
    "How many tomatoes do I have?",
    "Mark the onions as used",
]

TTS_PROMPTS = [
    "You have 3 items running low in your pantry: milk, eggs, and bread.",
    "I found basmati rice at ₹45 per kg at Swiggy, which is 20% below your average price.",
    "Your shopping list has 5 items. The estimated total is ₹350.",
    "Don't forget to use the tomatoes before they expire in 2 days.",
    "I've added 2 kg of rice to your pantry. Would you like to set a refill reminder?",
]

EMBEDDINGS_TEXTS = [
    "milk", "doodh", "dudh", "whole milk", "toned milk",
    "rice", "chawal", "basmati rice", "sona masoori",
    "tomato", "tamatar", "vine ripe tomato", "cherry tomato",
    "onion", "pyaaz", "red onion", "spring onion",
    "potato", "aloo", "sweet potato", "mashed potato",
    "eggs", "ande", "brown eggs", "egg whites",
    "bread", "double roti", "whole wheat bread", "sandwich bread",
    "butter", "makkhan", "salted butter", "unsalted butter",
    "cheese", "paneer", "mozzarella", "cheddar",
    "yogurt", "dahi", "greek yogurt", "curd",
]

SEGMENTATION_PROMPTS = [
    "segment the product in this image",
    "remove the background from this item",
    "extract the food item from the shelf",
]
