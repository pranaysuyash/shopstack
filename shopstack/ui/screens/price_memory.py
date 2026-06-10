from __future__ import annotations

import logging
from datetime import date
from html import escape

import gradio as gr
import pandas as pd

from shopstack.app_context import db
from shopstack.schemas.models import PriceObservation
from shopstack.ui.views import build_price_memory_view  # noqa: E402 — deferred to avoid circular import via shopstack.ui.screens.__init__
from shopstack.ui.screens._utils import safe_render


logger = logging.getLogger(__name__)


@safe_render
def price_memory_view(item_name: str = ""):
    """Price memory view — shows price history, unit prices, and chart data for a given item."""
    view = build_price_memory_view(db, item_name)
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
    """Price intelligence view — compares stores, detects price drops, finds best value."""
    latest_by_item: dict[str, dict] = {}
    for row in db.conn.execute(
        "SELECT canonical_name, store_name, price, quantity, unit, observation_date "
        "FROM price_observations ORDER BY observation_date DESC"
    ).fetchall():
        name = row["canonical_name"]
        if name not in latest_by_item:
            latest_by_item[name] = {
                "best_price": float(row["price"]),
                "best_store": row["store_name"] or "Unknown",
                "best_qty": float(row["quantity"]),
                "best_unit": row["unit"],
                "best_date": row["observation_date"],
                "all_prices": [(float(row["price"]), row["store_name"] or "Unknown", float(row["quantity"]), row["unit"])],
            }
        else:
            latest_by_item[name]["all_prices"].append(
                (float(row["price"]), row["store_name"] or "Unknown", float(row["quantity"]), row["unit"])
            )

    alerts: list[str] = []
    comparisons: list[str] = []

    for name, info in sorted(latest_by_item.items()):
        all_prices = info["all_prices"]
        if len(all_prices) < 2:
            continue

        unit_prices = []
        for price, store, qty, unit in all_prices:
            if qty > 0:
                up = price / qty
                if unit and unit.lower() in ("g", "gram", "grams", "gm"):
                    up = price / (qty / 1000)
                elif unit and unit.lower() in ("ml", "milliliter"):
                    up = price / (qty / 1000)
                unit_prices.append((round(up, 2), store, price))
        if len(unit_prices) < 2:
            continue

        unit_prices.sort()
        best_up, best_store, best_price = unit_prices[0]
        worst_up, worst_store, worst_price = unit_prices[-1]
        if best_up > 0 and worst_up > best_up:
            savings_pct = round((worst_up - best_up) / worst_up * 100)
            if savings_pct >= 5:
                comparisons.append(
                    f"<div style='padding:6px 0;border-bottom:1px solid var(--border);'>"
                    f"<strong>{escape(name)}</strong>: Best at {escape(best_store)} "
                    f"(\u20b9{best_up:.2f}/unit) vs {escape(worst_store)} (\u20b9{worst_up:.2f}) "
                    f"\u2014 save {savings_pct}%"
                    f"</div>"
                )

        history = db.get_price_history(name)
        if len(history) >= 2:
            sorted_hist = sorted(history, key=lambda o: o.observation_date)
            recent = sorted_hist[-1]
            older = sorted_hist[-2] if len(sorted_hist) >= 2 else None
            if older and recent.price < older.price:
                drop_pct = round((older.price - recent.price) / older.price * 100)
                if drop_pct >= 5:
                    alerts.append(
                        f"<div style='padding:6px 0;border-bottom:1px solid var(--border);'>"
                        f"<strong>{escape(name)}</strong> price dropped {drop_pct}% "
                        f"(\u20b9{older.price:.0f} \u2192 \u20b9{recent.price:.0f}) "
                        f"\u2014 good time to buy"
                        f"</div>"
                    )

    html_parts: list[str] = []
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
            all_names: set[str] = set()
            for snap in snapshots.values():
                for r in snap.normalized_records:
                    if r.is_available and not r.is_combo:
                        all_names.add(r.canonical_name)
            cross_source: list[CrossSourcePrice] = []
            for name in sorted(all_names):
                c = compare_across_sources(_reg, name)
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
        f"<div style='color:var(--green);'>Seeded {count} price observations "
        f"from Swiggy Instamart ({snapshot.captured_at}). "
        f"Price Memory and Price Intelligence now have real data.</div>"
    )


