from __future__ import annotations


import pytest

from shopstack.portability import (
    export_csv_inventory,
    export_backup,
    export_json,
    import_csv,
    import_json,
)
from shopstack.schemas.models import InventoryLot, PurchaseEvent


@pytest.fixture
def populated_db(db):
    db.add_inventory_lot(InventoryLot(canonical_name="milk", display_name="Milk", quantity=2.0, unit="L"))
    db.add_inventory_lot(InventoryLot(canonical_name="eggs", display_name="Eggs", quantity=12.0, unit="pieces"))
    db.add_purchase_event(PurchaseEvent(canonical_name="milk", quantity=2.0, total_price=60))
    return db


class TestExportJSON:
    def test_export_contains_schema_version(self, populated_db):
        data = export_json(populated_db)
        assert data["schema_version"] == "1.0"
        assert "exported_at" in data

    def test_export_contains_inventory(self, populated_db):
        data = export_json(populated_db)
        assert len(data["inventory"]) >= 2
        names = [i["canonical_name"] for i in data["inventory"]]
        assert "milk" in names
        assert "eggs" in names

    def test_export_contains_purchase_events(self, populated_db):
        data = export_json(populated_db)
        assert len(data["purchase_events"]) >= 1

    def test_export_empty_inventory(self, db):
        data = export_json(db)
        assert data["inventory"] == []


def test_export_backup_includes_household_locations(db):
    data = export_backup(db)
    assert "household_locations" in data
    assert "storage_locations" in data
    assert isinstance(data["household_locations"], list)
    assert isinstance(data["storage_locations"], list)
    assert len(data["household_locations"]) > 0
    assert len(data["household_locations"]) == len(data["storage_locations"])


class TestExportCSV:
    def test_csv_has_header(self, populated_db):
        csv_text = export_csv_inventory(populated_db)
        assert csv_text.startswith("lot_id,canonical_name,display_name")

    def test_csv_contains_items(self, populated_db):
        csv_text = export_csv_inventory(populated_db)
        assert "milk" in csv_text
        assert "eggs" in csv_text

    def test_csv_empty(self, db):
        csv_text = export_csv_inventory(db)
        assert csv_text.strip().endswith("currency")


class TestImportJSON:
    def test_import_adds_items(self, db):
        data = {
            "schema_version": "1.0",
            "inventory": [
                {"canonical_name": "rice", "quantity": 5.0, "unit": "kg"},
                {"canonical_name": "pasta", "quantity": 2.0, "unit": "packets"},
            ],
        }
        result = import_json(db, data)
        assert result.items_added == 2
        assert result.items_updated == 0
        assert len(result.errors) == 0

    def test_import_updates_existing(self, db):
        db.add_inventory_lot(InventoryLot(canonical_name="milk", display_name="Milk", quantity=1.0, unit="L"))
        data = {
            "schema_version": "1.0",
            "inventory": [{"canonical_name": "milk", "quantity": 3.0}],
        }
        result = import_json(db, data)
        assert result.items_updated == 1
        inventory = db.get_inventory(canonical_name="milk")
        assert inventory[0].quantity == 3.0

    def test_import_missing_canonical_name(self, db):
        data = {
            "schema_version": "1.0",
            "inventory": [{"quantity": 1.0}],
        }
        result = import_json(db, data)
        assert result.items_added == 0
        assert len(result.errors) == 1

    def test_import_invalid_data(self, db):
        result = import_json(db, "not a dict")  # type: ignore
        assert len(result.errors) == 1

    def test_import_price_observations(self, db):
        data = {
            "schema_version": "1.0",
            "price_observations": [
                {"canonical_name": "milk", "price": 60.0, "store_name": "Test Store"},
            ],
        }
        result = import_json(db, data)
        assert result.price_observations_added == 1
        assert len(result.errors) == 0

    def test_import_field_notes(self, db):
        data = {
            "schema_version": "1.0",
            "field_notes": "# My notes\nTest content",
        }
        _result = import_json(db, data)
        assert db.get_config_value("field_notes_markdown") == "# My notes\nTest content"

    def test_summary_html(self, db):
        data = {"schema_version": "1.0", "inventory": [{"canonical_name": "test", "quantity": 1.0}]}
        result = import_json(db, data)
        html = result.summary_html
        assert "<strong>1</strong> items added" in html


