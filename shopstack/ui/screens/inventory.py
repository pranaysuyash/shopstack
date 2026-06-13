from __future__ import annotations

import json
import logging
from datetime import date
from html import escape
from typing import Any

from shopstack.app_context import db, tools
from shopstack.services.dashboard import clear_dashboard_cache
from shopstack.services.storage_suggest import suggest_storage_location
from shopstack.traces.export import create_trace
from shopstack.ui.components.cards import empty_state, list_to_table
from shopstack.ui.components.primitives import (
    aria_live_screen,
    form_error,
    item_row,
    toast,
)

logger = logging.getLogger(__name__)

from shopstack.data.seed_demo import DEMO_SEED_INVENTORY  # noqa: E402 — data module, must follow logger


def _user_id() -> str:
    from shopstack.app_context import current_user_id
    return current_user_id()


def _search_inventory_items(search: str) -> tuple[list[Any], str]:
    """Return inventory lots matching the search query.

    Uses the fast direct text path first, then falls back to semantic search
    when the user query does not directly match any canonical or display name.
    """
    uid = _user_id()
    items = db.get_inventory(user_id=uid)
    query = (search or "").strip().lower()
    if not query:
        return items, "all"

    direct_matches = [
        lot for lot in items
        if query in lot.canonical_name.lower() or query in lot.display_name.lower()
    ]
    if direct_matches:
        return direct_matches, "direct"

    try:
        semantic = tools.semantic_find_item(search, user_id=uid)
    except Exception as exc:
        logger.debug("Semantic inventory search failed: %s", exc)
        return [], "none"

    seen: set[str] = set()
    semantic_matches: list[Any] = []
    for result in semantic.get("results", []):
        lot_data = result.get("lot") if isinstance(result, dict) else None
        lot_id = lot_data.get("lot_id") if isinstance(lot_data, dict) else None
        if not lot_id or lot_id in seen:
            continue
        lot = next((candidate for candidate in items if candidate.lot_id == lot_id), None)
        if lot is None:
            continue
        semantic_matches.append(lot)
        seen.add(lot_id)

    return semantic_matches, "semantic" if semantic_matches else "none"


def suggest_location_for_item(name: str, category: str) -> str:
    """Gradio handler: suggest a storage location for a new inventory item.

    Returns a short toast that includes the suggested location ID and a
    human-readable reason. The UI can use the location_id as the
    storage_location_id field value via a follow-up `.then()` chain.
    """
    suggestion = suggest_storage_location(
        canonical_name=(name or "").strip().lower(),
        category=(category or "").strip(),
    )
    return toast(
        f"Suggested: {suggestion.storage_location_id} ({suggestion.reason})",
        kind="info",
    )


@aria_live_screen()
def add_purchase_form(
    name: str, qty: float, unit: str, price: float, store: str, location: str, purchase_date_str: str, category: str
) -> str:

    item_name = (name or "").strip()
    item_unit = (unit or "unit").strip() or "unit"
    if not item_name:
        return form_error("Item name is required.", field_id="p_name")
    if qty < 0:
        return form_error("Quantity must be 0 or more.", field_id="p_qty")
    if price < 0:
        return form_error("Price must be 0 or more.", field_id="p_price")
    uid = _user_id()
    add_result = tools.add_inventory_item(
        canonical_name=item_name.lower(),
        display_name=item_name,
        quantity=qty,
        unit=item_unit,
        storage_location_id=location or "kitchen",
        purchase_date=purchase_date_str or date.today().isoformat(),
        category=category,
        user_id=uid,
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
    clear_dashboard_cache(_user_id())
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
            user_id=uid,
        )
    except Exception as exc:
        logger.debug("Failed to record add purchase trace: %s", exc)
    return result


