from __future__ import annotations

import logging
from html import escape
from typing import Any

import pandas as pd


from shopstack.app_context import db, providers, current_user_id
from shopstack.services.dashboard import clear_dashboard_cache
from shopstack.services.ocr_pipeline import run_ocr_pipeline
from shopstack.services.receipt import (
    ReceiptResult,
    canonicalize_receipt_name,
    confirm_receipt,
    parse_receipt_text,
)
from shopstack.ui.components.primitives import data_table, home_card

logger = logging.getLogger(__name__)


def _load_ocr_model() -> str:
    """Pre-load the GLM-OCR model so the first scan doesn't include cold-start latency.

    Returns an HTML status message for display.
    """
    try:
        ocr_provider = providers.get("ocr")
        if ocr_provider is None:
            return "<div style='color:var(--text-dim);font-size: 0.75rem;margin-bottom:4px;'>OCR backend not available</div>"
        if not getattr(ocr_provider, "available", False):
            return f"<div style='color:var(--text-dim);font-size: 0.75rem;margin-bottom:4px;'>OCR backend {getattr(ocr_provider, 'name', '?')} not available.</div>"

        # Check if model is already loaded
        model = getattr(ocr_provider, "_model", None)
        if model is not None:
            return "<div style='color:var(--green);font-size: 0.75rem;margin-bottom:4px;'>OCR model loaded &#10003;</div>"

        # Trigger load
        ocr_provider.load()
        if getattr(ocr_provider, "_model", None) is not None:
            return "<div style='color:var(--green);font-size: 0.75rem;margin-bottom:4px;'>OCR model loaded &#10003;</div>"
        return "<div style='color:var(--text-dim);font-size: 0.75rem;margin-bottom:4px;'>OCR model not loaded (will load on first scan)</div>"
    except Exception as e:
        logger.warning("OCR model pre-load failed: %s", e)
        return f"<div style='color:var(--text-dim);font-size: 0.75rem;margin-bottom:4px;'>OCR model pre-load: {escape(str(e))}</div>"


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
        f"<div role='region' aria-label='Receipt from {escape(result.merchant)}' style='text-align:left;'><h3 id='receipt-heading'>Receipt from {escape(result.merchant)}</h3>"
        f"<div style='font-size: 0.75rem;color:var(--text-dim);' aria-label='Purchase date'>{result.purchase_date}</div><div style='margin-top:8px;' aria-labelledby='receipt-heading'>{table_html}</div>"
        f"<div style='margin-top:8px;padding-top:8px;border-top:2px solid var(--border);font-weight:600;text-align:right;font-size: 0.875rem;'>Total: \u20b9{result.total:.2f}"
        f"</div></div>"
    )


RECEIPT_COLUMNS = ["Item", "Quantity", "Unit", "Price"]


def _build_receipt_rows(lines: list) -> pd.DataFrame:
    rows = [[
        line.display_name,
        line.quantity,
        line.unit,
        line.price,
    ] for line in lines]
    return pd.DataFrame(rows, columns=RECEIPT_COLUMNS)


def _resolve_path(file_input: Any) -> str:
    if file_input is None:
        return ""
    if isinstance(file_input, str):
        return file_input
    if hasattr(file_input, "name"):
        return file_input.name
    return str(file_input)


def receipt_scan_ocr(file_input: Any) -> tuple[list[list[Any]], str, str, str, str]:
    from shopstack.ui.errors import safe_render_html
    fi = file_input
    try:
        return _receipt_scan_ocr_inner(fi)
    except Exception as exc:
        logger.warning("receipt_scan_ocr failed: %s", exc)
        err = safe_render_html(lambda: "", user_message="Receipt scan failed", help_tab="inventory", icon="🧾")
        return [], "", "", "", err


