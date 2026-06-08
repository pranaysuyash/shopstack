"""Typed result objects for all service operations.

Every service returns one of these instead of raw HTML or dicts.
Rendering belongs in shopstack.ui.screens.*, not in service logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape


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

    def to_html(self) -> str:
        """Render as minimal HTML for the Gradio UI."""
        if not self.success:
            return f"<div style='color:var(--text-dim);'>{escape(self.message)}</div>"
        if self.count == 0:
            return f"<div style='color:var(--green);'>{escape(self.message)}</div>"
        summary = ", ".join(
            f"{escape(i.canonical_name)} (lot {i.lot_id[:8]})" for i in self.items_added
        )
        return (
            f"<div style='color:var(--green);'>List completed! "
            f"Added {self.count} items to inventory: {summary}</div>"
        )


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

    def to_html(self) -> str:
        if not self.success or self.count == 0:
            return f"<div style='color:var(--text-dim);'>{escape(self.message)}</div>"
        summary = ", ".join(
            f"{escape(i.canonical_name)} (lot {i.lot_id[:8]})" for i in self.items_added
        )
        return (
            f"<div style='color:var(--green);'>Marked {self.count} item(s) as purchased "
            f"and added to inventory: {summary}</div>"
        )
