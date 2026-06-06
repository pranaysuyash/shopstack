from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from shopstack.config import settings
from shopstack.persistence.database import Database
from shopstack.schemas.models import PriceObservation

SWIGGY_SOURCE_ID = "swiggy_fresh_vegetables_20260606"
SWIGGY_STORE_NAME = "Swiggy Instamart"
SWIGGY_SNAPSHOT_DATE = date(2026, 6, 6)
SWIGGY_JSON_NAME = "swiggy_fresh_vegetables_cards_6jun26.json"
SWIGGY_CSV_NAME = "swiggy_fresh_vegetables_cards_6jun26.csv"

_GENERIC_ITEM_KEYWORDS = [
    "bottle gourd",
    "ridge gourd",
    "bitter gourd",
    "pointed gourd",
    "snake gourd",
    "tomato",
    "potato",
    "onion",
    "cauliflower",
    "cabbage",
    "cucumber",
    "capsicum",
    "brinjal",
    "eggplant",
    "beans",
    "drumstick",
    "coriander",
    "cilantro",
    "garlic",
    "ginger",
    "spinach",
    "mint",
    "lemon",
    "carrot",
    "beetroot",
    "pumpkin",
    "sweet potato",
    "broad beans",
    "chickpeas",
]


@dataclass
class SwiggyVegetableRecord:
    canonical_name: str
    display_name: str
    quantity: float
    unit: str
    price_inr: float
    category: str
    availability: str
    discount_percent: float | None
    mrp_inr: float | None
    notes: str

    def to_price_observation(self) -> PriceObservation:
        return PriceObservation(
            canonical_name=self.canonical_name,
            quantity=self.quantity,
            unit=self.unit,
            price=self.price_inr,
            currency="INR",
            store_name=SWIGGY_STORE_NAME,
            observation_date=SWIGGY_SNAPSHOT_DATE,
            source_event_id=SWIGGY_SOURCE_ID,
            notes=self.notes,
        )


