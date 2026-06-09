from __future__ import annotations

import logging
from html import escape

from shopstack.market.schema import NormalizedMarketRecord
from shopstack.ui.screens._utils import safe_render, source_freshness_html


logger = logging.getLogger(__name__)


def _market_freshness_html(snapshot) -> str:
    return source_freshness_html("swiggy")


@safe_render
def swiggy_market_view() -> str:
    from shopstack.market import compute_snapshot_analytics
    from shopstack.market.sources.swiggy import load_snapshot

    try:
        snapshot = load_snapshot()
    except FileNotFoundError:
        return "<div style='color:var(--text-dim);'>Swiggy data not found. Place snapshot files in data/ directory.</div>"

    analytics = compute_snapshot_analytics(snapshot)

    parts: list[str] = []

    parts.append(
        f"<div class='home-card' style='text-align:left;margin-bottom:12px;'>"
        f"<h3>Swiggy Fresh Vegetables \u2014 {snapshot.captured_at}</h3>"
        f"{_market_freshness_html(snapshot)}"
        f"<div style='display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;'>"
        f"<div><strong>{analytics['total']}</strong> items</div>"
        f"<div style='color:#22c55e;'><strong>{analytics['available']}</strong> available</div>"
        f"<div style='color:#ef4444;'><strong>{analytics['sold_out']}</strong> sold out</div>"
        f"<div><strong>{analytics['combos']}</strong> combos</div>"
        f"<div>Avg: <strong>&#8377;{analytics['avg_price']}</strong></div>"
        f"<div>Median: <strong>&#8377;{analytics['median_price']}</strong></div>"
        f"<div>Avg discount: <strong>{analytics['avg_discount']}%</strong></div>"
        f"</div></div>"
    )

    bv = analytics.get("best_value_by_canonical", {})
    if bv:
        weight_records = [
            r for r in snapshot.normalized_records
            if r.is_weight_based and r.price_per_kg and not r.is_combo
        ]
        def _ppa_key(r: NormalizedMarketRecord) -> float:
            v = r.price_per_kg
            return v if v is not None else 0.0
        sorted_by_ppkg = sorted(weight_records, key=_ppa_key)

        rows: list[str] = []
        for r in sorted_by_ppkg[:20]:
            avail_badge = "<span style='color:#22c55e;'>&#10003;</span>" if r.is_available else "<span style='color:#ef4444;'>&#10007;</span>"
            meta = get_produce_meta_inline(r.canonical_name)
            risk_badge = ""
            if meta and meta.waste_risk == "high":
                risk_badge = " <span style='color:#f59e0b;font-size:10px;'>&#9888; high waste risk</span>"
            rows.append(
                f"<tr>"
                f"<td>{escape(r.canonical_name.replace('_', ' ').title())}{risk_badge}</td>"
                f"<td>&#8377;{r.price_per_kg:.0f}</td>"
                f"<td>{escape(r.raw_size)}</td>"
                f"<td>&#8377;{r.price_inr:.0f}</td>"
                f"<td>{avail_badge}</td>"
                f"<td>{r.computed_discount_percent:.0f}%</td>"
                f"</tr>"
            )

        parts.append(
            f"<div class='home-card' style='text-align:left;margin-bottom:12px;'>"
            f"<h3>Best Value by Price/kg <span style='font-weight:normal;font-size:12px;color:var(--text-dim);'>(available first, weight-based only)</span></h3>"
            f"<table style='width:100%;border-collapse:collapse;font-size:12px;'>"
            f"<thead><tr style='border-bottom:2px solid var(--border);'>"
            f"<th style='text-align:left;padding:4px;'>Item</th>"
            f"<th style='text-align:right;padding:4px;'>&#8377;/kg</th>"
            f"<th style='text-align:left;padding:4px;'>Size</th>"
            f"<th style='text-align:right;padding:4px;'>Price</th>"
            f"<th style='text-align:center;padding:4px;'>Avail</th>"
            f"<th style='text-align:right;padding:4px;'>Off</th>"
            f"</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            f"</table></div>"
        )

    sold_out = [r for r in snapshot.normalized_records if not r.is_available and not r.is_combo]
    if sold_out:
        sold_out_names = sorted(set(r.canonical_name.replace("_", " ").title() for r in sold_out))
        parts.append(
            f"<div class='home-card' style='text-align:left;margin-bottom:12px;'>"
            f"<h3>Sold Out ({len(sold_out_names)} items)</h3>"
            f"<div style='font-size:11px;color:var(--text-dim);'>"
            f"{', '.join(escape(n) for n in sold_out_names[:30])}"
            f"</div></div>"
        )

    return "".join(parts) if parts else "<div style='color:var(--text-dim);'>No market data available.</div>"


