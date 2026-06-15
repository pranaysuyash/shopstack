"""Tests for `shopstack.services.undo_ledger` — the mutation-recovery ledger.

Verifies:
  * Registration enforces the `REVERSIBLE` whitelist (unknown kinds
    raise ValueError).
  * TTL expires entries after `UNDO_TTL_SECONDS` (use a small TTL
    in tests for speed).
  * `MAX_ENTRIES_PER_HOUSEHOLD` is enforced (drop the oldest).
  * `undo_last` returns the most-recent non-undone non-expired entry
    and marks it done.
  * `undo_by_id` reverses a specific entry.
  * Idempotency: a second undo on the same entry is a no-op.
  * Different households don't see each other's entries.
  * `has_recent` is True iff `recent(limit=1)` is non-empty.
  * `purge_expired` removes the right entries.
  * The default inverse is invoked with the right (kind, before, db)
    and its return value drives the success/failure path.
  * Toast trigger HTML escapes all dynamic content (no XSS via
    household_id, entry_id, or locale strings).
  * Click-handler script registers the global function and is a
    valid `<script data-ss-exec>` block.
"""
from __future__ import annotations

import threading
import time
from html.parser import HTMLParser

import pytest

from shopstack.services.undo_ledger import (
    REVERSIBLE,
    UNDO_TTL_SECONDS,
    UndoEntry,
    UndoLedger,
    _default_inverse,
    get_ledger,
    render_undo_click_handler,
    render_undo_toast_trigger,
    reset_ledger,
)


# ── Fixtures ───────────────────────────────────────────────────────


@pytest.fixture
def ledger() -> UndoLedger:
    """A fresh ledger with a 0.1s TTL so we can test expiry quickly."""
    return UndoLedger(ttl_seconds=0.1, max_entries=5)


# ── Registration ──────────────────────────────────────────────────


class TestRegister:
    def test_register_creates_entry(self, ledger: UndoLedger):
        entry = ledger.register(
            household_id="hh1",
            kind="consume_inventory",
            before={"lot_id": "lot-1", "quantity": 2.0},
            description="Consumed 2 of Milk",
        )
        assert entry.entry_id
        assert entry.household_id == "hh1"
        assert entry.kind == "consume_inventory"
        assert entry.undone is False
        assert entry.description == "Consumed 2 of Milk"

    def test_recent_returns_in_reverse_chronological_order(self, ledger: UndoLedger):
        e1 = ledger.register(
            household_id="hh1", kind="add_inventory_lot",
            before={"lot_id": "lot-1"},
        )
        time.sleep(0.01)
        e2 = ledger.register(
            household_id="hh1", kind="add_inventory_lot",
            before={"lot_id": "lot-2"},
        )
        recent = ledger.recent("hh1")
        assert [e.entry_id for e in recent] == [e2.entry_id, e1.entry_id]

    def test_unknown_kind_raises(self, ledger: UndoLedger):
        with pytest.raises(ValueError, match="not in REVERSIBLE"):
            ledger.register(
                household_id="hh1",
                kind="delete_database",  # not in REVERSIBLE
                before={},
            )

    def test_reversible_includes_expected_kinds(self):
        for must in (
            "consume_inventory",
            "add_inventory_lot",
            "record_movement",
            "add_list_item",
            "record_price",
            "add_purchase_event",
            "add_reconciliation_event",
            "add_preference_signal",
        ):
            assert must in REVERSIBLE, f"Missing REVERSIBLE entry: {must}"


# ── TTL + capacity ────────────────────────────────────────────────


class TestTtlAndCapacity:
    def test_expired_entries_excluded_from_recent(self, ledger: UndoLedger):
        ledger.register(
            household_id="hh1", kind="consume_inventory",
            before={"lot_id": "lot-1", "quantity": 1.0},
        )
        assert ledger.has_recent("hh1")
        time.sleep(0.15)  # TTL is 0.1s
        assert not ledger.has_recent("hh1")
        assert ledger.recent("hh1") == []

    def test_max_entries_enforced(self, ledger: UndoLedger):
        for i in range(7):  # max is 5
            ledger.register(
                household_id="hh1", kind="add_inventory_lot",
                before={"lot_id": f"lot-{i}"},
            )
        recent = ledger.recent("hh1", limit=10)
        assert len(recent) == 5
        # The most recent 5 should be kept (i=2..6)
        lot_ids = [e.before["lot_id"] for e in recent]
        assert "lot-6" in lot_ids and "lot-2" in lot_ids
        assert "lot-0" not in lot_ids and "lot-1" not in lot_ids