class TestImportCSV:
    def test_import_csv_adds_items(self, db):
        csv_text = "canonical_name,quantity,unit\nrice,5,kg\npasta,2,packets\n"
        result = import_csv(db, csv_text)
        assert result.items_added == 2
        assert len(result.errors) == 0

    def test_import_csv_updates_existing(self, db):
        db.add_inventory_lot(InventoryLot(canonical_name="milk", display_name="Milk", quantity=1.0, unit="L"))
        csv_text = "canonical_name,quantity\nmilk,4\n"
        result = import_csv(db, csv_text)
        assert result.items_updated == 1

    def test_import_csv_no_header(self, db):
        result = import_csv(db, "invalid\nno header")
        assert len(result.errors) == 1

    def test_import_csv_blank_rows(self, db):
        csv_text = "canonical_name,quantity\n,1\n"
        result = import_csv(db, csv_text)
        assert result.items_added == 0
        assert len(result.errors) == 1


class TestImportDataFilePathResolution:
    """import_data_file must handle Gradio's various file upload
    return types: string path, Path, tempfile wrapper, dict.

    Per the 2026-06-14 fix: Gradio 5.x returns different types
    depending on the gr.File configuration. The fix adds
    _resolve_uploaded_file_path() to normalize all of them.
    """

    def test_string_path_is_returned_as_is(self):
        from shopstack.ui.screens.portability import _resolve_uploaded_file_path
        assert _resolve_uploaded_file_path("/tmp/test.json") == "/tmp/test.json"

    def test_path_object_is_converted_to_string(self):
        from pathlib import Path
        from shopstack.ui.screens.portability import _resolve_uploaded_file_path
        result = _resolve_uploaded_file_path(Path("/tmp/test.json"))
        assert result == "/tmp/test.json"
        assert isinstance(result, str)

    def test_none_returns_none(self):
        from shopstack.ui.screens.portability import _resolve_uploaded_file_path
        assert _resolve_uploaded_file_path(None) is None

    def test_empty_string_returns_none(self):
        from shopstack.ui.screens.portability import _resolve_uploaded_file_path
        assert _resolve_uploaded_file_path("") is None

    def test_dict_with_name_key_returns_path(self):
        from shopstack.ui.screens.portability import _resolve_uploaded_file_path
        result = _resolve_uploaded_file_path({"name": "/tmp/upload.json"})
        assert result == "/tmp/upload.json"

    def test_dict_with_path_key_returns_path(self):
        from shopstack.ui.screens.portability import _resolve_uploaded_file_path
        result = _resolve_uploaded_file_path({"path": "/tmp/upload.json"})
        assert result == "/tmp/upload.json"

    def test_dict_without_path_returns_none(self):
        from shopstack.ui.screens.portability import _resolve_uploaded_file_path
        result = _resolve_uploaded_file_path({"other_key": "value"})
        assert result is None

    def test_object_with_name_attribute_returns_path(self):
        from shopstack.ui.screens.portability import _resolve_uploaded_file_path

        class FakeFile:
            name = "/tmp/fakefile.json"

        assert _resolve_uploaded_file_path(FakeFile()) == "/tmp/fakefile.json"


class TestImportDataFileErrorHandling:
    """import_data_file must produce helpful error messages for
    common failure modes.
    """

    def test_no_file_path_returns_helpful_message(self):
        from shopstack.ui.screens.portability import import_data_file
        result = import_data_file(None)
        assert "Upload" in result
        assert "JSON or CSV" in result

    def test_invalid_json_returns_error_html(self):
        import json
        import tempfile
        from shopstack.ui.screens.portability import import_data_file

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False,
        ) as f:
            f.write("{invalid json")
            tmp_path = f.name
        try:
            result = import_data_file(tmp_path)
            assert "Import failed" in result
            assert "red" in result  # error styling
        finally:
            import os
            os.unlink(tmp_path)