def _receipt_scan_ocr_inner(file_input: Any) -> tuple[list[list[Any]], str, str, str, str]:
    # Returns [dataframe_data, merchant, date, raw_text, status_html]
    file_path = _resolve_path(file_input)
    if not file_path:
        return [], "", "", "", "<div style='color:var(--text-dim);'>Upload an image or text file first.</div>"

    file_lower = file_path.lower()
    if file_lower.endswith((".txt", ".csv")):
        try:
            with open(file_path, "r") as f:
                raw_text = f.read()
        except Exception as e:
            return [], "", "", "", f"<div style='color:var(--red);'>Failed to read file: {escape(str(e))}</div>"
    elif file_lower.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        try:
            ocr_result = run_ocr_pipeline(file_path, providers, enable_preprocessing=True)
            if "error" in ocr_result:
                return [], "", "", "", f"<div style='color:var(--red);'>{escape(ocr_result['error'])}</div>"
            raw_text = ocr_result.get("text", ocr_result.get("raw_text", ""))
            if not raw_text:
                raw_text = ocr_result.get("product_name", "") or ""
                brand = ocr_result.get("brand", "")
                if brand:
                    raw_text = f"{brand}\n{raw_text}"
        except Exception as e:
            return [], "", "", "", f"<div style='color:var(--red);'>OCR failed: {escape(str(e))}</div>"
    else:
        return [], "", "", "", "<div style='color:var(--text-dim);'>Unsupported file type. Use .txt, .png, or .jpg</div>"

    if not raw_text.strip():
        return [], "", "", raw_text, "<div style='color:var(--text-dim);'>No text found in the uploaded file.</div>"

    result = parse_receipt_text(raw_text)
    rows = _build_receipt_rows(result.lines)
    return rows, result.merchant, result.purchase_date.isoformat(), raw_text, ""



def receipt_parse_text(raw_text: str) -> tuple[list[list[Any]], str, str]:
    from shopstack.ui.errors import safe_render_html
    txt = raw_text
    try:
        return _receipt_parse_text_inner(txt)
    except Exception as exc:
        logger.warning("receipt_parse_text failed: %s", exc)
        err = safe_render_html(lambda: "", user_message="Could not parse receipt text", help_tab="inventory", icon="🧾")
        return [], "", ""


def _receipt_parse_text_inner(raw_text: str) -> tuple[list[list[Any]], str, str]:
    if not raw_text.strip():
        return [], "", ""

    result = parse_receipt_text(raw_text)
    rows = _build_receipt_rows(result.lines)
    return rows, result.merchant, result.purchase_date.isoformat()



def receipt_confirm(df_data: Any, merchant: str, date_str: str, raw_text: str) -> str:
    from shopstack.ui.errors import safe_render_html
    dd, m, ds, rt = df_data, merchant, date_str, raw_text
    return safe_render_html(
        lambda: _receipt_confirm_inner(dd, m, ds, rt),
        user_message="Could not confirm receipt",
        help_tab="inventory",
        icon="🧾",
    )


