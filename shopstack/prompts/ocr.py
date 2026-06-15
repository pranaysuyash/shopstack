"""Versioned OCR prompts for ShopStack.

OCR providers extract text from product images and receipts.
GLM-OCR uses a vision model prompt; Tesseract/EasyOCR use engine defaults.

motto_v3 §0.9: all prompts versioned, evaluated, documented.
"""

from __future__ import annotations

from shopstack.prompts import PromptMeta, register_prompt

# ── OCR prompts ─────────────────────────────────────────────────────────────

GLM_OCR_EXTRACTION_PROMPT = (
    "Extract all text from this image. Return the text exactly as it appears, "
    "preserving line breaks and spacing. Focus on product names, prices, dates, "
    "and any other text visible on the packaging or receipt."
)

GLM_OCR_TEXT_EXTRACTION_PROMPT = (
    "Extract all text from this receipt or document image. Return exactly what is written, "
    "preserving the original formatting."
)

GLM_OCR_STRUCTURED_EXTRACTION_PROMPT = """{
    "brand": "",
    "product_name": "",
    "weight": "",
    "mrp": "",
    "price_paid": "",
    "expiry_date": "",
    "manufacturing_date": "",
    "batch_number": ""
}"""

# ── Registration ────────────────────────────────────────────────────────────

register_prompt(
    PromptMeta(
        name="ocr.glm_extraction",
        version="v1",
        date="2026-06-13",
        description="GLM-OCR text extraction prompt. Used with GLM-4.6V for receipt/label OCR.",
        eval_link="benchmarks/modal/results/ocr_20260613.jsonl",
        tags=("ocr", "text-extraction", "vision-model"),
    )
)

register_prompt(
    PromptMeta(
        name="ocr.glm_text_extraction",
        version="v1",
        date="2026-06-13",
        description="GLM-OCR raw text extraction prompt. Preserves original formatting.",
        eval_link=None,
        tags=("ocr", "text-extraction", "raw-text"),
    )
)

register_prompt(
    PromptMeta(
        name="ocr.glm_structured_extraction",
        version="v1",
        date="2026-06-13",
        description="GLM-OCR structured field extraction template. JSON template for product metadata.",
        eval_link=None,
        tags=("ocr", "structured-extraction", "json-template"),
    )
)
