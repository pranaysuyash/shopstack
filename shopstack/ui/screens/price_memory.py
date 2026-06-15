from __future__ import annotations

import logging
from datetime import date
from html import escape

import gradio as gr
import pandas as pd

from shopstack.app_context import db, current_user_id
from shopstack.schemas.models import PriceObservation
from shopstack.ui.views import build_price_memory_view  # noqa: E402 — deferred to avoid circular import via shopstack.ui.screens.__init__
from shopstack.ui.screens._utils import safe_render


logger = logging.getLogger(__name__)


@safe_render
def price_memory_view(item_name: str = ""):
    """Price memory view — shows price history, unit prices, and chart data for a given item."""
    view = build_price_memory_view(db, item_name, user_id=current_user_id())
    has_data = view.observation_count > 0
    unit_plot_df = view.df[["date", "unit_price"]].dropna() if has_data else pd.DataFrame(columns=["date", "unit_price"])
    return (
        view.summary_html,
        gr.update(value=view.df, visible=has_data),
        gr.update(value=unit_plot_df, visible=len(unit_plot_df) > 0),
        view.table,
    )


@safe_render
def price_intelligence_view() -> str:
    """Price intelligence view — store comparisons, deal scoring, price drops, best store."""
    from shopstack.services.price_memory import PriceMemoryService

    service = PriceMemoryService(db)

    # Collect all canonical names with observations
    all_names: set[str] = set()
    for row in db.conn.execute(
        "SELECT DISTINCT canonical_name FROM price_observations"
    ).fetchall():
        name = row["canonical_name"]
        if name:
            all_names.add(name)

    alerts: list[str] = []
    comparisons: list[str] = []
    deal_scores: list[str] = []

    for name in sorted(all_names):
        # Store comparison via service
        ranking = service.get_store_comparison(name)
        if ranking.store_prices and len(ranking.store_prices) >= 2:
            best = ranking.store_prices[0]
            worst = ranking.store_prices[-1]
            if ranking.spread_pct and ranking.spread_pct >= 5:
                ppk_label = ""
                if best.get("median_per_kg"):
                    ppk_label = f" (&#8377;{best['median_per_kg']:.0f}/kg)"
                as_of_label = ""
                if best.get("last_seen"):
                    as_of_label = f"<span style='color:var(--text-dim);font-size: 0.6875rem;'> &middot; as of {escape(best['last_seen'])}</span>"
                comparisons.append(
                    f"<div style='padding:6px 0;border-bottom:1px solid var(--border);'><strong>{escape(name)}</strong>: Best at {escape(best['store'])} "
                    f"(&#8377;{best['median_price']:.0f}{ppk_label}) vs {escape(worst['store'])} (&#8377;{worst['median_price']:.0f}) "
                    f"&mdash; save {ranking.spread_pct}%{as_of_label}</div>"
                )

        # Price drop detection from history
        history = service.get_history(name)
        if history.recent_prices and len(history.recent_prices) >= 2:
            sorted_prices = sorted(history.recent_prices, key=lambda p: p.get("date", ""))
            older = sorted_prices[0]
            recent = sorted_prices[-1]
            older_p = older.get("price_per_kg") or older.get("price", 0)
            recent_p = recent.get("price_per_kg") or recent.get("price", 0)
            if older_p > 0 and recent_p < older_p:
                drop_pct = round((older_p - recent_p) / older_p * 100)
                if drop_pct >= 5:
                    recent_date = recent.get("date")
                    as_of_label = (
                        f"<span style='color:var(--text-dim);font-size: 0.6875rem;'> &middot; as of {escape(str(recent_date))}</span>"
                        if recent_date else ""
                    )
                    alerts.append(
                        f"<div style='padding:6px 0;border-bottom:1px solid var(--border);'><strong>{escape(name)}</strong> price dropped {drop_pct}% "
                        f"(&#8377;{older_p:.0f} &#8594; &#8377;{recent_p:.0f}) &mdash; good time to buy{as_of_label}"
                        f"</div>"
                    )

        # Deal scoring against historical data
        summary = service.get_summary(name)
        if summary.last_price and summary.median_price and summary.observations >= 3:
            deal = service.score_deal(name, summary.last_price, per_kg=summary.normalized_per_kg)
            if deal.is_good_deal:
                deal_scores.append(
                    f"<div style='padding:6px 0;border-bottom:1px solid var(--border);'><strong>{escape(name)}</strong>: {escape(deal.reason)} "
                    f"<span style='color:var(--green);font-weight:600;'>[{deal.score.upper()}]</span></div>"
                )

    html_parts: list[str] = []

    if deal_scores:
        html_parts.append(
            "<div class='home-card' style='text-align:left;margin-bottom:12px;'>"
            "<h3>Top Deals Right Now</h3>"
            + "".join(deal_scores[:8])
            + "</div>"
        )
    if alerts:
        html_parts.append(
            "<div class='home-card' style='text-align:left;margin-bottom:12px;'>"
            "<h3>Price Drop Alerts</h3>"
            + "".join(alerts[:8])
            + "</div>"
        )
    if comparisons:
        html_parts.append(
            "<div class='home-card' style='text-align:left;margin-bottom:12px;'>"
            "<h3>Best Price Across Stores</h3>"
            + "".join(comparisons[:8])
            + "</div>"
        )

    # Best store recommendation across all tracked items
    if len(all_names) >= 2:
        best_store = service.get_best_store(list(all_names))
        if best_store.store:
            coverage = f"{best_store.coverage_pct:.0f}%" if best_store.total_items_compared > 0 else "N/A"
            savings = f"&#8377;{best_store.estimated_savings_vs_worst:.0f}" if best_store.estimated_savings_vs_worst > 0 else "N/A"
            html_parts.append(
                "<div class='home-card' style='text-align:left;margin-bottom:12px;'>"
                f"<h3>Best Store Overall</h3><div style='padding:8px;font-size: 0.875rem;'>"
                f"<strong>{escape(best_store.store)}</strong> has the best price for {best_store.items_with_best_price}/{best_store.total_items_compared} items "
                f"({coverage} coverage). Estimated savings vs worst store: {savings}.</div></div>"
            )

    # Cross-source comparison from market snapshots
    try:
        from shopstack.market.sources import (
            build_registry,
            CrossSourcePrice,
            compare_across_sources,
            format_cross_source_html,
            MarketSnapshotRepository,
        )

        _reg = build_registry(repository=MarketSnapshotRepository())
        snapshots = _reg.all_snapshots()
        if len(snapshots) >= 2:
            snap_names: set[str] = set()
            for snap in snapshots.values():
                for r in snap.normalized_records:
                    if r.is_available and not r.is_combo:
                        snap_names.add(r.canonical_name)
            cross_source: list[CrossSourcePrice] = []
            for snap_name in sorted(snap_names):
                c = compare_across_sources(_reg, snap_name)
                if c is not None:
                    cross_source.append(c)
            if cross_source:
                cross_source.sort(key=lambda c: c.savings_pct, reverse=True)
                html_parts.append(format_cross_source_html(cross_source[:10]))
    except Exception:
        logger.warning("Multi-source comparison not available", exc_info=True)

    if not html_parts:
        return "<div style='color:var(--text-dim);'>No price intelligence yet. Add more price observations across stores to see comparisons.</div>"
    return "".join(html_parts)


