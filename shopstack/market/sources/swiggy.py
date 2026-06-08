from __future__ import annotations

import csv
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

from ..normalization import (
    SizeParseResult,
    canonicalize_name,
    compute_unit_prices,
    parse_size,
)
from ..schema import MarketSnapshot, NormalizedMarketRecord

logger = logging.getLogger(__name__)

SOURCE_ID = "swiggy"
SOURCE_CATEGORY = "fresh_vegetables"
DEFAULT_SNAPSHOT_ID = f"{SOURCE_ID}_{SOURCE_CATEGORY}_2026-06-06"
DEFAULT_CAPTURED_AT = "2026-06-06"
FRESHNESS_WARNING_DAYS = 1

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _find_json_file(data_dir: Path | None = None) -> Path:
    d = data_dir or _DEFAULT_DATA_DIR
    candidates = sorted(d.glob("swiggy_fresh_vegetables_cards_*.json"))
    if not candidates:
        raise FileNotFoundError(
            f"No swiggy_fresh_vegetables_cards_*.json found in {d}"
        )
    return candidates[-1]


def _find_csv_file(data_dir: Path | None = None) -> Path:
    d = data_dir or _DEFAULT_DATA_DIR
    candidates = sorted(d.glob("swiggy_fresh_vegetables_cards_*.csv"))
    if not candidates:
        raise FileNotFoundError(
            f"No swiggy_fresh_vegetables_cards_*.csv found in {d}"
        )
    return candidates[-1]


def load_raw_json(data_dir: Path | None = None) -> list[dict[str, Any]]:
    fp = _find_json_file(data_dir)
    with open(fp, encoding="utf-8") as f:
        return json.load(f)


def load_raw_csv(data_dir: Path | None = None) -> list[dict[str, Any]]:
    fp = _find_csv_file(data_dir)
    with open(fp, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_raw(data_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load raw Swiggy cards from JSON (preferred) or CSV fallback."""
    try:
        return load_raw_json(data_dir)
    except FileNotFoundError:
        return load_raw_csv(data_dir)


def _coerce_float(val: Any, default: float = 0.0) -> float:
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _coerce_int(val: Any, default: int = 0) -> int:
    if val is None or val == "":
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def normalize_record(
    raw: dict[str, Any],
    snapshot_id: str = DEFAULT_SNAPSHOT_ID,
    captured_at: str = DEFAULT_CAPTURED_AT,
) -> NormalizedMarketRecord:
    raw_name = str(raw.get("name", "")).strip()
    raw_size = str(raw.get("size", "")).strip()

    canonical, variety, components = canonicalize_name(raw_name)
    size_result: SizeParseResult = parse_size(raw_size)

    is_combo = len(components) > 1 or size_result.is_combo
    tag = str(raw.get("tag", "")).strip()
    availability = str(raw.get("availability", "")).strip()
    is_available = availability.lower() == "available"

    price = _coerce_float(raw.get("price_inr"))
    mrp = _coerce_float(raw.get("mrp_inr"))

    unit_prices = compute_unit_prices(
        price=price,
        quantity=size_result.normalized_quantity,
        unit=size_result.normalized_unit,
        is_weight_based=size_result.is_weight_based,
        is_piece_based=size_result.is_piece_based,
    )

    warnings: list[str] = list(size_result.warnings or [])

    return NormalizedMarketRecord(
        source=SOURCE_ID,
        source_category=SOURCE_CATEGORY,
        raw_name=raw_name,
        canonical_name=canonical,
        description=str(raw.get("description", "")).strip(),
        raw_size=raw_size,
        normalized_quantity=size_result.normalized_quantity,
        normalized_unit=size_result.normalized_unit,
        package_count=size_result.package_count,
        is_combo=is_combo,
        is_weight_based=size_result.is_weight_based,
        is_piece_based=size_result.is_piece_based,
        is_size_class=size_result.is_size_class,
        size_class=size_result.size_class,
        price_inr=price,
        mrp_inr=mrp,
        discount_percent_displayed=_coerce_float(
            raw.get("discount_percent")
        ),
        discount_amount_inr=_coerce_float(
            raw.get("discount_amount_inr")
        ),
        computed_discount_percent=_coerce_float(
            raw.get("computed_discount_percent")
        ),
        availability=availability,
        is_available=is_available,
        tag=tag,
        is_ad=tag.lower() == "ad",
        is_upgrade=tag.lower() == "upgrade",
        card_index=_coerce_int(raw.get("card_index")),
        delivery_time=str(raw.get("delivery_time", "")).strip(),
        captured_at=captured_at,
        snapshot_id=snapshot_id,
        price_per_kg=unit_prices["price_per_kg"],
        price_per_100g=unit_prices["price_per_100g"],
        price_per_piece=unit_prices["price_per_piece"],
        normalization_warnings=warnings,
        component_names=components or [],
        variety=variety,
    )


def load_snapshot(
    data_dir: Path | None = None,
    snapshot_id: str | None = None,
    captured_at: str | None = None,
) -> MarketSnapshot:
    raw_records = load_raw(data_dir)
    sid = snapshot_id or DEFAULT_SNAPSHOT_ID
    cat = captured_at or DEFAULT_CAPTURED_AT

    normalized = [normalize_record(r, sid, cat) for r in raw_records]

    return MarketSnapshot(
        snapshot_id=sid,
        source=SOURCE_ID,
        source_category=SOURCE_CATEGORY,
        captured_at=cat,
        raw_records=raw_records,
        normalized_records=normalized,
    )


def snapshot_freshness(snapshot: MarketSnapshot, today: date | None = None) -> dict[str, Any]:
    """Return freshness metadata for a Swiggy point-in-time snapshot."""
    current = today or date.today()
    try:
        captured = date.fromisoformat(snapshot.captured_at[:10])
    except (ValueError, TypeError):
        return {
            "captured_at": snapshot.captured_at,
            "age_days": None,
            "is_stale": True,
            "label": f"Snapshot date unclear: {snapshot.captured_at or 'unknown'}",
        }

    age_days = (current - captured).days
    if age_days <= 0:
        label = f"Captured today ({snapshot.captured_at})"
    elif age_days == 1:
        label = f"Captured yesterday ({snapshot.captured_at})"
    else:
        label = f"Captured {age_days} days ago ({snapshot.captured_at})"
    return {
        "captured_at": snapshot.captured_at,
        "age_days": age_days,
        "is_stale": age_days > FRESHNESS_WARNING_DAYS,
        "label": label,
    }
