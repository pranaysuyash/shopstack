"""Tests for the receipt audit-trail export (§4.1 from NOT_STARTED_FEATURES).

The receipt service should save the parsed result to a structured
JSON file when ``confirm_receipt`` is called, so the raw OCR text +
parse result can be reviewed later even if the parse was wrong.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from shopstack.services.receipt import (
    ReceiptLine,
    ReceiptResult,
    export_receipt_json,
)


def _make_result(raw_text: str = "raw OCR text") -> ReceiptResult:
    return ReceiptResult(
        merchant="TestMart",
        purchase_date=date(2026, 6, 13),
        total=100.0,
        lines=[
            ReceiptLine(
                canonical_name="milk",
                display_name="Milk",
                quantity=1.0,
                unit="L",
                price=50.0,
            ),
            ReceiptLine(
                canonical_name="bread",
                display_name="Bread",
                quantity=1.0,
                unit="loaf",
                price=50.0,
            ),
        ],
        raw_text=raw_text,
    )


def test_export_creates_file_in_data_receipts(tmp_path: Path):
    """A file is created in the data/receipts/ directory (or override)."""
    result = _make_result()
    path = export_receipt_json(result, user_id="hh1", data_dir=tmp_path / "receipts")
    assert path.exists()
    assert path.suffix == ".json"
    assert "TestMart" in path.name


def test_export_contains_raw_text_and_parsed(tmp_path: Path):
    """The JSON includes raw_text + parsed structure + user_id + timestamp."""
    result = _make_result(raw_text="milk 1L 50.00\nbread 1loaf 50.00")
    path = export_receipt_json(result, user_id="hh1", data_dir=tmp_path)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["raw_text"] == "milk 1L 50.00\nbread 1loaf 50.00"
    assert payload["user_id"] == "hh1"
    assert "confirmed_at" in payload
    # Parsed structure
    assert payload["parsed"]["merchant"] == "TestMart"
    assert payload["parsed"]["total"] == 100.0
    assert len(payload["parsed"]["lines"]) == 2
    assert payload["parsed"]["lines"][0]["canonical_name"] == "milk"


def test_export_sanitizes_merchant_filename(tmp_path: Path):
    """Unsafe characters in merchant are stripped from the filename."""
    result = _make_result()
    result.merchant = "../../etc/passwd"  # path traversal attempt
    path = export_receipt_json(result, data_dir=tmp_path)
    # Path is contained within tmp_path (no traversal)
    assert path.resolve().is_relative_to(tmp_path.resolve())


def test_export_creates_directory_if_missing(tmp_path: Path):
    """The data/receipts/ directory is auto-created."""
    receipt_dir = tmp_path / "nested" / "deeper" / "receipts"
    assert not receipt_dir.exists()
    result = _make_result()
    path = export_receipt_json(result, data_dir=receipt_dir)
    assert receipt_dir.exists()
    assert path.exists()
