from __future__ import annotations

import logging
import re
from datetime import date
from html import escape

from shopstack.schemas.models import new_id
from shopstack.app_context import db, tools, current_user_id
from shopstack.services.dashboard import clear_dashboard_cache
from shopstack.ui.components.decorators import aria_live_screen
from shopstack.ui.components.primitives import (
    item_row,
    stat_card,
    home_card,
)
from shopstack.ui.screens._utils import safe_render


logger = logging.getLogger(__name__)

@safe_render
def household_map_view() -> str:
    locations = db.get_locations()
    inventory = db.get_inventory(user_id=current_user_id())
    loc_counts: dict[str, int] = {}
    loc_items: dict[str, list[str]] = {}
    for lot in inventory:
        lid = lot.storage_location_id or "unknown"
        loc_counts[lid] = loc_counts.get(lid, 0) + 1
        loc_items.setdefault(lid, []).append(f"{lot.display_name} ({lot.quantity} {lot.unit})")

    cards = ""
    for loc in locations:
        count = loc_counts.get(loc.location_id, 0)
        parent = loc.parent_location_id or ""
        item_list = loc_items.get(loc.location_id, [])
        item_details = item_list[:8]
        if len(item_list) > 8:
            item_details.append(f"... and {len(item_list) - 8} more")
        item_details_html = (
            "<div style='margin-top:8px;font-size: 0.6875rem;color:var(--text-dim);'>"
            + "".join(f"<div>{escape(str(item))}</div>" for item in item_details)
            + "</div>"
            if item_details
            else "<div style='margin-top:8px;font-size: 0.6875rem;color:var(--text-dim);'>No items stored here yet.</div>"
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
      <div style="font-size: 0.6875rem;color:var(--text-dim);">{safe_type}{arrow}</div>
    </div>
    <div class="stat-value" style="font-size: 1.5rem;">{count}</div>
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


@aria_live_screen()
def move_inventory_to_location(lot_id_prefix: str, to_location_id: str) -> str:
    if not lot_id_prefix:
        return "<div style='color:var(--text-dim);'>Select a lot first.</div>"
    if not to_location_id:
        return "<div style='color:var(--red);'>Choose destination location.</div>"
    uid = current_user_id()
    result = tools.move_inventory_item(lot_id_prefix, to_location_id)
    if "error" in result:
        return f"<div style='color:var(--red);'>Move failed: {escape(str(result['error']))}</div>"
    movement = result.get("movement", {})
    from_loc = movement.get("from_location_id") or "unknown"
    to_loc = movement.get("to", to_location_id)
    clear_dashboard_cache(uid)
    return f"<div style='color:var(--green);'>Moved item {escape(str(result.get('movement', {}).get('lot_id', '')))} from {escape(str(from_loc))} to {escape(str(to_loc))}.</div>"


def what_is_in_fridge_now() -> str:
    locations = {loc.location_id: loc for loc in db.get_locations()}
    fridge_nodes = {
        lid for lid, loc in locations.items()
        if loc.location_id == "fridge" or loc.parent_location_id == "fridge" or loc.location_id.startswith("fridge_")
    }
    items = [
        i for i in db.get_inventory(user_id=current_user_id())
        if (i.storage_location_id in fridge_nodes)
    ]
    if not items:
        from shopstack.services.empty_states import render as _es_render
        return _es_render("household.fridge")
    rows = "".join(
        item_row(
            name=i.display_name,
            quantity=i.quantity,
            unit=i.unit,
            status=i.status,
        )
        for i in items
    )
    return f"home_card(body='<h3>What is in the fridge now?</h3>{rows}', style='text-align:left;')"


def inventory_alerts(days_since_purchase: int = 3) -> str:
    uid = current_user_id()
    if days_since_purchase <= 0:
        days_since_purchase = 3
    low = [
        lot for lot in db.get_inventory(user_id=uid)
        if lot.quantity <= 0.5 or lot.status == "low"
    ]
    stale = [
        lot for lot in db.get_inventory(user_id=uid)
        if lot.purchase_date and (date.today() - lot.purchase_date).days >= days_since_purchase and lot.quantity > 0
    ]

    today = date.today()
    expiring_today = []
    expiring_tomorrow = []
    for lot in db.get_inventory(status="active", user_id=uid):
        ref = lot.label_expiry_date or lot.estimated_use_by_date
        if not ref:
            continue
        delta = (ref - today).days
        if delta == 0:
            expiring_today.append(lot)
        elif delta == 1:
            expiring_tomorrow.append(lot)

    if not low and not stale and not expiring_today and not expiring_tomorrow:
        return "<div style='color:var(--text-dim);'>No proactive alerts at this time.</div>"

    alerts = ""
    if expiring_today:
        alerts += "<div style='margin-bottom:8px;border-left:4px solid var(--red);padding-left:10px;'><strong style='color:var(--red);'>Expiring today!</strong><ul>"
        alerts += "".join(f"<li>{escape(lot.display_name)} ({escape(str(lot.quantity))} {escape(lot.unit)})</li>" for lot in expiring_today)
        alerts += "</ul></div>"
    if expiring_tomorrow:
        alerts += "<div style='margin-bottom:8px;border-left:4px solid var(--amber);padding-left:10px;'><strong style='color:var(--amber);'>Expiring tomorrow</strong><ul>"
        alerts += "".join(f"<li>{escape(lot.display_name)} ({escape(str(lot.quantity))} {escape(lot.unit)})</li>" for lot in expiring_tomorrow)
        alerts += "</ul></div>"
    if low:
        alerts += "<div style='margin-bottom:8px;'><strong>Reorder Candidates</strong><ul>"
        alerts += "".join(f"<li>{escape(i.display_name)}: only {escape(str(i.quantity))} {escape(i.unit)} left</li>" for i in low)
        alerts += "</ul></div>"
    if stale:
        alerts += "<div style='margin-bottom:8px;'><strong>Use soon reminders</strong><ul>"
        alerts += "".join(f"<li>{escape(lot.display_name)}: last purchased {(date.today() - lot.purchase_date).days if lot.purchase_date else '?'} days ago</li>" for lot in stale)
        alerts += "</ul></div>"
    return f"home_card(body='{alerts}', style='text-align:left')"
