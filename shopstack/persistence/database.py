from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from shopstack.config import settings
from shopstack.schemas.models import (
    InventoryLot,
    HouseholdLocation,
    MovementEvent,
    PriceObservation,
    PurchaseEvent,
    ShoppingList,
    ShoppingListItem,
    Store,
    Trace,
)


class Database:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path if db_path is not None else settings.db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _init_db(self) -> None:
        c = self.conn
        c.executescript("""
            CREATE TABLE IF NOT EXISTS inventory_lots (
                lot_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                category TEXT DEFAULT '',
                quantity REAL DEFAULT 1.0,
                unit TEXT DEFAULT 'unit',
                storage_location_id TEXT DEFAULT '',
                purchase_date TEXT,
                estimated_use_by_date TEXT,
                label_expiry_date TEXT,
                opened_date TEXT,
                price_paid REAL,
                currency TEXT DEFAULT 'INR',
                source_event_id TEXT DEFAULT '',
                confidence REAL DEFAULT 1.0,
                image_crop_path TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT,
                updated_at TEXT,
                user_id TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS purchase_events (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT,
                canonical_name TEXT DEFAULT '',
                quantity REAL DEFAULT 1.0,
                unit TEXT DEFAULT 'unit',
                total_price REAL DEFAULT 0.0,
                currency TEXT DEFAULT 'INR',
                source_type TEXT DEFAULT 'manual',
                store_name TEXT,
                raw_text TEXT,
                source_file_path TEXT,
                confirmed INTEGER DEFAULT 0,
                user_id TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS shopping_lists (
                list_id TEXT PRIMARY KEY,
                name TEXT DEFAULT 'Shopping List',
                created_at TEXT,
                updated_at TEXT,
                goal TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                user_id TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS shopping_list_items (
                item_id TEXT PRIMARY KEY,
                list_id TEXT NOT NULL,
                canonical_name TEXT NOT NULL,
                requested_quantity REAL,
                unit TEXT,
                priority TEXT DEFAULT 'optional',
                reason TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                linked_lots TEXT DEFAULT '[]',
                FOREIGN KEY (list_id) REFERENCES shopping_lists(list_id)
            );

            CREATE TABLE IF NOT EXISTS household_locations (
                location_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                parent_location_id TEXT,
                location_type TEXT DEFAULT 'shelf',
                photo_path TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS movement_events (
                movement_id TEXT PRIMARY KEY,
                lot_id TEXT NOT NULL,
                from_location_id TEXT,
                to_location_id TEXT NOT NULL,
                timestamp TEXT,
                source TEXT DEFAULT 'manual',
                confidence REAL DEFAULT 1.0,
                FOREIGN KEY (lot_id) REFERENCES inventory_lots(lot_id)
            );

            CREATE TABLE IF NOT EXISTS price_observations (
                price_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                quantity REAL DEFAULT 1.0,
                unit TEXT DEFAULT 'unit',
                price REAL NOT NULL,
                currency TEXT DEFAULT 'INR',
                store_name TEXT,
                store_id TEXT,
                observation_date TEXT,
                source_event_id TEXT DEFAULT '',
                notes TEXT,
                user_id TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS stores (
                store_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                location TEXT,
                store_type TEXT DEFAULT 'kirana',
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                input_type TEXT DEFAULT '',
                user_goal TEXT DEFAULT '',
                redacted_user_request TEXT DEFAULT '',
                perception TEXT DEFAULT '{}',
                inventory_context TEXT DEFAULT '{}',
                decision TEXT DEFAULT '{}',
                proposed_tool_calls TEXT DEFAULT '[]',
                human_confirmation TEXT,
                final_response TEXT DEFAULT '',
                timestamp TEXT,
                user_id TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS app_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE VIEW IF NOT EXISTS price_history AS
                SELECT * FROM price_observations;

            CREATE TRIGGER IF NOT EXISTS price_history_delete
            INSTEAD OF DELETE ON price_history
            BEGIN
                DELETE FROM price_observations WHERE price_id = OLD.price_id;
            END;

            CREATE VIEW IF NOT EXISTS agent_traces AS
                SELECT * FROM traces;

            CREATE TRIGGER IF NOT EXISTS agent_traces_delete
            INSTEAD OF DELETE ON agent_traces
            BEGIN
                DELETE FROM traces WHERE trace_id = OLD.trace_id;
            END;
        """)
        self._migrate_add_user_scoping()
        self._seed_locations()
        self.conn.commit()

    def _migrate_add_user_scoping(self) -> None:
        tables = ["inventory_lots", "purchase_events", "shopping_lists", "traces", "price_observations"]
        for table in tables:
            try:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT DEFAULT ''")
            except Exception:
                pass

    def _seed_locations(self) -> None:
        existing = self.conn.execute("SELECT COUNT(*) FROM household_locations").fetchone()[0]
        if existing > 0:
            return
        locations = [
            ("home", "Home", None, "room"),
            ("kitchen", "Kitchen", "home", "room"),
            ("fridge", "Fridge", "kitchen", "fridge"),
            ("fridge_door", "Fridge Door", "fridge", "fridge"),
            ("fridge_top", "Fridge Top Shelf", "fridge", "fridge"),
            ("fridge_drawer", "Fridge Vegetable Drawer", "fridge", "fridge"),
            ("freezer", "Freezer", "fridge", "freezer"),
            ("pantry", "Pantry", "kitchen", "pantry"),
            ("pantry_top", "Pantry Top Shelf", "pantry", "shelf"),
            ("pantry_mid", "Pantry Middle Shelf", "pantry", "shelf"),
            ("spice_box", "Spice Box", "pantry", "shelf"),
            ("bathroom", "Bathroom", None, "room"),
            ("bathroom_cabinet", "Bathroom Cabinet", "bathroom", "cabinet"),
            ("bathroom_sink", "Under Bathroom Sink", "bathroom", "cabinet"),
            ("bedroom", "Bedroom", None, "room"),
            ("medicine_drawer", "Medicine Drawer", "bedroom", "drawer"),
            ("balcony", "Balcony", None, "balcony"),
            ("cleaning_shelf", "Balcony Cleaning Shelf", "balcony", "shelf"),
        ]
        for loc_id, name, parent, loc_type in locations:
            self.conn.execute(
                "INSERT INTO household_locations (location_id, name, parent_location_id, location_type) VALUES (?, ?, ?, ?)",
                (loc_id, name, parent, loc_type),
            )

    # --- Inventory CRUD ---

    def add_inventory_lot(self, lot: InventoryLot, user_id: str = "") -> InventoryLot:
        self.conn.execute(
            """INSERT INTO inventory_lots
               (lot_id, canonical_name, display_name, category, quantity, unit,
                storage_location_id, purchase_date, estimated_use_by_date,
                label_expiry_date, opened_date, price_paid, currency,
                source_event_id, confidence, image_crop_path, status, created_at, updated_at, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lot.lot_id, lot.canonical_name, lot.display_name, lot.category,
                lot.quantity, lot.unit, lot.storage_location_id,
                _d(lot.purchase_date), _d(lot.estimated_use_by_date),
                _d(lot.label_expiry_date), _d(lot.opened_date),
                lot.price_paid, lot.currency, lot.source_event_id,
                lot.confidence, lot.image_crop_path, lot.status,
                lot.created_at.isoformat(), lot.updated_at.isoformat(),
                user_id,
            ),
        )
        self.conn.commit()
        return lot

    def update_inventory_lot(self, lot_id: str, updates: dict, user_id: str = "") -> InventoryLot | None:
        existing = self.get_inventory_lot(lot_id)
        if not existing:
            return None
        fields = ["canonical_name", "display_name", "category", "quantity", "unit",
                  "storage_location_id", "purchase_date", "estimated_use_by_date",
                  "label_expiry_date", "opened_date", "price_paid", "currency",
                  "confidence", "image_crop_path", "status", "user_id"]
        set_clauses = []
        vals = []
        for f in fields:
            if f in updates:
                set_clauses.append(f"{f} = ?")
                vals.append(updates[f])
        if set_clauses:
            set_clauses.append("updated_at = ?")
            vals.append(datetime.now().isoformat())
            vals.append(lot_id)
            self.conn.execute(
                f"UPDATE inventory_lots SET {', '.join(set_clauses)} WHERE lot_id = ?",
                vals,
            )
            self.conn.commit()
        return self.get_inventory_lot(lot_id)

    def get_inventory_lot(self, lot_id: str) -> InventoryLot | None:
        row = self.conn.execute(
            "SELECT * FROM inventory_lots WHERE lot_id = ?", (lot_id,)
        ).fetchone()
        return _row_to_lot(row) if row else None

    def get_inventory_lot_ids(self, lot_id_prefix: str) -> list[str]:
        if not lot_id_prefix:
            return []
        exact = self.get_inventory_lot(lot_id_prefix)
        if exact:
            return [lot_id_prefix]
        rows = self.conn.execute(
            "SELECT lot_id FROM inventory_lots WHERE lot_id LIKE ? ORDER BY lot_id", (f"{lot_id_prefix}%",)
        ).fetchall()
        return [r["lot_id"] for r in rows]

    def resolve_inventory_lot_id(self, lot_id_or_prefix: str) -> str | None:
        ids = self.get_inventory_lot_ids(lot_id_or_prefix)
        if len(ids) == 1:
            return ids[0]
        return None

    def get_inventory(
        self, status: str | None = None, location_id: str | None = None,
        category: str | None = None, user_id: str = "",
        canonical_name: str | None = None,
    ) -> list[InventoryLot]:
        parts = ["SELECT * FROM inventory_lots WHERE 1=1"]
        params: list[Any] = []
        if user_id:
            parts.append("AND user_id = ?")
            params.append(user_id)
        if status:
            parts.append("AND status = ?")
            params.append(status)
        if location_id:
            parts.append("AND storage_location_id = ?")
            params.append(location_id)
        if category:
            parts.append("AND category = ?")
            params.append(category)
        if canonical_name:
            parts.append("AND canonical_name = ?")
            params.append(canonical_name)
        parts.append("ORDER BY created_at DESC")
        rows = self.conn.execute(" ".join(parts), params).fetchall()
        return [_row_to_lot(r) for r in rows if r]

    def consume_inventory(self, lot_id: str, quantity: float) -> InventoryLot | None:
        if quantity < 0:
            raise ValueError("quantity must be greater than 0")
        lot = self.get_inventory_lot(lot_id)
        if not lot:
            return None
        new_qty = max(0.0, lot.quantity - quantity)
        status = lot.status
        if new_qty <= 0:
            new_qty = 0
            status = "used"
        elif new_qty < lot.quantity * 0.2:
            status = "low"
        return self.update_inventory_lot(lot_id, {"quantity": new_qty, "status": status})

    def mark_list_complete(self, list_id: str) -> None:
        self.conn.execute(
            "UPDATE shopping_lists SET is_active = 0, updated_at = ? WHERE list_id = ?",
            (datetime.now().isoformat(), list_id),
        )
        self.conn.commit()

    # --- Shopping List CRUD ---

    def create_shopping_list(self, name: str = "Shopping List", goal: str = "", user_id: str = "") -> ShoppingList:
        sl = ShoppingList(name=name, goal=goal)
        self.conn.execute(
            "INSERT INTO shopping_lists (list_id, name, created_at, updated_at, goal, is_active, user_id) VALUES (?, ?, ?, ?, ?, 1, ?)",
            (sl.list_id, sl.name, sl.created_at.isoformat(), sl.updated_at.isoformat(), sl.goal, user_id),
        )
        self.conn.commit()
        return sl

    def get_active_shopping_list(self, user_id: str = "") -> ShoppingList | None:
        query = "SELECT * FROM shopping_lists WHERE is_active = 1"
        params: list[str] = []
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY created_at DESC LIMIT 1"
        row = self.conn.execute(query, params).fetchone()
        if not row:
            return None
        return _row_to_list(row, self.conn)

    def add_list_item(self, list_id: str, item: ShoppingListItem) -> ShoppingListItem:
        self.conn.execute(
            "INSERT INTO shopping_list_items (item_id, list_id, canonical_name, requested_quantity, unit, priority, reason, status, linked_lots) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item.list_item_id, list_id, item.canonical_name, item.requested_quantity,
             item.unit, item.priority, item.reason, item.status,
             json.dumps(item.linked_inventory_lots)),
        )
        self.conn.execute(
            "UPDATE shopping_lists SET updated_at = ? WHERE list_id = ?",
            (datetime.now().isoformat(), list_id),
        )
        self.conn.commit()
        return item

    def update_list_item(self, item_id: str, updates: dict) -> None:
        item = self.conn.execute(
            "SELECT * FROM shopping_list_items WHERE item_id = ?", (item_id,)
        ).fetchone()
        if not item:
            return
        fields = ["canonical_name", "requested_quantity", "unit", "priority", "reason", "status"]
        set_clauses = []
        vals = []
        for f in fields:
            if f in updates:
                set_clauses.append(f"{f} = ?")
                vals.append(updates[f])
        if set_clauses:
            vals.append(item_id)
            self.conn.execute(
                f"UPDATE shopping_list_items SET {', '.join(set_clauses)} WHERE item_id = ?",
                vals,
            )
            self.conn.commit()
        if "list_id" in updates:
            self.conn.execute(
                "UPDATE shopping_lists SET updated_at = ? WHERE list_id = ?",
                (datetime.now().isoformat(), updates["list_id"]),
            )
            self.conn.commit()

    # --- Locations ---

    def get_locations(self) -> list[HouseholdLocation]:
        rows = self.conn.execute("SELECT * FROM household_locations ORDER BY name").fetchall()
        return [_row_to_location(r) for r in rows]

    def get_location(self, location_id: str) -> HouseholdLocation | None:
        row = self.conn.execute(
            "SELECT * FROM household_locations WHERE location_id = ?", (location_id,)
        ).fetchone()
        return _row_to_location(row) if row else None

    # --- Movements ---

    def record_movement(self, movement: MovementEvent) -> MovementEvent:
        self.conn.execute(
            "INSERT INTO movement_events (movement_id, lot_id, from_location_id, to_location_id, timestamp, source, confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (movement.movement_id, movement.lot_id, movement.from_location_id,
             movement.to_location_id, movement.timestamp.isoformat(),
             movement.source, movement.confidence),
        )
        self.conn.execute(
            "UPDATE inventory_lots SET storage_location_id = ?, updated_at = ? WHERE lot_id = ?",
            (movement.to_location_id, datetime.now().isoformat(), movement.lot_id),
        )
        self.conn.commit()
        return movement

    def get_movements_for_lot(self, lot_id: str) -> list[MovementEvent]:
        rows = self.conn.execute(
            "SELECT * FROM movement_events WHERE lot_id = ? ORDER BY timestamp DESC",
            (lot_id,),
        ).fetchall()
        return [_row_to_movement(r) for r in rows]

    # --- Price Observations ---

    def record_price(self, price: PriceObservation, user_id: str = "") -> PriceObservation:
        self.conn.execute(
            "INSERT INTO price_observations (price_id, canonical_name, quantity, unit, price, currency, store_name, store_id, observation_date, source_event_id, notes, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (price.price_id, price.canonical_name, price.quantity, price.unit,
             price.price, price.currency, price.store_name, price.store_id,
             _d(price.observation_date), price.source_event_id, price.notes,
             user_id),
        )
        self.conn.commit()
        return price

    def get_price_history(self, canonical_name: str, user_id: str = "") -> list[PriceObservation]:
        query = "SELECT * FROM price_observations WHERE canonical_name = ?"
        params: list[str | None] = [canonical_name]
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY observation_date DESC, rowid DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_price(r) for r in rows]

    # --- Stores ---

    def add_store(self, store: Store) -> Store:
        self.conn.execute(
            "INSERT INTO stores (store_id, name, location, store_type, notes) VALUES (?, ?, ?, ?, ?)",
            (store.store_id, store.name, store.location, store.store_type, store.notes),
        )
        self.conn.commit()
        return store

    def get_stores(self) -> list[Store]:
        rows = self.conn.execute("SELECT * FROM stores ORDER BY name").fetchall()
        return [_row_to_store(r) for r in rows]

    # --- App Config ---

    def get_config_value(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM app_config WHERE key = ?",
            (key,),
        ).fetchone()
        return row["value"] if row else default

    def set_config_value(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

    # --- Traces ---

    def save_trace(self, trace: Trace, user_id: str = "") -> Trace:
        self.conn.execute(
            "INSERT OR REPLACE INTO traces (trace_id, input_type, user_goal, redacted_user_request, perception, inventory_context, decision, proposed_tool_calls, human_confirmation, final_response, timestamp, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                trace.trace_id, trace.input_type, trace.user_goal,
                trace.redacted_user_request, json.dumps(trace.perception),
                json.dumps(trace.inventory_context), json.dumps(trace.decision),
                json.dumps([t.model_dump() for t in trace.proposed_tool_calls], default=str),
                trace.human_confirmation, trace.final_response,
                trace.timestamp.isoformat(),
                user_id,
            ),
        )
        self.conn.commit()
        return trace

    def get_traces(self, limit: int = 50, user_id: str = "") -> list[Trace]:
        query = "SELECT * FROM traces"
        params: list[str | int] = []
        if user_id:
            query += " WHERE user_id = ?"
            params.append(user_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_trace(r) for r in rows]

    # --- Purchase Events ---

    def add_purchase_event(self, event: PurchaseEvent, user_id: str = "") -> PurchaseEvent:
        self.conn.execute(
            "INSERT INTO purchase_events (event_id, timestamp, canonical_name, quantity, unit, total_price, currency, source_type, store_name, raw_text, source_file_path, confirmed, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (event.event_id, event.timestamp.isoformat(),
             event.canonical_name, event.quantity, event.unit,
             event.total_price, event.currency, event.source_type,
             event.store_name, event.raw_text, event.source_file_path,
             1 if event.confirmed else 0,
             user_id),
        )
        self.conn.commit()
        return event

    def get_purchase_events(self, limit: int = 20, user_id: str = "") -> list[PurchaseEvent]:
        query = "SELECT * FROM purchase_events"
        params: list[str | int] = []
        if user_id:
            query += " WHERE user_id = ?"
            params.append(user_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_purchase(r) for r in rows]

    def get_purchases(self, limit: int = 20) -> list[PurchaseEvent]:
        return self.get_purchase_events(limit=limit)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None


def _d(dt: date | str | None) -> str | None:
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.isoformat()


def _row_to_lot(row: sqlite3.Row) -> InventoryLot:
    return InventoryLot(
        lot_id=row["lot_id"], canonical_name=row["canonical_name"],
        display_name=row["display_name"], category=row["category"],
        quantity=row["quantity"], unit=row["unit"],
        storage_location_id=row["storage_location_id"],
        purchase_date=_parse_d(row["purchase_date"]),
        estimated_use_by_date=_parse_d(row["estimated_use_by_date"]),
        label_expiry_date=_parse_d(row["label_expiry_date"]),
        opened_date=_parse_d(row["opened_date"]),
        price_paid=row["price_paid"], currency=row["currency"],
        source_event_id=row["source_event_id"], confidence=row["confidence"],
        image_crop_path=row["image_crop_path"], status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now(),
    )


def _parse_d(val: str | None) -> date | None:
    if val is None:
        return None
    try:
        return date.fromisoformat(val)
    except (ValueError, TypeError):
        return None


def _row_to_list(row: sqlite3.Row, conn: sqlite3.Connection) -> ShoppingList:
    item_rows = conn.execute(
        "SELECT * FROM shopping_list_items WHERE list_id = ?", (row["list_id"],)
    ).fetchall()
    items = []
    for ir in item_rows:
        items.append(ShoppingListItem(
            list_item_id=ir["item_id"], canonical_name=ir["canonical_name"],
            requested_quantity=ir["requested_quantity"], unit=ir["unit"],
            priority=ir["priority"], reason=ir["reason"], status=ir["status"],
            linked_inventory_lots=json.loads(ir["linked_lots"] or "[]"),
        ))
    return ShoppingList(
        list_id=row["list_id"], name=row["name"], goal=row["goal"],
        is_active=bool(row["is_active"]), items=items,
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now(),
    )


def _row_to_location(row: sqlite3.Row) -> HouseholdLocation:
    return HouseholdLocation(
        location_id=row["location_id"], name=row["name"],
        parent_location_id=row["parent_location_id"],
        location_type=row["location_type"], photo_path=row["photo_path"],
        notes=row["notes"],
    )


def _row_to_movement(row: sqlite3.Row) -> MovementEvent:
    return MovementEvent(
        movement_id=row["movement_id"], lot_id=row["lot_id"],
        from_location_id=row["from_location_id"],
        to_location_id=row["to_location_id"],
        timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.now(),
        source=row["source"], confidence=row["confidence"],
    )


def _row_to_price(row: sqlite3.Row) -> PriceObservation:
    return PriceObservation(
        price_id=row["price_id"], canonical_name=row["canonical_name"],
        quantity=row["quantity"], unit=row["unit"], price=row["price"],
        currency=row["currency"], store_name=row["store_name"],
        store_id=row["store_id"],
        observation_date=_parse_d(row["observation_date"]),
        source_event_id=row["source_event_id"], notes=row["notes"],
    )


def _row_to_store(row: sqlite3.Row) -> Store:
    return Store(
        store_id=row["store_id"], name=row["name"],
        location=row["location"], store_type=row["store_type"],
        notes=row["notes"],
    )


def _row_to_trace(row: sqlite3.Row) -> Trace:
    return Trace(
        trace_id=row["trace_id"], input_type=row["input_type"],
        user_goal=row["user_goal"],
        redacted_user_request=row["redacted_user_request"],
        perception=json.loads(row["perception"] or "{}"),
        inventory_context=json.loads(row["inventory_context"] or "{}"),
        decision=json.loads(row["decision"] or "{}"),
        proposed_tool_calls=[
            _dict_to_tc(t) for t in json.loads(row["proposed_tool_calls"] or "[]")
        ],
        human_confirmation=row["human_confirmation"],
        final_response=row["final_response"],
        timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.now(),
    )


def _row_to_purchase(row: sqlite3.Row) -> PurchaseEvent:
    return PurchaseEvent(
        event_id=row["event_id"],
        timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.now(),
        canonical_name=row["canonical_name"], quantity=row["quantity"],
        unit=row["unit"], total_price=row["total_price"],
        currency=row["currency"], source_type=row["source_type"],
        store_name=row["store_name"], raw_text=row["raw_text"],
        source_file_path=row["source_file_path"],
        confirmed=bool(row["confirmed"]),
    )


from shopstack.schemas.models import ToolCall as _ToolCall


def _dict_to_tc(d: dict) -> _ToolCall:
    return _ToolCall(**d)
