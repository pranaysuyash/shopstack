from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field

class BasketItem(BaseModel):
    canonical_name: str
    display_name: str
    source: str
    quantity: float
    price_inr: float
    price_per_kg: float | None = None
    freshness: str = "unknown"
    waste_risk: str = "unknown"
    is_ad: bool = False
    is_upgrade: bool = False
    price_status: str = "known"
    notes: str | None = None

class BasketCandidate(BaseModel):
    id: str = ""
    items: list[BasketItem] = Field(default_factory=list)
    source_name: str  # "swiggy", "zepto", "dmart", or "mixed"
    total_cost: float = 0.0
    
    # Components of the rank
    usefulness_score: float = 0.0
    cost_score: float = 0.0
    freshness_score: float = 0.0
    waste_risk_score: float = 0.0
    preference_score: float = 0.0
    
    overall_score: float = 0.0
    missing_items: list[str] = Field(default_factory=list)
    
    @property
    def item_count(self) -> int:
        return len(self.items)
