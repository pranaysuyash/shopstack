from __future__ import annotations

import logging
import re
from datetime import date
from html import escape

import gradio as gr
import pandas as pd

from shopstack.schemas.models import new_id
from shopstack.app_context import db, tools
from shopstack.ui import build_price_memory_view, load_field_notes, save_field_notes
from shopstack.ui.screens._utils import safe_render


logger = logging.getLogger(__name__)


def _market_freshness_html(snapshot) -> str:
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
    if not html_parts:
        return "<div style='color:var(--text-dim);'>No price intelligence yet. Add more price observations across stores to see comparisons.</div>"
    return "".join(html_parts)


@safe_render
def household_map_view() -> str:
    locations = db.get_locations()
    inventory = db.get_inventory()
    loc_counts: dict[str, int] = {}
    loc_items: dict[str, list[str]] = {}
    for l in inventory:
        lid = l.storage_location_id or "unknown"
        loc_counts[lid] = loc_counts.get(lid, 0) + 1
        loc_items.setdefault(lid, []).append(f"{l.display_name} ({l.quantity} {l.unit})")

    cards = ""
    for loc in locations:
        count = loc_counts.get(loc.location_id, 0)
        parent = loc.parent_location_id or ""
        item_list = loc_items.get(loc.location_id, [])
        item_details = item_list[:8]
        if len(item_list) > 8:
            item_details.append(f"... and {len(item_list) - 8} more")
        item_details_html = (
            "<div style='margin-top:8px;font-size:11px;color:var(--text-dim);'>"
            + "".join(f"<div>{escape(str(item))}</div>" for item in item_details)
            + "</div>"
            if item_details
            else "<div style='margin-top:8px;font-size:11px;color:var(--text-dim);'>No items stored here yet.</div>"
        )
        safe_name = escape(str(loc.name))
        safe_type = escape(str(loc.location_type))
        safe_parent = escape(str(parent))
        arrow = f" \u2192 {safe_parent}" if parent else ""
        cards += f"""
<div class="stat-card" style="text-align:left;margin-bottom:8px;">
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div>
      <div style="font-weight:600;color:var(--text);">{safe_name}</div>
      <div style="font-size:11px;color:var(--text-dim);">{safe_type}{arrow}</div>
    </div>
    <div class="stat-value" style="font-size:24px;">{count}</div>
  </div>
  {item_details_html}
</div>"""
    return f"<h3>Household Storage Map</h3><div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;'>{cards}</div>"


def create_household_location(name: str, parent_id: str, location_type: str) -> str:
    if not (name or "").strip():
        return "<div style='color:var(--red);'>Location name is required.</div>"
    normalized = re.sub(r"\s+", "_", name.strip().lower())
    normalized = re.sub(r"[^a-z0-9_-]", "", normalized)
    if not normalized:
        normalized = "loc"
    loc_id = f"{normalized}_{new_id()[:6]}"
    try:
        db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES (?, ?, ?, ?, '')",
            (loc_id, name.strip(), parent_id.strip() if parent_id else None, location_type or "shelf"),
        )
        db.conn.commit()
    except Exception as exc:
        return f"<div style='color:var(--red);'>Failed to create location: {escape(str(exc))}</div>"
    return f"<div style='color:var(--green);'>Created location {escape(name)}.</div>"


def move_inventory_to_location(lot_id_prefix: str, to_location_id: str) -> str:
    if not lot_id_prefix:
        return "<div style='color:var(--text-dim);'>Select a lot first.</div>"
    if not to_location_id:
        return "<div style='color:var(--red);'>Choose destination location.</div>"
    result = tools.move_inventory_item(lot_id_prefix, to_location_id)
    if "error" in result:
        return f"<div style='color:var(--red);'>Move failed: {escape(str(result['error']))}</div>"
    movement = result.get("movement", {})
    from_loc = movement.get("from_location_id") or "unknown"
    to_loc = movement.get("to", to_location_id)
    return f"<div style='color:var(--green);'>Moved item {escape(str(result.get('movement', {}).get('lot_id', '')))} from {escape(str(from_loc))} to {escape(str(to_loc))}.</div>"


