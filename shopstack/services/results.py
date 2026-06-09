"""Typed result objects for all service operations.

Every service returns one of these instead of raw HTML or dicts.
Rendering happens in shopstack.ui.renderers, not in service logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CompletionItem:
    canonical_name: str
    lot_id: str
    quantity: float
    unit: str


@dataclass
class ShoppingCompletionResult:
    success: bool
    list_id: str
    items_added: list[CompletionItem] = field(default_factory=list)
    items_skipped: int = 0
    goal: str = ""
    message: str = ""

    @property
    def count(self) -> int:
        return len(self.items_added)


@dataclass
class PurchaseResultItem:
    canonical_name: str
    lot_id: str
    quantity: float
    unit: str


@dataclass
class MarkPurchasedResult:
    success: bool
    items_added: list[PurchaseResultItem] = field(default_factory=list)
    message: str = ""

    @property
    def count(self) -> int:
        return len(self.items_added)
