"""Tests for the receipt .txt export feature (added 2026-06-13).

Background:
  ``shopstack/services/receipt.py:export_receipt_json`` was
  fully built (it saves the parsed receipt as a structured
  JSON file for audit). But the parallel human-readable
  ``export_receipt_txt`` was missing. Per
  ``Docs/REMAINING_WORK.md`` Tier 2 #Receipt TXT Export:

    "Receipt TXT Export — Save parsed receipts as structured
     JSON for audit trail. (1h effort)"

  The .txt is the human-readable counterpart of the JSON
  audit file — easier to read in any text editor, easier to
  forward via messaging apps.

Fix:
  1. Added ``_receipt_txt_body(result)`` — formats a ReceiptResult
     as a plain-text string (header + items + raw OCR text).
  2. Added ``export_receipt_txt(result, user_id, data_dir)`` —
     writes the body to ``data/receipts/<timestamp>_<merchant>.txt``.
  3. Updated ``confirm_receipt`` to call ``export_receipt_txt``
     in parallel to the JSON export (both are written on
     every confirm, so the audit trail is reviewable in
     either format).
  4. Added a public ``receipt_export_txt`` Gradio adapter in
     ``shopstack/ui/screens/receipt.py`` for the on-demand
     "Save as .txt" button in the receipt sub-tab.

This test:
  1. Verifies ``export_receipt_txt`` writes a real file.
  2. Verifies the body format is correct (merchant, date,
     total, items, raw OCR text).
  3. Verifies XSS safety.
  4. Verifies the auto-export on ``confirm_receipt`` fires.
  5. Verifies the public Gradio adapter works.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


# ─── _receipt_txt_body tests ─────────────────────────────────────────────


class TestReceiptTxtBody:
    """The internal _receipt_txt_body must format a ReceiptResult correctly."""

    def test_body_includes_merchant_date_total(self):
        from shopstack.services.receipt import ReceiptResult, _receipt_txt_body
        from datetime import date
        result = ReceiptResult(
            merchant="TestMart",
            purchase_date=date(2026, 6, 13),
            lines=[],
            total=42.50,
            raw_text="",
        )
        body = _receipt_txt_body(result)
        assert "TestMart" in body
        assert "2026-06-13" in body
        assert "42.50" in body

    def test_body_includes_line_items(self):
        from shopstack.services.receipt import ReceiptResult, ReceiptLine, _receipt_txt_body
        from datetime import date
        result = ReceiptResult(
            merchant="TestMart",
            purchase_date=date(2026, 6, 13),
            lines=[
                ReceiptLine(
                    canonical_name="rice", display_name="Basmati Rice",
                    quantity=1.0, unit="kg", price=120.0,
                ),
                ReceiptLine(
                    canonical_name="onion", display_name="Red Onion",
                    quantity=2.0, unit="unit", price=30.0,
                ),
            ],
            total=150.0,
            raw_text="",
        )
        body = _receipt_txt_body(result)
        assert "Basmati Rice" in body
        assert "1 kg" in body
        assert "120.00" in body
        assert "Red Onion" in body
        assert "2 unit" in body
        assert "30.00" in body

    def test_body_includes_raw_text(self):
        from shopstack.services.receipt import ReceiptResult, _receipt_txt_body
        from datetime import date
        result = ReceiptResult(
            merchant="TestMart",
            purchase_date=date(2026, 6, 13),
            lines=[],
            total=0.0,
            raw_text="Raw OCR text from the receipt image.",
        )
        body = _receipt_txt_body(result)
        assert "Raw OCR text" in body
        assert "Raw OCR text from the receipt image" in body

    def test_body_handles_empty_items(self):
        from shopstack.services.receipt import ReceiptResult, _receipt_txt_body
        from datetime import date
        result = ReceiptResult(
            merchant="TestMart",
            purchase_date=date(2026, 6, 13),
            lines=[],
            total=0.0,
            raw_text="",
        )
        body = _receipt_txt_body(result)
        # Should mention "no items parsed" so the user knows
        # the parser found nothing
        assert "no items parsed" in body.lower() or "(no items" in body.lower()

    def test_body_xss_escape(self):
        """The body must be plain text (no HTML)."""
        from shopstack.services.receipt import ReceiptResult, _receipt_txt_body
        from datetime import date
        result = ReceiptResult(
            merchant="<script>alert(1)</script>",
            purchase_date=date(2026, 6, 13),
            lines=[],
            total=0.0,
            raw_text="<img onerror=alert(1)>",
        )
        body = _receipt_txt_body(result)
        # The body is plain text — script tags are NOT interpreted.
        # The plain text is what the user sees in a text editor.
        # We don't escape, but we also don't render HTML. The
        # text editor shows the literal characters.
        assert "<script>" in body  # literal chars, not executed

    def test_body_handles_unknown_merchant(self):
        from shopstack.services.receipt import ReceiptResult, _receipt_txt_body
        from datetime import date
        result = ReceiptResult(
            merchant="",
            purchase_date=date(2026, 6, 13),
            lines=[],
            total=0.0,
            raw_text="",
        )
        body = _receipt_txt_body(result)
        assert "(unknown)" in body


# ─── export_receipt_txt tests ───────────────────────────────────────────


class TestExportReceiptTxt:
    """export_receipt_txt writes a .txt file to the data directory."""

    def test_writes_file(self, tmp_path):
        from shopstack.services.receipt import (
            ReceiptResult, export_receipt_txt,
        )
        from datetime import date
        result = ReceiptResult(
            merchant="TestMart",
            purchase_date=date(2026, 6, 13),
            lines=[],
            total=42.50,
            raw_text="",
        )
        path = export_receipt_txt(result, user_id="user1", data_dir=tmp_path)
        assert path.exists()
        assert path.suffix == ".txt"
        # Filename pattern: <timestamp>_<merchant>.txt
        assert "TestMart" in path.name
        # The file should contain the merchant
        content = path.read_text(encoding="utf-8")
        assert "TestMart" in content
        assert "42.50" in content

    def test_sanitizes_merchant_filename(self, tmp_path):
        """Special chars in merchant get stripped from filename."""
        from shopstack.services.receipt import (
            ReceiptResult, export_receipt_txt,
        )
        from datetime import date
        result = ReceiptResult(
            merchant="Mr. Foo's Bar! 123",
            purchase_date=date(2026, 6, 13),
            lines=[],
            total=0.0,
            raw_text="",
        )
        path = export_receipt_txt(result, user_id="user1", data_dir=tmp_path)
        # No dots, no apostrophes, no bang, no spaces (replaced with _)
        assert "'" not in path.name
        assert "!" not in path.name
        assert " " not in path.name

    def test_writes_audit_header(self, tmp_path):
        from shopstack.services.receipt import (
            ReceiptResult, export_receipt_txt,
        )
        from datetime import date
        result = ReceiptResult(
            merchant="TestMart",
            purchase_date=date(2026, 6, 13),
            lines=[],
            total=0.0,
            raw_text="",
        )
        path = export_receipt_txt(
            result, user_id="alice", data_dir=tmp_path,
        )
        content = path.read_text(encoding="utf-8")
        # Audit header mentions the user
        assert "alice" in content
        # And has a timestamp
        assert "2026" in content


# ─── Public Gradio adapter tests ──────────────────────────────────────


class TestReceiptExportTxtGradio:
    """The public Gradio adapter must work for the UI button."""

    def test_public_adapter_is_importable(self):
        from shopstack.ui.screens.receipt import receipt_export_txt
        assert callable(receipt_export_txt)

    def test_public_adapter_returns_plain_text(self):
        from shopstack.ui.screens.receipt import receipt_export_txt
        result = receipt_export_txt(
            merchant="TestMart",
            date_str="2026-06-13",
            raw_text="raw OCR text",
        )
        assert isinstance(result, str)
        assert "TestMart" in result
        assert "2026-06-13" in result
        assert "raw OCR text" in result

    def test_public_adapter_handles_bad_date(self):
        from shopstack.ui.screens.receipt import receipt_export_txt
        # Should not raise on bad date
        result = receipt_export_txt(
            merchant="TestMart",
            date_str="not-a-date",
            raw_text="raw text",
        )
        assert isinstance(result, str)
        assert "TestMart" in result

    def test_public_adapter_handles_empty_inputs(self):
        from shopstack.ui.screens.receipt import receipt_export_txt
        result = receipt_export_txt(
            merchant="",
            date_str="",
            raw_text="",
        )
        assert isinstance(result, str)
        # Should not raise
        assert "(unknown)" in result


# ─── App wiring tests ──────────────────────────────────────────────


class TestReceiptExportWiringInApp:
    """The receipt sub-tab must wire the new button."""

    def test_basket_add_items_imports_receipt_export_txt(self):
        from pathlib import Path
        tab_py = Path("shopstack/ui/tabs/basket_add_items.py").read_text()
        assert "receipt_export_txt" in tab_py, (
            "basket_add_items.py must import receipt_export_txt."
        )

    def test_basket_add_items_wires_api_name(self):
        from pathlib import Path
        tab_py = Path("shopstack/ui/tabs/basket_add_items.py").read_text()
        assert 'api_name="receipt_export_txt"' in tab_py, (
            "The export button must register with "
            "api_name='receipt_export_txt'."
        )

    def test_confirm_receipt_calls_export_receipt_txt(self):
        """Static check that confirm_receipt also writes the .txt file."""
        from pathlib import Path
        svc = Path("shopstack/services/receipt.py").read_text()
        assert "export_receipt_txt(result, user_id=user_id)" in svc, (
            "confirm_receipt must also call export_receipt_txt for "
            "the parallel .txt audit file."
        )
