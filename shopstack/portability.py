from __future__ import annotations

import csv
import io
import logging
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, cast

from shopstack.persistence.database import Database
from shopstack.schemas.models import InventoryLot, ItemStatus, PriceObservation
from shopstack.ui.components.primitives import stat_card

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "1.0"


def export_json(database: Database) -> dict[str, Any]:
    inventory = database.get_inventory()

    price_obs = []
    try:
        cursor = database.conn.execute("SELECT * FROM price_observations ORDER BY observation_date")
        for row in cursor.fetchall():
            price_obs.append(dict(row))
    except Exception as e:
        logger.warning("Failed to export price observations: %s", e)

    purchase_events = []
    try:
        cursor = database.conn.execute("SELECT * FROM purchase_events ORDER BY timestamp DESC LIMIT 500")
        for row in cursor.fetchall():
            purchase_events.append(dict(row))
    except Exception as e:
        logger.warning("Failed to export purchase events: %s", e)

    field_notes = ""
    try:
        field_notes = database.get_config_value("field_notes_markdown", "")
    except Exception:
        pass

    return {
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "inventory": [_lot_to_dict(lot) for lot in inventory],
        "price_observations": price_obs,
        "purchase_events": purchase_events,
        "field_notes": field_notes,
    }


def export_backup(database: Database) -> dict[str, Any]:
    """Full household backup with restored purchase-event IDs and price memory."""
    export = export_json(database)


    export["export_type"] = "household_backup"
    export["description"] = (
        "Full household inventory backup. Restore via import_json() "
        "with import_mode='replace' for a clean restore."
    )

    household_locations = []
    try:
        cursor = database.conn.execute(
            "SELECT location_id, name, parent_location_id, location_type, photo_path, notes "
            "FROM household_locations ORDER BY name"
        )
        for row in cursor.fetchall():
            household_locations.append(dict(row))
    except Exception:
        pass
    export["household_locations"] = household_locations
    # Backward-compatibility alias for existing importers/docs.
    export["storage_locations"] = household_locations

    return export


def export_trace_bundle(database: Database) -> dict[str, Any]:
    """Redacted/shareable trace bundle with no personally-identifying details.

    Useful for bug reports, debugging, or sharing with maintainers. Strips
    lot_id (replaced with sequential IDs), display_name (kept as canonical),
    and field_notes (kept as excerpt only).
    """
    inventory = database.get_inventory()

    items_redacted = []
    for idx, lot in enumerate(inventory):
        items_redacted.append({
            "id": f"item_{idx}",
            "canonical_name": lot.canonical_name,
            "quantity": lot.quantity,
            "unit": lot.unit,
            "status": lot.status if isinstance(lot.status, str) else lot.status.value,
            "category": lot.category,
        })

    price_obs_redacted = []
    try:
        cursor = database.conn.execute(
            "SELECT canonical_name, quantity, unit, price, currency, "
            "observation_date FROM price_observations ORDER BY observation_date"
        )
        for row in cursor.fetchall():
            d = dict(row)
            d.pop("observation_id", None)
            price_obs_redacted.append(d)
    except Exception:
        pass

    field_notes = ""
    try:
        raw = database.get_config_value("field_notes_markdown", "")
        if raw:
            field_notes = raw[:500] + ("..." if len(raw) > 500 else "")
    except Exception:
        pass

    return {
        "schema_version": SCHEMA_VERSION,
        "export_type": "trace_bundle",
        "exported_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "description": "Redacted/shareable trace bundle. No personally-identifying details.",
        "inventory": items_redacted,
        "price_observations": price_obs_redacted,
        "field_notes_excerpt": field_notes,
        "lot_count": len(items_redacted),
        "price_observation_count": len(price_obs_redacted),
    }


def _lot_to_dict(lot: InventoryLot) -> dict[str, Any]:
    return {
        "lot_id": lot.lot_id,
        "canonical_name": lot.canonical_name,
        "display_name": lot.display_name,
        "quantity": lot.quantity,
        "unit": lot.unit,
        "storage_location_id": lot.storage_location_id,
        "status": lot.status if isinstance(lot.status, str) else lot.status.value,
        "category": lot.category,
        "purchase_date": lot.purchase_date.isoformat() if lot.purchase_date else None,
        "price_paid": lot.price_paid,
        "currency": lot.currency,
    }


