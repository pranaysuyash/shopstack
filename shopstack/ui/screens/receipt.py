from __future__ import annotations

import logging
from html import escape
from typing import Any


from shopstack.app_context import db, providers
from shopstack.services.receipt import ReceiptResult, confirm_receipt, parse_receipt_text
from shopstack.ui.components.primitives import data_table
from shopstack.ui.screens._utils import safe_render

logger = logging.getLogger(__name__)


def _load_ocr_model() -> str:
    """Pre-load the GLM-OCR model so the first scan doesn't include cold-start latency.

    Returns an HTML status message for display.
    """
    try:
        ocr_provider = providers.get("ocr")
        if ocr_provider is None:
            return "<div style='color:var(--text-dim);font-size:12px;margin-bottom:4px;'>OCR backend not available</div>"
        if not getattr(ocr_provider, "available", False):
            return f"<div style='color:var(--text-dim);font-size:12px;margin-bottom:4px;'>OCR backend {getattr(ocr_provider, 'name', '?')} not available.</div>"

        # Check if model is already loaded
        model = getattr(ocr_provider, "_model", None)
        if model is not None:
            return "<div style='color:var(--green);font-size:12px;margin-bottom:4px;'>OCR model loaded &#10003;</div>"

        # Trigger load
        ocr_provider.load()
        if getattr(ocr_provider, "_model", None) is not None:
            return "<div style='color:var(--green);font-size:12px;margin-bottom:4px;'>OCR model loaded &#10003;</div>"
        return "<div style='color:var(--text-dim);font-size:12px;margin-bottom:4px;'>OCR model not loaded (will load on first scan)</div>"
    except Exception as e:
        logger.warning("OCR model pre-load failed: %s", e)
        return f"<div style='color:var(--text-dim);font-size:12px;margin-bottom:4px;'>OCR model pre-load: {escape(str(e))}</div>"


def _render_receipt_review(result: ReceiptResult | None) -> str:
    if not result or not result.lines:
        return "<div style='color:var(--text-dim);'>No receipt parsed yet.</div>"

    rows = [
        {
            "Item": line.display_name,
            "Qty": str(line.quantity),
            "Unit": line.unit,
            "Price": f"\u20b9{line.price:.2f}",
        }
        for line in result.lines
    ]

    table_html = data_table(
        rows,
        columns=["Item", "Qty", "Unit", "Price"],
        empty_message="No receipt lines parsed.",
    )

    # Replace the outer card wrapper's id so the data_table's inner card
    # is the only card, avoiding nested card borders.
    return (
        f"<div role='region' aria-label='Receipt from {escape(result.merchant)}' style='text-align:left;'>"
        f"<h3 id='receipt-heading'>Receipt from {escape(result.merchant)}</h3>"
        f"<div style='font-size:12px;color:var(--text-dim);' aria-label='Purchase date'>{result.purchase_date}</div>"
        f"<div style='margin-top:8px;' aria-labelledby='receipt-heading'>{table_html}</div>"
        f"<div style='margin-top:8px;padding-top:8px;border-top:2px solid var(--border);font-weight:600;text-align:right;font-size:14px;'>"
        f"Total: \u20b9{result.total:.2f}"
        f"</div>"
        f"</div>"
    )


def _resolve_path(file_input: Any) -> str:
    if file_input is None:
        return ""
    if isinstance(file_input, str):
        return file_input
    if hasattr(file_input, "name"):
        return file_input.name
    return str(file_input)


@safe_render
def receipt_scan_ocr(file_input: Any) -> tuple[str, str]:
    file_path = _resolve_path(file_input)
    if not file_path:
        return "<div style='color:var(--text-dim);'>Upload an image or text file first.</div>", ""

    file_lower = file_path.lower()
    if file_lower.endswith((".txt", ".csv")):
        try:
            with open(file_path, "r") as f:
                raw_text = f.read()
        except Exception as e:
            return f"<div style='color:var(--red);'>Failed to read file: {escape(str(e))}</div>", ""
    elif file_lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        try:
            ocr_provider = providers.get("ocr")
            if not ocr_provider:
                return "<div style='color:var(--red);'>No OCR provider available.</div>", ""
            ocr_result = ocr_provider.extract(file_path)
            raw_text = ocr_result.get("text", ocr_result.get("raw_text", ""))
            if not raw_text:
                raw_text = ocr_result.get("product_name", "") or ""
                brand = ocr_result.get("brand", "")
                if brand:
                    raw_text = f"{brand}\n{raw_text}"
        except Exception as e:
            return f"<div style='color:var(--red);'>OCR failed: {escape(str(e))}</div>", ""
    else:
        return "<div style='color:var(--text-dim);'>Unsupported file type. Use .txt, .png, or .jpg</div>", ""

    if not raw_text.strip():
        return "<div style='color:var(--text-dim);'>No text found in the uploaded file.</div>", ""

    result = parse_receipt_text(raw_text)
    html = _render_receipt_review(result)
    return html, raw_text


@safe_render
def receipt_parse_text(raw_text: str) -> str:
    if not raw_text.strip():
        return "<div style='color:var(--text-dim);'>Enter receipt text to parse.</div>"

    result = parse_receipt_text(raw_text)
    return _render_receipt_review(result)


@safe_render
def receipt_confirm(raw_text: str) -> str:
    if not raw_text.strip():
        return "<div style='color:var(--red);'>No receipt text to confirm. Scan or paste a receipt first.</div>"

    result = parse_receipt_text(raw_text)
    ir = confirm_receipt(db, result)
    return ir.summary_html
