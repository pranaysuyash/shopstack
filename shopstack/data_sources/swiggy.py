from __future__ import annotations

import warnings
warnings.warn(
    "shopstack.data_sources.swiggy is deprecated and will be removed in a future version. "
    "Use shopstack.market.sources.swiggy instead.",
    DeprecationWarning,
    stacklevel=2,
)
import csv
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from shopstack.config import settings
from shopstack.market.normalization import canonicalize_name, parse_size
from shopstack.persistence.database import Database
from shopstack.schemas.models import PriceObservation
from shopstack.market.sources import swiggy as swiggy_source

SWIGGY_SOURCE_ID = "swiggy_fresh_vegetables_20260606"
SWIGGY_STORE_NAME = "Swiggy Instamart"
SWIGGY_SNAPSHOT_DATE = date(2026, 6, 6)
SWIGGY_JSON_NAME = "swiggy_fresh_vegetables_cards_6jun26.json"
SWIGGY_CSV_NAME = "swiggy_fresh_vegetables_cards_6jun26.csv"


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


def _normalize_swiggy_name(raw_name: str) -> str:
    canonical, _, _ = canonicalize_name(raw_name or "")
    return canonical or "unknown_item"


def _parse_size(size: str | None) -> tuple[float, str]:
    if not size:
        return 1.0, "unit"
    raw = str(size).strip().lower()

    # Preserve legacy tuple semantics expected by existing callers/tests.
    legacy_multiplier_patterns = {
        r"^(\d+(?:[\.,]\d+)?)\s*kg$": "kg",
        r"^(\d+(?:[\.,]\d+)?)\s*(g|gram|grams)$": "g",
        r"^(\d+(?:[\.,]\d+)?)\s*(ml|millilitre|milliliter|millil)$": "ml",
        r"^(\d+(?:[\.,]\d+)?)\s*(l|litre|liter)$": "l",
    }
    for pattern, unit in legacy_multiplier_patterns.items():
        match = re.match(pattern, raw)
        if match:
            return float(match.group(1).replace(",", ".")), unit

    legacy_pattern = re.match(r"^(\d+(?:[\.,]\d+)?)\s*(medium|small|large)$", raw)
    if legacy_pattern:
        return float(legacy_pattern.group(1).replace(",", ".")), "unit"

    size_result = parse_size(raw)
    if not size_result.normalized_quantity or not size_result.normalized_unit:
        return 1.0, "unit"

    unit = size_result.normalized_unit
    if unit == "pieces":
        unit = "unit"
    if unit == "mL":
        unit = "ml"
    return float(size_result.normalized_quantity), unit


def _load_records_from_json(path: Path) -> list[SwiggyVegetableRecord]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return [_record_from_row(row) for row in payload if isinstance(row, dict)]


def _load_records_from_csv(path: Path) -> list[SwiggyVegetableRecord]:
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [_record_from_row(row) for row in reader if isinstance(row, dict)]


def _record_from_row(row: dict[str, Any]) -> SwiggyVegetableRecord:
    normalized = swiggy_source.normalize_record(
        row,
        snapshot_id=SWIGGY_SOURCE_ID,
        captured_at=SWIGGY_SNAPSHOT_DATE.isoformat(),
    )
    discount_percent = normalized.discount_percent_displayed
    quantity = normalized.normalized_quantity if normalized.normalized_quantity else 1.0
    unit = "unit" if not normalized.normalized_unit or normalized.normalized_unit == "pieces" else normalized.normalized_unit
    notes_components = [
        f"canonical={normalized.canonical_name}",
        f"raw={normalized.raw_name}",
        f"size={normalized.raw_size}" if normalized.raw_size else None,
        f"source={normalized.source}",
        f"source_id={normalized.snapshot_id}",
        f"category={row.get('category', '')}" if row.get("category") else None,
        f"availability={normalized.availability}" if normalized.availability else None,
    ]
    notes = ", ".join(part for part in notes_components if part)
    return SwiggyVegetableRecord(
        canonical_name=normalized.canonical_name,
        display_name=normalized.raw_name.strip(),
        quantity=quantity,
        unit=unit,
        price_inr=normalized.price_inr,
        category=str(row.get("category", normalized.source_category)).strip(),
        availability=normalized.availability,
        discount_percent=discount_percent,
        mrp_inr=normalized.mrp_inr,
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