def export_csv_inventory(database: Database) -> str:
    inventory = database.get_inventory()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["lot_id", "canonical_name", "display_name", "quantity", "unit",
                     "storage_location", "status", "category", "purchase_date",
                     "price_paid", "currency"])
    for lot in inventory:
        writer.writerow([
            lot.lot_id,
            lot.canonical_name,
            lot.display_name,
            lot.quantity,
            lot.unit,
            lot.storage_location_id,
            lot.status if isinstance(lot.status, str) else lot.status.value,
            lot.category or "",
            lot.purchase_date.isoformat() if lot.purchase_date else "",
            lot.price_paid or "",
            lot.currency or "",
        ])
    return output.getvalue()


class ImportResult:
    def __init__(self) -> None:
        self.items_added: int = 0
        self.items_updated: int = 0
        self.price_observations_added: int = 0
        self.errors: list[str] = []
        self.messages: list[str] = []

    @property
    def summary_html(self) -> str:
        parts = [f"<div><strong>{self.items_added}</strong> items added."]
        if self.items_updated:
            parts.append(f" <strong>{self.items_updated}</strong> items updated.")
        if self.price_observations_added:
            parts.append(f" <strong>{self.price_observations_added}</strong> price observations added.")
        if self.errors:
            parts.append(f"</div><div style='color:var(--red);margin-top:8px;'>{len(self.errors)} error(s):")
            for err in self.errors[:5]:
                parts.append(f"<div style='font-size: 0.75rem;'>{err}</div>")
            if len(self.errors) > 5:
                parts.append(f"<div style='font-size: 0.75rem;'>...and {len(self.errors) - 5} more</div>")
        return stat_card(body_html="".join(parts))


def import_json(
    database: Database,
    data: dict[str, Any],
    import_mode: str = "merge",
) -> ImportResult:
    result = ImportResult()

    if not isinstance(data, dict):
        result.errors.append("Import data must be a JSON object")
        return result

    version = data.get("schema_version", "0.0")
    result.messages.append(f"Schema version: {version}, mode: {import_mode}")

    # Replace mode: clear inventory before importing
    if import_mode == "replace":
        try:
            existing_items = database.get_inventory()
            for lot in existing_items:
                database.conn.execute("DELETE FROM inventory_lots WHERE lot_id = ?", (lot.lot_id,))
            database.conn.commit()
            result.messages.append(f"Cleared {len(existing_items)} existing inventory items.")
        except Exception as e:
            result.errors.append(f"Failed to clear inventory for replace mode: {e}")

    items = data.get("inventory") or data.get("items") or []
    for item in items:
        try:
            if not isinstance(item, dict):
                result.errors.append(f"Skipping non-dict item: {item}")
                continue
            canonical_name = (item.get("canonical_name") or "").strip()
            if not canonical_name:
                result.errors.append("Item missing canonical_name, skipping")
                continue

            existing = database.get_inventory(canonical_name=canonical_name)
            if existing and import_mode != "replace":
                lot = existing[0]
                new_qty = float(item.get("quantity", lot.quantity))
                database.update_inventory_lot(lot.lot_id, {"quantity": new_qty})
                result.items_updated += 1
            else:
                import_lot = InventoryLot(
                    canonical_name=canonical_name,
                    display_name=item.get("display_name", canonical_name),
                    quantity=float(item.get("quantity", 1.0)),
                    unit=item.get("unit", "unit"),
                    storage_location_id=item.get("storage_location_id", "pantry"),
                    status=item.get("status", "active"),
                    category=item.get("category", ""),
                    purchase_date=_parse_date(item.get("purchase_date")),
                    price_paid=_parse_float(item.get("price_paid")),
                    currency=item.get("currency", "INR"),
                )
                database.add_inventory_lot(import_lot)
                result.items_added += 1
        except Exception as e:
            result.errors.append(f"Failed to import item '{item.get('canonical_name', '?')}': {e}")

    price_obs = data.get("price_observations") or []
    for obs in price_obs:
        try:
            po = PriceObservation(
                canonical_name=str(obs.get("canonical_name", obs.get("item_name", ""))),
                quantity=float(obs.get("quantity", 1.0)),
                unit=str(obs.get("unit", "unit")),
                price=float(obs.get("price", 0.0)),
                currency=str(obs.get("currency", "INR")),
                store_name=obs.get("store_name"),
                store_id=obs.get("store_id"),
                observation_date=_parse_date(obs.get("observation_date")) or date.today(),
                source_event_id=obs.get("source_event_id", "import"),
                notes=obs.get("notes"),
            )
            database.record_price(po)
            result.price_observations_added += 1
        except Exception as e:
            result.errors.append(f"Failed to import price observation: {e}")

    field_notes = data.get("field_notes", "")
    if field_notes and isinstance(field_notes, str) and field_notes.strip():
        try:
            database.set_config_value("field_notes_markdown", field_notes.strip())
            result.messages.append("Field notes restored.")
        except Exception as e:
            result.errors.append(f"Failed to restore field notes: {e}")

    return result


