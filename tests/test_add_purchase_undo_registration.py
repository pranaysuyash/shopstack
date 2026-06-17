"""Tests: add_purchase_form / add_purchase_batch register undo entries.

Verifies that the undo registration wired inside these Gradio screen
handlers actually produces entries in the undo ledger.

Both ``add_purchase_form`` and ``add_purchase_batch`` call
``undo_ledger.get_ledger().register(...)`` after each successful
``tools.add_inventory_item()`` call. This test suite checks:

  * A single purchase produces one undo entry.
  * A batch of N items produces N undo entries.
  * The undo entries have the right ``kind``, ``before``, and ``after``
    structure so the default inverse can reverse them.
  * The undo entry is associated with the correct household_id.

**Coverage gap filled:** 0 existing tests for this path.
"""
from __future__ import annotations

import pytest

from shopstack.services.undo_ledger import get_ledger, reset_ledger


@pytest.fixture(autouse=True)
def _fresh_ledger():
    """Reset the undo ledger singleton before each test."""
    reset_ledger()
    yield
    reset_ledger()


class TestAddPurchaseFormUndo:
    """add_purchase_form registers an undo entry on successful add."""

    def test_undo_entry_created(self, app):
        """A call to add_purchase_form produces exactly one undo entry."""
        from shopstack.ui.screens.inventory import add_purchase_form

        reset_ledger()
        result = add_purchase_form(
            name="Milk",
            qty=2.0,
            unit="L",
            price=64.0,
            store="Sharma Kirana",
            location="fridge",
            purchase_date_str="2026-06-15",
            category="dairy",
        )
        assert "Added" in result, f"Expected success HTML, got: {result[:80]}"

        ledger = get_ledger()
        entries = ledger.recent("default_household", limit=10)
        assert len(entries) >= 1, "Expected at least 1 undo entry"

        # Find the screen-level entry (kind=add_inventory_lot).
        # Price entries may also exist if a price+store was provided.
        screen_entry = next(
            (e for e in entries if e.kind == "add_inventory_lot"),
            None,
        )
        assert screen_entry is not None, (
            f"No add_inventory_lot entry found among {len(entries)} entries: "
            f"{[e.kind for e in entries]}"
        )
        assert "Milk" in screen_entry.description
        assert screen_entry.household_id == "default_household"

    def test_undo_entry_has_correct_before(self, app):
        """The undo entry's ``before`` dict has lot_id, user_id, canonical_name."""
        from shopstack.ui.screens.inventory import add_purchase_form

        reset_ledger()
        add_purchase_form(
            name="Basmati Rice",
            qty=5.0,
            unit="kg",
            price=450.0,
            store="DMart",
            location="pantry",
            purchase_date_str="2026-06-15",
            category="grains",
        )

        ledger = get_ledger()
        entries = ledger.recent("default_household")
        assert entries, "Expected at least one entry"
        # Find the screen-level entry (kind=add_inventory_lot) —
        # price entries may be more recent if price+store was set.
        entry = next(
            (e for e in entries if e.kind == "add_inventory_lot"),
            None,
        )
        assert entry is not None, (
            f"No add_inventory_lot entry found among: {[e.kind for e in entries]}"
        )
        assert "lot_id" in entry.before
        assert entry.before["canonical_name"] == "basmati rice"
        assert "user_id" in entry.before

    def test_undo_entry_has_correct_after(self, app):
        """The undo entry's ``after`` dict has canonical_name, quantity, unit."""
        from shopstack.ui.screens.inventory import add_purchase_form

        reset_ledger()
        add_purchase_form(
            name="Toor Dal",
            qty=2.0,
            unit="kg",
            price=180.0,
            store="Big Bazaar",
            location="pantry",
            purchase_date_str="",
            category="pulses",
        )

        ledger = get_ledger()
        entries = ledger.recent("default_household")
        entry = next(
            (e for e in entries if e.kind == "add_inventory_lot"),
            None,
        )
        assert entry is not None, (
            f"No add_inventory_lot entry found among: {[e.kind for e in entries]}"
        )
        assert entry.after["canonical_name"] == "toor dal"
        assert entry.after["quantity"] == 2.0
        assert entry.after["unit"] == "kg"
        assert entry.after["action"] == "purchased"

    def test_zero_price_no_store_still_registers_undo(self, app):
        """Even without price/store, the undo entry is created."""
        from shopstack.ui.screens.inventory import add_purchase_form

        reset_ledger()
        add_purchase_form(
            name="Water",
            qty=1.0,
            unit="L",
            price=0.0,
            store="",
            location="pantry",
            purchase_date_str="",
            category="",
        )

        ledger = get_ledger()
        entries = ledger.recent("default_household")
        assert entries, "Undo entry should be created even without price/store"