@aria_live_screen()
def add_purchase_batch(raw_batch: str) -> str:
    uid = _user_id()
    if not raw_batch or not str(raw_batch).strip():
        return form_error(
            "Add at least one row in the format name, qty, unit, price, store, "
            "location, category (one per line).",
            field_id="p_batch_input",
            level="warning",
        )

    rows = str(raw_batch).strip().splitlines()
    raw_text = "\n".join(r.strip() for r in rows if r.strip())
    parsed: list[tuple[str, float, str, float, str, str, str]] = []

    try:
        if raw_text.startswith("[") or raw_text.startswith("{"):
            loaded = json.loads(raw_text)
            if isinstance(loaded, dict):
                loaded = [loaded]
            if not isinstance(loaded, list):
                return "<div style='color:var(--red);'>Batch JSON must be an array of purchase objects.</div>"
            for item in loaded:
                if not isinstance(item, dict):
                    continue
                parsed.append(
                    (
                        str(item.get("display_name", item.get("name", item.get("canonical_name", ""))).strip()),
                        float(item.get("quantity", 1.0) or 1.0),
                        str(item.get("unit", "unit")),
                        float(item.get("price", 0.0) or 0.0),
                        str(item.get("store", "")).strip(),
                        str(item.get("location", "kitchen")).strip(),
                        str(item.get("category", "")).strip(),
                    )
                )
        else:
            for row in rows:
                if not row.strip():
                    continue
                parts = [part.strip() for part in row.split(",")]
                if len(parts) < 3:
                    continue
                parsed.append((
                    parts[0],
                    float(parts[1]) if len(parts) > 1 and parts[1] else 1.0,
                    parts[2] or "unit",
                    float(parts[3]) if len(parts) > 3 and parts[3] else 0.0,
                    parts[4] if len(parts) > 4 else "",
                    parts[5] if len(parts) > 5 else "kitchen",
                    parts[6] if len(parts) > 6 else "",
                ))
    except (json.JSONDecodeError, ValueError):
        return "<div style='color:var(--red);'>Could not parse batch purchase payload.</div>"

    if not parsed:
        return "<div style='color:var(--red);'>No valid purchase rows found.</div>"

    added = []
    for name, qty, unit, price, store, location, category in parsed:
        if not name:
            continue
        result = tools.add_inventory_item(
            canonical_name=name.lower().strip(),
            display_name=name.strip(),
            quantity=qty,
            unit=unit,
            storage_location_id=location or "kitchen",
            category=category,
            price_paid=price,
            source_event_id="batch_add",
            user_id=uid,
        )
        lot_id = result.get("lot_id", "")
        if price > 0 and store:
            tools.record_price_observation(
                canonical_name=name.lower().strip(),
                price=price,
                quantity=qty,
                unit=unit,
                store_name=store,
            )
        added.append(f"{escape(name)} ({escape(str(lot_id)[:8])})")

    if not added:
        return "<div style='color:var(--text-dim);'>No items were added.</div>"
    clear_dashboard_cache(_user_id())
    return f"<div style='color:var(--green);'>Added {len(added)} item(s): {', '.join(added)}</div>"


def seed_demo_inventory() -> str:
    uid = _user_id()
    existing = db.get_inventory(user_id=uid)
    if existing:
        return "<div style='color:var(--text-dim);'>Demo seed already loaded.</div>"

    added = []
    for item in DEMO_SEED_INVENTORY:
        name = item.get("display_name", item.get("canonical_name", ""))
        result = tools.add_inventory_item(
            canonical_name=str(item.get("canonical_name")).strip(),
            display_name=str(name).strip(),
            quantity=float(item.get("quantity", 1.0)),
            unit=str(item.get("unit", "unit")),
            storage_location_id=str(item.get("location", "kitchen")),
            category=str(item.get("category", "")),
            price_paid=float(item.get("price", 0.0) or 0.0),
            source_event_id="demo_seed",
            user_id=uid,
        )
        lot_id = result.get("lot_id", "")
        if item.get("price") and item.get("store"):
            tools.record_price_observation(
                canonical_name=item.get("canonical_name", ""),
                price=float(item.get("price", 0.0)),
                quantity=float(item.get("quantity", 1.0)),
                unit=str(item.get("unit", "unit")),
                store_name=str(item.get("store", "")),
            )
        added.append(f"{name} ({lot_id[:8]})")

    return (
        f"<div style='color:var(--green);'>Loaded demo stock ({len(added)} items): "
        f"{', '.join(escape(a) for a in added)}.</div>"
    )