@safe_render
def swiggy_basket_estimate(items_text: str) -> str:
    from shopstack.market import basket_summary, build_basket
    from shopstack.market.metadata import get_produce_metadata
    from shopstack.market.sources.swiggy import load_snapshot

    if not items_text.strip():
        return "<div style='color:var(--text-dim);'>Enter items above (one per line).</div>"

    try:
        snapshot = load_snapshot()
    except FileNotFoundError:
        return "<div style='color:var(--text-dim);'>Swiggy data not found.</div>"

    items = [line.strip() for line in items_text.strip().split("\n") if line.strip()]
    basket = build_basket(items, snapshot)
    summary = basket_summary(basket)

    parts: list[str] = []

    parts.append(
        f"<div style='margin-bottom:12px;'>"
        f"<strong>{summary['matched']}</strong> of {summary['total_requested']} matched "
        f"&mdash; estimated total: <strong>&#8377;{summary['total_estimated_price_inr']}</strong>"
        f"{_market_freshness_html(snapshot)}"
        f"</div>"
    )

    rows: list[str] = []
    for item in basket:
        if item.matched and item.recommended_record:
            r = item.recommended_record
            meta = get_produce_metadata(r.canonical_name)
            shelf = f"{meta.shelf_life_days}d" if meta else "?"
            risk = meta.waste_risk if meta else ""
            risk_color = {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e"}.get(risk, "var(--text-dim)")
            pkgkg = f"&#8377;{r.price_per_kg:.0f}/kg" if r.price_per_kg else f"&#8377;{r.price_per_piece:.0f}/pc" if r.price_per_piece else ""
            rows.append(
                f"<tr>"
                f"<td>{escape(item.requested_name)}</td>"
                f"<td>{escape(r.canonical_name.replace('_',' ').title())}</td>"
                f"<td>{escape(r.raw_size)}</td>"
                f"<td>&#8377;{r.price_inr:.0f}</td>"
                f"<td>{pkgkg}</td>"
                f"<td style='color:{risk_color};'>{shelf}</td>"
                f"</tr>"
            )
        elif item.matched:
            rows.append(
                f"<tr style='color:var(--text-dim);'>"
                f"<td>{escape(item.requested_name)}</td>"
                f"<td>{escape(item.canonical_name.replace('_',' ').title())}</td>"
                f"<td colspan='4'>{escape(item.reason)}</td>"
                f"</tr>"
            )
        else:
            rows.append(
                f"<tr style='color:#ef4444;'>"
                f"<td>{escape(item.requested_name)}</td>"
                f"<td colspan='5'>Not found in market data</td>"
                f"</tr>"
            )

    parts.append(
        f"<table style='width:100%;border-collapse:collapse;font-size:12px;'>"
        f"<thead><tr style='border-bottom:2px solid var(--border);'>"
        f"<th style='text-align:left;padding:4px;'>Requested</th>"
        f"<th style='text-align:left;padding:4px;'>Matched</th>"
        f"<th style='text-align:left;padding:4px;'>Size</th>"
        f"<th style='text-align:right;padding:4px;'>Price</th>"
        f"<th style='text-align:right;padding:4px;'>Unit</th>"
        f"<th style='text-align:right;padding:4px;'>Shelf</th>"
        f"</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        f"</table>"
    )

    unmatched = summary.get("unmatched_items", [])
    if unmatched:
        parts.append(
            f"<div style='margin-top:8px;color:#ef4444;font-size:11px;'>"
            f"Not found: {', '.join(escape(u) for u in unmatched)}"
            f"</div>"
        )

    return "".join(parts)


def get_produce_meta_inline(canonical_name: str):
    from shopstack.market.metadata import get_produce_metadata
    return get_produce_metadata(canonical_name)
