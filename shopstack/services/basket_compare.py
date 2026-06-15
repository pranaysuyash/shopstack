"""Multi-source basket comparison — compute per-source totals for a shopping list.

Builds on the cross-source single-item comparison in
``shopstack.market.sources._comparison`` by aggregating line totals across a
whole basket and surfacing the cheapest source, total savings, and per-item
breakdown.

This is a pure-data service: it takes a ``SourceRegistry`` and a list of
requested items, returns a ``BasketComparison`` dataclass. The HTML rendering
lives in ``render_basket_comparison_html`` and the free-text input parsing in
``parse_basket_input``. Both can be used independently of Gradio.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from html import escape
from typing import Any

from shopstack.ui.components.primitives import home_card

logger = logging.getLogger(__name__)


# Human-readable labels for the four core sources. Exposed as a constant so
# callers (e.g. tests) can inspect or override without re-defining.
SOURCE_LABELS: dict[str, str] = {
    "swiggy": "Swiggy Instamart",
    "blinkit": "Blinkit",
    "zepto": "Zepto",
    "dmart": "DMart",
}


# ─── Unit normalization ───────────────────────────────────────────────────


def _normalize_unit_to_grams(qty: float, unit: str) -> float:
    """Convert a (quantity, unit) pair into a grams-equivalent for line-total math.

    Weight units (kg, g) and volume units (l, ml) both collapse to grams/mL
    because the market price data is normalized to grams. Piece-based items
    (eggs, bread loaves) are passed through as the raw count — the price math
    is handled separately in ``_best_line_total``.

    Mirrors the helper of the same name in ``shopstack.market.basket`` — kept
    private to that module, so re-implemented here to avoid a cross-layer import.
    """
    u = unit.lower().strip()
    if u in ("kg", "kilo", "kilos", "kilogram", "kilograms"):
        return qty * 1000.0
    if u in ("g", "gram", "grams"):
        return qty
    if u in ("l", "litre", "liter", "litres", "liters"):
        return qty * 1000.0
    if u in ("ml", "milliliter", "millilitre", "milliliters", "millilitres"):
        return qty
    # Default: treat as unit/piece count, return raw value
    return qty


# ─── Dataclasses ──────────────────────────────────────────────────────────


@dataclass
class BasketLine:
    """One requested item's pricing across all sources.

    ``line_totals`` maps ``source_id`` → INR line total for the requested
    quantity. Sources where the item is unavailable are recorded in
    ``unavailable_at`` instead of being present in the dict.
    """

    requested_name: str
    canonical_name: str
    requested_quantity: float
    unit: str
    line_totals: dict[str, float] = field(default_factory=dict)
    unavailable_at: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def cheapest_source(self) -> str | None:
        if not self.line_totals:
            return None
        return min(self.line_totals, key=lambda s: self.line_totals[s])

    @property
    def cheapest_total(self) -> float | None:
        s = self.cheapest_source
        return self.line_totals.get(s) if s else None

    @property
    def worst_total(self) -> float | None:
        if not self.line_totals:
            return None
        return max(self.line_totals.values())


@dataclass
class SourceBasket:
    """One source's view of the entire basket."""

    source_id: str
    label: str
    line_totals: dict[str, float] = field(default_factory=dict)
    unavailable_items: list[str] = field(default_factory=list)
    basket_total: float = 0.0
    coverage_pct: float = 0.0
    freshness_label: str = ""
    is_stale: bool = False

    @property
    def missing_count(self) -> int:
        return len(self.unavailable_items)


@dataclass
class BasketComparison:
    """Multi-source comparison for one shopping basket.

    The cheapest and most-expensive source are computed by ``basket_total``
    among sources that cover at least one item. If only one source has data,
    both are ``None`` and savings are zero.
    """

    requested_items: list[dict[str, Any]] = field(default_factory=list)
    per_item: list[BasketLine] = field(default_factory=list)
    per_source: list[SourceBasket] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    cheapest_source_id: str | None = None
    most_expensive_source_id: str | None = None
    total_savings_inr: float = 0.0
    savings_pct: float = 0.0
    matched_count: int = 0
    total_requested: int = 0

    @property
    def is_meaningful(self) -> bool:
        """A comparison is meaningful when ≥ 2 sources cover at least one item."""
        return len([s for s in self.per_source if s.line_totals]) >= 2

    @property
    def has_any_data(self) -> bool:
        return len(self.source_ids) > 0

    def summary(self) -> dict[str, Any]:
        return {
            "total_requested": self.total_requested,
            "matched": self.matched_count,
            "cheapest_source": self.cheapest_source_id,
            "most_expensive_source": self.most_expensive_source_id,
            "total_savings_inr": round(self.total_savings_inr, 2),
            "savings_pct": self.savings_pct,
            "sources_loaded": self.source_ids,
        }