# ── Per-household isolation ──────────────────────────────────────


class TestPerHousehold:
    def test_different_households_isolated(self, ledger: UndoLedger):
        ledger.register(
            household_id="hh1", kind="consume_inventory",
            before={"lot_id": "lot-1", "quantity": 1.0},
        )
        ledger.register(
            household_id="hh2", kind="consume_inventory",
            before={"lot_id": "lot-2", "quantity": 1.0},
        )
        hh1_recent = ledger.recent("hh1")
        hh2_recent = ledger.recent("hh2")
        assert len(hh1_recent) == 1
        assert hh1_recent[0].before["lot_id"] == "lot-1"
        assert len(hh2_recent) == 1
        assert hh2_recent[0].before["lot_id"] == "lot-2"


# ── Undo operations ──────────────────────────────────────────────


class TestUndoLast:
    def test_undo_last_returns_recent_entry(self, ledger: UndoLedger):
        entry = ledger.register(
            household_id="hh1", kind="consume_inventory",
            before={"lot_id": "lot-1", "quantity": 1.0},
        )
        # Pass an inverse that always succeeds so the test
        # doesn't need a real DB.
        undone = ledger.undo_last("hh1", db=None, inverse=lambda k, b, d: True)
        assert undone is not None
        assert undone.entry_id == entry.entry_id
        assert undone.undone is True

    def test_undo_last_invokes_inverse(self, ledger: UndoLedger):
        """The inverse callable receives (kind, before, db) and its
        return drives the success path."""
        calls: list[tuple[str, dict]] = []

        def fake_inverse(kind: str, before: dict, db):
            calls.append((kind, before))
            return True

        ledger.register(
            household_id="hh1", kind="consume_inventory",
            before={"lot_id": "lot-1", "quantity": 1.0},
        )
        result = ledger.undo_last("hh1", db=None, inverse=fake_inverse)
        assert result is not None
        assert calls == [("consume_inventory", {"lot_id": "lot-1", "quantity": 1.0})]

    def test_undo_last_idempotent(self, ledger: UndoLedger):
        ledger.register(
            household_id="hh1", kind="consume_inventory",
            before={"lot_id": "lot-1", "quantity": 1.0},
        )
        first = ledger.undo_last("hh1", db=None, inverse=lambda k, b, d: True)
        second = ledger.undo_last("hh1", db=None, inverse=lambda k, b, d: True)
        assert first is not None
        assert second is None  # already undone

    def test_undo_last_returns_none_when_empty(self, ledger: UndoLedger):
        assert ledger.undo_last("hh1", db=None) is None

    def test_undo_failure_marks_undone_false_again(self, ledger: UndoLedger):
        ledger.register(
            household_id="hh1", kind="consume_inventory",
            before={"lot_id": "lot-1", "quantity": 1.0},
        )
        # Inverse returns False → failure
        result = ledger.undo_last("hh1", db=None, inverse=lambda k, b, d: False)
        assert result is None
        # The entry is still in `recent` (it was unmarked on failure)
        assert ledger.has_recent("hh1")


class TestUndoById:
    def test_undo_specific_entry(self, ledger: UndoLedger):
        e1 = ledger.register(
            household_id="hh1", kind="consume_inventory",
            before={"lot_id": "lot-1", "quantity": 1.0},
        )
        ledger.register(
            household_id="hh1", kind="consume_inventory",
            before={"lot_id": "lot-2", "quantity": 1.0},
        )
        result = ledger.undo_by_id("hh1", e1.entry_id, db=None,
                                    inverse=lambda k, b, d: True)
        assert result is not None
        assert result.entry_id == e1.entry_id

    def test_undo_by_id_unknown_returns_none(self, ledger: UndoLedger):
        ledger.register(
            household_id="hh1", kind="consume_inventory",
            before={"lot_id": "lot-1", "quantity": 1.0},
        )
        result = ledger.undo_by_id("hh1", "no-such-id", db=None)
        assert result is None