def _parse_numeric(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw.replace("₹", "").replace("inr", "").replace(",", "")
    try:
        return float(raw)
    except ValueError:
        if raw.count("/") == 1:
            parts = raw.split("/")
            try:
                return float(parts[0]) / float(parts[1])
            except (ValueError, ZeroDivisionError):
                return None
    return None


_ITEM_ALIASES: dict[str, list[str]] = {
    "tomato": ["tamatar", "tomatoes", "desi tomato", "hybrid tomato", "indian tomato"],
    "potato": ["aloo", "baby potato", "chikka aloo", "sweet potato"],
    "onion": ["eerulli", "sambar onion"],
    "coriander": ["dhania", "cilantro"],
    "curd": ["dahi", "yogurt"],
    "rice": ["chawal"],
    "lentils": ["dal", "daal"],
    "cucumber": ["sowthekaayi"],
}


def normalize_item_name(name: str) -> str:
    normalized = re.sub(r"[^\w\s]", " ", name.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    for canonical, aliases in _ITEM_ALIASES.items():
        if normalized == canonical or normalized in aliases:
            return canonical
    return normalized


def _normalize_swiggy_name(raw_name: str) -> str:
    cleaned = re.sub(r"\s*\(.*?\)", "", raw_name or "").strip().lower()
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    found = []
    for keyword in sorted(_GENERIC_ITEM_KEYWORDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(keyword)}\b", cleaned):
            found.append(keyword)
    if len(found) == 1:
        return normalize_item_name(found[0])
    return normalize_item_name(cleaned)


def _parse_size(size: str | None) -> tuple[float, str]:
    if not size:
        return 1.0, "unit"
    raw = str(size).strip().lower()
    raw = re.sub(r"[()]", "", raw)
    raw = raw.replace("each", "unit").replace("pcs", "piece").replace("pc", "piece")
    raw = raw.replace("kgs", "kg").replace("litres", "l").replace("liters", "l")
    raw = raw.replace("mls", "ml").replace("grams", "g").replace("kilograms", "kg")
    raw = re.sub(r"[^\w\d\.\s/-]", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()

    if not raw:
        return 1.0, "unit"

    if raw in ("medium", "small", "large", "unit", "piece", "piece ", "packet", "pack", "bunch"):
        return 1.0, "unit"

    if m := re.match(r"^(\d+(?:[\.,]\d+)?)(?:\s*)(medium|small|large|piece|unit|bunch|pack|packet)$", raw):
        quantity = float(m.group(1).replace(",", "."))
        return quantity, "unit"

    match = re.match(r"^(\d+(?:[\.,]\d+)?)(?:\s*)(kg|g|l|ml|piece|unit|bunch|pack|packet)$", raw)
    if match:
        quantity = float(match.group(1).replace(",", "."))
        unit = match.group(2)
        if unit == "piece":
            unit = "unit"
        return quantity, unit

    split = raw.split()
    if len(split) == 2 and split[0].replace(".", "", 1).isdigit():
        try:
            quantity = float(split[0].replace(",", "."))
            return quantity, split[1]
        except ValueError:
            pass

    digits = re.findall(r"[\d\.]+", raw)
    if digits:
        try:
            quantity = float(digits[0])
            if "kg" in raw:
                return quantity, "kg"
            if "g" in raw:
                return quantity, "g"
            if "l" in raw:
                return quantity, "l"
            if "ml" in raw:
                return quantity, "ml"
            return quantity, "unit"
        except ValueError:
            pass

    return 1.0, "unit"


def _load_records_from_json(path: Path) -> list[SwiggyVegetableRecord]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return [_record_from_row(row) for row in payload if isinstance(row, dict)]


def _load_records_from_csv(path: Path) -> list[SwiggyVegetableRecord]:
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [_record_from_row(row) for row in reader if isinstance(row, dict)]


def _record_from_row(row: dict[str, Any]) -> SwiggyVegetableRecord:
    name = str(row.get("name", ""))
    size = str(row.get("size", ""))
    price_inr = _parse_numeric(row.get("price_inr")) or 0.0
    mrp_inr = _parse_numeric(row.get("mrp_inr"))
    discount_percent = _parse_numeric(row.get("discount_percent"))
    quantity, unit = _parse_size(size)
    canonical_name = _normalize_swiggy_name(name)
    notes_components = [
        f"raw={name}",
        f"size={size}" if size else None,
        f"category={row.get('category', '')}" if row.get("category") else None,
        f"availability={row.get('availability', '')}" if row.get("availability") else None,
        f"discount={discount_percent:.0f}%" if discount_percent is not None else None,
    ]
    notes = ", ".join([part for part in notes_components if part])
    return SwiggyVegetableRecord(
        canonical_name=canonical_name,
        display_name=name.strip(),
        quantity=quantity,
        unit=unit,
        price_inr=price_inr,
        category=str(row.get("category", "")).strip(),
        availability=str(row.get("availability", "")).strip(),
        discount_percent=discount_percent,
        mrp_inr=mrp_inr,
        notes=notes,
    )


def _find_swiggy_source_file() -> Path:
    data_dir = Path(settings.data_dir)
    json_path = data_dir / SWIGGY_JSON_NAME
    csv_path = data_dir / SWIGGY_CSV_NAME
    if json_path.exists():
        return json_path
    if csv_path.exists():
        return csv_path
    raise FileNotFoundError(
        "Swiggy snapshot source file not found in data directory. "
        f"Expected {SWIGGY_JSON_NAME} or {SWIGGY_CSV_NAME}."
    )


def load_swiggy_fresh_vegetables(path: Path | None = None) -> list[SwiggyVegetableRecord]:
    source_path = Path(path) if path is not None else _find_swiggy_source_file()
    if source_path.suffix.lower() == ".json":
        return _load_records_from_json(source_path)
    if source_path.suffix.lower() == ".csv":
        return _load_records_from_csv(source_path)
    raise ValueError(f"Unsupported file format: {source_path.suffix}")


def summarize_swiggy_snapshot(records: list[SwiggyVegetableRecord]) -> dict[str, Any]:
    total = len(records)
    category_counts: dict[str, int] = {}
    prices_by_item: dict[str, list[float]] = {}
    discount_items: list[SwiggyVegetableRecord] = []

    for record in records:
        category_counts[record.category] = category_counts.get(record.category, 0) + 1
        prices_by_item.setdefault(record.canonical_name, []).append(record.price_inr)
        if record.discount_percent is not None and record.discount_percent > 0:
            discount_items.append(record)

    avg_price_by_item = {
        item: round(sum(prices) / len(prices), 2)
        for item, prices in prices_by_item.items()
    }
    top_discounts = sorted(discount_items, key=lambda r: r.discount_percent or 0, reverse=True)[:5]

    return {
        "total_records": total,
        "unique_items": len(prices_by_item),
        "categories": category_counts,
        "avg_price_by_item": avg_price_by_item,
        "top_discounts": [
            {
                "name": record.display_name,
                "canonical_name": record.canonical_name,
                "price_inr": record.price_inr,
                "discount_percent": record.discount_percent,
            }
            for record in top_discounts
        ],
    }


def import_swiggy_fresh_vegetables_snapshot(
    db: Database,
    path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    records = load_swiggy_fresh_vegetables(path)
    imported = 0
    skipped = 0
    for record in records:
        if record.price_inr <= 0 or record.quantity <= 0:
            skipped += 1
            continue
        observation = record.to_price_observation()
        if not dry_run:
            db.record_price(observation)
        imported += 1

    summary = summarize_swiggy_snapshot(records)
    summary["imported_records"] = imported
    summary["skipped_records"] = skipped
    summary["source_file"] = str(path or _find_swiggy_source_file())
    summary["source_event_id"] = SWIGGY_SOURCE_ID
    return summary
