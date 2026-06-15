"""Versioned vision prompts for ShopStack.

These prompts are the contract between the VLM and the Market Lens pipeline.
If you change them, re-run the Modal bench to confirm accuracy holds.

motto_v3 §0.9: all prompts versioned, evaluated, documented.
"""

from __future__ import annotations

from shopstack.prompts import PromptMeta, register_prompt

# ── Vision prompts ──────────────────────────────────────────────────────────

UNDERSTAND_PRODUCT_SHELF_PROMPT_V2 = (
    "You are looking at a household product photo (shelf, packet, jar, or receipt).\n"
    "Identify the visible product(s) and return STRICT JSON only — no prose, no markdown:\n"
    '{\n'
    '  "products": [\n'
    '    {"name": "<product canonical name>", "brand": "<brand>", "quantity": <number>, "unit": "<kg|g|ml|packets|pieces|liters>", "price_rupees": <number|null>, "expiry_date": "<YYYY-MM-DD|null>"}\n'
    "  ]\n"
    "}\n"
    "If the image is unreadable, return {\"products\": []}. One product per visible item. No duplicates."
)

UNDERSTAND_PRODUCT_SHELF_PROMPT = (
    "You are looking at a household product photo. Your task is to identify EVERY "
    "visible product — do not cherry-pick only the most prominent one.\n\n"
    "SCANNING RULES:\n"
    "1. Scan the entire image systematically (left to right, top to bottom).\n"
    "2. Include products that are partially visible, behind other items, or at the edges.\n"
    "3. Include products in the background, on shelves behind the main subject.\n"
    "4. Include small items, packets, bottles, jars — even if only the label is visible.\n"
    "5. Common household products to watch for: Atta/flour, Rice, Oil, Salt, Sugar, "
    "Maggi/noodles, Detergent/soap, Milk, Bread, Eggs, Tea, Coffee, Biscuits, "
    "Shampoo, Toothpaste, Handwash, Spices.\n\n"
    "OUTPUT: Return STRICT JSON only — no prose, no markdown:\n"
    '{\n'
    '  "products": [\n'
    '    {"name": "<product canonical name>", "brand": "<brand or empty>", "quantity": <number>, "unit": "<kg|g|ml|packets|pieces|liters>", "price_rupees": <number|null>, "expiry_date": "<YYYY-MM-DD|null>"}\n'
    "  ]\n"
    "}\n"
    "If the image is unreadable, return {\"products\": []}. "
    "Include EVERY visible product, even if you are uncertain about the exact name. "
    "Use generic names (e.g., \"Atta\") if brand is unclear. "
    "One entry per distinct product. No duplicates."
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
        version="v3",
        date="2026-06-15",
        description="Canonical product-shelf VLM prompt. v3 adds systematic scanning rules, enumeration of ALL visible products, common product watchlist, and generic name fallback. Improved recall from 64% (v2) to ≥80% target.",
        eval_link="benchmarks/modal/results/vision_real_reeval_20260614.json",
        tags=("vision", "product-detection", "json-output", "recall-optimized"),
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