def validate_import_json(database: Database, data: dict[str, Any]) -> ImportResult:
    """Dry-run import validation — reports changes WITHOUT writing to DB.

    Returns an ImportResult with counts of what *would* happen but does not
    call any database mutation methods. Safe to call on production data.
    """
    result = ImportResult()

    if not isinstance(data, dict):
        result.errors.append("Import data must be a JSON object")
        return result

    version = data.get("schema_version", "0.0")
    result.messages.append(f"Dry-run: schema version {version}")

    current_inventory = database.get_inventory()
    current_by_name: dict[str, list[InventoryLot]] = defaultdict(list)
    for lot in current_inventory:
        current_by_name[lot.canonical_name].append(lot)

    items = data.get("inventory") or data.get("items") or []
    for item in items:
        if not isinstance(item, dict):
            result.errors.append(f"Skipping non-dict item: {item}")
            continue
        canonical_name = (item.get("canonical_name") or "").strip()
        if not canonical_name:
            result.errors.append("Item missing canonical_name, skipping")
            continue

        existing = current_by_name.get(canonical_name, [])
        if existing:
            result.items_updated += 1
        else:
            result.items_added += 1

    price_obs = data.get("price_observations") or []
    result.price_observations_added = len(price_obs)

    field_notes = data.get("field_notes", "")
    if field_notes and isinstance(field_notes, str) and field_notes.strip():
        result.messages.append("Field notes would be restored.")

    result.messages.append(
        f"Dry-run summary: {result.items_added} new, {result.items_updated} updated, "
        f"{result.price_observations_added} price obs"
    )
    result.messages.append("No data was written. Call import_json() to apply.")
    return result


def import_csv(database: Database, csv_text: str) -> ImportResult:
    result = ImportResult()
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        result.errors.append("CSV has no header row")
        return result

    for row in reader:
        try:
            canonical_name = (row.get("canonical_name") or "").strip()
            if not canonical_name:
                result.errors.append(f"Skipping row without canonical_name: {row}")
                continue

            existing = database.get_inventory(canonical_name=canonical_name)
            if existing:
                lot = existing[0]
                new_qty = float(row.get("quantity", lot.quantity))
                database.update_inventory_lot(lot.lot_id, {"quantity": new_qty})
                result.items_updated += 1
            else:
                import_lot = InventoryLot(
                    canonical_name=canonical_name,
                    display_name=row.get("display_name", canonical_name),
                    quantity=float(row.get("quantity", 1.0)),
                    unit=row.get("unit", "unit"),
                    storage_location_id=row.get("storage_location_id", "pantry"),
                    status=cast(ItemStatus, row.get("status", "active")),
                    category=row.get("category", ""),
                    purchase_date=_parse_date(row.get("purchase_date")),
                    price_paid=_parse_float(row.get("price_paid")),
                    currency=row.get("currency", "INR"),
                )
                database.add_inventory_lot(import_lot)
                result.items_added += 1
        except Exception as e:
            result.errors.append(f"Failed to import CSV row: {e}")

    return result


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return date.fromisoformat(str(value).split("T")[0])
    except (ValueError, TypeError):
        return None


def _parse_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