# ─── Per-record price math ────────────────────────────────────────────────


def _line_total_for_record(record: Any, requested_grams: float) -> float | None:
    """Compute INR line total for a single market record + requested quantity.

    Returns ``None`` if the record is unavailable, a combo, size-class, or has
    no usable quantity/price. The math is ``price_inr * (requested / record_qty)``,
    so it correctly handles different pack sizes — a 500g pack at ₹15 and a
    1kg pack at ₹30 both yield ₹60 for 2kg.
    """
    if not getattr(record, "is_available", False):
        return None
    if getattr(record, "is_combo", False) or getattr(record, "is_size_class", False):
        return None
    qty = getattr(record, "normalized_quantity", None)
    price = getattr(record, "price_inr", None)
    if qty is None or qty <= 0 or price is None or price <= 0:
        return None
    if requested_grams <= 0:
        # Zero requested — surface the record's own price as a degenerate case.
        return round(price, 2)
    return round(price * (requested_grams / qty), 2)


def _best_line_total(records: list[Any], requested_grams: float) -> float | None:
    """Pick the cheapest line total from one source's records for a single item.

    Tries weight-based records first, falls back to piece-based records if
    no weight record yields a valid line total. Returns ``None`` when no
    record can satisfy the request.
    """
    weight_candidates: list[float] = []
    for r in records:
        if not getattr(r, "is_weight_based", False):
            continue
        total = _line_total_for_record(r, requested_grams)
        if total is not None:
            weight_candidates.append(total)

    if weight_candidates:
        return min(weight_candidates)

    # Fall back to piece-based records (eggs, loaves, etc.)
    piece_candidates: list[float] = []
    for r in records:
        if getattr(r, "is_weight_based", False):
            continue
        if getattr(r, "is_piece_based", False) or getattr(r, "is_combo", False):
            total = _line_total_for_record(r, requested_grams)
            if total is not None:
                piece_candidates.append(total)
    if piece_candidates:
        return min(piece_candidates)
    return None


# ─── Comparison service ───────────────────────────────────────────────────


def _resolve_source_id(source_obj: Any) -> str:
    """Pull a source id string from either a snapshot, a record, or a string."""
    if isinstance(source_obj, str):
        return source_obj
    for attr in ("source", "source_id"):
        v = getattr(source_obj, attr, None)
        if isinstance(v, str) and v:
            return v
    return str(source_obj)


