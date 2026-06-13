"""Tests for the encrypted backup service.

The service exports a household's data to an encrypted JSON envelope and
imports it back. Tests cover:

- Round-trip: export → import → same row counts.
- Wrong passphrase fails with a clear error.
- Tampered ciphertext fails (AES-GCM auth tag).
- Malformed JSON / wrong version fail with clear errors.
- Per-table counts are reported accurately.
- Empty / minimal backups work.
- Passphrase length validation (export).
- Cross-household restoration: restore into a different household.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

from shopstack.config import Settings
from shopstack.persistence.database import Database
from shopstack.schemas.models import InventoryLot, ShoppingListItem
from shopstack.services.backup import (
    BACKUP_VERSION,
    export_backup,
    import_backup,
)


@pytest.fixture()
def fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = Settings(_env_file=None, db_path=path, off_the_grid=True, planner_backend="mock")
    db = Database(path)
    yield db, path
    Path(path).unlink(missing_ok=True)


def _seed_minimal(db: Database, hh: str) -> dict[str, int]:
    """Seed a tiny but realistic dataset and return expected counts."""
    db.active_household_id = hh
    # 2 inventory lots
    db.add_inventory_lot(
        InventoryLot(
            canonical_name="milk",
            display_name="Milk",
            quantity=1.0,
            unit="L",
            status="active",
            storage_location_id="home.kitchen.fridge.door_1",
        ),
        user_id=hh,
    )
    db.add_inventory_lot(
        InventoryLot(
            canonical_name="onion",
            display_name="Onion",
            quantity=2.0,
            unit="kg",
            status="active",
            storage_location_id="home.pantry.shelf_1",
        ),
        user_id=hh,
    )
    # 1 shopping list + 2 items
    sl = db.create_shopping_list(goal="Test", user_id=hh)
    db.add_list_item(
        sl.list_id,
        ShoppingListItem(
            canonical_name="tomato", display_name="Tomato", requested_quantity=2, unit="kg"
        ),
    )
    db.add_list_item(
        sl.list_id,
        ShoppingListItem(
            canonical_name="rice", display_name="Rice", requested_quantity=5, unit="kg"
        ),
    )
    return {
        "inventory_lots": 2,
        "shopping_lists": 1,
        "shopping_list_items": 2,
    }


class TestExportBackup:
    def test_export_minimal_returns_success(self, fresh_db):
        db, _ = fresh_db
        _seed_minimal(db, "hh1")
        result = export_backup(db, "hh1", "test-passphrase")
        assert result.success is True
        assert result.operation == "export"
        assert result.error == ""
        assert result.envelope_json != ""

    def test_export_counts_match_seeded_data(self, fresh_db):
        db, _ = fresh_db
        _seed_minimal(db, "hh1")
        result = export_backup(db, "hh1", "test-passphrase")
        assert result.counts["inventory_lots"] == 2
        assert result.counts["shopping_lists"] == 1
        assert result.counts["shopping_list_items"] == 2

    def test_envelope_is_valid_json_with_version(self, fresh_db):
        db, _ = fresh_db
        _seed_minimal(db, "hh1")
        result = export_backup(db, "hh1", "test-passphrase")
        envelope = json.loads(result.envelope_json)
        assert envelope["version"] == BACKUP_VERSION
        assert envelope["kdf"] == "pbkdf2-sha256"
        assert envelope["iterations"] == 200_000
        assert envelope["household_id"] == "hh1"
        assert "salt_b64" in envelope
        assert "nonce_b64" in envelope
        assert "ciphertext_b64" in envelope

    def test_too_short_passphrase_rejected(self, fresh_db):
        db, _ = fresh_db
        result = export_backup(db, "hh1", "abc")  # < 4 chars
        assert result.success is False
        assert "at least 4 characters" in result.error

    def test_empty_passphrase_rejected(self, fresh_db):
        db, _ = fresh_db
        result = export_backup(db, "hh1", "")
        assert result.success is False

    def test_export_empty_db_still_succeeds(self, fresh_db):
        """No data should still produce a valid (empty) envelope."""
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = export_backup(db, "hh1", "test-passphrase")
        assert result.success is True
        assert result.counts["inventory_lots"] == 0
        assert result.counts["shopping_lists"] == 0

    def test_two_exports_have_different_salts_and_nonces(self, fresh_db):
        """Each export must be unique (random salt + nonce)."""
        db, _ = fresh_db
        _seed_minimal(db, "hh1")
        e1 = json.loads(export_backup(db, "hh1", "pass").envelope_json)
        e2 = json.loads(export_backup(db, "hh1", "pass").envelope_json)
        assert e1["salt_b64"] != e2["salt_b64"]
        assert e1["nonce_b64"] != e2["nonce_b64"]
        assert e1["ciphertext_b64"] != e2["ciphertext_b64"]


class TestImportBackup:
    def test_round_trip_restores_all_rows(self, fresh_db):
        db, path = fresh_db
        _seed_minimal(db, "hh1")
        result = export_backup(db, "hh1", "pass-phrase")
        assert result.success
        # Wipe inventory/lists/prices/prefs
        for table in [
            "inventory_lots", "shopping_list_items", "shopping_lists",
            "price_observations", "preference_signals",
        ]:
            try:
                db.conn.execute(f"DELETE FROM {table}")
                db.conn.commit()
            except Exception:
                pass
        # Restore
        imp = import_backup(db, result.envelope_json, "pass-phrase", "hh1")
        assert imp.success
        assert imp.counts["inventory_lots"] == 2
        assert imp.counts["shopping_lists"] == 1
        assert imp.counts["shopping_list_items"] == 2

    def test_wrong_passphrase_fails(self, fresh_db):
        db, _ = fresh_db
        _seed_minimal(db, "hh1")
        result = export_backup(db, "hh1", "right-pass")
        imp = import_backup(db, result.envelope_json, "wrong-pass", "hh1")
        assert imp.success is False
        assert "Decryption failed" in imp.error or "tampered" in imp.error.lower()

    def test_tampered_ciphertext_fails(self, fresh_db):
        db, _ = fresh_db
        _seed_minimal(db, "hh1")
        result = export_backup(db, "hh1", "pass")
        envelope = json.loads(result.envelope_json)
        # Flip one character in the ciphertext
        ct = envelope["ciphertext_b64"]
        tampered = "A" + ct[1:] if ct[0] != "A" else "B" + ct[1:]
        envelope["ciphertext_b64"] = tampered
        imp = import_backup(db, json.dumps(envelope), "pass", "hh1")
        assert imp.success is False

    def test_malformed_envelope_json_fails(self, fresh_db):
        db, _ = fresh_db
        imp = import_backup(db, "not json at all", "pass", "hh1")
        assert imp.success is False
        assert "not JSON" in imp.error or "JSON" in imp.error

    def test_wrong_version_rejected(self, fresh_db):
        db, _ = fresh_db
        envelope = {
            "version": 99,
            "kdf": "pbkdf2-sha256",
            "iterations": 200000,
            "salt_b64": "AAAA",
            "nonce_b64": "AAAA",
            "ciphertext_b64": "AAAA",
            "created_at": "2026-06-12T00:00:00Z",
            "household_id": "hh1",
        }
        imp = import_backup(db, json.dumps(envelope), "pass", "hh1")
        assert imp.success is False
        assert "version" in imp.error.lower()

    def test_missing_envelope_fields_rejected(self, fresh_db):
        db, _ = fresh_db
        envelope = {
            "version": BACKUP_VERSION,
            "salt_b64": "AAAA",
            # missing nonce_b64, ciphertext_b64
        }
        imp = import_backup(db, json.dumps(envelope), "pass", "hh1")
        assert imp.success is False
        assert "missing" in imp.error.lower()

    def test_empty_envelope_fails(self, fresh_db):
        db, _ = fresh_db
        imp = import_backup(db, "", "pass", "hh1")
        assert imp.success is False

    def test_empty_passphrase_fails(self, fresh_db):
        db, _ = fresh_db
        _seed_minimal(db, "hh1")
        result = export_backup(db, "hh1", "pass")
        imp = import_backup(db, result.envelope_json, "", "hh1")
        assert imp.success is False

    def test_restore_into_different_household(self, fresh_db):
        """Restore from hh1 envelope into hh2. Items are scoped to the
        restore household (hh2), not the source (hh1)."""
        db, _ = fresh_db
        _seed_minimal(db, "hh1")
        result = export_backup(db, "hh1", "pass")
        assert result.success
        # Now restore into hh2
        imp = import_backup(db, result.envelope_json, "pass", "hh2")
        assert imp.success
        # Verify the items are visible in hh2
        lots = db.get_inventory(user_id="hh2")
        assert len(lots) == 2
        assert {l.canonical_name for l in lots} == {"milk", "onion"}

    def test_conflicts_are_reported_on_reimport(self, fresh_db):
        """Re-importing the same envelope over the same DB should report
        conflicts (not overwrite)."""
        db, _ = fresh_db
        _seed_minimal(db, "hh1")
        result = export_backup(db, "hh1", "pass")
        imp1 = import_backup(db, result.envelope_json, "pass", "hh1")
        assert imp1.success
        # Second import — every row should already exist
        imp2 = import_backup(db, result.envelope_json, "pass", "hh1")
        assert imp2.success
        # Conflicts should be in notes
        assert any("Skipped" in n and "conflicting" in n for n in imp2.notes)