def _receipt_confirm_inner(df_data: Any, merchant: str, date_str: str, raw_text: str) -> str:
    # df_data is a pandas DataFrame or list of lists
    if df_data is None:
        return (
            "<div style='color:var(--red);'>Receipt draft not ready yet. "
            "Wait for Scan &amp; Parse to finish, then click Confirm again.</div>"
        )
    if hasattr(df_data, "values"):
        # pandas DataFrame
        df_list = df_data.values.tolist()
    else:
        df_list = df_data

    if not df_list:
        return "<div style='color:var(--red);'>No receipt lines to confirm. Scan or paste a receipt first.</div>"
    
    try:
        from datetime import date
        purchase_date = date.fromisoformat(date_str)
    except Exception:
        purchase_date = date.today()

    from shopstack.services.receipt import ReceiptResult, ReceiptLine
    lines = []
    for row in df_list:
        try:
            if len(row) < 4:
                continue
            name = str(row[0]).strip()
            if not name:
                continue
            canonical_name = canonicalize_receipt_name(name)
            if not canonical_name:
                continue
            qty_str = row[1]
            unit = row[2]
            price_str = row[3]

            qty = float(qty_str) if qty_str else 1.0
            price = float(price_str) if price_str else 0.0
            lines.append(ReceiptLine(
                canonical_name=canonical_name,
                display_name=name,
                quantity=qty,
                unit=str(unit),
                price=price,
            ))
        except Exception:
            continue

    result = ReceiptResult(
        merchant=merchant,
        purchase_date=purchase_date,
        lines=lines,
        total=sum(l.price for l in lines),
        raw_text=raw_text,
    )
    
    uid = current_user_id()
    ir = confirm_receipt(db, result, user_id=uid)
    clear_dashboard_cache(uid)
    # Item 12: Post-receipt-confirm guidance — append "What's next?" card
    # after the receipt summary so the user knows what to do after scanning.
    summary = ir.summary_html or ""
    items_added = ir.items_added or len(lines)
    body = (
        f"<div class='muted' style='margin-bottom:8px;'>{items_added} item{'s' if items_added != 1 else ''} added to your pantry.</div>"
        f"<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:8px;margin-top:8px;'><div style='padding:10px;border:1px solid var(--border);border-radius:8px;text-align:center;cursor:pointer;'>"
        f"<div style='font-size:1.25rem;margin-bottom:4px;'>🏠</div><div style='font-weight:600;font-size:0.8125rem;'>Put groceries away</div>"
        f"<div style='font-size:0.75rem;color:var(--text-dim);'>Move items to the right shelf</div></div>"
        f"<div style='padding:10px;border:1px solid var(--border);border-radius:8px;text-align:center;cursor:pointer;'><div style='font-size:1.25rem;margin-bottom:4px;'>📋</div>"
        f"<div style='font-weight:600;font-size:0.8125rem;'>Check your list</div><div style='font-size:0.75rem;color:var(--text-dim);'>Mark off what you bought</div>"
        f"</div><div style='padding:10px;border:1px solid var(--border);border-radius:8px;text-align:center;cursor:pointer;'>"
        f"<div style='font-size:1.25rem;margin-bottom:4px;'>🍳</div><div style='font-weight:600;font-size:0.8125rem;'>See what to cook</div>"
        f"<div style='font-size:0.75rem;color:var(--text-dim);'>Recipes from what you just bought</div></div>"
        f"</div>"
    )
    guidance = home_card(
        title="What's next?",
        body=body,
        style="margin-top:12px;text-align:left;border:2px solid var(--green, #176B49);",
    )
    return summary + guidance


def receipt_export_txt(merchant: str, date_str: str, raw_text: str) -> str:
    """Render the most-recently-confirmed receipt as plain text.

    Public Gradio adapter (added 2026-06-13). The user can click
    a "Save as .txt" button in the receipt sub-tab to download
    a human-readable text version of the receipt. The plain text
    is easier to forward via messaging apps (WhatsApp, email)
    than the JSON audit file.

    Args:
        merchant: From the receipt form (used for header).
        date_str: ISO date string (used for header).
        raw_text: The original OCR text (used for the body).

    Returns:
        A plain-text string with merchant, date, total, line
        items, and the raw OCR text. Empty string on any error
        (no crash).

    Note: this is a *re-render* of the last-confirmed receipt,
    not a re-export. The actual file is written on confirm
    via :func:`export_receipt_txt` in the service layer; this
    function returns the same body for in-app display / clipboard
    use.
    """
    from shopstack.ui.errors import safe_render_html
    return safe_render_html(
        lambda: _receipt_export_txt_inner(merchant, date_str, raw_text),
        user_message="Could not generate receipt text export",
        help_tab="inventory",
        icon="🧾",
    )


def _receipt_export_txt_inner(merchant: str, date_str: str, raw_text: str) -> str:
    from datetime import date as _date
    try:
        purchase_date = _date.fromisoformat(date_str) if date_str else _date.today()
    except Exception:
        purchase_date = _date.today()
    from shopstack.services.receipt import (
        ReceiptResult,
        _receipt_txt_body,
    )
    result = ReceiptResult(
        merchant=merchant or "(unknown)",
        purchase_date=purchase_date,
        lines=[],
        total=0.0,
        raw_text=raw_text or "",
    )
    return _receipt_txt_body(result)