def compare_basket_across_sources(
    registry: Any,
    requested_items: list[dict[str, Any]],
    inventory_map: dict[str, float] | None = None,
) -> BasketComparison:
    """Compare a basket of items across all loaded market sources.

    Args:
        registry: A ``SourceRegistry`` (or any object exposing
            ``all_snapshots()`` and ``freshness_of(source_id)``). Loaded
            snapshots are taken from ``registry.all_snapshots()``.
        requested_items: List of dicts. Each must have ``canonical_name``
            and may have ``requested_quantity`` (default ``1.0``) and
            ``unit`` (default ``"unit"``). Extra keys are ignored.
        inventory_map: Optional mapping of ``canonical_name`` → quantity
            owned in the same base unit as ``unit``. If the user already has
            enough at home, the line total is still computed (we surface
            availability, not buy/skip decisions) but the rendered HTML
            surfaces a "you have enough" note.

    Returns:
        A populated ``BasketComparison``. If fewer than two sources have
        data, ``is_meaningful`` is ``False`` and the renderer falls back to
        an informative empty state.
    """
    inventory_map = inventory_map or {}
    snapshots = registry.all_snapshots() or {}
    source_ids = sorted(_resolve_source_id(sid) for sid in snapshots.keys())

    per_item: list[BasketLine] = []
    matched_count = 0
    total_requested = 0

    for raw in requested_items or []:
        name = (raw.get("canonical_name") or raw.get("name") or "").strip()
        if not name:
            continue
        total_requested += 1
        qty = float(raw.get("requested_quantity") or 1.0)
        unit = (raw.get("unit") or "unit").strip() or "unit"
        requested_grams = _normalize_unit_to_grams(qty, unit)

        # Inventory subtraction in the same base unit
        owned = float(inventory_map.get(name, 0.0) or 0.0)
        net_grams = max(requested_grams - owned, 0.0)

        line_totals: dict[str, float] = {}
        unavailable: list[str] = []
        notes: list[str] = []

        for sid in source_ids:
            snap = snapshots.get(sid) or snapshots.get(sid.lower())
            if snap is None:
                # Try matching the snapshot's own source identifier
                for k, v in snapshots.items():
                    if _resolve_source_id(k) == sid:
                        snap = v
                        break
            if snap is None:
                unavailable.append(sid)
                continue
            records = [
                r for r in getattr(snap, "normalized_records", [])
                if _resolve_source_id(r) in (sid, sid.title(), sid.upper())
                or getattr(r, "canonical_name", None) == name
                and getattr(r, "is_available", False)
            ]
            # Filter to only matching canonical_name
            records = [
                r for r in records
                if getattr(r, "canonical_name", None) == name
                and getattr(r, "is_available", False)
                and not getattr(r, "is_combo", False)
            ]
            if not records:
                unavailable.append(sid)
                continue
            line = _best_line_total(records, net_grams if net_grams > 0 else requested_grams)
            if line is None:
                unavailable.append(sid)
                continue
            line_totals[sid] = line

        if line_totals:
            matched_count += 1
        if owned > 0 and net_grams < requested_grams and requested_grams > 0:
            notes.append(
                f"Subtracted {owned:.0f} from inventory; need {net_grams:.0f} more"
            )
        if owned >= requested_grams and requested_grams > 0:
            notes.append("You have enough at home — no need to buy")

        per_item.append(BasketLine(
            requested_name=name,
            canonical_name=name,
            requested_quantity=qty,
            unit=unit,
            line_totals=line_totals,
            unavailable_at=unavailable,
            notes=notes,
        ))

    # Per-source aggregation
    per_source: list[SourceBasket] = []
    for sid in source_ids:
        line_totals_by_item: dict[str, float] = {}
        unavailable_items: list[str] = []
        for line in per_item:
            if sid in line.line_totals and line.line_totals[sid] is not None:
                line_totals_by_item[line.canonical_name] = line.line_totals[sid]
            else:
                unavailable_items.append(line.canonical_name)

        basket_total = round(sum(line_totals_by_item.values()), 2)
        coverage = (len(line_totals_by_item) / len(per_item) * 100.0) if per_item else 0.0

        # Freshness (graceful failure if registry doesn't expose it)
        freshness_label = ""
        is_stale = False
        try:
            freshness = registry.freshness_of(sid) or {}
            freshness_label = freshness.get("label", "") or ""
            is_stale = bool(freshness.get("is_stale", False))
        except Exception:
            pass

        per_source.append(SourceBasket(
            source_id=sid,
            label=SOURCE_LABELS.get(sid, sid.title()),
            line_totals=line_totals_by_item,
            unavailable_items=unavailable_items,
            basket_total=basket_total,
            coverage_pct=round(coverage, 1),
            freshness_label=freshness_label,
            is_stale=is_stale,
        ))

    # Cheapest / most expensive by basket_total (only when ≥ 2 sources cover
    # at least one item — with a single source, "cheapest" is meaningless).
    sources_with_items = [s for s in per_source if s.line_totals]
    if len(sources_with_items) >= 2:
        cheapest = min(sources_with_items, key=lambda s: s.basket_total)
        most_expensive = max(sources_with_items, key=lambda s: s.basket_total)
        cheapest_id = cheapest.source_id
        most_expensive_id = most_expensive.source_id
        savings = round(most_expensive.basket_total - cheapest.basket_total, 2)
        savings_pct = (
            round(savings / most_expensive.basket_total * 100, 1)
            if most_expensive.basket_total > 0
            else 0.0
        )
    else:
        cheapest_id = None
        most_expensive_id = None
        savings = 0.0
        savings_pct = 0.0

    return BasketComparison(
        requested_items=list(requested_items or []),
        per_item=per_item,
        per_source=per_source,
        source_ids=source_ids,
        cheapest_source_id=cheapest_id,
        most_expensive_source_id=most_expensive_id,
        total_savings_inr=savings,
        savings_pct=savings_pct,
        matched_count=matched_count,
        total_requested=total_requested,
    )


