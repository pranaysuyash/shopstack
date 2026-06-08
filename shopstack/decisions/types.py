"""Decision types — pure data structures for the ShopStack decision engine.

No HTML rendering, no database access, no provider calls.
Every ShopStack decision (buy / skip / use-soon / compare / etc.) uses
these types as its canonical representation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class Decision(str, Enum):
    BUY = "buy"
    SKIP = "skip"
    USE_SOON = "use_soon"
    OPTIONAL = "optional"
    COMPARE = "compare"
    CONFIRM = "confirm"
    WATCH = "watch"


DECISION_COLORS: dict[str, str] = {
    "buy": "#22c55e",
    "skip": "#6b7280",
    "use_soon": "#f59e0b",
    "optional": "#3b82f6",
    "compare": "#8b5cf6",
    "confirm": "#ef4444",
    "watch": "#9ca3af",
}

DECISION_ICONS: dict[str, str] = {
    "buy": "\U0001f6d2",
    "skip": "\u23f9",
    "use_soon": "\u23f0",
    "optional": "\u2794",
    "compare": "\u2696",
    "confirm": "\u2753",
    "watch": "\U0001f441",
}


@dataclass
class Reason:
    label: str
    detail: str = ""
    evidence_refs: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return self.label


@dataclass
class Evidence:
    source: str
    value: Any
    confidence: float = 1.0
    captured_at: date | datetime | str | None = None

    @property
    def is_stale(self) -> bool:
        if self.captured_at is None:
            return False
        try:
            if isinstance(self.captured_at, str):
                d = date.fromisoformat(self.captured_at[:10])
            elif isinstance(self.captured_at, datetime):
                d = self.captured_at.date()
            else:
                d = self.captured_at
            return (date.today() - d).days > 1
        except (ValueError, TypeError):
            return False


@dataclass
class MarketEvidence:
    source: str = ""
    captured_at: str = ""
    age_days: int = 0
    is_stale: bool = False
    available_options: list[dict] = field(default_factory=list)
    sold_out_options: list[dict] = field(default_factory=list)
    best_value_price: float | None = None
    best_value_per_kg: float | None = None
    premium_options: list[dict] = field(default_factory=list)
    comparison_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "captured_at": self.captured_at,
            "age_days": self.age_days,
            "is_stale": self.is_stale,
            "best_value_price": self.best_value_price,
            "best_value_per_kg": self.best_value_per_kg,
        }


@dataclass
class ItemDecision:
    canonical_name: str
    display_name: str
    decision: str
    reason: str = ""
    confidence: float = 0.5
    quantity_at_home: float = 0
    unit: str = ""
    market_price: float | None = None
    market_price_per_kg: float | None = None
    market_available: bool = False
    market_raw_size: str = ""
    shopping_list_status: str = ""
    waste_risk: str = "unknown"
    shelf_life_days: int = 0
    last_purchase_date: date | None = None
    location: str = ""
    reasons: list[Reason] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    market_evidence: MarketEvidence | None = None

    def badge_html(self) -> str:
        color = DECISION_COLORS.get(self.decision, "var(--text-dim)")
        icon = DECISION_ICONS.get(self.decision, "")
        return (
            f"<span style='background:{color}20;color:{color};"
            f"padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;'>"
            f"{icon} {self.decision.upper()}</span>"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "display_name": self.display_name,
            "decision": self.decision,
            "reason": self.reason,
            "confidence": self.confidence,
            "quantity_at_home": self.quantity_at_home,
            "unit": self.unit,
            "market_price": self.market_price,
            "market_price_per_kg": self.market_price_per_kg,
            "market_available": self.market_available,
            "market_raw_size": self.market_raw_size,
            "shopping_list_status": self.shopping_list_status,
            "waste_risk": self.waste_risk,
            "shelf_life_days": self.shelf_life_days,
            "location": self.location,
        }


@dataclass
class DecisionSet:
    decisions: list[ItemDecision] = field(default_factory=list)

    @property
    def buy(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.BUY.value]

    @property
    def skip(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.SKIP.value]

    @property
    def use_soon(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.USE_SOON.value]

    @property
    def optional(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.OPTIONAL.value]

    @property
    def compare(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.COMPARE.value]

    @property
    def confirm(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.CONFIRM.value]

    @property
    def watch(self) -> list[ItemDecision]:
        return [d for d in self.decisions if d.decision == Decision.WATCH.value]

    @property
    def estimated_basket_total(self) -> float:
        return round(sum(d.market_price or 0 for d in self.buy), 2)