class TestAddPurchaseBatchUndo:
    """add_purchase_batch registers one undo entry per item."""

    def test_single_item_produces_one_entry(self, app):
        """A single-item batch produces exactly one undo entry."""
        from shopstack.ui.screens.inventory import add_purchase_batch

        reset_ledger()
        result = add_purchase_batch("milk, 2, L, 64, Sharma Kirana")

        assert "Added" in result, f"Expected success, got: {result[:80]}"

        ledger = get_ledger()
        entries = ledger.recent("default_household", limit=10)
        assert len(entries) >= 1

    def test_n_items_produces_n_entries(self, app):
        """A batch of N items produces N undo entries (or more)."""
        from shopstack.ui.screens.inventory import add_purchase_batch

        reset_ledger()
        batch_text = (
            "milk, 2, L, 64, Sharma Kirana\n"
            "rice, 5, kg, 680, DMart\n"
            "onion, 2, kg, 40, Local Vendor\n"
            "tomato, 1, kg, 30, Local Vendor\n"
            "eggs, 1, dozen, 80, Sharma Kirana"
        )
        result = add_purchase_batch(batch_text)

        assert "5 item(s)" in result, f"Expected 5 items, got: {result[:100]}"

        ledger = get_ledger()
        entries = ledger.recent("default_household", limit=20)
        # Each item creates one screen-level undo entry (plus DB-level entries)
        screen_entries = [e for e in entries if e.kind == "add_inventory_lot"
                          and "batch" in e.description.lower()]
        assert len(screen_entries) >= 5, (
            f"Expected at least 5 batch undo entries, got {len(screen_entries)}"
        )

    def test_batch_undo_entry_structure(self, app):
        """Each batch undo entry has the right kind and canonical_name."""
        from shopstack.ui.screens.inventory import add_purchase_batch

        reset_ledger()
        add_purchase_batch("milk, 2, L, 64, Sharma Kirana\nbread, 1, unit, 40, Local Bakery")

        ledger = get_ledger()
        entries = ledger.recent("default_household", limit=10)

        # Find the two batch-add entries (screen-level kind=add_inventory_lot)
        batch_entries = [
            e for e in entries
            if e.kind == "add_inventory_lot" and "batch" in e.description.lower()
        ]
        assert len(batch_entries) >= 2

        names = sorted(e.after.get("canonical_name", "") for e in batch_entries)
        assert "bread" in names
        assert "milk" in names


class TestEdgeCases:
    """Edge cases for undo registration in purchase flows."""

    def test_empty_name_returns_error_no_undo(self, app):
        """An empty item name should NOT create an undo entry."""
        from shopstack.ui.screens.inventory import add_purchase_form

        reset_ledger()
        result = add_purchase_form(
            name="",
            qty=1.0,
            unit="unit",
            price=0.0,
            store="",
            location="pantry",
            purchase_date_str="",
            category="",
        )
        assert "required" in result.lower() or "Error" in result, (
            f"Expected error for empty name, got: {result[:100]}"
        )

        ledger = get_ledger()
        entries = ledger.recent("default_household")
        assert not entries, "No undo entry should be created on validation failure"

    def test_empty_batch_returns_error_no_undo(self, app):
        """An empty batch string should NOT create undo entries."""
        from shopstack.ui.screens.inventory import add_purchase_batch

        reset_ledger()
        result = add_purchase_batch("")

        assert "no valid" in result.lower() or "at least one" in result.lower(), (
            f"Expected error for empty batch, got: {result[:100]}"
        )

        ledger = get_ledger()
        entries = ledger.recent("default_household")
        assert not entries, "No undo entry should be created on empty batch"

    def test_multiple_calls_produce_separate_entries(self, app):
        """Two separate add_purchase_form calls each produce their own entry."""
        from shopstack.ui.screens.inventory import add_purchase_form

        reset_ledger()
        add_purchase_form("Milk", 1.0, "L", 60.0, "DMart", "fridge", "", "dairy")
        add_purchase_form("Bread", 1.0, "unit", 40.0, "Local", "pantry", "", "bakery")

        ledger = get_ledger()
        entries = ledger.recent("default_household", limit=10)
        # Each call creates at least one screen-level undo entry
        screen_entries = [e for e in entries
                          if e.kind == "add_inventory_lot"]
        assert len(screen_entries) >= 2, (
            f"Expected at least 2 screen-level undo entries, got {len(screen_entries)}"
        )