# ─── Free-text input parsing ──────────────────────────────────────────────


_BASKET_LINE_RE = re.compile(
    r"^(\d+(?:\.\d+)?)\s*"
    r"(kg|g|ml|l|liter|litre|piece|pieces|pcs|pc|unit|units)?\s+"
    r"(.+?)\s*$",
    re.IGNORECASE,
)


def parse_basket_input(text: str) -> list[dict[str, Any]]:
    """Parse free-text basket input into structured items.

    Accepts one item per line. Recognised patterns::

        "2kg onions"
        "1 L milk"
        "500g tomatoes"
        "5 eggs"
        "onions"             # → quantity 1.0, unit "unit"

    Lines starting with ``#`` and blank lines are ignored. Item names are
    canonicalised via ``shopstack.domain.resolve_canonical``
    so Hinglish / regional aliases map to the same canonical name used by
    the market snapshots.
    """
    from shopstack.domain import resolve_canonical

    items: list[dict[str, Any]] = []
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        m = _BASKET_LINE_RE.match(line)
        if m:
            qty = float(m.group(1))
            unit = (m.group(2) or "unit").lower()
            name = m.group(3).strip()
        else:
            qty = 1.0
            unit = "unit"
            name = line

        canonical = resolve_canonical(name) or name.lower().strip().replace(" ", "_")
        items.append({
            "canonical_name": canonical,
            "requested_quantity": qty,
            "unit": unit,
        })

    return items


# ─── HTML rendering ───────────────────────────────────────────────────────


def _savings_callout(comparison: BasketComparison) -> str:
    if not comparison.cheapest_source_id:
        return ""
    if comparison.total_savings_inr <= 0:
        return home_card(
            style="margin-bottom:12px;",
            body=(
                f"<h3 style='margin:0 0 4px 0;'>Basket Comparison</h3>"
                f"<div style='font-size: 0.8125rem;'>All loaded sources price this basket within ₹0–₹10 of each other."
                f"</div>"
            ),
        )
    label = SOURCE_LABELS.get(
        comparison.cheapest_source_id, comparison.cheapest_source_id.title()
    )
    return home_card(
        style="margin-bottom:12px;",
        body=(
            f"<h3 style='margin:0 0 4px 0;'>Basket Comparison</h3>"
            f"<div style='font-size: 0.875rem;'><strong>Cheapest:</strong> {escape(label)} · "
            f"<strong>Save up to:</strong> <span style='color:var(--green);font-weight:600;'>"
            f"₹{comparison.total_savings_inr:.0f} ({comparison.savings_pct:.0f}%)</span></div>"
            f"<div style='font-size: 0.6875rem;color:var(--text-dim);margin-top:4px;'>{comparison.matched_count}/{comparison.total_requested} items matched across sources"
            f"</div>"
        ),
    )


