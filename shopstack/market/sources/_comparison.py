from __future__ import annotations

from dataclasses import dataclass
from html import escape
from typing import Any

from shopstack.market.sources._registry import SourceRegistry
from shopstack.ui.components.primitives import home_card


@dataclass
class CrossSourcePrice:
    canonical_name: str
    prices: dict[str, float]
    best_source: str
    savings_pct: float


def _best_weight_option(records: list[Any]) -> float | None:
    candidates = [
        r for r in records
        if not r.is_combo and r.is_available and r.price_per_kg is not None
    ]
    if not candidates:
        candidates = [
            r for r in records
            if not r.is_combo and r.is_available
        ]
        if not candidates:
            return None
        return min(r.price_inr for r in candidates)
    return min(r.price_per_kg for r in candidates)


def compare_across_sources(
    registry: SourceRegistry,
    canonical_name: str,
) -> CrossSourcePrice | None:
    snapshots = registry.all_snapshots()
    if not snapshots:
        return None

    prices: dict[str, float] = {}
    for source_id, snap in snapshots.items():
        records = [
            r for r in snap.normalized_records
            if r.canonical_name == canonical_name
        ]
        if not records:
            continue
        best = _best_weight_option(records)
        if best is not None:
            prices[source_id] = best

    if len(prices) < 2:
        return None

    best_source = min(prices, key=lambda s: prices[s])
    worst_source = max(prices, key=lambda s: prices[s])
    best_price = prices[best_source]
    worst_price = prices[worst_source]
    savings_pct = round((worst_price - best_price) / worst_price * 100) if worst_price > 0 else 0

    return CrossSourcePrice(
        canonical_name=canonical_name,
        prices=prices,
        best_source=best_source,
        savings_pct=savings_pct,
    )


def format_cross_source_html(comparisons: list[CrossSourcePrice]) -> str:
    if not comparisons:
        return ""

    source_ids: set[str] = set()
    for c in comparisons:
        source_ids.update(c.prices.keys())
    sorted_sources = sorted(source_ids)

    header_cells = "".join(
        f"<th style='text-align:right;padding:4px;'>{escape(s.title())}</th>"
        for s in sorted_sources
    )

    rows: list[str] = []
    for c in comparisons:
        name_label = escape(c.canonical_name.replace("_", " ").title())
        price_cells = ""
        for sid in sorted_sources:
            price = c.prices.get(sid)
            if price is None:
                price_cells += "<td style='text-align:right;padding:4px;color:var(--text-dim);'>--</td>"
            elif sid == c.best_source:
                price_cells += f"<td style='text-align:right;padding:4px;color:var(--green);font-weight:600;'>&#8377;{price:.0f}</td>"
            else:
                price_cells += f"<td style='text-align:right;padding:4px;'>&#8377;{price:.0f}</td>"

        savings_label = f"save {c.savings_pct}%" if c.savings_pct > 0 else ""
        rows.append(
            f"<tr><td style='padding:4px;'><strong>{name_label}</strong></td>"
            f"{price_cells}<td style='padding:4px;color:var(--green);'>{savings_label}</td>"
            f"</tr>"
        )

    return home_card(
        style="text-align:left;margin-bottom:12px;",
        body=(
            f"<h3>Multi-Source Price Comparison</h3>"
            f"<table style='width:100%;border-collapse:collapse;font-size: 0.75rem;'><thead><tr style='border-bottom:2px solid var(--border);'>"
            f"<th style='text-align:left;padding:4px;'>Item</th>{header_cells}"
            f"<th style='text-align:left;padding:4px;'>Savings</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        ),
    )


__all__ = ["CrossSourcePrice", "compare_across_sources", "format_cross_source_html"]
