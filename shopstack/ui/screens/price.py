from __future__ import annotations

import logging
from html import escape
import pandas as pd

import gradio as gr

from shopstack.app_context import db
from shopstack.ui import build_price_memory_view
from shopstack.ui.screens._utils import safe_render

logger = logging.getLogger(__name__)


def _market_freshness_html(snapshot) -> str:
    """Generate freshness badge HTML for Swiggy market snapshot."""
    from shopstack.market.sources.swiggy import snapshot_freshness

    freshness = snapshot_freshness(snapshot)
    color = "#ef4444" if freshness["is_stale"] else "var(--text-dim)"
    prefix = "Market data may be stale" if freshness["is_stale"] else "Market snapshot"
    return (
        f"<div style='font-size:11px;color:{color};margin-top:4px;'>"
        f"{escape(prefix)}: {escape(freshness['label'])}. Prices and availability are point-in-time signals."
        f"</div>"
    )


@safe_render
def price_memory_view(item_name: str = ""):
    """Price memory view - delegates to view builder and returns Gradio-compatible updates."""
    from html import escape
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
    """Price intelligence view - compares stores, detects price drops, finds best value."""
    from html import escape
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
                    f"(&#8377;{best_up:.2f}/unit) vs {escape(worst_store)} (&#8377;{worst_up:.2f}) "
                    f"&#8212; save {savings_pct}%"
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
                        f"(&#8377;{older.price:.0f} &#8594; &#8377;{recent.price:.0f}) "
                        f"&#8212; good time to buy"
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
    if not html_parts:
        return "<div style='color:var(--text-dim);'>No price intelligence yet. Add more price observations across stores to see comparisons.</div>"
    return "".join(html_parts)