def what_is_in_fridge_now() -> str:
    locations = {l.location_id: l for l in db.get_locations()}
    fridge_nodes = {
        lid for lid, loc in locations.items()
        if loc.location_id == "fridge" or loc.parent_location_id == "fridge" or loc.location_id.startswith("fridge_")
    }
    items = [
        i for i in db.get_inventory()
        if (i.storage_location_id in fridge_nodes)
    ]
    if not items:
        return "<div style='color:var(--text-dim);'>Fridge is empty right now.</div>"
    rows = "".join(
        f"<div style='display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);'>"
        f"<span>{escape(i.display_name)}</span>"
        f"<span>{escape(str(i.quantity))} {escape(i.unit)}</span></div>"
        for i in items
    )
    return f"<div class='home-card' style='text-align:left;'><h3>What's in the fridge now?</h3>{rows}</div>"


def inventory_alerts(days_since_purchase: int = 3) -> str:
    if days_since_purchase <= 0:
        days_since_purchase = 3
    low = [
        l for l in db.get_inventory()
        if l.quantity <= 0.5 or l.status == "low"
    ]
    stale = [
        l for l in db.get_inventory()
        if l.purchase_date and (date.today() - l.purchase_date).days >= days_since_purchase and l.quantity > 0
    ]

    today = date.today()
    expiring_today = []
    expiring_tomorrow = []
    for l in db.get_inventory(status="active"):
        ref = l.label_expiry_date or l.estimated_use_by_date
        if not ref:
            continue
        delta = (ref - today).days
        if delta == 0:
            expiring_today.append(l)
        elif delta == 1:
            expiring_tomorrow.append(l)

    if not low and not stale and not expiring_today and not expiring_tomorrow:
        return "<div style='color:var(--text-dim);'>No proactive alerts at this time.</div>"

    alerts = ""
    if expiring_today:
        alerts += "<div style='margin-bottom:8px;border-left:4px solid var(--red);padding-left:10px;'><strong style='color:var(--red);'>Expiring today!</strong><ul>"
        alerts += "".join(f"<li>{escape(l.display_name)} ({escape(str(l.quantity))} {escape(l.unit)})</li>" for l in expiring_today)
        alerts += "</ul></div>"
    if expiring_tomorrow:
        alerts += "<div style='margin-bottom:8px;border-left:4px solid var(--amber);padding-left:10px;'><strong style='color:var(--amber);'>Expiring tomorrow</strong><ul>"
        alerts += "".join(f"<li>{escape(l.display_name)} ({escape(str(l.quantity))} {escape(l.unit)})</li>" for l in expiring_tomorrow)
        alerts += "</ul></div>"
    if low:
        alerts += "<div style='margin-bottom:8px;'><strong>Reorder Candidates</strong><ul>"
        alerts += "".join(f"<li>{escape(i.display_name)}: only {escape(str(i.quantity))} {escape(i.unit)} left</li>" for i in low)
        alerts += "</ul></div>"
    if stale:
        alerts += "<div style='margin-bottom:8px;'><strong>Use soon reminders</strong><ul>"
        alerts += "".join(f"<li>{escape(l.display_name)}: last purchased {(date.today() - l.purchase_date).days if l.purchase_date else '?'} days ago</li>" for l in stale)
        alerts += "</ul></div>"
    return f"<div class='home-card' style='text-align:left'>{alerts}</div>"


def field_notes_view():
    view = load_field_notes(db)
    return view.editor_value, view.preview_value, view.status_html


def field_notes_save(note_text: str):
    view = save_field_notes(db, note_text)
    return view.editor_value, view.preview_value, view.status_html


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
        f"<h3>Swiggy Fresh Vegetables — {snapshot.captured_at}</h3>"
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
        sorted_by_ppkg = sorted(weight_records, key=lambda r: r.price_per_kg)

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

    from shopstack.schemas.models import PriceObservation
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
                observation_date=r.captured_at,
                notes=f"From Swiggy snapshot {r.snapshot_id}, raw: {r.raw_name} ({r.raw_size})",
            )
            db.record_price(obs)
            count += 1

    return (
        f"<div style='color:var(--green);'>Seeded {count} price observations "
        f"from Swiggy Instamart ({snapshot.captured_at}). "
        f"Price Memory and Price Intelligence now have real data.</div>"
    )


def get_produce_meta_inline(canonical_name: str):
    from shopstack.market.metadata import get_produce_metadata
    return get_produce_metadata(canonical_name)