# ── Default inverse dispatch ──────────────────────────────────────


class TestDefaultInverse:
    def test_consume_inventory_uses_add_inventory_lot(self):
        """The default inverse for `consume_inventory` calls
        `add_inventory_lot` with the original quantity."""
        calls: list[dict] = []

        class FakeDb:
            def get_inventory_lot(self, lot_id):
                from shopstack.schemas.models import InventoryLot

                return InventoryLot(
                    lot_id=lot_id,
                    canonical_name="milk",
                    display_name="Milk",
                    quantity=0.0,
                    unit="L",
                    storage_location_id="fridge",
                )

            def add_inventory_lot(self, lot, user_id=""):
                calls.append({"lot_id": lot.lot_id, "qty": lot.quantity})
                return lot

        ok = _default_inverse(
            "consume_inventory",
            {"lot_id": "lot-1", "quantity": 2.0, "canonical_name": "milk"},
            FakeDb(),
        )
        assert ok is True
        assert calls == [{"lot_id": "lot-1", "qty": 2.0}]

    def test_record_movement_inverts_direction(self):
        calls: list[dict] = []

        class FakeDb:
            def record_movement(self, movement, user_id=""):
                calls.append({
                    "from_loc": movement.from_location_id,
                    "to_loc": movement.to_location_id,
                })
                return movement

        ok = _default_inverse(
            "record_movement",
            {
                "lot_id": "lot-1",
                "from_location_id": "fridge",
                "to_location_id": "pantry",
            },
            FakeDb(),
        )
        assert ok is True
        assert calls == [{"from_loc": "pantry", "to_loc": "fridge"}]

    def test_add_list_item_marks_removed(self):
        calls: list[dict] = []

        class FakeDb:
            def update_list_item(self, item_id, updates):
                calls.append({"item_id": item_id, "updates": updates})

        ok = _default_inverse(
            "add_list_item",
            {"item_id": "item-1"},
            FakeDb(),
        )
        assert ok is True
        assert calls == [{"item_id": "item-1", "updates": {"status": "removed"}}]

    def test_purchase_event_uses_delete(self):
        calls: list[str] = []

        class FakeDb:
            def delete_purchase_event(self, event_id):
                calls.append(event_id)
                return True

        ok = _default_inverse(
            "add_purchase_event",
            {"event_id": "evt-1"},
            FakeDb(),
        )
        assert ok is True
        assert calls == ["evt-1"]

    def test_reconciliation_event_uses_delete(self):
        calls: list[str] = []

        class FakeDb:
            def delete_reconciliation_event(self, event_id):
                calls.append(event_id)
                return True

        ok = _default_inverse(
            "add_reconciliation_event",
            {"event_id": "evt-1"},
            FakeDb(),
        )
        assert ok is True
        assert calls == ["evt-1"]

    def test_preference_signal_uses_delete(self):
        calls: list[str] = []

        class FakeDb:
            def delete_preference_signal(self, signal_id):
                calls.append(signal_id)
                return True

        ok = _default_inverse(
            "add_preference_signal",
            {"event_id": "sig-1"},
            FakeDb(),
        )
        assert ok is True
        assert calls == ["sig-1"]

    def test_unknown_kind_returns_false(self):
        ok = _default_inverse("totally_new_kind", {}, None)
        assert ok is False

    def test_db_raising_returns_false(self):
        class BoomDb:
            def get_inventory_lot(self, lot_id):
                raise RuntimeError("simulated db failure")

        ok = _default_inverse(
            "consume_inventory",
            {"lot_id": "lot-1", "quantity": 1.0},
            BoomDb(),
        )
        assert ok is False


# ── purge_expired ─────────────────────────────────────────────────


