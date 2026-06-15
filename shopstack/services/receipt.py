from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from shopstack.portability import ImportResult
from shopstack.domain import canonicalize_name, normalize_item_name
from shopstack.schemas.models import (
    InventoryLot,
    PriceObservation,
    PurchaseEvent,
    ReconciliationEvent,
)
from shopstack.tools.registry import DEFAULT_STORAGE_LOCATION

logger = logging.getLogger(__name__)

__all__ = [
    "ReceiptLine",
    "ReceiptResult",
    "canonicalize_receipt_name",
    "parse_receipt_text",
    "confirm_receipt",
]

UNIT_ALIASES: dict[str, str] = {
    "kg": "kg", "kgs": "kg", "kilo": "kg", "kilogram": "kg",
    "g": "g", "gm": "g", "gram": "g", "grams": "g",
    "l": "L", "lt": "L", "liter": "L", "litre": "L", "liters": "L", "litres": "L",
    "ml": "ml", "milliliter": "ml", "millilitre": "ml",
    "pcs": "unit", "pc": "unit", "piece": "unit", "pieces": "unit",
    "no": "unit", "nos": "unit", "pack": "unit", "box": "unit",
    "dozen": "dozen",
}


@dataclass
class ReceiptLine:
    canonical_name: str
    display_name: str
    quantity: float
    unit: str
    price: float
    category: str = ""


@dataclass
class ReceiptResult:
    merchant: str
    purchase_date: date
    lines: list[ReceiptLine]
    total: float
    raw_text: str


def canonicalize_receipt_name(raw_name: str) -> str:
    raw = str(raw_name or "").strip()
    if not raw:
        return ""
    canonical = canonicalize_name(raw)[0]
    if not canonical:
        canonical = normalize_item_name(raw)
    if not canonical:
        # Prevent data loss: fallback to a cleaned, lowercased version of raw name
        cleaned = re.sub(r"[^\w\s]", " ", raw.lower()).strip()
        canonical = re.sub(r"\s+", "_", cleaned)
    return canonical


def _normalise_unit(raw: str) -> str:
    raw = raw.strip().lower()
    return UNIT_ALIASES.get(raw, raw)


def _parse_quantity_unit(raw: str) -> tuple[float, str]:
    raw = raw.strip().lower()
    m = re.match(r"^([\d.]+)\s*(kg|kgs|kilo|kilogram|g|gm|gram|grams|l|lt|liter|litre|litres|ml|milliliter|millilitre|pcs|pc|piece|pieces|no|nos|pack|box|dozen)$", raw)
    if m:
        qty = float(m.group(1))
        unit = _normalise_unit(m.group(2))
        if unit == "g" and qty >= 100:
            return qty / 1000, "kg"
        return qty, unit
    m2 = re.match(r"^([\d.]+)\s*$", raw)
    if m2:
        return float(m2.group(1)), "unit"
    return 1.0, "unit"


def _find_merchant(text: str) -> str:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return "Unknown Store"
    first = lines[0]
    skip_words = {"date", "bill", "invoice", "receipt", "gst", "store", "shop", ":"}
    if any(first.lower().startswith(w) for w in skip_words) and len(lines) > 1:
        return lines[1]
    return first


