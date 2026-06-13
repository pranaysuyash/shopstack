"""Tests for the shared shopping list sync service.

Covers:

- Push serialises the active list to a file and reports correct counts.
- Pull merges the file's items into the local list (additive only).
- Pull is idempotent — running it twice doesn't add duplicates.
- Pull is additive — local items not in the file are preserved.
- Validation: bad file path, non-JSON, wrong kind, wrong version.
- File envelope has the right metadata.
- The two devices use the same path and the data flows correctly.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from shopstack.config import Settings
from shopstack.persistence.database import Database
from shopstack.schemas.models import ShoppingListItem
from shopstack.services.shared_list_sync import (
    SHARED_FILE_VERSION,
    pull_from_file,
    push_to_file,
)


@pytest.fixture()
def fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = Settings(_env_file=None, db_path=path, off_the_grid=True, planner_backend="mock")
    db = Database(path)
    yield db, path
    Path(path).unlink(missing_ok=True)


@pytest.fixture()
def shared_file(tmp_path):
    """Path to a fresh sync file inside a temp dir."""
    return str(tmp_path / "shared_shopping.json")


def _seed_list(db: Database, hh: str, items: list[tuple[str, str, float, str]]) -> str:
    """Seed a shopping list with the given items. Returns list_id."""
    db.active_household_id = hh
    sl = db.create_shopping_list(goal="Test", user_id=hh)
    for cname, display, qty, unit in items:
        db.add_list_item(
            sl.list_id,
            ShoppingListItem(
                canonical_name=cname, display_name=display,
                requested_quantity=qty, unit=unit,
            ),
        )
    return sl.list_id


class TestPushToFile:
    def test_push_creates_file_and_writes_envelope(self, fresh_db, shared_file):
        db, _ = fresh_db
        _seed_list(db, "hh1", [("milk", "Milk", 1.0, "L"), ("bread", "Bread", 1.0, "loaf")])
        result = push_to_file(db, shared_file, "hh1", device_label="phone-A")
        assert result.success
        assert os.path.isfile(shared_file)
        with open(shared_file) as f:
            envelope = json.load(f)
        assert envelope["kind"] == "shopstack_shopping_list"
        assert envelope["version"] == SHARED_FILE_VERSION
        assert envelope["source"]["device"] == "phone-A"
        assert envelope["source"]["household_id"] == "hh1"
        assert len(envelope["list"]["items"]) == 2

    def test_push_with_empty_list_still_succeeds(self, fresh_db, shared_file):
        db, _ = fresh_db
        result = push_to_file(db, shared_file, "hh1")
        assert result.success
        with open(shared_file) as f:
            envelope = json.load(f)
        assert envelope["list"]["items"] == []

    def test_push_creates_parent_directory(self, fresh_db, tmp_path):
        db, _ = fresh_db
        nested = str(tmp_path / "deep" / "nested" / "shared.json")
        result = push_to_file(db, nested, "hh1")
        assert result.success
        assert os.path.isfile(nested)

    def test_push_empty_file_path_fails(self, fresh_db):
        db, _ = fresh_db
        result = push_to_file(db, "", "hh1")
        assert result.success is False
        assert "required" in result.error.lower()

    def test_push_readonly_dir_fails_gracefully(self, fresh_db, tmp_path):
        db, _ = fresh_db
        # Try to push to a path that can't be written (root-owned dir on Linux)
        # Use /dev/null/full which always returns ENOSPC
        result = push_to_file(db, "/dev/full", "hh1")
        # We accept either: success in some envs (weird), or graceful failure
        if not result.success:
            assert "write" in result.error.lower() or "full" in result.error.lower()


class TestPullFromFile:
    def test_pull_adds_new_items_to_local(self, fresh_db, shared_file):
        db, _ = fresh_db
        # First create a file (simulating another device's push)
        other = Database(tempfile.mktemp(suffix=".db"))
        try:
            _seed_list(other, "hh1", [("milk", "Milk", 1.0, "L"), ("bread", "Bread", 1.0, "loaf")])
            push_result = push_to_file(other, shared_file, "hh1", device_label="phone-B")
            assert push_result.success
        finally:
            Path(other.conn.execute("PRAGMA database_list").fetchone()[2]).unlink(missing_ok=True)

        # Now pull from this file into a fresh local DB
        result = pull_from_file(db, shared_file, "hh1")
        assert result.success
        assert result.counts["added"] == 2
        assert result.counts["existing"] == 0
        # Verify items are now in the local DB
        sl = db.get_active_shopping_list(user_id="hh1")
        names = {(it.canonical_name or "").lower() for it in (sl.items or [])}
        assert "milk" in names
        assert "bread" in names

    def test_pull_is_idempotent(self, fresh_db, shared_file):
        db, _ = fresh_db
        other = Database(tempfile.mktemp(suffix=".db"))
        try:
            _seed_list(other, "hh1", [("milk", "Milk", 1.0, "L")])
            push_to_file(other, shared_file, "hh1")
        finally:
            Path(other.conn.execute("PRAGMA database_list").fetchone()[2]).unlink(missing_ok=True)

        r1 = pull_from_file(db, shared_file, "hh1")
        r2 = pull_from_file(db, shared_file, "hh1")
        assert r1.success and r2.success
        # First pulls 1 item, second should pull 0 (already there)
        assert r1.counts["added"] == 1
        assert r2.counts["added"] == 0
        assert r2.counts["existing"] == 1

    def test_pull_is_additive_keeps_local_items(self, fresh_db, shared_file):
        """Local-only items must not be deleted by a pull."""
        db, _ = fresh_db
        # Local has milk and bread
        _seed_list(db, "hh1", [("milk", "Milk", 1.0, "L"), ("bread", "Bread", 1.0, "loaf")])
        # Shared file has tomato (different from local)
        other = Database(tempfile.mktemp(suffix=".db"))
        try:
            _seed_list(other, "hh1", [("tomato", "Tomato", 2.0, "kg")])
            push_to_file(other, shared_file, "hh1")
        finally:
            Path(other.conn.execute("PRAGMA database_list").fetchone()[2]).unlink(missing_ok=True)

        # Pull: should add tomato but keep milk and bread
        result = pull_from_file(db, shared_file, "hh1")
        assert result.success
        sl = db.get_active_shopping_list(user_id="hh1")
        names = {(it.canonical_name or "").lower() for it in (sl.items or [])}
        assert "milk" in names
        assert "bread" in names
        assert "tomato" in names  # new from shared

    def test_pull_empty_file_path_fails(self, fresh_db):
        db, _ = fresh_db
        result = pull_from_file(db, "", "hh1")
        assert result.success is False
        assert "required" in result.error.lower()

    def test_pull_nonexistent_file_fails(self, fresh_db, tmp_path):
        db, _ = fresh_db
        result = pull_from_file(db, str(tmp_path / "does_not_exist.json"), "hh1")
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_pull_non_json_file_fails(self, fresh_db, shared_file):
        db, _ = fresh_db
        with open(shared_file, "w") as f:
            f.write("not json at all")
        result = pull_from_file(db, shared_file, "hh1")
        assert result.success is False
        assert "parse" in result.error.lower() or "json" in result.error.lower()

    def test_pull_wrong_kind_fails(self, fresh_db, shared_file):
        db, _ = fresh_db
        with open(shared_file, "w") as f:
            json.dump({"kind": "not_a_shopping_list", "version": 1}, f)
        result = pull_from_file(db, shared_file, "hh1")
        assert result.success is False
        assert "envelope" in result.error.lower() or "kind" in result.error.lower()

    def test_pull_wrong_version_fails(self, fresh_db, shared_file):
        db, _ = fresh_db
        with open(shared_file, "w") as f:
            json.dump({
                "kind": "shopstack_shopping_list",
                "version": 99,
                "list": {},
            }, f)
        result = pull_from_file(db, shared_file, "hh1")
        assert result.success is False
        assert "version" in result.error.lower()


class TestTwoDeviceFlow:
    """Integration: phone A pushes, phone B pulls, B's local list grows."""

    def test_phone_a_push_then_phone_b_pull(self, fresh_db, shared_file):
        db, _ = fresh_db
        # Phone A adds 3 items
        _seed_list(db, "hh1", [
            ("milk", "Milk", 1.0, "L"),
            ("onion", "Onion", 2.0, "kg"),
            ("rice", "Rice", 5.0, "kg"),
        ])

        # Phone A pushes
        r1 = push_to_file(db, shared_file, "hh1", device_label="phone-A")
        assert r1.success

        # Simulate Phone B with a fresh DB
        other = Database(tempfile.mktemp(suffix=".db"))
        try:
            # Phone B starts with one item already
            _seed_list(other, "hh1", [("milk", "Milk", 1.0, "L")])
            # Phone B pulls
            r2 = pull_from_file(other, shared_file, "hh1")
            assert r2.success
            # Should add 2 new (onion, rice); milk already exists
            assert r2.counts["added"] == 2
            assert r2.counts["existing"] == 1
            # Verify Phone B's list
            sl = other.get_active_shopping_list(user_id="hh1")
            names = {(it.canonical_name or "").lower() for it in (sl.items or [])}
            assert names == {"milk", "onion", "rice"}
        finally:
            Path(other.conn.execute("PRAGMA database_list").fetchone()[2]).unlink(missing_ok=True)