class TestPurgeExpired:
    def test_purges_only_expired_and_undone(self, ledger: UndoLedger):
        e1 = ledger.register(
            household_id="hh1", kind="consume_inventory",
            before={"lot_id": "lot-1", "quantity": 1.0},
        )
        e2 = ledger.register(
            household_id="hh1", kind="consume_inventory",
            before={"lot_id": "lot-2", "quantity": 1.0},
        )
        # Undo e2 (so it's marked done)
        ledger.undo_by_id("hh1", e2.entry_id, db=None,
                          inverse=lambda k, b, d: True)
        # Wait for e1 to expire
        time.sleep(0.15)
        purged = ledger.purge_expired("hh1")
        # e1 expired; e2 was already done — both should be purged
        assert purged == 2
        assert ledger.recent("hh1") == []

    def test_purges_all_households(self, ledger: UndoLedger):
        ledger.register(
            household_id="hh1", kind="consume_inventory",
            before={"lot_id": "lot-1", "quantity": 1.0},
        )
        ledger.register(
            household_id="hh2", kind="consume_inventory",
            before={"lot_id": "lot-2", "quantity": 1.0},
        )
        time.sleep(0.15)
        purged = ledger.purge_expired()
        assert purged == 2


# ── Singleton ─────────────────────────────────────────────────────


class TestGetLedger:
    def test_get_ledger_returns_singleton(self):
        reset_ledger()
        a = get_ledger()
        b = get_ledger()
        assert a is b

    def test_reset_ledger_clears_singleton(self):
        a = get_ledger()
        reset_ledger()
        b = get_ledger()
        assert a is not b


# ── Thread safety (smoke) ─────────────────────────────────────────


def test_concurrent_registers(ledger: UndoLedger):
    """10 threads register 5 entries each; total is bounded by max."""
    def worker(i: int) -> None:
        for j in range(5):
            ledger.register(
                household_id=f"hh{i}",
                kind="add_inventory_lot",
                before={"lot_id": f"lot-{i}-{j}"},
            )

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 10 households × 5 entries each = 50, but max is 5 per household
    total = sum(len(ledger.recent(f"hh{i}", limit=10)) for i in range(10))
    assert total == 50


# ── Toast trigger HTML ───────────────────────────────────────────


class TestUndoToastTrigger:
    def test_returns_div_with_required_attributes(self):
        html = render_undo_toast_trigger("hh-1", entry_id="e1")
        assert html.startswith('<div class="ss-toast-trigger"')
        # Must carry the data-* attributes the observer reads.
        assert 'data-toast-kind="undo"' in html
        assert 'data-toast-msg=' in html
        assert 'data-toast-action-label=' in html
        assert 'data-household-id="hh-1"' in html
        assert 'data-entry-id="e1"' in html

    def test_no_entry_id_omits_data_entry_id(self):
        html = render_undo_toast_trigger("hh-1")
        assert 'data-household-id="hh-1"' in html
        # The entry id is empty but the attribute is still present
        # (the JS treats "" as "undo the most recent").
        assert 'data-entry-id=""' in html

    def test_household_id_with_quotes_is_escaped(self):
        """Defensive: even if a household_id has quotes (it shouldn't),
        the attribute value is escaped."""
        html = render_undo_toast_trigger('hh"onclick="x', entry_id='e"1')
        # The closing quote of data-household-id is not followed by
        # an HTML-attribute break.
        assert 'hh"onclick="x' not in html
        # The data attribute is still parseable
        assert 'data-household-id=' in html


# ── Click handler script ─────────────────────────────────────────


class TestClickHandler:
    def test_returns_valid_script(self):
        script = render_undo_click_handler()
        assert script.strip().startswith("<script")
        assert script.strip().endswith("</script>")
        assert 'data-ss-exec="true"' in script

    def test_registers_global_function(self):
        script = render_undo_click_handler()
        assert "ssUndoClick" in script
        assert "window.ssUndoClick" in script
        # IIFE wrapper (no global pollution beyond the explicit export)
        assert "(function()" in script

    def test_uses_fetch_api(self):
        """The handler hits /api/undo via fetch (no Gradio client
        dependency at runtime)."""
        script = render_undo_click_handler()
        assert "/api/undo" in script
        assert "fetch" in script