def _find_purchase_date(text: str) -> date:
    patterns = [
        r"(\d{2})[-/](\d{2})[-/](\d{4})",
        r"(\d{4})[-/](\d{2})[-/](\d{2})",
        r"(\d{2})[-/](\d{2})[-/](\d{2})\b",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            groups = m.groups()
            if len(groups[0]) == 4:
                try:
                    return date(int(groups[0]), int(groups[1]), int(groups[2]))
                except ValueError:
                    continue
            year = int(groups[2])
            if year < 100:
                year += 2000
            try:
                return date(year, int(groups[1]), int(groups[0]))
            except ValueError:
                try:
                    return date(year, int(groups[0]), int(groups[1]))
                except ValueError:
                    continue
    return date.today()


def _find_total(text: str) -> float:
    patterns = [
        r"(?:total|grand total|net|amount|pay)\s*:?\s*(?:rs\.?|inr|&#8377;|\u20b9)?\s*([\d,]+\.?\d*)",
        r"(?:rs\.?|inr|&#8377;|\u20b9)\s*([\d,]+\.?\d*)\s*(?:total|only)",
        r"(?:^|\n)\s*(?:rs\.?|inr|&#8377;|\u20b9)\s*([\d,]+\.?\d*)\s*$",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.MULTILINE)
        if m:
            return float(m.group(1).replace(",", ""))
    fallback = re.findall(r"([\d,]+\.\d{2})", text)
    if fallback:
        return max(float(v.replace(",", "")) for v in fallback)
    return 0.0


# Pattern: "ONION 1 KG 40.00" — name, qty, unit, price
_LINE_WITH_UNIT = re.compile(
    r"^(.+?)\s+"
    r"([\d.]+)\s*(kg|kgs|kilo|kilogram|g|gm|gram|grams|"
    r"l|lt|liter|litre|litres|ml|milliliter|millilitre|"
    r"pcs|pc|piece|pieces|no|nos|pack|box|dozen)\s+"
    r"(?:(?:@|x)\s*[\d.]+\s*[/x]\s*)?"
    r"(?:[\u20b9rs.\s]*)?([\d,]+\.?\d*)\s*$",
    re.IGNORECASE,
)

# Pattern: "Milk 2 120" — name, qty (numeric), price
_LINE_QTY_PRICE = re.compile(
    r"^(.+?)\s+"
    r"([\d.]+)\s+(?:x\s+)?"
    r"(?:[\u20b9rs.\s]*)?([\d,]+\.?\d*)\s*$",
    re.IGNORECASE,
)

# Pattern: "Bread 35" — name, price only
_LINE_PRICE_ONLY = re.compile(
    r"^(.+?)\s+"
    r"(?:[\u20b9rs.\s]*)?([\d,]+\.?\d*)\s*$",
    re.IGNORECASE,
)


def _parse_line(line_text: str) -> ReceiptLine | None:
    stripped = line_text.strip()
    if not stripped:
        return None

    m = _LINE_WITH_UNIT.match(stripped)
    if m:
        raw_name = m.group(1).strip()
        qty, unit = _parse_quantity_unit(f"{m.group(2)} {m.group(3)}")
        price = float(m.group(4).replace(",", ""))
        canonical_name = canonicalize_receipt_name(raw_name)
        if not canonical_name:
            return None
        return ReceiptLine(
            canonical_name=canonical_name,
            display_name=raw_name,
            quantity=qty,
            unit=unit,
            price=price,
        )

    m = _LINE_QTY_PRICE.match(stripped)
    if m:
        raw_name = m.group(1).strip()
        qty = float(m.group(2))
        price = float(m.group(3).replace(",", ""))
        canonical_name = canonicalize_receipt_name(raw_name)
        if not canonical_name:
            return None
        return ReceiptLine(
            canonical_name=canonical_name,
            display_name=raw_name,
            quantity=qty,
            unit="unit",
            price=price,
        )

    m = _LINE_PRICE_ONLY.match(stripped)
    if m:
        raw_name = m.group(1).strip()
        price = float(m.group(2).replace(",", ""))
        canonical_name = canonicalize_receipt_name(raw_name)
        if not canonical_name:
            return None
        return ReceiptLine(
            canonical_name=canonical_name,
            display_name=raw_name,
            quantity=1.0,
            unit="unit",
            price=price,
        )

    return None


def _extract_reconciliation_details(
    db: Any,
    canonical_name: str,
    user_id: str = "",
) -> tuple[str, float | None, str]:
    """Return planned action, planned price, and notes from active shopping list.

    If the item is not on the active list, planned_action is "unknown".
    """
    active_list = db.get_active_shopping_list(user_id=user_id) if db is not None else None
    if not active_list or not getattr(active_list, "items", None):
        return "unknown", None, ""

    target = canonical_name.strip().lower()
    for item in active_list.items:
        candidate = canonicalize_receipt_name(item.canonical_name)
        if candidate == target:
            planned_price = None
            reason = (item.reason or "").strip()
            if reason:
                match = re.search(r"(?:rs\.?|inr|₹)\s*(\d+(?:\.\d+)?)", reason, flags=re.IGNORECASE)
                if match:
                    try:
                        planned_price = float(match.group(1))
                    except ValueError:
                        planned_price = None
            notes = f"Matched active shopping list item: {item.canonical_name}"
            try:
                db.update_list_item(item.list_item_id, {"status": "bought"})
            except Exception:
                notes += " (status update deferred)"
            return "buy", planned_price, notes

    return "unknown", None, ""


_SKIP_KEYWORDS = {"total", "gst", "tax", "cgst", "sgst", "change", "cash", "card", "sub total", "subtotal", "round", ":"}


def parse_receipt_text(raw_text: str) -> ReceiptResult:
    text = raw_text.strip()
    merchant = _find_merchant(text)
    purchase_date = _find_purchase_date(text)
    total = _find_total(text)

    lines: list[ReceiptLine] = []
    seen_names: set[str] = set()

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        if any(kw in lower for kw in _SKIP_KEYWORDS):
            continue
        if re.search(r"^\d{2}[-/]\d{2}[-/]\d{2,4}", line):
            continue
        if re.match(r"^[\s\d\-/.|:]*$", line):
            continue

        parsed = _parse_line(line)
        if parsed:
            normalised = parsed.canonical_name
            if normalised not in seen_names:
                seen_names.add(normalised)
                lines.append(parsed)

    return ReceiptResult(
        merchant=merchant,
        purchase_date=purchase_date,
        lines=lines,
        total=total,
        raw_text=raw_text,
    )


def confirm_receipt(database: Any, result: ReceiptResult, user_id: str = "") -> ImportResult:
    ir = ImportResult()

    if not result.lines:
        ir.errors.append("No receipt lines to confirm.")
        return ir

    for line in result.lines:
        try:
            lot = InventoryLot(
                canonical_name=line.canonical_name,
                display_name=line.display_name,
                quantity=line.quantity,
                unit=line.unit,
                storage_location_id=DEFAULT_STORAGE_LOCATION,
                purchase_date=result.purchase_date,
                price_paid=line.price,
                currency="INR",
                category=line.category,
                source_event_id="receipt",
            )
            database.add_inventory_lot(lot, user_id=user_id)
            ir.items_added += 1

            pe = PurchaseEvent(
                canonical_name=line.canonical_name,
                quantity=line.quantity,
                unit=line.unit,
                total_price=line.price,
                currency="INR",
                source_type="receipt",
                store_name=result.merchant,
                raw_text=result.raw_text,
                confirmed=True,
            )
            database.add_purchase_event(pe, user_id=user_id)

            planned_action, planned_price, plan_notes = _extract_reconciliation_details(
                database,
                line.canonical_name,
                user_id=user_id,
            )

            reconcile_event = ReconciliationEvent(
                canonical_name=line.canonical_name,
                planned_action=planned_action,
                actual_action="bought",
                quantity=line.quantity,
                unit=line.unit,
                price_paid=line.price,
                planned_price=planned_price,
                source="receipt",
                notes="; ".join(p for p in [f"Receipt scan from {result.merchant}", plan_notes] if p),
            )
            database.add_reconciliation_event(reconcile_event, user_id=user_id)
        except Exception as e:
            ir.errors.append(f"Failed for '{line.display_name}': {e}")

        try:
            po = PriceObservation(
                canonical_name=line.canonical_name,
                quantity=line.quantity,
                unit=line.unit,
                price=line.price,
                currency="INR",
                store_name=result.merchant,
                observation_date=result.purchase_date,
                source_event_id="receipt",
                notes=f"Receipt scan from {result.merchant}",
            )
            database.record_price(po, user_id=user_id)
            ir.price_observations_added += 1
        except Exception as e:
            ir.errors.append(f"Failed to record price for '{line.display_name}': {e}")

    ir.messages.append(
        f"Receipt from {result.merchant} ({result.purchase_date}): {len(result.lines)} items, total {result.total:.2f}"
    )

    # Audit trail: save the parsed receipt as a structured JSON file
    # so the raw OCR text + parse result can be reviewed later.
    # Per Docs/NOT_STARTED_FEATURES.md §4.1 acceptance criteria.
    try:
        receipt_path = export_receipt_json(result, user_id=user_id)
        ir.messages.append(f"Saved receipt audit trail: {receipt_path}")
        logger.info("receipt audit trail saved: %s", receipt_path)
    except OSError as exc:
        # Disk full, permission denied, or other I/O error. Don't fail
        # the whole confirm; just surface the issue via messages.
        ir.errors.append(f"Failed to save receipt audit trail: {exc}")
        logger.warning("receipt audit trail save failed: %s", exc)

    return ir


def export_receipt_json(
    result: "ReceiptResult",
    user_id: str = "",
    data_dir: Path | None = None,
) -> Path:
    """Save a parsed receipt as a structured JSON file for audit.

    Per Docs/NOT_STARTED_FEATURES.md §4.1, the receipt service
    saves the parsed result to ``data/receipts/<timestamp>_<merchant>.json``
    so the raw OCR text + parse result can be reviewed later. This
    is the audit trail: even if the parsed lines are wrong, the
    raw text is preserved.

    The JSON includes:
        * raw_text: the original OCR text (input to parse_receipt_text)
        * parsed: the structured ReceiptResult (merchant, date, total, lines)
        * user_id: who confirmed the receipt (for multi-user audit)
        * confirmed_at: ISO timestamp

    Args:
        result: The parsed receipt (must have raw_text attribute).
        user_id: The user who confirmed the receipt (for audit trail).
        data_dir: Optional override for the data directory. Defaults
            to ``data/receipts/`` relative to the working directory.

    Returns:
        The path of the written JSON file.

    Raises:
        OSError: If the directory cannot be created or the file written.
    """
    base_dir = data_dir if data_dir is not None else Path("data") / "receipts"
    base_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize merchant for filename: keep only alphanumeric + spaces + hyphens
    safe_merchant = re.sub(r"[^A-Za-z0-9 _-]", "", result.merchant or "unknown").strip()[:50]
    safe_merchant = safe_merchant.replace(" ", "_") or "unknown"
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    filename = f"{timestamp}_{safe_merchant}.json"
    path = base_dir / filename

    payload = {
        "raw_text": getattr(result, "raw_text", ""),
        "parsed": {
            "merchant": result.merchant,
            "purchase_date": result.purchase_date.isoformat()
            if hasattr(result.purchase_date, "isoformat")
            else str(result.purchase_date),
            "total": result.total,
            "lines": [
                {
                    "canonical_name": line.canonical_name,
                    "display_name": line.display_name,
                    "quantity": line.quantity,
                    "unit": line.unit,
                    "price": line.price,
                }
                for line in result.lines
            ],
        },
        "user_id": user_id,
        "confirmed_at": datetime.now().isoformat(),
    }

    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    return path
