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

OPENAI_RECEIPT_TEXT_EXTRACTION_PROMPT = (
    "Extract all visible text from this receipt image. Return only the transcribed text, "
    "preserving line breaks and the original numbers, dates, prices, and item names. "
    "Do not summarize, infer missing values, or return JSON."
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

RECEIPT_STRUCTURED_NORMALIZATION_PROMPT = (
    "Extract this receipt into STRICT JSON only - no prose, no markdown.\n"
    '{"merchant":"<merchant>","purchase_date":"<YYYY-MM-DD>","total":<number>,'
    '"lines":[{"canonical_name":"<lowercase item>","display_name":"<item>",'
    '"quantity":<number>,"unit":"<kg|g|ml|L|unit|dozen>","price":<number}]}'
)

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
        name="ocr.openai_receipt_text_extraction",
        version="v1",
        date="2026-08-26",
        description="OpenAI vision prompt for raw receipt transcription before deterministic parsing.",
        eval_link=None,
        tags=("ocr", "receipt", "text-extraction", "openai", "vision"),
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

register_prompt(
    PromptMeta(
        name="ocr.receipt_structured_normalization",
        version="v1",
        date="2026-08-26",
        description="Structured receipt normalization prompt used to compare model output with labeled text cases. Not image OCR.",
        eval_link="Docs/evals/openai_receipt_normalization_latest.json",
        tags=("ocr", "receipt", "structured-extraction", "normalization"),
    )
)