@safe_render
def seed_swiggy_prices() -> str:
    """Seed price_observations table from Swiggy snapshot data."""
    from shopstack.market.sources.swiggy import load_snapshot

    try:
        snapshot = load_snapshot()
    except FileNotFoundError:
        return "<div style='color:var(--text-dim);'>Swiggy data not found.</div>"

    existing = db.conn.execute(
        "SELECT COUNT(*) as cnt FROM price_observations WHERE store_name = 'Swiggy Instamart'"
    ).fetchone()["cnt"]
    if existing > 0:
        return f"<div style='color:var(--text-dim);'>Swiggy prices already seeded ({existing} records).</div>"

    count = 0
    for r in snapshot.normalized_records:
        if r.is_combo or not r.is_weight_based:
            continue
        if r.normalized_quantity and r.normalized_quantity > 0:
            obs = PriceObservation(
                canonical_name=r.canonical_name,
                quantity=r.normalized_quantity,
                unit=r.normalized_unit or "g",
                price=r.price_inr,
                currency="INR",
                store_name="Swiggy Instamart",
                observation_date=date.fromisoformat(r.captured_at[:10]),
                notes=f"From Swiggy snapshot {r.snapshot_id}, raw: {r.raw_name} ({r.raw_size})",
            )
            db.record_price(obs)
            count += 1

    return (
        f"<div style='color:var(--green);'>Seeded {count} price observations rom Swiggy Instamart ({snapshot.captured_at}). "
        f"Price Memory and Price Intelligence now have real data.</div>"
    )
