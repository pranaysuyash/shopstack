"""Versioned vision prompts for ShopStack.

These prompts are the contract between the VLM and the Market Lens pipeline.
If you change them, re-run the Modal bench to confirm accuracy holds.

motto_v3 §0.9: all prompts versioned, evaluated, documented.
"""

from __future__ import annotations

from shopstack.prompts import PromptMeta, register_prompt

# ── Vision prompts ──────────────────────────────────────────────────────────

UNDERSTAND_PRODUCT_SHELF_PROMPT = (
    "You are looking at a household product photo (shelf, packet, jar, or receipt).\n"
    "Identify the visible product(s) and return STRICT JSON only — no prose, no markdown:\n"
    '{\n'
    '  "products": [\n'
    '    {"name": "<product canonical name>", "brand": "<brand>", "quantity": <number>, "unit": "<kg|g|ml|packets|pieces|liters>", "price_rupees": <number|null>, "expiry_date": "<YYYY-MM-DD|null>"}\n'
    "  ]\n"
    "}\n"
    "If the image is unreadable, return {\"products\": []}. One product per visible item. No duplicates."
)

GENERAL_UNDERSTAND_PROMPT = (
    "Describe what you see in this image. List any food items, products, or text visible."
)

MINICPM_DETECT_PROMPT = (
    "List every food item, product, or object you can see in this image. "
    "Format: one item per line with confidence."
)

OPENAI_DESCRIBE_PROMPT = (
    "Describe what you see in this image in detail. "
    "List any food items, products, or text you can identify."
)

# ── Registration ────────────────────────────────────────────────────────────

register_prompt(
    PromptMeta(
        name="vision.understand_product_shelf",
        version="v2",
        date="2026-06-13",
        description="Canonical product-shelf VLM prompt. Emits strict JSON with product name, brand, quantity, unit, price, expiry.",
        eval_link="benchmarks/modal/results/vision_synthetic_20260613.jsonl",
        tags=("vision", "product-detection", "json-output"),
        _content_hash="",  # computed at import time
    )
)

register_prompt(
    PromptMeta(
        name="vision.general_understand",
        version="v1",
        date="2026-06-13",
        description="General VQA prompt for describing image contents.",
        eval_link=None,
        tags=("vision", "general"),
    )
)

register_prompt(
    PromptMeta(
        name="vision.mincpm_detect",
        version="v1",
        date="2026-06-13",
        description="MiniCPM object detection prompt. Lists items with confidence.",
        eval_link=None,
        tags=("vision", "detection", "minicpm"),
    )
)

register_prompt(
    PromptMeta(
        name="vision.openai_describe",
        version="v1",
        date="2026-06-13",
        description="OpenAI vision describe prompt. Used with GPT-4o/GPT-4.1 for image understanding.",
        eval_link=None,
        tags=("vision", "openai", "describe"),
    )
)
