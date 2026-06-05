from __future__ import annotations

from shopstack.schemas.models import InventoryLot, PriceObservation, Trace
from shopstack.ui_support import build_price_memory_view, load_field_notes, save_field_notes


def test_build_price_memory_view_returns_summary_plot_and_table(db):
    db.record_price(PriceObservation(canonical_name="milk", price=50.0, quantity=1.0, unit="L", store_name="Store A"))
    db.record_price(PriceObservation(canonical_name="milk", price=55.0, quantity=1.0, unit="L", store_name="Store B"))

    summary, df, table = build_price_memory_view(db, "milk")

    assert "Price Memory for milk" in summary
    assert list(df["price"]) == [50.0, 55.0]
    assert table[0] == ["Date", "Store", "Price", "Qty", "Unit", "Notes"]
    assert len(table) == 3


def test_build_price_memory_view_handles_missing_item(db):
    summary, df, table = build_price_memory_view(db, "")

    assert "Enter an item name" in summary
    assert df.empty
    assert table[0][0] == "Enter an item name to see price history"


def test_field_notes_round_trip(db):
    db.add_inventory_lot(InventoryLot(canonical_name="bread", display_name="Bread", quantity=0.5, unit="loaf"))
    db.save_trace(Trace(input_type="voice", final_response="buy bread"))

    draft, preview, status = load_field_notes(db)

    assert "# Field Notes" in draft
    assert draft == preview
    assert "generated from recent activity" in status.lower()

    saved_draft, saved_preview, saved_status = save_field_notes(db, "# Saved notes")

    assert saved_draft == "# Saved notes"
    assert saved_preview == "# Saved notes"
    assert "saved locally" in saved_status.lower()

    reloaded_draft, reloaded_preview, reloaded_status = load_field_notes(db)

    assert reloaded_draft == "# Saved notes"
    assert reloaded_preview == "# Saved notes"
    assert "loaded saved field notes" in reloaded_status.lower()
