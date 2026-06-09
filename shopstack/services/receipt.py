from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from shopstack.portability import ImportResult
from shopstack.schemas.models import InventoryLot, PriceObservation, PurchaseEvent
from shopstack.tools.registry import DEFAULT_STORAGE_LOCATION

logger = logging.getLogger(__name__)

__all__ = [
    "ReceiptLine",
    "ReceiptResult",
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
        return ReceiptLine(
            canonical_name=raw_name.lower(),
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
        return ReceiptLine(
            canonical_name=raw_name.lower(),
            display_name=raw_name,
            quantity=qty,
            unit="unit",
            price=price,
        )

    m = _LINE_PRICE_ONLY.match(stripped)
    if m:
        raw_name = m.group(1).strip()
        price = float(m.group(2).replace(",", ""))
        return ReceiptLine(
            canonical_name=raw_name.lower(),
            display_name=raw_name,
            quantity=1.0,
            unit="unit",
            price=price,
        )

    return None


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


def confirm_receipt(database: Any, result: ReceiptResult) -> ImportResult:
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
            database.add_inventory_lot(lot)
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
            database.add_purchase_event(pe)
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
            database.record_price(po)
            ir.price_observations_added += 1
        except Exception as e:
            ir.errors.append(f"Failed to record price for '{line.display_name}': {e}")

    ir.messages.append(
        f"Receipt from {result.merchant} ({result.purchase_date}): "
        f"{len(result.lines)} items, total {result.total:.2f}"
    )
    return ir
