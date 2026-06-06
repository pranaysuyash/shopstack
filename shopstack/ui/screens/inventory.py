from __future__ import annotations

import logging
from datetime import date
from html import escape
from typing import Any

from shopstack.app_context import db, tools
from shopstack.traces.export import create_trace
from shopstack.ui import empty_state, list_to_table
from shopstack.ui.screens._utils import workflow_header

logger = logging.getLogger(__name__)


def add_purchase_form(
    name: str, qty: float, unit: str, price: float, store: str, location: str, purchase_date_str: str, category: str
) -> str:

    item_name = (name or "").strip()
    item_unit = (unit or "unit").strip() or "unit"
    if not item_name:
        return "<div style='color:var(--red);'>Item name is required.</div>"
    if qty < 0:
        return "<div style='color:var(--red);'>Quantity must be 0 or more.</div>"
    if price < 0:
        return "<div style='color:var(--red);'>Price must be 0 or more.</div>"
    add_result = tools.add_inventory_item(
        canonical_name=item_name.lower(),
        display_name=item_name,
        quantity=qty,
        unit=item_unit,
        storage_location_id=location or "kitchen",
        purchase_date=purchase_date_str or date.today().isoformat(),
        category=category,
    )
    lot_id = add_result.get("lot_id", "")
    if price > 0 and store:
        tools.record_price_observation(
            canonical_name=item_name.lower(),
            price=price,
            quantity=qty,
            unit=item_unit,
            store_name=store,
        )
    result = f"<div style='color:var(--green);'>Added {escape(item_name)} (lot {escape(str(lot_id))})</div>"
    try:
        create_trace(
            db,
            input_type="form",
            user_goal="add_purchase",
            redacted_user_request=f"add purchase: {item_name}",
            perception={"item": item_name, "quantity": qty, "unit": item_unit, "store": store},
            inventory_context={"storage_location": location, "category": category},
            decision={"action": "add_inventory_item", "lot_id": lot_id},
            proposed_tool_calls=[
                {"tool_name": "add_inventory_item", "args": {"name": item_name, "quantity": qty, "unit": item_unit}},
                {"tool_name": "record_price_observation", "args": {"price": price, "store": store}},
            ],
            final_response=result,
            human_confirmation="confirmed-by-user",
        )
    except Exception as exc:
        logger.debug("Failed to record add purchase trace: %s", exc)
    return result


def inventory_view(search: str = "") -> list[list[str]]:
    items = db.get_inventory()
    if search:
        q = search.lower()
        items = [l for l in items if q in l.canonical_name.lower() or q in l.display_name.lower()]
    locations = {loc.location_id: loc.name for loc in db.get_locations()}
    tbl = list_to_table(
        [
            {
                "name": l.display_name,
                "qty": l.quantity,
                "unit": l.unit,
                "location": locations.get(l.storage_location_id, l.storage_location_id or ""),
                "status": l.status,
                "purchased": l.purchase_date.isoformat() if l.purchase_date else "",
                "expires": (l.label_expiry_date or l.estimated_use_by_date or "").isoformat() if (l.label_expiry_date or l.estimated_use_by_date) else "",
                "lot_id": l.lot_id,
            }
            for l in items
        ],
        ["name", "qty", "unit", "location", "status", "purchased", "expires", "lot_id"],
    )
    return tbl


def inventory_cards_view(search: str = "") -> str:
    items = db.get_inventory()
    if search:
        q = search.lower()
        items = [l for l in items if q in l.canonical_name.lower() or q in l.display_name.lower()]
    locations = {loc.location_id: loc.name for loc in db.get_locations()}
    if not items:
        return empty_state("Your inventory is empty. Add one item in Add Purchase to start.")

    grouped: dict[str, list[dict[str, Any]]] = {}
    for lot in items:
        loc = locations.get(lot.storage_location_id, lot.storage_location_id or "Unknown")
        grouped.setdefault(loc, []).append(
            {
                "name": lot.display_name,
                "qty": lot.quantity,
                "unit": lot.unit,
                "status": lot.status,
                "reason": f"Added {lot.purchase_date.isoformat() if lot.purchase_date else 'today'}",
                "expiry": (lot.label_expiry_date.isoformat() if lot.label_expiry_date else ""),
            }
        )

    cards = ""
    for loc_name, lots in grouped.items():
        body = "<div style='margin-bottom:8px;'>"
        for lot in lots:
            body += "<div class='item-row'>"
            body += f"<div><strong>{escape(str(lot['name']))}</strong><div style='font-size:11px;color:var(--text-dim)'>{escape(str(lot['reason']))}</div></div>"
            body += f"<div style='text-align:right'>{escape(str(lot['qty']))} {escape(str(lot['unit']))}</div>"
            body += "</div>"
        body += "</div>"
        cards += (
            "<div class='home-card' style='margin-bottom:10px;'>"
            f"<h4>{escape(str(loc_name))}</h4>{body}</div>"
        )
    return cards


def consume_item(lot_id: str, qty: float) -> str:
    result = tools.consume_inventory_item(lot_id, qty)
    if "error" in result:
        return f"<div style='color:var(--red);'>Error: {escape(str(result['error']))}</div>"
    return f"<div style='color:var(--green);'>Consumed {escape(str(qty))}. Remaining: {escape(str(result.get('remaining', 0)))}</div>"


def use_soon_view(days: int = 3) -> list[list[str]]:
    data = tools.get_use_soon_items(days=days)
    items = data.get("items", [])
    tbl = list_to_table(
        [
            {
                "name": i.get("display_name", i.get("canonical_name", "")),
                "qty": i.get("quantity", 0),
                "unit": i.get("unit", ""),
                "expires": i.get("expiry_date", i.get("purchase_date", "")),
                "days": i.get("days_remaining", i.get("days_since_purchase", 0)),
                "reason": i.get("reason", i.get("expiry_type", "")),
            }
            for i in items
        ],
        ["name", "qty", "unit", "expires", "days", "reason"],
    )
    return tbl
