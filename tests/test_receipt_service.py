from __future__ import annotations

from datetime import date

from shopstack.services.receipt import (
    ReceiptLine,
    ReceiptResult,
    _find_merchant,
    _find_purchase_date,
    _find_total,
    _parse_line,
    _parse_quantity_unit,
    confirm_receipt,
    parse_receipt_text,
)


def test_parse_quantity_unit_kg():
    qty, unit = _parse_quantity_unit("1 kg")
    assert qty == 1.0
    assert unit == "kg"


def test_parse_quantity_unit_grams_to_kg():
    qty, unit = _parse_quantity_unit("500 g")
    assert qty == 0.5
    assert unit == "kg"


def test_parse_quantity_unit_small_grams_stay():
    qty, unit = _parse_quantity_unit("50 g")
    assert qty == 50.0
    assert unit == "g"


def test_parse_quantity_unit_numeric_only():
    qty, unit = _parse_quantity_unit("3")
    assert qty == 3.0
    assert unit == "unit"


def test_parse_quantity_unit_empty():
    qty, unit = _parse_quantity_unit("")
    assert qty == 1.0
    assert unit == "unit"


def test_find_merchant_first_line():
    assert _find_merchant("DMart Store\nTomato 1kg 40") == "DMart Store"


def test_find_merchant_skips_date():
    assert _find_merchant("Date: 06/06/2026\nBigBasket\nItem 100") == "BigBasket"


def test_find_merchant_empty():
    assert _find_merchant("") == "Unknown Store"


def test_find_purchase_date_dd_mm_yyyy():
    text = "Invoice\n06/06/2026\nTotal: 500"
    assert _find_purchase_date(text) == date(2026, 6, 6)


def test_find_purchase_date_yyyy_mm_dd():
    text = "2026-06-06\nItem 100"
    assert _find_purchase_date(text) == date(2026, 6, 6)


def test_find_purchase_date_no_date():
    text = "Store Name\nItem 100"
    result = _find_purchase_date(text)
    assert isinstance(result, date)


def test_find_total_explicit():
    text = "Item 100\nTotal: 450.00"
    assert _find_total(text) == 450.0


def test_find_total_rs_prefix():
    text = "Item 100\nRs. 250.50"
    assert _find_total(text) == 250.5


def test_find_total_no_total():
    text = "Store Name\nNo prices here"
    assert _find_total(text) == 0.0


def test_parse_line_with_unit():
    line = _parse_line("ONION 1 KG 40.00")
    assert line is not None
    assert line.canonical_name == "onion"
    assert line.quantity == 1.0
    assert line.unit == "kg"
    assert line.price == 40.0


def test_parse_line_qty_price():
    line = _parse_line("Milk 2 120")
    assert line is not None
    assert line.canonical_name == "milk"
    assert line.quantity == 2.0
    assert line.price == 120.0


def test_parse_line_price_only():
    line = _parse_line("Bread 35")
    assert line is not None
    assert line.canonical_name == "bread"
    assert line.quantity == 1.0
    assert line.price == 35.0


def test_parse_line_empty():
    assert _parse_line("") is None
    assert _parse_line("   ") is None


def test_parse_receipt_text_full():
    text = "DMart\n06/06/2026\nONION 1 KG 40.00\nMilk 2 120\nTotal: 160.00"
    result = parse_receipt_text(text)

    assert isinstance(result, ReceiptResult)
    assert result.merchant == "DMart"
    assert result.purchase_date == date(2026, 6, 6)
    assert result.total == 160.0
    assert len(result.lines) == 2
    assert result.lines[0].canonical_name == "onion"
    assert result.lines[1].canonical_name == "milk"


def test_parse_receipt_text_skips_total_line():
    text = "Store\nONION 1 KG 40\nTotal 40\nGST 5"
    result = parse_receipt_text(text)
    # Only onion, total and GST are skipped
    assert len(result.lines) == 1
    assert result.lines[0].canonical_name == "onion"


def test_parse_receipt_text_deduplicates():
    text = "Store\nONION 1 KG 40\nONION 1 KG 45"
    result = parse_receipt_text(text)
    assert len(result.lines) == 1


def test_confirm_receipt_scopes_to_user_id(db):
    result = ReceiptResult(
        merchant="Demo Mart",
        purchase_date=date(2026, 6, 6),
        lines=[
            ReceiptLine(
                canonical_name="milk",
                display_name="Milk",
                quantity=2.0,
                unit="L",
                price=120.0,
            ),
        ],
        total=120.0,
        raw_text="Milk 2 L 120",
    )

    ir = confirm_receipt(db, result, user_id="house_a")

    assert ir.errors == []
    assert ir.items_added == 1
    assert ir.price_observations_added == 1
    assert len(db.get_inventory(canonical_name="milk", user_id="house_a")) == 1
    assert len(db.get_inventory(canonical_name="milk", user_id="house_b")) == 0
    assert len(db.get_purchase_events(user_id="house_a")) == 1
    assert len(db.get_purchase_events(user_id="house_b")) == 0
