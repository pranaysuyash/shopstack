from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NormalizedMarketRecord:
    source: str
    source_category: str
    raw_name: str
    canonical_name: str
    description: str
    raw_size: str
    normalized_quantity: float | None
    normalized_unit: str | None
    package_count: int
    is_combo: bool
    is_weight_based: bool
    is_piece_based: bool
    is_size_class: bool
    size_class: str
    price_inr: float
    mrp_inr: float
    discount_percent_displayed: float
    discount_amount_inr: float
    computed_discount_percent: float
    availability: str
    is_available: bool
    tag: str
    is_ad: bool
    is_upgrade: bool
    card_index: int
    delivery_time: str
    captured_at: str
    snapshot_id: str
    price_per_kg: float | None
    price_per_100g: float | None
    price_per_piece: float | None
    normalization_warnings: list[str] = field(default_factory=list)
    component_names: list[str] = field(default_factory=list)
    variety: str = ""
    brand: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_category": self.source_category,
            "raw_name": self.raw_name,
            "canonical_name": self.canonical_name,
            "description": self.description,
            "raw_size": self.raw_size,
            "normalized_quantity": self.normalized_quantity,
            "normalized_unit": self.normalized_unit,
            "package_count": self.package_count,
            "is_combo": self.is_combo,
            "is_weight_based": self.is_weight_based,
            "is_piece_based": self.is_piece_based,
            "is_size_class": self.is_size_class,
            "size_class": self.size_class,
            "price_inr": self.price_inr,
            "mrp_inr": self.mrp_inr,
            "discount_percent_displayed": self.discount_percent_displayed,
            "discount_amount_inr": self.discount_amount_inr,
            "computed_discount_percent": self.computed_discount_percent,
            "availability": self.availability,
            "is_available": self.is_available,
            "tag": self.tag,
            "is_ad": self.is_ad,
            "is_upgrade": self.is_upgrade,
            "card_index": self.card_index,
            "delivery_time": self.delivery_time,
            "captured_at": self.captured_at,
            "snapshot_id": self.snapshot_id,
            "price_per_kg": self.price_per_kg,
            "price_per_100g": self.price_per_100g,
            "price_per_piece": self.price_per_piece,
            "normalization_warnings": self.normalization_warnings,
            "component_names": self.component_names,
            "variety": self.variety,
            "brand": self.brand,
        }


@dataclass
class MarketSnapshot:
    snapshot_id: str
    source: str
    source_category: str
    captured_at: str
    raw_records: list[dict[str, Any]]
    normalized_records: list[NormalizedMarketRecord]
    analytics: dict[str, Any] = field(default_factory=dict)
