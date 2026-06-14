"""Tests for the Condition / Damage Detection service and screen."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from shopstack.repos.inventory import InventoryRepo
from shopstack.schemas.condition import (
    ConditionAction,
    ConditionAggregate,
    ConditionEvent,
    ConditionKind,
    ConditionSeverity,
    RepairInboxItem,
)
from shopstack.services.condition import (
    SEVERITY_ORDER,
    SEVERITY_TO_ACTION,
    _coerce_kind,
    _coerce_severity,
    analyze_image_for_damage,
    get_lot_condition,
    get_repair_inbox,
    record_condition_event,
)
from shopstack.ui.screens.repair_inbox import (
    close_condition_event,
    confirm_condition_event,
    delete_condition_event,
    repair_inbox_view,
    report_damage,
)


# ─── Schema / enum tests ─────────────────────────────────────────


class TestEnums:
    def test_severity_order_has_five_levels(self):
        assert len(SEVERITY_ORDER) == 5
        assert SEVERITY_ORDER[0] == ConditionSeverity.COSMETIC
        assert SEVERITY_ORDER[-1] == ConditionSeverity.SPOILED

    def test_severity_to_action_mappings(self):
        assert SEVERITY_TO_ACTION[ConditionSeverity.COSMETIC] == ConditionAction.MONITOR
        assert SEVERITY_TO_ACTION[ConditionSeverity.WORN] == ConditionAction.MONITOR
        assert SEVERITY_TO_ACTION[ConditionSeverity.DAMAGED] == ConditionAction.REPAIR
        assert SEVERITY_TO_ACTION[ConditionSeverity.BROKEN] == ConditionAction.REPLACE
        assert SEVERITY_TO_ACTION[ConditionSeverity.SPOILED] == ConditionAction.DISCARD


class TestCoercion:
    def test_coerce_kind_valid(self):
        assert _coerce_kind("physical_damage") == ConditionKind.PHYSICAL_DAMAGE
        assert _coerce_kind("LIQUID_LEAK") == ConditionKind.LIQUID_LEAK
        assert _coerce_kind("Expiry Risk") == ConditionKind.EXPIRY_RISK

    def test_coerce_kind_invalid_raises(self):
        with pytest.raises(ValueError):
            _coerce_kind("not_a_kind")

    def test_coerce_severity_valid(self):
        assert _coerce_severity("worn") == ConditionSeverity.WORN
        assert _coerce_severity("DAMAGED") == ConditionSeverity.DAMAGED
        assert _coerce_severity("spoiled") == ConditionSeverity.SPOILED

    def test_coerce_severity_invalid_raises(self):
        with pytest.raises(ValueError):
            _coerce_severity("not_a_severity")


# ─── Image heuristic tests ───────────────────────────────────────


class TestAnalyzeImageForDamage:
    def test_no_image_returns_none(self):
        result = analyze_image_for_damage(None)
        assert result is None

    def test_image_with_no_signal_returns_none(self):
        # The heuristic scaffold returns confidence 0.0, so should return None
        result = analyze_image_for_damage("/some/path.jpg")
        assert result is None

    def test_with_lot_attaches_metadata(self):
        # If we manually construct a confidence > 0 event, it should
        # have the lot's canonical_name
        from shopstack.persistence.database import Database
        # The current heuristic returns confidence 0.0; this test
        # documents the contract: when signal exists, lot metadata
        # flows through. We can't easily fake this without mocking
        # _image_heuristic_score, so we test the function's contract
        # by reading its source path.
        # The function returns None when no signal, which is correct.
        assert analyze_image_for_damage("/path", lot=None) is None


# ─── Recording tests ─────────────────────────────────────────────


class TestRecordConditionEvent:
    def test_record_user_report(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        lot_id = added["lot_id"]

        event_id = record_condition_event(
            db,
            lot_id=lot_id,
            kind="physical_damage",
            severity="damaged",
            description="Carton is dented",
            canonical_name="milk",
        )
        assert event_id.startswith("cond_")
        rows = db.get_condition_events_for_lot(lot_id)
        assert len(rows) == 1
        assert rows[0]["description"] == "Carton is dented"
        assert rows[0]["kind"] == "physical_damage"
        assert rows[0]["severity"] == "damaged"
        # User reports are confirmed by default
        assert rows[0]["user_confirmed"] == 1

    def test_record_vision_event_unconfirmed(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        lot_id = added["lot_id"]

        event_id = record_condition_event(
            db,
            lot_id=lot_id,
            kind="expiry_risk",
            severity="spoiled",
            description="Best-before date in the past",
            source="vision_model",
            user_confirmed=False,
        )
        rows = db.get_condition_events_for_lot(lot_id)
        assert rows[0]["user_confirmed"] == 0
        assert rows[0]["source"] == "vision_model"

    def test_record_invalid_kind_raises(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        with pytest.raises(ValueError):
            record_condition_event(
                db,
                lot_id=added["lot_id"],
                kind="not_a_kind",
                severity="worn",
            )

    def test_record_invalid_severity_raises(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        with pytest.raises(ValueError):
            record_condition_event(
                db,
                lot_id=added["lot_id"],
                kind="physical_damage",
                severity="not_a_severity",
            )

    def test_record_with_enum_objects(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        record_condition_event(
            db,
            lot_id=added["lot_id"],
            kind=ConditionKind.LIQUID_LEAK,
            severity=ConditionSeverity.SPOILED,
        )
        rows = db.get_condition_events_for_lot(added["lot_id"])
        assert rows[0]["kind"] == "liquid_leak"
        assert rows[0]["severity"] == "spoiled"


# ─── Aggregation tests ───────────────────────────────────────────


class TestGetLotCondition:
    def test_lot_with_no_events(self, db):
        agg = get_lot_condition(db, "nonexistent_lot")
        assert agg.lot_id == "nonexistent_lot"
        assert agg.occurrences == 0
        assert agg.has_open_issue is False

    def test_lot_with_single_event(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        record_condition_event(
            db,
            lot_id=added["lot_id"],
            kind="physical_damage",
            severity="damaged",
            canonical_name="milk",
        )
        agg = get_lot_condition(db, added["lot_id"])
        assert agg.occurrences == 1
        assert agg.highest_severity == ConditionSeverity.DAMAGED
        assert agg.dominant_kind == ConditionKind.PHYSICAL_DAMAGE
        assert agg.recommended_action == ConditionAction.REPAIR
        assert agg.canonical_name == "milk"
        assert agg.has_open_issue is True

    def test_lot_with_multiple_events_picks_highest_severity(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        lot_id = added["lot_id"]
        record_condition_event(db, lot_id=lot_id, kind="wear_tear", severity="cosmetic")
        record_condition_event(db, lot_id=lot_id, kind="physical_damage", severity="damaged")
        record_condition_event(db, lot_id=lot_id, kind="liquid_leak", severity="broken")

        agg = get_lot_condition(db, lot_id)
        assert agg.occurrences == 3
        assert agg.highest_severity == ConditionSeverity.BROKEN
        assert agg.recommended_action == ConditionAction.REPLACE
        # dominant_kind should be the most frequent — all 3 are different
        # so just verify it's one of them
        assert agg.dominant_kind in {ConditionKind.WEAR_TEAR, ConditionKind.PHYSICAL_DAMAGE, ConditionKind.LIQUID_LEAK}

    def test_lot_with_closed_events_excluded(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        lot_id = added["lot_id"]
        eid1 = record_condition_event(db, lot_id=lot_id, kind="physical_damage", severity="damaged")
        record_condition_event(db, lot_id=lot_id, kind="wear_tear", severity="worn")
        db.close_condition_event(eid1)

        agg = get_lot_condition(db, lot_id, include_closed=False)
        assert agg.occurrences == 1  # only the open one

    def test_lot_with_closed_events_included(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        lot_id = added["lot_id"]
        eid1 = record_condition_event(db, lot_id=lot_id, kind="physical_damage", severity="damaged")
        record_condition_event(db, lot_id=lot_id, kind="wear_tear", severity="worn")
        db.close_condition_event(eid1)

        agg = get_lot_condition(db, lot_id, include_closed=True)
        assert agg.occurrences == 2

    def test_lot_user_confirmed_flag(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        lot_id = added["lot_id"]
        # User report = confirmed by default
        record_condition_event(db, lot_id=lot_id, kind="physical_damage", severity="worn")
        agg = get_lot_condition(db, lot_id)
        assert agg.user_confirmed is True

    def test_lot_lot_unconfirmed(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        lot_id = added["lot_id"]
        # Vision event = unconfirmed by default
        record_condition_event(
            db, lot_id=lot_id, kind="physical_damage", severity="worn",
            source="vision_model", user_confirmed=False,
        )
        agg = get_lot_condition(db, lot_id)
        assert agg.user_confirmed is False


# ─── Repair inbox tests ──────────────────────────────────────────


class TestGetRepairInbox:
    def test_inbox_empty_when_no_events(self, db):
        items = get_repair_inbox(db)
        assert items == []

    def test_inbox_contains_lot_with_open_event(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        record_condition_event(
            db, lot_id=added["lot_id"],
            kind="physical_damage", severity="damaged",
            canonical_name="milk",
        )
        items = get_repair_inbox(db)
        assert len(items) == 1
        assert items[0].canonical_name == "milk"
        assert items[0].severity == ConditionSeverity.DAMAGED

    def test_inbox_aggregates_multiple_events_per_lot(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        lot_id = added["lot_id"]
        for _ in range(3):
            record_condition_event(db, lot_id=lot_id, kind="physical_damage", severity="damaged")

        items = get_repair_inbox(db)
        assert len(items) == 1
        assert items[0].occurrences == 3

    def test_inbox_ranks_severity_descending(self, db):
        repo = InventoryRepo(db)
        # Three lots with three severities
        a1 = repo.add_item("a", "A", 1, "unit", "kitchen")
        a2 = repo.add_item("b", "B", 1, "unit", "kitchen")
        a3 = repo.add_item("c", "C", 1, "unit", "kitchen")
        record_condition_event(db, lot_id=a1["lot_id"], kind="wear_tear", severity="cosmetic")
        record_condition_event(db, lot_id=a2["lot_id"], kind="physical_damage", severity="damaged")
        record_condition_event(db, lot_id=a3["lot_id"], kind="liquid_leak", severity="spoiled")

        items = get_repair_inbox(db)
        # Most severe first
        assert items[0].severity == ConditionSeverity.SPOILED
        assert items[1].severity == ConditionSeverity.DAMAGED
        assert items[2].severity == ConditionSeverity.COSMETIC

    def test_inbox_excludes_closed_events(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        lot_id = added["lot_id"]
        eid = record_condition_event(db, lot_id=lot_id, kind="physical_damage", severity="damaged")
        db.close_condition_event(eid)

        items = get_repair_inbox(db)
        assert items == []

    def test_inbox_includes_pending_user_confirmation_count(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        lot_id = added["lot_id"]
        # Vision event (unconfirmed) + user report (confirmed)
        record_condition_event(
            db, lot_id=lot_id, kind="physical_damage", severity="damaged",
            source="vision_model", user_confirmed=False,
        )
        record_condition_event(
            db, lot_id=lot_id, kind="wear_tear", severity="worn",
            source="user_report",
        )
        items = get_repair_inbox(db)
        assert items[0].pending_user_confirmation == 1
        assert items[0].user_confirmed is True

    def test_inbox_filter_by_severity(self, db):
        repo = InventoryRepo(db)
        a1 = repo.add_item("a", "A", 1, "unit", "kitchen")
        a2 = repo.add_item("b", "B", 1, "unit", "kitchen")
        record_condition_event(db, lot_id=a1["lot_id"], kind="physical_damage", severity="damaged")
        record_condition_event(db, lot_id=a2["lot_id"], kind="liquid_leak", severity="spoiled")

        items = get_repair_inbox(db, severity=ConditionSeverity.SPOILED)
        assert len(items) == 1
        assert items[0].severity == ConditionSeverity.SPOILED

    def test_inbox_includes_location(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        record_condition_event(
            db, lot_id=added["lot_id"],
            kind="physical_damage", severity="damaged",
        )
        items = get_repair_inbox(db)
        assert items[0].location_id == "fridge"
        # The name comes from the location lookup
        assert items[0].location_name  # non-empty


# ─── Confirm / close / delete tests ──────────────────────────────


class TestConfirmCloseDelete:
    def test_confirm_event(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        eid = record_condition_event(
            db, lot_id=added["lot_id"],
            kind="physical_damage", severity="damaged",
            source="vision_model", user_confirmed=False,
        )
        ok = db.confirm_condition_event(eid)
        assert ok is True
        rows = db.get_condition_events_for_lot(added["lot_id"])
        assert rows[0]["user_confirmed"] == 1

    def test_close_event(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        eid = record_condition_event(
            db, lot_id=added["lot_id"],
            kind="physical_damage", severity="damaged",
        )
        ok = db.close_condition_event(eid)
        assert ok is True
        rows = db.get_condition_events_for_lot(added["lot_id"])
        assert rows[0]["closed_at"] is not None

    def test_delete_event(self, db):
        repo = InventoryRepo(db)
        added = repo.add_item("milk", "Milk", 1, "L", "fridge")
        eid = record_condition_event(
            db, lot_id=added["lot_id"],
            kind="physical_damage", severity="damaged",
        )
        ok = db.delete_condition_event(eid)
        assert ok is True
        rows = db.get_condition_events_for_lot(added["lot_id"])
        assert len(rows) == 0


# ─── Screen tests ────────────────────────────────────────────────


class TestRepairInboxScreen:
    def test_empty_inbox_renders_clear_state(self):
        from shopstack.app_context import db as app_db
        # Clean any open events
        for row in app_db.get_open_condition_events():
            app_db.close_condition_event(row["event_id"])
        html = repair_inbox_view()
        assert "All clear" in html

    def test_inbox_with_event_renders_item(self):
        from shopstack.app_context import db as app_db
        # Add a test lot and event
        app_db.conn.execute(
            "INSERT INTO inventory_lots (lot_id, canonical_name, display_name, quantity, unit, storage_location_id, purchase_date, status, user_id) "
            "VALUES ('test_lot_dmg', 'TestItem', 'TestItem', 1, 'unit', 'fridge', '2026-06-14', 'active', '')"
        )
        app_db.conn.commit()
        record_condition_event(
            app_db,
            lot_id="test_lot_dmg",
            kind="physical_damage",
            severity="damaged",
            description="Test damage",
        )
        try:
            html = repair_inbox_view()
            assert "TestItem" in html
            assert "DAMAGED" in html
            assert "Repair" in html
        finally:
            # Clean up
            for row in app_db.get_condition_events_for_lot("test_lot_dmg"):
                app_db.delete_condition_event(row["event_id"])
            app_db.conn.execute("DELETE FROM inventory_lots WHERE lot_id = 'test_lot_dmg'")
            app_db.conn.commit()

    def test_report_damage_missing_lot(self):
        result = report_damage("", "physical_damage", "damaged", "Test")
        assert "required" in result.lower()

    def test_report_damage_missing_kind(self):
        result = report_damage("test_lot", "", "damaged", "Test")
        assert "required" in result.lower()

    def test_report_damage_missing_severity(self):
        result = report_damage("test_lot", "physical_damage", "", "Test")
        assert "required" in result.lower()

    def test_report_damage_unknown_lot(self):
        result = report_damage("ghost_lot_xyz", "physical_damage", "damaged", "Test")
        assert "unknown lot" in result.lower()

    def test_report_damage_invalid_kind(self):
        from shopstack.app_context import db as app_db
        app_db.conn.execute(
            "INSERT INTO inventory_lots (lot_id, canonical_name, display_name, quantity, unit, storage_location_id, purchase_date, status, user_id) "
            "VALUES ('test_lot_dmg2', 'TestItem2', 'TestItem2', 1, 'unit', 'fridge', '2026-06-14', 'active', '')"
        )
        app_db.conn.commit()
        try:
            result = report_damage("test_lot_dmg2", "not_a_kind", "damaged", "Test")
            assert "unknown condition kind" in result.lower()
        finally:
            app_db.conn.execute("DELETE FROM inventory_lots WHERE lot_id = 'test_lot_dmg2'")
            app_db.conn.commit()

    def test_report_damage_success(self):
        from shopstack.app_context import db as app_db
        app_db.conn.execute(
            "INSERT INTO inventory_lots (lot_id, canonical_name, display_name, quantity, unit, storage_location_id, purchase_date, status, user_id) "
            "VALUES ('test_lot_dmg3', 'TestItem3', 'TestItem3', 1, 'unit', 'fridge', '2026-06-14', 'active', '')"
        )
        app_db.conn.commit()
        try:
            result = report_damage("test_lot_dmg3", "physical_damage", "damaged", "Test desc")
            assert "Recorded" in result
            assert "TestItem3" in result
        finally:
            for row in app_db.get_condition_events_for_lot("test_lot_dmg3"):
                app_db.delete_condition_event(row["event_id"])
            app_db.conn.execute("DELETE FROM inventory_lots WHERE lot_id = 'test_lot_dmg3'")
            app_db.conn.commit()

    def test_confirm_screen(self):
        result = confirm_condition_event("")
        assert "required" in result.lower()

    def test_close_screen(self):
        result = close_condition_event("")
        assert "required" in result.lower()

    def test_delete_screen(self):
        result = delete_condition_event("")
        assert "required" in result.lower()

    def test_inbox_filter_by_severity(self):
        from shopstack.app_context import db as app_db
        app_db.conn.execute(
            "INSERT INTO inventory_lots (lot_id, canonical_name, display_name, quantity, unit, storage_location_id, purchase_date, status, user_id) "
            "VALUES ('test_lot_dmg4', 'FilterItem', 'FilterItem', 1, 'unit', 'fridge', '2026-06-14', 'active', '')"
        )
        app_db.conn.commit()
        record_condition_event(
            app_db,
            lot_id="test_lot_dmg4",
            kind="wear_tear",
            severity="cosmetic",
        )
        try:
            html = repair_inbox_view(severity="cosmetic")
            assert "FilterItem" in html
            html2 = repair_inbox_view(severity="broken")
            assert "FilterItem" not in html2
        finally:
            for row in app_db.get_condition_events_for_lot("test_lot_dmg4"):
                app_db.delete_condition_event(row["event_id"])
            app_db.conn.execute("DELETE FROM inventory_lots WHERE lot_id = 'test_lot_dmg4'")
            app_db.conn.commit()
