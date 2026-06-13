"""Shopping-list substitution service.

Builds on ``shopstack.services.substitution`` to surface in-list substitution
suggestions for each shopping list item. This is the Phase 1 #14 wire-up —
the underlying ``find_substitutions`` engine was already complete, but no UI
surface called it from the shopping list view.

Returns a mapping ``canonical_name → list[SubstitutionSuggestion]`` so the
shopping list screen can render inline "sold out? try X" rows for items
where alternatives exist in market data.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from html import escape
from typing import Any

from shopstack.market.sources import SourceRegistry
from shopstack.services.substitution import (
    SubstitutionSuggestion,
    find_substitutions,
)

logger = logging.getLogger(__name__)


@dataclass
class ItemSubstitutions:
    """Substitution suggestions for one shopping list item."""

    canonical_name: str
    display_name: str
    is_sold_out: bool
    suggestions: list[SubstitutionSuggestion] = field(default_factory=list)

    @property
    def has_suggestions(self) -> bool:
        return len(self.suggestions) > 0

    @property
    def best(self) -> SubstitutionSuggestion | None:
        return self.suggestions[0] if self.suggestions else None


def get_substitutions_for_list(
    list_items: list[Any],
    source_registry: SourceRegistry | None = None,
) -> list[ItemSubstitutions]:
    """For each shopping list item, find substitution suggestions.

    Args:
        list_items: Shopping list items. Each item must expose
            ``canonical_name`` (or have it via attribute / dict key).
        source_registry: A loaded ``SourceRegistry``. If ``None`` or empty,
            returns an empty suggestion set per item (no market data).

    Returns:
        List of ``ItemSubstitutions`` (one per input item) with suggestions
        populated where the market has alternatives.
    """
    if source_registry is None:
        return [
            ItemSubstitutions(
                canonical_name=_canonical_of(item),
                display_name=_display_of(item),
                is_sold_out=False,
                suggestions=[],
            )
            for item in (list_items or [])
        ]

    snapshots = source_registry.all_snapshots() or {}
    # Use any snapshot that has data — substitution suggestions are
    # source-agnostic at the user-facing level (we just want "what else
    # could I buy instead?"). Prefer Swiggy if present (most canonical).
    snapshot = (
        snapshots.get("swiggy")
        or snapshots.get("blinkit")
        or snapshots.get("zepto")
        or snapshots.get("dmart")
        or next(iter(snapshots.values()), None)
    )
    if snapshot is None:
        return [
            ItemSubstitutions(
                canonical_name=_canonical_of(item),
                display_name=_display_of(item),
                is_sold_out=False,
                suggestions=[],
            )
            for item in (list_items or [])
        ]

    results: list[ItemSubstitutions] = []
    for item in list_items or []:
        cname = _canonical_of(item)
        if not cname:
            continue
        result = find_substitutions(cname, snapshot, include_available=False)
        is_sold_out = result.has_available_alternative or any(
            r.canonical_name == cname and not r.is_available
            for r in snapshot.normalized_records
        )
        results.append(ItemSubstitutions(
            canonical_name=cname,
            display_name=result.original_display or cname.replace("_", " ").title(),
            is_sold_out=is_sold_out,
            suggestions=result.suggestions,
        ))
    return results


def _canonical_of(item: Any) -> str:
    if isinstance(item, dict):
        return (item.get("canonical_name") or item.get("name") or "").strip()
    return (getattr(item, "canonical_name", "") or getattr(item, "name", "") or "").strip()


def _display_of(item: Any) -> str:
    if isinstance(item, dict):
        return (item.get("display_name") or item.get("canonical_name") or "").strip()
    raw = (
        getattr(item, "display_name", "")
        or getattr(item, "canonical_name", "")
        or ""
    ).strip()
    return raw.replace("_", " ").title() if raw else raw


# ─── HTML rendering ───────────────────────────────────────────────────────


_TYPE_LABELS: dict[str, str] = {
    "variety_substitution": "Different variety",
    "premium_to_basic": "Basic version available",
    "category_alternative": "Try this instead",
    "size_substitution": "Different pack size",
    "ingredient_swap": "Swap with this",
}


def render_substitutions_html(items: list[ItemSubstitutions]) -> str:
    """Render substitution suggestions as a compact HTML block.

    Only items with suggestions are rendered. Each suggestion shows the
    substitute name, type, and price (when known). Output is XSS-safe.
    """
    actionable = [i for i in items if i.has_suggestions]
    if not actionable:
        return ""

    rows: list[str] = []
    for item in actionable:
        if not item.suggestions:
            continue
        first = item.suggestions[0]
        if not first.is_available:
            continue
        type_label = _TYPE_LABELS.get(first.substitution_type, "Try instead")
        price_str = (
            f"₹{first.price_inr:.0f}"
            if first.price_inr is not None
            else ""
        )
        per_kg_str = (
            f" (₹{first.price_per_kg:.0f}/kg)"
            if first.price_per_kg is not None
            else ""
        )
        reason = escape(first.reason or type_label)
        sub_name = escape(first.substitute_display)
        sold_out_badge = ""
        if item.is_sold_out:
            sold_out_badge = (
                f" <span style='color:var(--red);font-size: 0.625rem;'>· sold out</span>"
            )

        # If there are more than one suggestion, summarise the count.
        more = ""
        if len(item.suggestions) > 1:
            more = (
                f" <span style='font-size: 0.625rem;color:var(--text-dim);'>"
                f"+{len(item.suggestions) - 1} more</span>"
            )

        rows.append(
            f"<div style='padding:6px 0;border-bottom:1px solid var(--border);'>"
            f"<div style='font-size: 0.6875rem;color:var(--text-dim);'>"
            f"<strong>{escape(item.display_name)}</strong>{sold_out_badge}"
            f"</div>"
            f"<div style='font-size: 0.75rem;'>"
            f"&#x21B3; <strong>{sub_name}</strong> "
            f"<span style='color:var(--green);'>{price_str}{per_kg_str}</span>"
            f" &middot; <span style='color:var(--text-dim);'>{reason}</span>"
            f"{more}</div></div>"
        )

    if not rows:
        return ""

    return (
        f"<div class='home-card' style='margin-bottom:12px;'>"
        f"<h3 style='margin:0 0 4px 0;'>Substitution Suggestions</h3>"
        f"<div style='font-size: 0.6875rem;color:var(--text-dim);margin-bottom:6px;'>"
        f"For items that are sold out or have better alternatives."
        f"</div>"
        f"{''.join(rows)}"
        f"</div>"
    )


__all__ = [
    "ItemSubstitutions",
    "get_substitutions_for_list",
    "render_substitutions_html",
]