def inventory_view(search: str = "") -> list[list[str]]:
    items, _match_mode = _search_inventory_items(search)
    locations = {loc.location_id: loc.name for loc in db.get_locations()}
    tbl = list_to_table(
        [
            {
                "name": lot.display_name,
                "qty": lot.quantity,
                "unit": lot.unit,
                "location": locations.get(lot.storage_location_id, lot.storage_location_id or ""),
                "status": lot.status,
                "purchased": lot.purchase_date.isoformat() if lot.purchase_date else "",
                "expires": lot.label_expiry_date.isoformat() if lot.label_expiry_date else lot.estimated_use_by_date.isoformat() if lot.estimated_use_by_date else "",
                "lot_id": lot.lot_id,
            }
            for lot in items
        ],
        ["name", "qty", "unit", "location", "status", "purchased", "expires", "lot_id"],
    )
    return tbl


def inventory_cards_view(search: str = "") -> str:
    items, match_mode = _search_inventory_items(search)
    locations = {loc.location_id: loc.name for loc in db.get_locations()}
    if not items:
        return empty_state("Your inventory is empty. Add one item in Add Purchase to start.")

    search_note = ""
    if search and match_mode == "semantic":
        search_note = (
            "<div style='margin-bottom:10px;font-size: 0.75rem;color:var(--text-dim);'>"
            f"Showing semantic matches for {escape(search.strip())}."
            "</div>"
        )

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
        body = ""
        for lot in lots:
            body += item_row(
                name=lot["name"],
                quantity=lot["qty"],
                unit=lot["unit"],
                status=lot["status"],
                extra=lot["reason"],
            )
        cards += (
            "<div class='home-card' style='margin-bottom:10px;'>"
            f"<h4>{escape(str(loc_name))}</h4>{body}</div>"
        )
    return search_note + cards


@aria_live_screen()
def consume_item(lot_id: str, qty: float) -> str:
    uid = _user_id()
    result = tools.consume_inventory_item(lot_id, qty, user_id=uid)
    if "error" in result:
        return f"<div style='color:var(--red);'>Error: {escape(str(result['error']))}</div>"
    clear_dashboard_cache(uid)
    return f"<div style='color:var(--green);'>Consumed {escape(str(qty))}. Remaining: {escape(str(result.get('remaining', 0)))}</div>"


@aria_live_screen()
def consume_items_batch(lines_text: str) -> str:
    if not lines_text:
        return "<div style='color:var(--text-dim);'>Add at least one lot id and quantity.</div>"
    entries = [line.strip() for line in str(lines_text).splitlines() if line.strip()]
    if not entries:
        return "<div style='color:var(--text-dim);'>No valid lines to parse.</div>"

    uid = _user_id()
    summary = []
    for entry in entries:
        lot_id, _, qty_text = entry.partition(":")
        if not qty_text:
            qty_text = "1"
        try:
            qty = float(qty_text.strip())
        except ValueError:
            qty = 1.0
        if not lot_id.strip():
            continue
        outcome = tools.consume_inventory_item(lot_id.strip(), qty, user_id=uid)
        if "error" in outcome:
            summary.append(f"{escape(lot_id)}: ❌ {escape(str(outcome['error']))}")
        else:
            summary.append(f"{escape(lot_id)}: ✅ remaining {escape(str(outcome.get('remaining', 0))) }")

    if not summary:
        return "<div style='color:var(--red);'>No consumable lot ids found.</div>"
    clear_dashboard_cache(uid)
    return "<div style='margin-top:8px;line-height:1.5;font-size: 0.75rem;'>" + "<br>".join(summary) + "</div>"


def use_soon_view(days: int = 3) -> list[list[str]]:
    data = tools.get_use_soon_items(days=days, user_id=_user_id())
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
