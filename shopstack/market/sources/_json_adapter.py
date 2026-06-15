"""Shared base for JSON-file-backed market source adapters.

Blinkit, Zepto, and DMart adapters are structurally identical except for:
  - source ID
  - JSON file glob pattern
  - raw-record field names for product name and price
  - price calculation logic

This module extracts the common code so each adapter is a thin config.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from shopstack.domain import (
    SizeParseResult,
    canonicalize_name,
    compute_unit_prices,
    parse_size,
)
from shopstack.market.schema import MarketSnapshot, NormalizedMarketRecord

logger = logging.getLogger(__name__)

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"
FRESHNESS_WARNING_DAYS = 1


# ── Shared helpers ─────────────────────────────────────────────────────


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


def _find_json(glob_pattern: str, data_dir: Path | None = None) -> Path:
    d = data_dir or _DEFAULT_DATA_DIR
    candidates = sorted(d.glob(glob_pattern))
    if not candidates:
        raise FileNotFoundError(f"No {glob_pattern} found in {d}")
    return candidates[-1]


def _load_raw_json(glob_pattern: str, data_dir: Path | None = None) -> list[dict[str, Any]]:
    fp = _find_json(glob_pattern, data_dir)
    with open(fp, encoding="utf-8") as f:
        return json.load(f)


# ── Per-source config ──────────────────────────────────────────────────


@dataclass
class JsonSourceConfig:
    source_id: str
    source_category: str
    file_glob: str
    name_field: str
    price_field: str
    original_price_field: str
    captured_at: str = "2026-06-06"

    @property
    def snapshot_id(self) -> str:
        return f"{self.source_id}_{self.source_category}_{self.captured_at}"

    def extract_price(self, raw: dict[str, Any]) -> tuple[float, float]:
        """Return (price, mrp) from a raw record. Override for custom logic."""
        price = _coerce_float(raw.get(self.price_field))
        mrp = _coerce_float(raw.get(self.original_price_field))
        if price <= 0:
            price = mrp
        if mrp <= 0 or mrp == price:
            mrp = price
        return price, mrp


# ── Shared normalization ───────────────────────────────────────────────


def _normalize_record_shared(
    raw: dict[str, Any],
    config: JsonSourceConfig,
) -> NormalizedMarketRecord:
    raw_name = str(raw.get(config.name_field, "")).strip()
    raw_size = str(raw.get("size", "")).strip()

    canonical, variety, components = canonicalize_name(raw_name)
    size_result: SizeParseResult = parse_size(raw_size)

    is_combo = len(components) > 1 or size_result.is_combo
    availability = str(raw.get("availability", "")).strip()
    is_available = availability.lower() == "available"

    price, mrp = config.extract_price(raw)

    unit_prices = compute_unit_prices(
        price=price,
        quantity=size_result.normalized_quantity,
        unit=size_result.normalized_unit,
        is_weight_based=size_result.is_weight_based,
        is_piece_based=size_result.is_piece_based,
    )

    discount_amount = mrp - price if mrp > price else 0.0
    computed_discount = round(discount_amount / mrp * 100, 1) if mrp > 0 else 0.0

    warnings: list[str] = list(size_result.warnings or [])

    return NormalizedMarketRecord(
        source=config.source_id,
        source_category=config.source_category,
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
        discount_percent_displayed=_coerce_float(raw.get("discount_percent")),
        discount_amount_inr=discount_amount,
        computed_discount_percent=computed_discount,
        availability=availability,
        is_available=is_available,
        tag=str(raw.get("tag", "")).strip(),
        is_ad=str(raw.get("tag", "")).strip().lower() == "ad",
        is_upgrade=str(raw.get("tag", "")).strip().lower() == "upgrade",
        card_index=_coerce_int(raw.get("card_index")),
        delivery_time=str(raw.get("delivery_time", "")).strip(),
        captured_at=config.captured_at,
        snapshot_id=config.snapshot_id,
        price_per_kg=unit_prices["price_per_kg"],
        price_per_100g=unit_prices["price_per_100g"],
        price_per_piece=unit_prices["price_per_piece"],
        normalization_warnings=warnings,
        component_names=components or [],
        variety=variety,
        brand=str(raw.get("brand", "")).strip(),
    )


def load_snapshot(
    config: JsonSourceConfig,
    data_dir: Path | None = None,
    snapshot_id: str | None = None,
    captured_at: str | None = None,
) -> MarketSnapshot:
    raw_records = _load_raw_json(config.file_glob, data_dir)
    sid = snapshot_id or config.snapshot_id
    cat = captured_at or config.captured_at

    from dataclasses import replace
    cfg = replace(config, captured_at=cat)

    normalized = [_normalize_record_shared(r, cfg) for r in raw_records]

    return MarketSnapshot(
        snapshot_id=sid,
        source=config.source_id,
        source_category=config.source_category,
        captured_at=cat,
        raw_records=raw_records,
        normalized_records=normalized,
    )


def snapshot_freshness(snapshot: MarketSnapshot, today: date | None = None) -> dict[str, Any]:
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
