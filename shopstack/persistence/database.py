from __future__ import annotations

import json
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from shopstack.config import settings
from shopstack.schemas.models import (
    FindFeedback,
    HouseholdObject,
    InventoryEvent,
    InventoryLot,
    HouseholdLocation,
    MovementEvent,
    ObjectNote,
    ObjectSighting,
    new_id,
    PriceObservation,
    PurchaseEvent,
    ShoppingList,
    ShoppingListItem,
    Store,
    Trace,
    ReconciliationEvent,
    PreferenceSignal,
)


class Database:
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path if db_path is not None else settings.db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # Per-thread sqlite3 connections.  ``sqlite3.Connection`` is not
        # safe to share across threads — even with ``check_same_thread=
        # False`` concurrent ``execute`` + ``commit`` from anyio worker
        # threads corrupts cursor state and surfaces as
        # ``InterfaceError: bad parameter or other API misuse`` or
        # ``NoneType`` from ``fetchone()`` deep in the call stack.
        # Each thread opens its own connection to the same file;
        # WAL mode serialises writes across them.
        self._local = threading.local()
        self._init_lock = threading.Lock()
        self._init_db()

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.db_path, check_same_thread=True)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("PRAGMA foreign_keys=ON")
            self._local.conn = c
        return c

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

            CREATE TABLE IF NOT EXISTS household_objects (
                object_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                object_type TEXT DEFAULT 'other',
                category TEXT DEFAULT '',
                owner_name TEXT,
                home_location_id TEXT,
                current_location_id TEXT,
                linked_lot_id TEXT,
                status TEXT DEFAULT 'active',
                importance TEXT DEFAULT 'normal',
                notes TEXT,
                created_at TEXT,
                updated_at TEXT,
                user_id TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_household_objects_user_name
                ON household_objects(user_id, canonical_name);

            CREATE TABLE IF NOT EXISTS object_sightings (
                sighting_id TEXT PRIMARY KEY,
                object_id TEXT NOT NULL,
                location_id TEXT NOT NULL,
                timestamp TEXT,
                source TEXT DEFAULT 'manual',
                confidence REAL DEFAULT 1.0,
                context TEXT,
                notes TEXT,
                photo_path TEXT,
                trace_id TEXT,
                user_id TEXT DEFAULT '',
                FOREIGN KEY (object_id) REFERENCES household_objects(object_id)
            );
            CREATE INDEX IF NOT EXISTS idx_object_sightings_object_time
                ON object_sightings(object_id, timestamp);

            CREATE TABLE IF NOT EXISTS object_notes (
                note_id TEXT PRIMARY KEY,
                object_id TEXT NOT NULL,
                note_text TEXT NOT NULL,
                timestamp TEXT,
                tags TEXT DEFAULT '[]',
                location_id TEXT,
                source TEXT DEFAULT 'manual',
                user_id TEXT DEFAULT '',
                FOREIGN KEY (object_id) REFERENCES household_objects(object_id)
            );
            CREATE INDEX IF NOT EXISTS idx_object_notes_object_time
                ON object_notes(object_id, timestamp);

            CREATE TABLE IF NOT EXISTS find_feedback (
                feedback_id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                feedback TEXT NOT NULL,
                object_id TEXT,
                lot_id TEXT,
                suggested_location_id TEXT,
                actual_location_id TEXT,
                notes TEXT,
                timestamp TEXT,
                user_id TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_find_feedback_user_query
                ON find_feedback(user_id, query);

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

            CREATE TABLE IF NOT EXISTS market_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_category TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                record_count INTEGER DEFAULT 0,
                analytics TEXT DEFAULT '{}',
                freshness_context TEXT DEFAULT 'unknown',
                stored_at TEXT
            );

            CREATE TABLE IF NOT EXISTS market_records (
                record_id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                raw_name TEXT NOT NULL,
                canonical_name TEXT NOT NULL,
                description TEXT DEFAULT '',
                raw_size TEXT DEFAULT '',
                normalized_quantity REAL,
                normalized_unit TEXT,
                package_count INTEGER DEFAULT 1,
                is_combo INTEGER DEFAULT 0,
                is_weight_based INTEGER DEFAULT 0,
                is_piece_based INTEGER DEFAULT 0,
                is_size_class INTEGER DEFAULT 0,
                size_class TEXT DEFAULT '',
                price_inr REAL DEFAULT 0.0,
                mrp_inr REAL DEFAULT 0.0,
                discount_percent_displayed REAL DEFAULT 0.0,
                discount_amount_inr REAL DEFAULT 0.0,
                computed_discount_percent REAL DEFAULT 0.0,
                availability TEXT DEFAULT '',
                is_available INTEGER DEFAULT 1,
                tag TEXT DEFAULT '',
                is_ad INTEGER DEFAULT 0,
                is_upgrade INTEGER DEFAULT 0,
                card_index INTEGER DEFAULT 0,
                delivery_time TEXT DEFAULT '',
                price_per_kg REAL,
                price_per_100g REAL,
                price_per_piece REAL,
                normalization_warnings TEXT DEFAULT '',
                variety TEXT DEFAULT '',
                brand TEXT DEFAULT '',
                FOREIGN KEY (snapshot_id) REFERENCES market_snapshots(snapshot_id)
            );

            CREATE TABLE IF NOT EXISTS market_record_components (
                component_id TEXT PRIMARY KEY,
                record_id TEXT NOT NULL,
                component_name TEXT NOT NULL,
                FOREIGN KEY (record_id) REFERENCES market_records(record_id)
            );

            CREATE TABLE IF NOT EXISTS reconciliation_events (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT,
                canonical_name TEXT NOT NULL,
                planned_action TEXT NOT NULL,
                actual_action TEXT NOT NULL,
                quantity REAL DEFAULT 0.0,
                unit TEXT DEFAULT 'unit',
                price_paid REAL,
                planned_price REAL,
                substituted_with TEXT,
                notes TEXT,
                source TEXT DEFAULT 'manual',
                user_id TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS preference_signals (
                signal_id TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                value TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                source TEXT DEFAULT 'observed',
                created_at TEXT,
                updated_at TEXT,
                user_id TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS inventory_events (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                lot_id TEXT DEFAULT '',
                canonical_name TEXT DEFAULT '',
                action TEXT NOT NULL,
                quantity_before REAL,
                quantity_after REAL,
                quantity_delta REAL,
                unit TEXT DEFAULT '',
                location_from TEXT,
                location_to TEXT,
                source TEXT DEFAULT 'manual',
                notes TEXT,
                user_id TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS households (
                household_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                notes TEXT DEFAULT ''
            );

            -- ── Phase 10: household_members (multi-household permissioning) ──
            -- A user is *in* zero or more households with a role.
            -- One row per (household_id, user_id) pair. Composite
            -- primary key prevents duplicate memberships.
            CREATE TABLE IF NOT EXISTS household_members (
                household_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                joined_at TEXT NOT NULL,
                PRIMARY KEY (household_id, user_id),
                FOREIGN KEY (household_id) REFERENCES households(household_id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_household_members_user
                ON household_members(user_id);

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

            -- ── Object Trail: negative memory (places where items are confirmed NOT to be) ──
            CREATE TABLE IF NOT EXISTS negative_memory (
                memory_id TEXT PRIMARY KEY,
                lot_id TEXT NOT NULL,
                location_id TEXT NOT NULL,
                location_name TEXT DEFAULT '',
                confirmed_at TEXT NOT NULL,
                source TEXT DEFAULT 'user_feedback',
                confidence REAL DEFAULT 1.0,
                user_id TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_negative_memory_lot
                ON negative_memory(lot_id);

            -- ── Object Trail: person associations (who owns/uses an item) ──
            CREATE TABLE IF NOT EXISTS person_associations (
                association_id TEXT PRIMARY KEY,
                lot_id TEXT NOT NULL,
                person_id TEXT NOT NULL,
                person_name TEXT NOT NULL,
                relationship TEXT DEFAULT 'owner',
                confidence REAL DEFAULT 1.0,
                user_id TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_person_associations_lot
                ON person_associations(lot_id);

            -- ── Condition / damage detection (Task 4) ──
            -- One row per observation. Multiple rows per lot over time
            -- are expected; the service aggregates them into a
            -- ConditionAggregate for the UI.
            CREATE TABLE IF NOT EXISTS condition_events (
                event_id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                lot_id TEXT NOT NULL,
                canonical_name TEXT DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'other',
                severity TEXT NOT NULL DEFAULT 'worn',
                confidence REAL DEFAULT 0.5,
                description TEXT DEFAULT '',
                source TEXT DEFAULT 'user_report',
                image_path TEXT,
                user_confirmed INTEGER DEFAULT 0,
                closed_at TEXT,
                user_id TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_condition_events_lot
                ON condition_events(lot_id);
            CREATE INDEX IF NOT EXISTS idx_condition_events_severity
                ON condition_events(severity);
        """)
        self._migrate_market_snapshot_schema()
        self._migrate_add_user_scoping()
        self._migrate_backfill_household_owners()
        self._seed_locations()
        self._seed_default_household()
        self._apply_trace_retention_policy()
        self.conn.commit()

    def _migrate_market_snapshot_schema(self) -> None:
        rows = self.conn.execute("PRAGMA table_info(market_snapshots)").fetchall()
        existing_cols = {r["name"] for r in rows}
        migrations: list[tuple[str, str]] = [
            ("record_count", "INTEGER DEFAULT 0"),
            ("analytics", "TEXT DEFAULT '{}'"),
            ("freshness_context", "TEXT DEFAULT 'unknown'"),
            ("stored_at", "TEXT"),
        ]
        for col_name, decl in migrations:
            if col_name not in existing_cols:
                self.conn.execute(f"ALTER TABLE market_snapshots ADD COLUMN {col_name} {decl}")

    def _migrate_add_user_scoping(self) -> None:
        tables = ["inventory_lots", "purchase_events", "shopping_lists", "traces", "price_observations"]
        for table in tables:
            try:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN user_id TEXT DEFAULT ''")
            except sqlite3.OperationalError as exc:
                message = str(exc).lower()
                if "duplicate column name" in message or "already exists" in message:
                    continue
                raise

    def _migrate_backfill_household_owners(self) -> None:
        """Backfill owner memberships for any pre-existing households.

        For each household that exists in the ``households``
        table but has no members, add the default user as
        the owner. This keeps the migration idempotent: running
        on a fresh install is a no-op (the seeder does it);
        running on an existing install backfills the gap.
        """
        from datetime import datetime
        now = datetime.now().isoformat()
        rows = self.conn.execute(
            "SELECT h.household_id FROM households h "
            "WHERE NOT EXISTS (SELECT 1 FROM household_members m "
            "WHERE m.household_id = h.household_id)"
        ).fetchall()
        for row in rows:
            hid = row["household_id"]
            self.conn.execute(
                "INSERT OR IGNORE INTO household_members "
                "(household_id, user_id, role, joined_at) "
                "VALUES (?, ?, ?, ?)",
                (hid, hid, "owner", now),
            )
        if rows:
            self.conn.commit()

    # ── Active household tracking ────────────────────────────────

    @property
    def active_household_id(self) -> str:
        """Get the currently active household ID, or default if none set.

        Returns ``""`` when explicitly set to empty (disabling user_id
        filtering), or ``settings.default_household_user_id`` when no
        household has ever been selected.
        """
        stored = self.get_config_value("active_household_id", "")
        # If the config key exists at all (including with empty value), return its value.
        # This allows callers to opt out of household scoping by setting to "".
        has_key = self.conn.execute(
            "SELECT COUNT(*) FROM app_config WHERE key = 'active_household_id'"
        ).fetchone()[0]
        if has_key:
            return stored
        return settings.default_household_user_id

    @active_household_id.setter
    def active_household_id(self, household_id: str) -> None:
        self.set_config_value("active_household_id", household_id)

    # ── Household CRUD ────────────────────────────────────────────

    def list_households(self) -> list[dict[str, str]]:
        """List all registered households with their IDs and names."""
        rows = self.conn.execute(
            "SELECT household_id, name, created_at, notes FROM households ORDER BY created_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def add_household(self, household_id: str, name: str, notes: str = "") -> bool:
        """Register a new household. Returns True if created, False if already exists."""
        from datetime import datetime
        now = datetime.now().isoformat()
        try:
            self.conn.execute(
                "INSERT INTO households (household_id, name, created_at, updated_at, notes) VALUES (?, ?, ?, ?, ?)",
                (household_id, name, now, now, notes),
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def remove_household(self, household_id: str) -> bool:
        """Remove a household registration."""
        try:
            self.conn.execute(
                "DELETE FROM households WHERE household_id = ?", (household_id,)
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    # ── Household members (Phase 10 #1) ──────────────────────────

    def list_household_members(self, household_id: str) -> list[dict[str, str]]:
        """Return all members of a household, oldest first.

        Each dict: ``{"household_id", "user_id", "role", "joined_at"}``.
        Empty list when the household has no members.
        """
        rows = self.conn.execute(
            "SELECT household_id, user_id, role, joined_at "
            "FROM household_members WHERE household_id = ? "
            "ORDER BY joined_at ASC",
            (household_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def list_households_for_user(self, user_id: str) -> list[dict[str, str]]:
        """Return all households a user is a member of.

        Each dict: ``{"household_id", "name", "role", "joined_at"}``.
        Empty list when the user is in no households.
        """
        rows = self.conn.execute(
            "SELECT h.household_id, h.name, m.role, m.joined_at "
            "FROM households h JOIN household_members m "
            "ON h.household_id = m.household_id "
            "WHERE m.user_id = ? "
            "ORDER BY m.joined_at ASC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_household_member(
        self, household_id: str, user_id: str
    ) -> dict[str, str] | None:
        """Return the membership row for (household, user), or None."""
        row = self.conn.execute(
            "SELECT household_id, user_id, role, joined_at "
            "FROM household_members "
            "WHERE household_id = ? AND user_id = ?",
            (household_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    def add_household_member(
        self, household_id: str, user_id: str, role: str = "member"
    ) -> bool:
        """Add ``user_id`` to ``household_id`` with the given role.

        Roles: ``"owner"`` (full control), ``"member"`` (read+write),
        ``"guest"`` (read-only). Returns True if added, False if
        already a member or the household doesn't exist.
        """
        from datetime import datetime
        if role not in ("owner", "member", "guest"):
            return False
        # Verify household exists
        exists = self.conn.execute(
            "SELECT 1 FROM households WHERE household_id = ?", (household_id,)
        ).fetchone()
        if not exists:
            return False
        try:
            self.conn.execute(
                "INSERT INTO household_members (household_id, user_id, role, joined_at) "
                "VALUES (?, ?, ?, ?)",
                (household_id, user_id, role, datetime.now().isoformat()),
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def remove_household_member(self, household_id: str, user_id: str) -> bool:
        """Remove ``user_id`` from ``household_id``.

        Refuses to remove the last owner. Returns True on
        success, False if the user wasn't a member or
        removing them would orphan the household.
        """
        # Disallow removing the last owner
        if self.get_household_member(household_id, user_id) is None:
            return False
        if self._is_last_owner(household_id, user_id):
            return False
        try:
            self.conn.execute(
                "DELETE FROM household_members "
                "WHERE household_id = ? AND user_id = ?",
                (household_id, user_id),
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def update_household_member_role(
        self, household_id: str, user_id: str, new_role: str
    ) -> bool:
        """Change ``user_id``'s role in ``household_id``.

        Refuses to demote the last owner. Returns True on
        success, False if the role is invalid or the demotion
        would orphan the household.
        """
        if new_role not in ("owner", "member", "guest"):
            return False
        if self.get_household_member(household_id, user_id) is None:
            return False
        if new_role != "owner" and self._is_last_owner(household_id, user_id):
            return False
        try:
            self.conn.execute(
                "UPDATE household_members SET role = ? "
                "WHERE household_id = ? AND user_id = ?",
                (new_role, household_id, user_id),
            )
            self.conn.commit()
            return True
        except Exception:
            return False

    def _is_last_owner(self, household_id: str, user_id: str) -> bool:
        """True if ``user_id`` is the only owner of ``household_id``."""
        member = self.get_household_member(household_id, user_id)
        if not member or member.get("role") != "owner":
            return False
        rows = self.conn.execute(
            "SELECT user_id FROM household_members "
            "WHERE household_id = ? AND role = 'owner'",
            (household_id,),
        ).fetchall()
        return len(rows) == 1 and rows[0]["user_id"] == user_id

    def _seed_default_household(self) -> None:
        """Ensure the default household + owner member exist.

        Phase 10 #1: when the default household is created, we
        also add the default user_id as its owner. This means
        every existing user (and every fresh install) has at
        least one household they own — no permission denials
        on first run.
        """
        household_id = settings.default_household_user_id
        existing = self.conn.execute(
            "SELECT COUNT(*) FROM households WHERE household_id = ?", (household_id,)
        ).fetchone()[0]
        if existing == 0:
            now = datetime.now().isoformat()
            self.conn.execute(
                "INSERT INTO households (household_id, name, created_at, updated_at, notes) VALUES (?, ?, ?, ?, ?)",
                (household_id, "Default Household", now, now,
                 "Default household created automatically. Use the household switcher to add more."),
            )
        # Always ensure the default user is at least a member
        # of the default household (idempotent — INSERT OR IGNORE).
        # The ``datetime`` reference below relies on the module-level
        # import (line 6) — a local import in the ``if`` block above
        # would shadow it and cause an UnboundLocalError on the second
        # call (when ``existing > 0`` skips the import).
        self.conn.execute(
            "INSERT OR IGNORE INTO household_members "
            "(household_id, user_id, role, joined_at) VALUES (?, ?, ?, ?)",
            (household_id, household_id, "owner", datetime.now().isoformat()),
        )
        # Mark as active
        self.set_config_value("active_household_id", household_id)
        self.conn.commit()

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

    # --- Trace retention policy ---

    def _apply_trace_retention_policy(self) -> None:
        max_rows = max(0, settings.trace_max_rows)
        ttl_days = settings.trace_ttl_days
        if max_rows:
            self.prune_traces(max_rows=max_rows)
        if ttl_days:
            self.prune_traces(ttl_days=ttl_days)

    def prune_traces(self, max_rows: int | None = None, ttl_days: int | None = None) -> int:
        removed = 0
        if max_rows is not None and max_rows > 0:
            cursor = self.conn.execute(
                """
                DELETE FROM traces
                WHERE rowid NOT IN (
                    SELECT rowid FROM traces
                    ORDER BY datetime(timestamp) DESC, rowid DESC LIMIT ?
                )
                """,
                (max_rows,),
            )
            removed += cursor.rowcount

        if ttl_days is not None and ttl_days > 0:
            cutoff = (datetime.now() - timedelta(days=ttl_days)).isoformat()
            cursor = self.conn.execute(
                "DELETE FROM traces WHERE datetime(timestamp) < datetime(?)",
                (cutoff,),
            )
            removed += cursor.rowcount

        self.conn.commit()
        return removed

    def get_trace_by_id(self, trace_id: str, user_id: str = "") -> Trace | None:
        target = (trace_id or "").strip()
        if not target:
            return None
        query = "SELECT * FROM traces WHERE trace_id = ?"
        params: list[str] = [target]
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        row = self.conn.execute(query, params).fetchone()
        return _row_to_trace(row) if row else None

    # --- Inventory CRUD ---

    def add_inventory_lot(self, lot: InventoryLot, user_id: str = "") -> InventoryLot:
        # ── Phase 11: permission gate (supersession-safe additive check) ──
        # The unwrapped behavior is preserved; we just fail closed
        # on permission denial.
        from shopstack.services.permissions import require_write as _rw
        if not user_id:
            user_id = self.active_household_id
        # InventoryLot.user_id is the household scope for this lot. If
        # the caller did not set it on the lot, default to the writer's
        # user_id — that is the household they are writing to. The writer
        # must be a member of the target household with write access.
        target_household = lot.user_id or user_id
        _rw(user_id, target_household, self)
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
                target_household,
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
        # DATA-1 fix (2026-06-15): an empty user_id previously returned
        # ALL inventory across every household — a cross-household data
        # leak when a caller forgot to pass user_id. Now an empty user_id
        # falls back to the active household, so the default behavior is
        # always scoped. Callers that truly want unscoped access (admin
        # tools) must pass user_id=None explicitly.
        if user_id == "":
            user_id = self.active_household_id
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

    def consume_inventory(self, lot_id: str, quantity: float, user_id: str = "") -> InventoryLot | None:
        # ── Phase 11: permission gate (additive, supersession-safe) ──
        # 2026-06-14 fix: previous call had its arguments swapped — it
        # asked "can lot.user_id write to active_household_id" instead
        # of "can the active user write to the lot's household". That
        # made the check a no-op whenever lot.user_id was the active
        # household. We now follow the canonical add_inventory_lot
        # pattern: deduce the target household from the lot, then
        # authorize the writer against that target.
        from shopstack.services.permissions import require_write as _rw
        if quantity < 0:
            raise ValueError("quantity must be greater than 0")
        lot = self.get_inventory_lot(lot_id)
        if not lot:
            return None
        if not user_id:
            user_id = self.active_household_id
        target_household = lot.user_id or user_id
        _rw(user_id, target_household, self)
        # Capture pre-mutation state for undo (Phase 12 R2.6).
        # The undo ledger is opt-in: handlers register after
        # success. The pre-state is the lot's current quantity.
        _undo_before = {
            "lot_id": lot.lot_id,
            "quantity": lot.quantity,
            "user_id": user_id,
        }
        new_qty = max(0.0, lot.quantity - quantity)
        status = lot.status
        if new_qty <= 0:
            new_qty = 0
            status = "used"
        elif new_qty < lot.quantity * 0.2:
            status = "low"
        result = self.update_inventory_lot(lot_id, {"quantity": new_qty, "status": status})
        # Register for undo (best-effort: never breaks the write).
        if result is not None:
            try:
                from shopstack.services.undo_ledger import get_ledger
                get_ledger().register(
                    household_id=target_household,
                    kind="consume_inventory",
                    before=_undo_before,
                    after={"lot_id": lot_id, "quantity": new_qty},
                    description=f"Consumed {quantity:g} {lot.unit} of {lot.display_name}",
                )
            except Exception:
                pass
        return result

    def mark_list_complete(self, list_id: str) -> None:
        self.conn.execute(
            "UPDATE shopping_lists SET is_active = 0, updated_at = ? WHERE list_id = ?",
            (datetime.now().isoformat(), list_id),
        )
        self.conn.commit()

    # --- Shopping List CRUD ---

    def create_shopping_list(
        self,
        name: str = "Shopping List",
        goal: str = "",
        user_id: str = "",
        list_id: str | None = None,
    ) -> ShoppingList:
        """Create a new shopping list. By default the list_id is auto-generated;
        callers (e.g. backup restore) can pass ``list_id`` to preserve an
        existing id from the source DB.
        """
        # DATA-1 fix (2026-06-15): an empty user_id defaults to the active
        # household so writes and reads with the same empty user_id stay
        # consistent and scoped (never cross-household).
        if user_id == "":
            user_id = self.active_household_id
        if list_id is not None:
            sl = ShoppingList(name=name, goal=goal)
            sl.list_id = list_id
        else:
            sl = ShoppingList(name=name, goal=goal)
        self.conn.execute(
            "INSERT INTO shopping_lists (list_id, name, created_at, updated_at, goal, is_active, user_id) VALUES (?, ?, ?, ?, ?, 1, ?)",
            (sl.list_id, sl.name, sl.created_at.isoformat(), sl.updated_at.isoformat(), sl.goal, user_id),
        )
        self.conn.commit()
        return sl

    def get_active_shopping_list(self, user_id: str = "") -> ShoppingList | None:
        # DATA-1 fix (2026-06-15): empty user_id falls back to active
        # household so the default read is always scoped (see get_inventory).
        if user_id == "":
            user_id = self.active_household_id
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

    def add_list_item(self, list_id: str, item: ShoppingListItem, user_id: str = "") -> ShoppingListItem:
        # ── Phase 11: permission gate ──
        # 2026-06-14 fix: previously used active_household_id for both
        # args, so the check always passed for the active owner. Now
        # deduces the target household from the shopping list's own
        # user_id column (the canonical scope) and authorizes the
        # writer against that target. Backward compatible: callers
        # that don't pass user_id fall back to active_household_id.
        from shopstack.services.permissions import require_write as _rw
        if not user_id:
            user_id = self.active_household_id
        list_row = self.conn.execute(
            "SELECT user_id FROM shopping_lists WHERE list_id = ?", (list_id,)
        ).fetchone()
        target_household = (list_row["user_id"] if list_row else "") or user_id
        _rw(user_id, target_household, self)
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

    def update_location_photo(self, location_id: str, photo_path: str | None) -> bool:
        """Set or clear the photo_path for a household location.

        Args:
            location_id: The location to update.
            photo_path: Absolute path to a photo file, or None to clear.

        Returns:
            True if the location was updated, False if it does not exist.
        """
        row = self.conn.execute(
            "SELECT 1 FROM household_locations WHERE location_id = ?", (location_id,)
        ).fetchone()
        if not row:
            return False
        self.conn.execute(
            "UPDATE household_locations SET photo_path = ? WHERE location_id = ?",
            (photo_path, location_id),
        )
        self.conn.commit()
        return True

    # --- Movements ---

    def record_movement(self, movement: MovementEvent, user_id: str = "") -> MovementEvent:
        # ── Phase 11: permission gate ──
        # 2026-06-14 fix: previously used active_household_id for both
        # args (always passed for the active owner). Now deduces the
        # target household from the lot being moved (the lot's user_id
        # is the canonical household scope) and authorizes the writer
        # against that target. Backward compatible.
        from shopstack.services.permissions import require_write as _rw
        if not user_id:
            user_id = self.active_household_id
        lot = self.get_inventory_lot(movement.lot_id)
        target_household = (lot.user_id if lot else "") or user_id
        _rw(user_id, target_household, self)
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

    def get_movements_in_window(
        self,
        user_id: str = "",
        since: str | None = None,
        until: str | None = None,
        limit: int = 500,
    ) -> list[MovementEvent]:
        """Return movements within a time window, scoped to a household via
        the linked inventory_lots.user_id column.

        Args:
            user_id: household id; empty string returns all rows.
            since: ISO datetime lower bound (inclusive). None = no lower bound.
            until: ISO datetime upper bound (exclusive). None = no upper bound.
            limit: hard ceiling on rows returned.
        """
        query = (
            "SELECT me.* FROM movement_events me "
            "JOIN inventory_lots il ON il.lot_id = me.lot_id "
            "WHERE 1=1"
        )
        params: list[Any] = []
        if user_id:
            query += " AND il.user_id = ?"
            params.append(user_id)
        if since:
            query += " AND me.timestamp >= ?"
            params.append(since)
        if until:
            query += " AND me.timestamp < ?"
            params.append(until)
        query += " ORDER BY me.timestamp DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_movement(r) for r in rows]

    # --- Household Objects / ShopFind memory ---

    def add_household_object(self, obj: HouseholdObject, user_id: str = "") -> HouseholdObject:
        if not user_id:
            user_id = self.active_household_id
        self.conn.execute(
            """
            INSERT INTO household_objects
            (object_id, canonical_name, display_name, object_type, category, owner_name,
             home_location_id, current_location_id, linked_lot_id, status, importance,
             notes, created_at, updated_at, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                obj.object_id, obj.canonical_name, obj.display_name, obj.object_type,
                obj.category, obj.owner_name, obj.home_location_id,
                obj.current_location_id, obj.linked_lot_id, obj.status,
                obj.importance, obj.notes, obj.created_at.isoformat(),
                obj.updated_at.isoformat(), user_id,
            ),
        )
        self.conn.commit()
        return obj

    def get_household_object(self, object_id: str, user_id: str = "") -> HouseholdObject | None:
        query = "SELECT * FROM household_objects WHERE object_id = ?"
        params: list[Any] = [object_id]
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        row = self.conn.execute(query, params).fetchone()
        return _row_to_household_object(row) if row else None

    def get_household_objects(self, user_id: str = "") -> list[HouseholdObject]:
        query = "SELECT * FROM household_objects"
        params: list[Any] = []
        if user_id:
            query += " WHERE user_id = ?"
            params.append(user_id)
        query += " ORDER BY updated_at DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_household_object(r) for r in rows]

    def update_household_object(self, object_id: str, updates: dict[str, Any], user_id: str = "") -> HouseholdObject | None:
        allowed = {
            "canonical_name", "display_name", "object_type", "category", "owner_name",
            "home_location_id", "current_location_id", "linked_lot_id", "status",
            "importance", "notes",
        }
        clean = {k: v for k, v in updates.items() if k in allowed}
        if not clean:
            return self.get_household_object(object_id, user_id=user_id)
        clean["updated_at"] = datetime.now().isoformat()
        parts = ", ".join(f"{key} = ?" for key in clean)
        params = list(clean.values()) + [object_id]
        query = f"UPDATE household_objects SET {parts} WHERE object_id = ?"
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        self.conn.execute(query, params)
        self.conn.commit()
        return self.get_household_object(object_id, user_id=user_id)

    def record_object_sighting(self, sighting: ObjectSighting, user_id: str = "") -> ObjectSighting:
        if not user_id:
            user_id = self.active_household_id
        self.conn.execute(
            """
            INSERT INTO object_sightings
            (sighting_id, object_id, location_id, timestamp, source, confidence,
             context, notes, photo_path, trace_id, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sighting.sighting_id, sighting.object_id, sighting.location_id,
                sighting.timestamp.isoformat(), sighting.source, sighting.confidence,
                sighting.context, sighting.notes, sighting.photo_path, sighting.trace_id,
                user_id,
            ),
        )
        self.update_household_object(
            sighting.object_id,
            {"current_location_id": sighting.location_id},
            user_id=user_id,
        )
        self.conn.commit()
        return sighting

    def get_object_sightings(self, object_id: str, user_id: str = "") -> list[ObjectSighting]:
        query = "SELECT * FROM object_sightings WHERE object_id = ?"
        params: list[Any] = [object_id]
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY timestamp DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_object_sighting(r) for r in rows]

    def add_object_note(self, note: ObjectNote, user_id: str = "") -> ObjectNote:
        if not user_id:
            user_id = self.active_household_id
        self.conn.execute(
            """
            INSERT INTO object_notes
            (note_id, object_id, note_text, timestamp, tags, location_id, source, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                note.note_id, note.object_id, note.note_text,
                note.timestamp.isoformat(), json.dumps(note.tags), note.location_id,
                note.source, user_id,
            ),
        )
        self.conn.commit()
        return note

    def get_object_notes(self, object_id: str, user_id: str = "") -> list[ObjectNote]:
        query = "SELECT * FROM object_notes WHERE object_id = ?"
        params: list[Any] = [object_id]
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY timestamp DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_object_note(r) for r in rows]

    def record_find_feedback(self, feedback: FindFeedback, user_id: str = "") -> FindFeedback:
        if not user_id:
            user_id = self.active_household_id
        self.conn.execute(
            """
            INSERT INTO find_feedback
            (feedback_id, query, feedback, object_id, lot_id, suggested_location_id,
             actual_location_id, notes, timestamp, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                feedback.feedback_id, feedback.query, feedback.feedback,
                feedback.object_id, feedback.lot_id, feedback.suggested_location_id,
                feedback.actual_location_id, feedback.notes,
                feedback.timestamp.isoformat(), user_id,
            ),
        )
        self.conn.commit()
        return feedback

    def get_find_feedback(self, query: str = "", user_id: str = "") -> list[FindFeedback]:
        sql = "SELECT * FROM find_feedback WHERE 1=1"
        params: list[Any] = []
        if query:
            sql += " AND query = ?"
            params.append(query)
        if user_id:
            sql += " AND user_id = ?"
            params.append(user_id)
        sql += " ORDER BY timestamp DESC"
        rows = self.conn.execute(sql, params).fetchall()
        return [_row_to_find_feedback(r) for r in rows]

    # --- Negative Memory (Object Trail) ---

    def add_negative_memory(self, lot_id: str, location_id: str, location_name: str = "", source: str = "user_feedback", confidence: float = 1.0, user_id: str = "") -> dict:
        """Record that an item has been confirmed NOT to be at a location."""
        memory_id = f"negmem_{new_id()}"
        self.conn.execute(
            "INSERT INTO negative_memory (memory_id, lot_id, location_id, location_name, confirmed_at, source, confidence, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (memory_id, lot_id, location_id, location_name, datetime.now().isoformat(), source, confidence, user_id),
        )
        self.conn.commit()
        return {"memory_id": memory_id, "lot_id": lot_id, "location_id": location_id}

    def get_negative_memory_for_lot(self, lot_id: str) -> list[dict]:
        """Get all negative memory entries for a given lot."""
        rows = self.conn.execute(
            "SELECT * FROM negative_memory WHERE lot_id = ? ORDER BY confirmed_at DESC",
            (lot_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_negative_memory(self, memory_id: str) -> bool:
        """Remove a negative memory entry."""
        self.conn.execute("DELETE FROM negative_memory WHERE memory_id = ?", (memory_id,))
        self.conn.commit()
        return True

    # --- Person Associations (Object Trail) ---

    def add_person_association(self, lot_id: str, person_id: str, person_name: str, relationship: str = "owner", confidence: float = 1.0, user_id: str = "") -> dict:
        """Record a person association for an item."""
        association_id = f"personassoc_{new_id()}"
        self.conn.execute(
            "INSERT INTO person_associations (association_id, lot_id, person_id, person_name, relationship, confidence, user_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (association_id, lot_id, person_id, person_name, relationship, confidence, user_id),
        )
        self.conn.commit()
        return {"association_id": association_id, "lot_id": lot_id, "person_id": person_id}

    def get_person_associations_for_lot(self, lot_id: str) -> list[dict]:
        """Get all person associations for a given lot."""
        rows = self.conn.execute(
            "SELECT * FROM person_associations WHERE lot_id = ?",
            (lot_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_person_association(self, association_id: str) -> bool:
        """Remove a person association."""
        self.conn.execute("DELETE FROM person_associations WHERE association_id = ?", (association_id,))
        self.conn.commit()
        return True

    # --- Condition Events (Task 4: condition/damage detection) ---

    def add_condition_event(
        self,
        lot_id: str,
        kind: str,
        severity: str,
        canonical_name: str = "",
        confidence: float = 0.5,
        description: str = "",
        source: str = "user_report",
        image_path: str | None = None,
        user_confirmed: bool = False,
        user_id: str = "",
    ) -> str:
        """Record a condition observation for a lot.

        Returns:
            The generated event_id.
        """
        from shopstack.schemas.models import new_id as _new_id
        event_id = f"cond_{_new_id()}"
        self.conn.execute(
            """INSERT INTO condition_events
               (event_id, timestamp, lot_id, canonical_name, kind, severity,
                confidence, description, source, image_path, user_confirmed, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id, datetime.now().isoformat(),
                lot_id, canonical_name, kind, severity,
                confidence, description, source, image_path,
                1 if user_confirmed else 0, user_id,
            ),
        )
        self.conn.commit()
        return event_id

    def get_condition_events_for_lot(
        self,
        lot_id: str,
        include_closed: bool = True,
    ) -> list[dict]:
        """Get all condition events for a lot, newest first."""
        query = "SELECT * FROM condition_events WHERE lot_id = ?"
        if not include_closed:
            query += " AND closed_at IS NULL"
        query += " ORDER BY timestamp DESC"
        rows = self.conn.execute(query, (lot_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_open_condition_events(
        self,
        severity: str | None = None,
        limit: int = 100,
        user_id: str = "",
    ) -> list[dict]:
        """Get all open (un-closed) condition events, newest first."""
        query = "SELECT * FROM condition_events WHERE closed_at IS NULL"
        params: list[Any] = []
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def confirm_condition_event(self, event_id: str) -> bool:
        """Mark a condition event as user-confirmed."""
        self.conn.execute(
            "UPDATE condition_events SET user_confirmed = 1 WHERE event_id = ?",
            (event_id,),
        )
        self.conn.commit()
        return True

    def close_condition_event(self, event_id: str) -> bool:
        """Mark a condition event as closed (resolved or dismissed)."""
        self.conn.execute(
            "UPDATE condition_events SET closed_at = ? WHERE event_id = ?",
            (datetime.now().isoformat(), event_id),
        )
        self.conn.commit()
        return True

    def delete_condition_event(self, event_id: str) -> bool:
        """Permanently remove a condition event."""
        self.conn.execute(
            "DELETE FROM condition_events WHERE event_id = ?",
            (event_id,),
        )
        self.conn.commit()
        return True

    # --- Price Observations ---

    def record_price(self, price: PriceObservation, user_id: str = "") -> PriceObservation:
        # ── Phase 11: permission gate (additive, supersession-safe) ──
        from shopstack.services.permissions import require_write as _rw
        if not user_id:
            user_id = self.active_household_id
        _rw(user_id, user_id, self)
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
        if not user_id:
            user_id = self.active_household_id
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
        self.prune_traces(
            max_rows=max(0, settings.trace_max_rows),
            ttl_days=settings.trace_ttl_days,
        )
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
        # ── Phase 11: permission gate (additive, supersession-safe) ──
        from shopstack.services.permissions import require_write as _rw
        if not user_id:
            user_id = self.active_household_id
        _rw(user_id, user_id, self)
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

    # --- Reconciliation Events ---

    def add_reconciliation_event(self, event: ReconciliationEvent, user_id: str = "") -> ReconciliationEvent:
        # ── Phase 11: permission gate (additive, supersession-safe) ──
        from shopstack.services.permissions import require_write as _rw
        if not user_id:
            user_id = self.active_household_id
        _rw(user_id, user_id, self)
        self.conn.execute(
            "INSERT INTO reconciliation_events (event_id, timestamp, canonical_name, planned_action, actual_action, quantity, unit, price_paid, planned_price, substituted_with, notes, source, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (event.event_id, event.timestamp.isoformat(),
             event.canonical_name, event.planned_action, event.actual_action,
             event.quantity, event.unit, event.price_paid, event.planned_price,
             event.substituted_with, event.notes, event.source, user_id),
        )
        self.conn.commit()
        return event

    def get_reconciliation_events(self, canonical_name: str | None = None, limit: int = 20, user_id: str = "") -> list[ReconciliationEvent]:
        query = "SELECT * FROM reconciliation_events WHERE 1=1"
        params: list[str | int] = []
        if canonical_name:
            query += " AND canonical_name = ?"
            params.append(canonical_name)
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_reconciliation(r) for r in rows]

    # --- Inventory Events (audit trail) ---

    def record_inventory_event(self, event: InventoryEvent, user_id: str = "") -> InventoryEvent:
        self.conn.execute(
            """INSERT INTO inventory_events
               (event_id, timestamp, lot_id, canonical_name, action,
                quantity_before, quantity_after, quantity_delta, unit,
                location_from, location_to, source, notes, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.event_id, event.timestamp.isoformat(),
             event.lot_id, event.canonical_name, event.action,
             event.quantity_before, event.quantity_after, event.quantity_delta,
             event.unit, event.location_from, event.location_to,
             event.source, event.notes, user_id),
        )
        self.conn.commit()
        return event

    def get_inventory_events(
        self,
        canonical_name: str = "",
        lot_id: str = "",
        limit: int = 50,
        user_id: str = "",
        since: str | None = None,
        until: str | None = None,
    ) -> list[InventoryEvent]:
        query = "SELECT * FROM inventory_events"
        params: list[Any] = []
        conditions: list[str] = []
        if canonical_name:
            conditions.append("canonical_name = ?")
            params.append(canonical_name.lower())
        if lot_id:
            conditions.append("lot_id = ?")
            params.append(lot_id)
        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if since:
            conditions.append("timestamp >= ?")
            params.append(since)
        if until:
            conditions.append("timestamp < ?")
            params.append(until)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_inventory_event(r) for r in rows]

    def get_inventory_timeline(self, canonical_name: str, limit: int = 20) -> list[InventoryEvent]:
        return self.get_inventory_events(canonical_name=canonical_name, limit=limit)

    # --- Preference Signals ---

    def add_preference_signal(self, signal: PreferenceSignal, user_id: str = "") -> PreferenceSignal:
        # ── Phase 11: permission gate (additive, supersession-safe) ──
        from shopstack.services.permissions import require_write as _rw
        if not user_id:
            user_id = self.active_household_id
        _rw(user_id, user_id, self)
        self.conn.execute(
            "INSERT INTO preference_signals (signal_id, canonical_name, signal_type, value, confidence, source, created_at, updated_at, user_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (signal.signal_id, signal.canonical_name, signal.signal_type,
             signal.value, signal.confidence, signal.source,
             signal.created_at.isoformat(), signal.updated_at.isoformat(), user_id),
        )
        self.conn.commit()
        return signal

    def get_preference_signals(self, canonical_name: str | None = None, user_id: str = "") -> list[PreferenceSignal]:
        query = "SELECT * FROM preference_signals WHERE 1=1"
        params: list[str] = []
        if canonical_name:
            query += " AND canonical_name = ?"
            params.append(canonical_name)
        if user_id:
            query += " AND user_id = ?"
            params.append(user_id)
        query += " ORDER BY updated_at DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [_row_to_preference(r) for r in rows]

    def delete_preference_signal(self, signal_id: str) -> bool:
        cursor = self.conn.execute(
            "DELETE FROM preference_signals WHERE signal_id = ?",
            (signal_id,),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    # --- Market Snapshot Records ---

    def save_market_snapshot(self, snapshot) -> bool:
        from shopstack.market.schema import NormalizedMarketRecord, MarketSnapshot
        if not isinstance(snapshot, MarketSnapshot):
            return False

        self.conn.execute(
            """
            INSERT OR REPLACE INTO market_snapshots
            (snapshot_id, source, source_category, captured_at, record_count, analytics, freshness_context, stored_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.snapshot_id,
                snapshot.source,
                snapshot.source_category,
                snapshot.captured_at,
                len(snapshot.normalized_records),
                json.dumps(snapshot.analytics or {}, sort_keys=True),
                snapshot.analytics.get("freshness", "unknown") if isinstance(snapshot.analytics, dict) else "unknown",
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.execute("DELETE FROM market_record_components WHERE record_id IN (SELECT record_id FROM market_records WHERE snapshot_id = ?)", (snapshot.snapshot_id,))
        self.conn.execute("DELETE FROM market_records WHERE snapshot_id = ?", (snapshot.snapshot_id,))

        for idx, record in enumerate(snapshot.normalized_records):
            if not isinstance(record, NormalizedMarketRecord):
                continue
            record_id = f"{snapshot.snapshot_id}::{idx:05d}"
            self.conn.execute(
                """
                INSERT OR REPLACE INTO market_records (
                    record_id, snapshot_id, raw_name, canonical_name, description, raw_size, normalized_quantity,
                    normalized_unit, package_count, is_combo, is_weight_based, is_piece_based, is_size_class,
                    size_class, price_inr, mrp_inr, discount_percent_displayed, discount_amount_inr,
                    computed_discount_percent, availability, is_available, tag, is_ad, is_upgrade, card_index,
                    delivery_time, price_per_kg, price_per_100g, price_per_piece, normalization_warnings, variety, brand
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record_id,
                    snapshot.snapshot_id,
                    record.raw_name,
                    record.canonical_name,
                    record.description,
                    record.raw_size,
                    record.normalized_quantity,
                    record.normalized_unit,
                    record.package_count,
                    int(record.is_combo),
                    int(record.is_weight_based),
                    int(record.is_piece_based),
                    int(record.is_size_class),
                    record.size_class,
                    record.price_inr,
                    record.mrp_inr,
                    record.discount_percent_displayed,
                    record.discount_amount_inr,
                    record.computed_discount_percent,
                    record.availability,
                    int(record.is_available),
                    record.tag,
                    int(record.is_ad),
                    int(record.is_upgrade),
                    record.card_index,
                    record.delivery_time,
                    record.price_per_kg,
                    record.price_per_100g,
                    record.price_per_piece,
                    json.dumps(record.normalization_warnings or []),
                    record.variety,
                    record.brand,
                ),
            )
            self.conn.execute("DELETE FROM market_record_components WHERE record_id = ?", (record_id,))
            for component_name in record.component_names:
                component_id = f"{record_id}::{component_name}"
                self.conn.execute(
                    "INSERT OR IGNORE INTO market_record_components (component_id, record_id, component_name) VALUES (?, ?, ?)",
                    (component_id, record_id, component_name),
                )

        self.conn.commit()
        return True

    def get_market_snapshot(self, snapshot_id: str):
        from shopstack.market.schema import MarketSnapshot
        row = self.conn.execute(
            "SELECT snapshot_id, source, source_category, captured_at, analytics FROM market_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if not row:
            return None

        return MarketSnapshot(
            snapshot_id=row["snapshot_id"],
            source=row["source"],
            source_category=row["source_category"],
            captured_at=row["captured_at"],
            raw_records=[],
            normalized_records=self.get_market_records(snapshot_id),
            analytics=json.loads(row["analytics"] or "{}"),
        )

    def get_latest_market_snapshot(self, source: str):
        row = self.conn.execute(
            "SELECT snapshot_id FROM market_snapshots WHERE source = ? ORDER BY captured_at DESC LIMIT 1",
            (source,),
        ).fetchone()
        if not row:
            return None
        return self.get_market_snapshot(row["snapshot_id"])

    def get_market_records(self, snapshot_id: str) -> list:
        from shopstack.market.schema import NormalizedMarketRecord
        rows = self.conn.execute(
            "SELECT * FROM market_records WHERE snapshot_id = ? ORDER BY card_index ASC, raw_name ASC",
            (snapshot_id,),
        ).fetchall()

        snap_row = self.conn.execute(
            "SELECT source, source_category, captured_at FROM market_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()

        source = snap_row["source"] if snap_row else ""
        source_category = snap_row["source_category"] if snap_row else ""
        captured_at = snap_row["captured_at"] if snap_row else ""

        records: list[NormalizedMarketRecord] = []
        for row in rows:
            comp_rows = self.conn.execute(
                "SELECT component_name FROM market_record_components WHERE record_id = ? ORDER BY component_name ASC",
                (row["record_id"],),
            ).fetchall()
            components = [r["component_name"] for r in comp_rows]
            raw_warnings = row["normalization_warnings"]
            if isinstance(raw_warnings, str):
                try:
                    warnings = json.loads(raw_warnings)
                except json.JSONDecodeError:
                    warnings = []
            else:
                warnings = []
            records.append(
                NormalizedMarketRecord(
                    source=source,
                    source_category=source_category,
                    raw_name=row["raw_name"],
                    canonical_name=row["canonical_name"],
                    description=row["description"],
                    raw_size=row["raw_size"],
                    normalized_quantity=row["normalized_quantity"],
                    normalized_unit=row["normalized_unit"],
                    package_count=row["package_count"],
                    is_combo=bool(row["is_combo"]),
                    is_weight_based=bool(row["is_weight_based"]),
                    is_piece_based=bool(row["is_piece_based"]),
                    is_size_class=bool(row["is_size_class"]),
                    size_class=row["size_class"],
                    price_inr=row["price_inr"],
                    mrp_inr=row["mrp_inr"],
                    discount_percent_displayed=row["discount_percent_displayed"],
                    discount_amount_inr=row["discount_amount_inr"],
                    computed_discount_percent=row["computed_discount_percent"],
                    availability=row["availability"],
                    is_available=bool(row["is_available"]),
                    tag=row["tag"],
                    is_ad=bool(row["is_ad"]),
                    is_upgrade=bool(row["is_upgrade"]),
                    card_index=row["card_index"],
                    delivery_time=row["delivery_time"],
                    captured_at=captured_at,
                    snapshot_id=row["snapshot_id"],
                    price_per_kg=row["price_per_kg"],
                    price_per_100g=row["price_per_100g"],
                    price_per_piece=row["price_per_piece"],
                    normalization_warnings=warnings,
                    component_names=components,
                    variety=row["variety"],
                    brand=row["brand"],
                )
            )
        return records

    def get_records_by_canonical(self, canonical_name: str) -> list:
        from shopstack.market.schema import NormalizedMarketRecord
        # If normalized rows are requested without full context, use snapshot join in SQL.
        rows_with_snap = self.conn.execute(
            """
            SELECT mr.*, ms.source, ms.source_category, ms.captured_at
            FROM market_records AS mr
            JOIN market_snapshots AS ms ON ms.snapshot_id = mr.snapshot_id
            WHERE mr.canonical_name = ?
            ORDER BY ms.captured_at DESC
            """,
            (canonical_name,),
        ).fetchall()
        records: list[NormalizedMarketRecord] = []
        for row in rows_with_snap:
            raw_warnings = row["normalization_warnings"]
            if isinstance(raw_warnings, str):
                try:
                    warnings = json.loads(raw_warnings)
                except json.JSONDecodeError:
                    warnings = []
            else:
                warnings = []

            _comp_rows = self.conn.execute(
                "SELECT component_name FROM market_record_components WHERE record_id = ? ORDER BY component_name ASC",
                (row["record_id"],),
            ).fetchall()
            records.append(
                NormalizedMarketRecord(
                    source=row["source"],
                    source_category=row["source_category"],
                    raw_name=row["raw_name"],
                    canonical_name=row["canonical_name"],
                    description=row["description"],
                    raw_size=row["raw_size"],
                    normalized_quantity=row["normalized_quantity"],
                    normalized_unit=row["normalized_unit"],
                    package_count=row["package_count"],
                    is_combo=bool(row["is_combo"]),
                    is_weight_based=bool(row["is_weight_based"]),
                    is_piece_based=bool(row["is_piece_based"]),
                    is_size_class=bool(row["is_size_class"]),
                    size_class=row["size_class"],
                    price_inr=row["price_inr"],
                    mrp_inr=row["mrp_inr"],
                    discount_percent_displayed=row["discount_percent_displayed"],
                    discount_amount_inr=row["discount_amount_inr"],
                    computed_discount_percent=row["computed_discount_percent"],
                    availability=row["availability"],
                    is_available=bool(row["is_available"]),
                    tag=row["tag"],
                    is_ad=bool(row["is_ad"]),
                    is_upgrade=bool(row["is_upgrade"]),
                    card_index=row["card_index"],
                    delivery_time=row["delivery_time"],
                    captured_at=row["captured_at"],
                    snapshot_id=row["snapshot_id"],
                    price_per_kg=row["price_per_kg"],
                    price_per_100g=row["price_per_100g"],
                    price_per_piece=row["price_per_piece"],
                    normalization_warnings=warnings,
                    component_names=[r2["component_name"] for r2 in self.conn.execute(
                        "SELECT component_name FROM market_record_components WHERE record_id = ? ORDER BY component_name ASC",
                        (row["record_id"],),
                    ).fetchall()],
                    variety=row["variety"],
                    brand=row["brand"],
                )
            )
        return records

    def close(self) -> None:
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self):
        # Defensive cleanup: ensure sqlite connections are closed even if callers
        # forget an explicit ``close()`` (important during module reloads and
        # test teardown paths that recreate app_context).
        try:
            self.close()
        except Exception:
            # Never raise during finalization; mirror sqlite's permissive close
            # semantics when objects are already partially torn down.
            pass


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
        user_id=row["user_id"] if "user_id" in row.keys() else "",
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
    parsed = _parse_d(row["observation_date"])
    return PriceObservation(
        price_id=row["price_id"], canonical_name=row["canonical_name"],
        quantity=row["quantity"], unit=row["unit"], price=row["price"],
        currency=row["currency"], store_name=row["store_name"],
        store_id=row["store_id"],
        observation_date=parsed if parsed is not None else date.today(),
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


def _row_to_reconciliation(row: sqlite3.Row) -> ReconciliationEvent:
    return ReconciliationEvent(
        event_id=row["event_id"],
        timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.now(),
        canonical_name=row["canonical_name"],
        planned_action=row["planned_action"],
        actual_action=row["actual_action"],
        quantity=row["quantity"],
        unit=row["unit"],
        price_paid=row["price_paid"],
        planned_price=row["planned_price"],
        substituted_with=row["substituted_with"],
        notes=row["notes"],
        source=row["source"],
    )


def _row_to_preference(row: sqlite3.Row) -> PreferenceSignal:
    return PreferenceSignal(
        signal_id=row["signal_id"],
        canonical_name=row["canonical_name"],
        signal_type=row["signal_type"],
        value=row["value"],
        confidence=row["confidence"],
        source=row["source"],
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now(),
    )


def _row_to_inventory_event(row: sqlite3.Row) -> InventoryEvent:
    return InventoryEvent(
        event_id=row["event_id"],
        timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.now(),
        lot_id=row["lot_id"] or "",
        canonical_name=row["canonical_name"] or "",
        action=row["action"],
        quantity_before=row["quantity_before"] if row["quantity_before"] is not None else None,
        quantity_after=row["quantity_after"] if row["quantity_after"] is not None else None,
        quantity_delta=row["quantity_delta"] if row["quantity_delta"] is not None else None,
        unit=row["unit"] or "",
        location_from=row["location_from"],
        location_to=row["location_to"],
        source=row["source"] or "manual",
        notes=row["notes"],
    )


def _row_to_household_object(row: sqlite3.Row) -> HouseholdObject:
    return HouseholdObject(
        object_id=row["object_id"],
        canonical_name=row["canonical_name"],
        display_name=row["display_name"],
        object_type=row["object_type"] or "other",
        category=row["category"] or "",
        owner_name=row["owner_name"],
        home_location_id=row["home_location_id"],
        current_location_id=row["current_location_id"],
        linked_lot_id=row["linked_lot_id"],
        status=row["status"] or "active",
        importance=row["importance"] or "normal",
        notes=row["notes"],
        created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.now(),
        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.now(),
    )


def _row_to_object_sighting(row: sqlite3.Row) -> ObjectSighting:
    return ObjectSighting(
        sighting_id=row["sighting_id"],
        object_id=row["object_id"],
        location_id=row["location_id"],
        timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.now(),
        source=row["source"] or "manual",
        confidence=row["confidence"] if row["confidence"] is not None else 1.0,
        context=row["context"],
        notes=row["notes"],
        photo_path=row["photo_path"],
        trace_id=row["trace_id"],
    )


def _row_to_object_note(row: sqlite3.Row) -> ObjectNote:
    try:
        tags = json.loads(row["tags"] or "[]")
    except json.JSONDecodeError:
        tags = []
    return ObjectNote(
        note_id=row["note_id"],
        object_id=row["object_id"],
        note_text=row["note_text"],
        timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.now(),
        tags=tags if isinstance(tags, list) else [],
        location_id=row["location_id"],
        source=row["source"] or "manual",
    )


def _row_to_find_feedback(row: sqlite3.Row) -> FindFeedback:
    return FindFeedback(
        feedback_id=row["feedback_id"],
        query=row["query"],
        feedback=row["feedback"],
        object_id=row["object_id"],
        lot_id=row["lot_id"],
        suggested_location_id=row["suggested_location_id"],
        actual_location_id=row["actual_location_id"],
        notes=row["notes"],
        timestamp=datetime.fromisoformat(row["timestamp"]) if row["timestamp"] else datetime.now(),
    )


from shopstack.schemas.models import ToolCall as _ToolCall  # noqa: E402 — circular import


def _coerce_tool_call_payload(d: dict) -> dict:
    if not isinstance(d, dict):
        return {
            "tool_name": "respond",
            "args": {"message": str(d)},
            "success": False,
            "error": "Invalid tool call payload",
        }

    tool_name = d.get("tool_name") or d.get("tool")
    if not tool_name:
        return {
            "tool_name": "respond",
            "args": {"message": "Missing tool"},
            "success": False,
            "error": "Missing tool name",
        }

    args = d.get("args")
    if not isinstance(args, dict):
        args = {}

    result = d.get("result")
    if result is not None and not isinstance(result, dict):
        result = {"value": result}

    return {
        "tool_name": str(tool_name),
        "args": args,
        "result": result,
        "success": bool(d.get("success", False)),
        "error": d.get("error"),
        "requires_confirmation": bool(d.get("requires_confirmation", True)),
        "confirmed": bool(d.get("confirmed", False)),
    }


def _dict_to_tc(d: dict) -> _ToolCall:
    return _ToolCall(**_coerce_tool_call_payload(d))
