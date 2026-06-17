"""Multi-item undo tests: N undo entries for N bought items.

Verifies the undo ledger can handle multiple undo entries created
from a single operation (e.g. reconciling a shopping trip with N
bought items creates N undo entries, and each can be undone).

Key scenarios:

1. test_n_undo_entries_for_n_items - N items create N undo entries
2. test_undo_order_reverse_chronological - Most recent undone first
3. test_undo_all_n_entries - All entries can be undone
4. test_concurrent_n_entries_across_households - Multi-tenant isolation
5. test_undo_n_entries_with_fake_inverse - Tracking inverse calls
6. test_undo_partial_n_entries - Partial undo leaves correct entries
7. test_record_price_inverse_deletes_with_real_db - Price deletion
8. test_record_price_inverse_no_price_id_returns_false - Edge case
"""
from __future__ import annotations

import threading
import time

import pytest

from shopstack.services.undo_ledger import (
    UndoLedger,
    _default_inverse,
)


@pytest.fixture
def ledger() -> UndoLedger:
    """A fresh ledger with 1s TTL for integration tests."""
    return UndoLedger(ttl_seconds=1.0, max_entries=10)


@pytest.fixture
def fast_ledger() -> UndoLedger:
    """A ledger with 2s TTL and generous max for multi-item tests."""
    return UndoLedger(ttl_seconds=2.0, max_entries=50)


class TestMultiItemUndo:
    """N undo entries for N bought items."""

    def test_n_undo_entries_for_n_items(self, fast_ledger: UndoLedger):
        """Register N entries for N items; verify N entries exist."""
        n = 5
        for i in range(n):
            fast_ledger.register(
                household_id="hh1",
                kind="add_inventory_lot",
                before={"lot_id": f"lot-{i}", "canonical_name": f"item_{i}"},
                after={"canonical_name": f"item_{i}"},
                description=f"Added item_{i}",
            )
        recent = fast_ledger.recent("hh1", limit=n + 1)
        assert len(recent) == n
        names = {e.description for e in recent}
        for i in range(n):
            assert f"Added item_{i}" in names

    def test_undo_order_reverse_chronological(self, fast_ledger: UndoLedger):
        """Undo returns most recent first."""
        n = 5
        lot_ids = []
        for i in range(n):
            e = fast_ledger.register(
                household_id="hh1",
                kind="consume_inventory",
                before={"lot_id": f"lot-{i}", "quantity": 1.0},
                description=f"Consumed item_{i}",
            )
            lot_ids.append(e.entry_id)
            time.sleep(0.01)

        undone = fast_ledger.undo_last(
            "hh1", db=None, inverse=lambda k, b, d: True
        )
        assert undone is not None
        assert undone.entry_id == lot_ids[-1]

    def test_undo_all_n_entries(self, fast_ledger: UndoLedger):
        """Undo all N entries; verify ledger is empty."""
        n = 3
        for i in range(n):
            fast_ledger.register(
                household_id="hh1",
                kind="add_inventory_lot",
                before={"lot_id": f"lot-{i}"},
            )
        undone_count = 0
        while True:
            result = fast_ledger.undo_last(
                "hh1", db=None, inverse=lambda k, b, d: True
            )
            if result is None:
                break
            undone_count += 1
        assert undone_count == n
        assert not fast_ledger.has_recent("hh1")

    def test_concurrent_n_entries_across_households(self, fast_ledger: UndoLedger):
        """N entries in each of M households; all isolated."""
        n_per_hh = 3
        hh_ids = ["hh1", "hh2", "hh3"]

        def worker(hid: str) -> None:
            for i in range(n_per_hh):
                fast_ledger.register(
                    household_id=hid,
                    kind="consume_inventory",
                    before={"lot_id": f"lot-{hid}-{i}", "quantity": 1.0},
                )

        threads = [threading.Thread(target=worker, args=(hid,)) for hid in hh_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for hid in hh_ids:
            recent = fast_ledger.recent(hid, limit=n_per_hh + 1)
            assert len(recent) == n_per_hh

    def test_undo_n_entries_with_fake_inverse(self, fast_ledger: UndoLedger):
        """N entries undone with a tracking fake inverse."""
        n = 3
        calls: list[tuple[str, dict]] = []

        def tracking_inverse(kind: str, before: dict, db):
            calls.append((kind, before))
            return True

        for i in range(n):
            fast_ledger.register(
                household_id="hh1",
                kind="consume_inventory",
                before={"lot_id": f"lot-{i}", "quantity": 1.0},
            )

        for _ in range(n):
            fast_ledger.undo_last("hh1", db=None, inverse=tracking_inverse)

        assert len(calls) == n
        assert calls[0][1]["lot_id"] == "lot-2"
        assert calls[-1][1]["lot_id"] == "lot-0"

    def test_undo_partial_n_entries(self, fast_ledger: UndoLedger):
        """Undo N/2 entries; verify remaining entries."""
        n = 4
        for i in range(n):
            fast_ledger.register(
                household_id="hh1",
                kind="add_inventory_lot",
                before={"lot_id": f"lot-{i}"},
            )

        for _ in range(2):
            fast_ledger.undo_last(
                "hh1", db=None, inverse=lambda k, b, d: True
            )

        remaining = fast_ledger.recent("hh1")
        assert len(remaining) == 2
        remaining_lots = {e.before["lot_id"] for e in remaining}
        assert "lot-0" in remaining_lots
        assert "lot-1" in remaining_lots


class TestRecordPriceInverseIntegration:
    """Verify record_price inverse handler actually deletes."""

    def test_record_price_inverse_deletes_with_real_db(self, ledger, db):
        """Undo a record_price entry; verify price observation is deleted."""
        from shopstack.schemas.models import PriceObservation

        obs = PriceObservation(
            canonical_name="test_item",
            price=100.0,
            quantity=1.0,
            unit="kg",
        )
        user_id = "test_user"
        try:
            db.add_household(user_id, "Test User")
            db.add_household_member(user_id, user_id, role="owner")
        except Exception:
            pass

        result = db.record_price(obs, user_id=user_id)
        history = db.get_price_history("test_item", user_id=user_id)
        assert len(history) == 1

        ok = _default_inverse(
            "record_price",
            {"price_id": result.price_id, "canonical_name": "test_item"},
            db,
        )
        assert ok is True

        history_after = db.get_price_history("test_item", user_id=user_id)
        assert len(history_after) == 0

    def test_record_price_inverse_no_price_id_returns_false(self):
        """record_price inverse with missing price_id returns False."""
        class FakeDb:
            conn = None

        ok = _default_inverse(
            "record_price",
            {"canonical_name": "test"},
            FakeDb(),
        )
        assert ok is False
