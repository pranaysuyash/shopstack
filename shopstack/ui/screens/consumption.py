"""Consumption logging screen — quick-tap interface for tracking what you use.

Provides:
  - Active inventory list with one-click consume buttons
  - Batch consumption with context (meal, wasted, expired)
  - Consumption rate summary per item
  - Recent consumption history
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from html import escape
from typing import Any

from shopstack.app_context import db, tools, current_user_id
from shopstack.ui.screens._utils import safe_render
from shopstack.ui.components.cards import card as ui_card

logger = logging.getLogger(__name__)

__all__ = [
    "consumption_dashboard",
    "quick_consume",
    "batch_consume_with_context",
    "consumption_history",
    "consumption_rates",
]

_MEAL_CONTEXTS = ("breakfast", "lunch", "dinner", "snack", "other")


def _active_inventory_rows(uid: str) -> list[dict[str, Any]]:
    """Return active inventory items as lightweight dicts."""
    items = db.get_inventory(user_id=uid)
    locations = {loc.location_id: loc.name for loc in db.get_locations()}
    rows = []
    for lot in items:
        if lot.status not in ("active", "low"):
            continue
        rows.append({
            "lot_id": lot.lot_id,
            "canonical_name": lot.canonical_name,
            "display_name": lot.display_name,
            "quantity": lot.quantity,
            "unit": lot.unit,
            "status": lot.status,
            "location": locations.get(lot.storage_location_id, lot.storage_location_id or ""),
            "purchase_date": lot.purchase_date.isoformat() if lot.purchase_date else "",
        })
    return rows


def _render_quick_consume_grid(items: list[dict[str, Any]]) -> str:
    """Render inventory items as a grid of consume buttons."""
    if not items:
        return (
            "<div class='home-card' style='text-align:center;padding:20px;color:var(--text-dim);'>"
            "No active inventory. Add purchases to start tracking consumption."
            "</div>"
        )

    rows_html = ""
    for item in items:
        name = escape(item["display_name"])
        qty = item["quantity"]
        unit = escape(item["unit"])
        lot_id = escape(item["lot_id"])
        status = item["status"]
        status_color = "var(--amber)" if status == "low" else "var(--text-dim)"
        loc = escape(item.get("location", ""))

        qty_display = f"{qty:.1f} {unit}" if qty != int(qty) else f"{int(qty)} {unit}"

        # onclick uses the Gradio API endpoint
        rows_html += (
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding:6px 0;border-bottom:1px solid var(--border);'>"
            f"<div>"
            f"<strong>{name}</strong> "
            f"<span style='font-size:11px;color:{status_color};'>({qty_display})</span>"
            f" <span style='font-size:10px;color:var(--text-dim);'>{loc}</span>"
            f"</div>"
            f"<div style='display:flex;gap:4px;'>"
            f"<button onclick=\"_shopstack_consume('{lot_id}', 0.5)\" "
            f"style='font-size:10px;padding:2px 8px;border:1px solid var(--border);"
            f"border-radius:3px;cursor:pointer;background:none;'>½</button>"
            f"<button onclick=\"_shopstack_consume('{lot_id}', 1)\" "
            f"style='font-size:10px;padding:2px 8px;border:1px solid var(--blue);"
            f"border-radius:3px;cursor:pointer;background:none;color:var(--blue);'>Use 1</button>"
            f"<button onclick=\"_shopstack_consume('{lot_id}', {qty})\" "
            f"style='font-size:10px;padding:2px 8px;border:1px solid var(--red);"
            f"border-radius:3px;cursor:pointer;background:none;color:var(--red);'>All</button>"
            f"</div></div>"
        )

    return (
        "<div class='home-card'><h4>Quick Consume</h4>"
        "<div style='font-size:11px;color:var(--text-dim);margin-bottom:8px;'>"
        "Tap to log what you use.</div>"
        f"{rows_html}</div>"
    )


def _render_recent_events(events: list[Any]) -> str:
    """Render recent consumption events as a timeline."""
    if not events:
        return "<div class='home-card'>No consumption history yet.</div>"

    rows = []
    for ev in events[:20]:
        name = escape(ev.canonical_name.replace("_", " ").title())
        action = escape(ev.action)
        delta = ev.quantity_delta or 0
        ts = ev.timestamp[:16] if ev.timestamp else ""
        source = escape(ev.source or "")
        sign = "-" if delta < 0 else "+"
        color = "var(--red)" if delta < 0 else "var(--green)"
        rows.append(
            f"<div style='display:flex;justify-content:space-between;padding:3px 0;"
            f"border-bottom:1px solid var(--border);font-size:12px;'>"
            f"<div><strong>{name}</strong> "
            f"<span style='color:{color};'>{sign}{abs(delta):.1f}</span></div>"
            f"<div><span style='color:var(--text-dim);'>{action}</span> "
            f"<span style='font-size:10px;color:var(--text-dim);'>{ts}</span></div>"
            f"</div>"
        )

    return (
        "<div class='home-card'><h4>Recent Consumption</h4>"
        + "".join(rows) + "</div>"
    )


def _compute_consumption_rates(uid: str) -> list[dict[str, Any]]:
    """Compute consumption rates from inventory events."""
    events = db.get_inventory_events(limit=500)
    consumed_by_name: dict[str, list[Any]] = {}
    for ev in events:
        if ev.action != "consumed" or not ev.canonical_name:
            continue
        consumed_by_name.setdefault(ev.canonical_name, []).append(ev)

    rates = []
    for cname, evts in consumed_by_name.items():
        if len(evts) < 2:
            continue
        total_consumed = sum(abs(e.quantity_delta or 0) for e in evts)
        dates = sorted(e.timestamp[:10] for e in evts if e.timestamp)
        if len(dates) < 2:
            continue
        first_date = dates[0]
        last_date = dates[-1]
        try:
            span = (date.fromisoformat(last_date) - date.fromisoformat(first_date)).days
        except ValueError:
            continue
        if span <= 0:
            continue
        daily_rate = total_consumed / span
        rates.append({
            "canonical_name": cname,
            "display_name": cname.replace("_", " ").title(),
            "total_consumed": round(total_consumed, 2),
            "days_tracked": span,
            "daily_rate": round(daily_rate, 3),
            "events": len(evts),
        })

    rates.sort(key=lambda r: r["daily_rate"], reverse=True)
    return rates


@safe_render
def consumption_dashboard() -> tuple[str, str, str]:
    """Return (quick_consume_grid, recent_history, rates_summary)."""
    uid = current_user_id()
    items = _active_inventory_rows(uid)
    grid_html = _render_quick_consume_grid(items)

    events = db.get_inventory_events(limit=30)
    history_html = _render_recent_events(events)

    rates = _compute_consumption_rates(uid)
    if rates:
        rate_rows = []
        for r in rates[:15]:
            name = escape(r["display_name"])
            rate = r["daily_rate"]
            total = r["total_consumed"]
            days = r["days_tracked"]
            rate_rows.append(
                f"<div style='display:flex;justify-content:space-between;padding:3px 0;"
                f"border-bottom:1px solid var(--border);font-size:12px;'>"
                f"<strong>{name}</strong>"
                f"<span>{rate:.2f}/day ({total:.1f} over {days}d)</span>"
                f"</div>"
            )
        rates_html = (
            "<div class='home-card'><h4>Consumption Rates</h4>"
            "<div style='font-size:11px;color:var(--text-dim);margin-bottom:6px;'>"
            "Average daily usage based on consumption history.</div>"
            + "".join(rate_rows) + "</div>"
        )
    else:
        rates_html = (
            "<div class='home-card'>No consumption rate data yet. "
            "Log consumption to start tracking rates.</div>"
        )

    return grid_html, history_html, rates_html


@safe_render
def quick_consume(lot_id: str, qty: float) -> str:
    """Consume a quantity from a lot and return status HTML."""
    if not lot_id or not lot_id.strip():
        return "<div style='color:var(--red);'>No lot ID provided.</div>"
    if qty <= 0:
        return "<div style='color:var(--red);'>Quantity must be positive.</div>"

    uid = current_user_id()
    result = tools.consume_inventory_item(lot_id.strip(), qty, user_id=uid)
    if "error" in result:
        return f"<div style='color:var(--red);'>{escape(str(result['error']))}</div>"

    remaining = result.get("remaining", 0)
    name = result.get("canonical_name", lot_id[:8]).replace("_", " ").title()
    return (
        f"<div style='color:var(--green);'>"
        f"Consumed {escape(str(qty))} of {escape(name)}. "
        f"Remaining: {escape(str(remaining))}</div>"
    )


@safe_render
def batch_consume_with_context(lines_text: str, meal_context: str, is_waste: str) -> str:
    """Batch consume with context tracking.

    Args:
        lines_text: One entry per line: ``lot_id:qty`` or just ``lot_id``
        meal_context: One of breakfast/lunch/dinner/snack/other
        is_waste: ``"waste"`` to mark as waste, anything else for normal consumption
    """
    if not lines_text or not lines_text.strip():
        return "<div style='color:var(--text-dim);'>Add at least one entry.</div>"

    uid = current_user_id()
    is_waste_flag = (is_waste or "").strip().lower() == "waste"
    meal = (meal_context or "other").strip().lower()
    if meal not in _MEAL_CONTEXTS:
        meal = "other"

    entries = [line.strip() for line in lines_text.strip().splitlines() if line.strip()]
    summary = []
    for entry in entries:
        lot_id, _, qty_text = entry.partition(":")
        try:
            qty = float(qty_text.strip()) if qty_text.strip() else 1.0
        except ValueError:
            qty = 1.0
        lot_id = lot_id.strip()
        if not lot_id:
            continue

        result = tools.consume_inventory_item(lot_id, qty, user_id=uid)
        if "error" in result:
            summary.append(f"{escape(lot_id)}: error — {escape(str(result['error']))}")
        else:
            name = result.get("canonical_name", lot_id[:8]).replace("_", " ").title()
            remaining = result.get("remaining", 0)
            summary.append(f"{escape(name)}: consumed {qty:.1f}, remaining {remaining:.1f}")

    if not summary:
        return "<div style='color:var(--red);'>No valid entries.</div>"

    ctx_label = " (wasted)" if is_waste_flag else f" ({meal})"
    return (
        f"<div style='margin-top:8px;line-height:1.6;font-size:12px;'>"
        f"<div style='color:var(--text-dim);margin-bottom:4px;'>Context: {escape(meal)}"
        f"{', marked as waste' if is_waste_flag else ''}</div>"
        + "<br>".join(summary) + "</div>"
    )


@safe_render
def consumption_history(canonical_name: str) -> str:
    """Show consumption history for a specific item."""
    canonical_name = (canonical_name or "").strip().lower()
    if not canonical_name:
        events = db.get_inventory_events(limit=30)
    else:
        events = db.get_inventory_events(canonical_name=canonical_name, limit=30)

    return _render_recent_events(events)


@safe_render
def consumption_rates() -> str:
    """Return consumption rate summary HTML."""
    uid = current_user_id()
    rates = _compute_consumption_rates(uid)

    if not rates:
        return "<div class='home-card'>No consumption rate data available.</div>"

    rate_rows = []
    for r in rates[:20]:
        name = escape(r["display_name"])
        rate = r["daily_rate"]
        total = r["total_consumed"]
        days = r["days_tracked"]
        rate_rows.append(
            f"<div style='display:flex;justify-content:space-between;padding:4px 0;"
            f"border-bottom:1px solid var(--border);'>"
            f"<strong>{name}</strong>"
            f"<span style='font-size:12px;'>"
            f"{rate:.2f}/day ({total:.1f} over {days}d, {r['events']} events)</span>"
            f"</div>"
        )

    return (
        "<div class='home-card'><h4>Consumption Rates</h4>"
        + "".join(rate_rows) + "</div>"
    )
