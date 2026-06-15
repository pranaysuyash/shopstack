"""Rendering helpers for typed service result objects.

Service-layer results are dataclasses. These renderers convert them
to minimal HTML for the Gradio UI — keeping HTML out of service logic.
"""

from __future__ import annotations

from html import escape

from shopstack.services.results import (
    MarkPurchasedResult,
    ShoppingCompletionResult,
)


def render_shopping_completion(result: ShoppingCompletionResult) -> str:
    """Render a ShoppingCompletionResult as minimal HTML."""
    if not result.success:
        return f"<div style='color:var(--text-dim);'>{escape(result.message)}</div>"
    if result.count == 0:
        return f"<div style='color:var(--green);'>{escape(result.message)}</div>"
    summary = ", ".join(
        f"{escape(i.canonical_name)} (lot {i.lot_id[:8]})" for i in result.items_added
    )
    return (
        f"<div style='color:var(--green);'>List completed! Added {result.count} items to inventory: {summary}</div>"
    )


def render_mark_purchased(result: MarkPurchasedResult) -> str:
    """Render a MarkPurchasedResult as minimal HTML."""
    if not result.success or result.count == 0:
        return f"<div style='color:var(--text-dim);'>{escape(result.message)}</div>"
    summary = ", ".join(
        f"{escape(i.canonical_name)} (lot {i.lot_id[:8]})" for i in result.items_added
    )
    return (
        f"<div style='color:var(--green);'>Marked {result.count} item(s) as purchased and added to inventory: {summary}</div>"
    )