def _source_totals_row(comparison: BasketComparison) -> str:
    if not comparison.per_source:
        return ""
    parts = ["<div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;'>"]
    for s in comparison.per_source:
        if not s.line_totals:
            continue
        is_cheapest = s.source_id == comparison.cheapest_source_id
        border = "var(--green)" if is_cheapest else "var(--border)"
        bg = "rgba(74,222,128,0.06)" if is_cheapest else "var(--card-bg, transparent)"
        stale_badge = (
            " <span style='color:var(--red);font-size: 0.625rem;'>· stale</span>"
            if s.is_stale
            else ""
        )
        parts.append(
            f"<div style='flex:1;min-width:140px;padding:10px;border:2px solid {border};border-radius:6px;background:{bg};'>"
            f"<div style='font-size: 0.6875rem;color:var(--text-dim);'>{escape(s.label)}</div><div style='font-size: 1.25rem;font-weight:600;'>₹{s.basket_total:.0f}</div>"
            f"<div style='font-size: 0.625rem;color:var(--text-dim);'>{s.coverage_pct:.0f}% covered · {len(s.line_totals)} items"
            f"{stale_badge}</div></div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _line_rows(comparison: BasketComparison) -> str:
    parts: list[str] = []
    n_sources = len(comparison.per_source)
    for line in comparison.per_item:
        if not line.line_totals:
            unavail = ", ".join(escape(s) for s in line.unavailable_at) or "any source"
            parts.append(
                f"<tr><td style='padding:6px;'>"
                f"{escape(line.canonical_name.replace('_', ' ').title())}<br><span style='font-size: 0.625rem;color:var(--text-dim);'>"
                f"{line.requested_quantity:.1f} {escape(line.unit)}</span></td><td colspan='{n_sources}' style='padding:6px;color:var(--text-dim);'>"
                f"not available at {unavail}</td></tr>"
            )
            continue

        cells: list[str] = []
        cheapest = line.cheapest_source
        for s in comparison.per_source:
            if s.source_id in line.line_totals:
                p = line.line_totals[s.source_id]
                if s.source_id == cheapest:
                    cells.append(
                        f"<td style='padding:6px;color:var(--green);font-weight:600;text-align:right;'>₹{p:.0f}</td>"
                    )
                else:
                    cells.append(
                        f"<td style='padding:6px;text-align:right;'>₹{p:.0f}</td>"
                    )
            else:
                cells.append(
                    "<td style='padding:6px;color:var(--text-dim);text-align:right;'>--</td>"
                )

        savings_html = ""
        if line.cheapest_total is not None and line.worst_total is not None and len(line.line_totals) > 1:
            diff = line.worst_total - line.cheapest_total
            if diff > 0:
                savings_html = (
                    f"<br><span style='color:var(--green);font-size: 0.625rem;'>save ₹{diff:.0f}</span>"
                )

        parts.append(
            f"<tr><td style='padding:6px;'>"
            f"<strong>{escape(line.canonical_name.replace('_', ' ').title())}</strong><br><span style='font-size: 0.625rem;color:var(--text-dim);'>"
            f"{line.requested_quantity:.1f} {escape(line.unit)}</span>{savings_html}</td>"
            f"{''.join(cells)}</tr>"
        )
    return "".join(parts)


def _freshness_footer(comparison: BasketComparison) -> str:
    stale = [s for s in comparison.per_source if s.is_stale]
    if not stale:
        return ""
    names = ", ".join(escape(s.label) for s in stale)
    return (
        f"<div style='font-size: 0.625rem;color:var(--red);margin-top:8px;'>⚠️ Snapshot data may be outdated for: {names}. "
        f"Verify prices before checkout.</div>"
    )


def render_basket_comparison_html(comparison: BasketComparison) -> str:
    """Render a ``BasketComparison`` as HTML for a Gradio ``HTML`` component.

    Output is XSS-safe: all user / data-derived content is passed through
    ``html.escape``. Layout uses the same ``home-card`` class and CSS
    variables as the rest of the dashboard.
    """
    if not comparison.has_any_data:
        return home_card(
            style="text-align:center;padding:20px;",
            body=(
                "No market sources loaded. Capture or import data for at least one "
                "source (Swiggy, Blinkit, Zepto, DMart) to compare baskets."
            ),
        )

    if not comparison.per_item:
        return home_card(
            style="text-align:center;padding:20px;",
            body="Enter at least one item to compare.",
        )

    if not comparison.is_meaningful:
        loaded = ", ".join(escape(s) for s in comparison.source_ids) or "none"
        return home_card(
            style="text-align:center;padding:20px;",
            body=(
                "Basket comparison needs at least 2 sources with matching data. "
                f"Currently loaded: {loaded}. "
                "Capture another source's snapshot to enable side-by-side totals."
            ),
        )

    header_cells = "".join(
        f"<th style='padding:6px;text-align:right;font-size: 0.6875rem;color:var(--text-dim);'>{escape(s.label)}</th>"
        for s in comparison.per_source
    )
    table = home_card(
        body=(
            f"<table style='width:100%;border-collapse:collapse;font-size: 0.75rem;'>"
            f"<thead><tr style='border-bottom:2px solid var(--border);'><th style='text-align:left;padding:6px;'>Item</th>"
            f"{header_cells}</tr></thead>"
            f"<tbody>{_line_rows(comparison)}</tbody></table>"
        ),
    )

    return (
        _savings_callout(comparison)
        + _source_totals_row(comparison)
        + table
        + _freshness_footer(comparison)
    )


__all__ = [
    "BasketLine",
    "SourceBasket",
    "BasketComparison",
    "SOURCE_LABELS",
    "compare_basket_across_sources",
    "parse_basket_input",
    "render_basket_comparison_html",
    "_normalize_unit_to_grams",
    "_line_total_for_record",
    "_best_line_total",
]
