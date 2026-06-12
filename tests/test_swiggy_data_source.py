from __future__ import annotations

from pathlib import Path
import pytest


from shopstack.config import settings
from shopstack.data_sources.swiggy import (
    SWIGGY_SOURCE_ID,
    SWIGGY_SNAPSHOT_DATE,
    import_swiggy_fresh_vegetables_snapshot,
    load_swiggy_fresh_vegetables,
    summarize_swiggy_snapshot,
    _parse_size,
)
from shopstack.persistence.database import Database


def test_parse_size_quantities() -> None:
    assert _parse_size("2 Medium") == (2.0, "unit")
    assert _parse_size("500 g") == (500.0, "g")
    assert _parse_size("1 kg") == (1.0, "kg")
    assert _parse_size("250 ml") == (250.0, "ml")
    assert _parse_size("each") == (1.0, "unit")
    assert _parse_size("1 packet") == (1.0, "unit")


def test_load_swiggy_fresh_vegetables_json() -> None:
    path = Path(settings.data_dir) / "swiggy_fresh_vegetables_cards_6jun26.json"
    with pytest.deprecated_call():
        records = load_swiggy_fresh_vegetables(path)
    assert len(records) > 0
    first = records[0]
    assert first.canonical_name
    assert first.quantity > 0
    assert first.unit in {"unit", "g", "kg", "l", "ml"}
    assert first.price_inr > 0


def test_swiggy_snapshot_summary_contains_top_discounts() -> None:
    path = Path(settings.data_dir) / "swiggy_fresh_vegetables_cards_6jun26.json"
    with pytest.deprecated_call():
        records = load_swiggy_fresh_vegetables(path)
    with pytest.deprecated_call():
        summary = summarize_swiggy_snapshot(records)
    assert summary["total_records"] == len(records)
    assert summary["unique_items"] > 0
    assert isinstance(summary["top_discounts"], list)
    assert summary["top_discounts"][0]["discount_percent"] is not None


def test_import_swiggy_snapshot_records(db: Database) -> None:
    with pytest.deprecated_call():
        summary = import_swiggy_fresh_vegetables_snapshot(db, path=Path(settings.data_dir) / "swiggy_fresh_vegetables_cards_6jun26.json")
    assert summary["imported_records"] > 0
    assert summary["skipped_records"] >= 0
    assert summary["source_event_id"] == SWIGGY_SOURCE_ID
    # Check that imported records are persisted.
    row = db.conn.execute("SELECT COUNT(*) as cnt FROM price_observations WHERE source_event_id = ?", (SWIGGY_SOURCE_ID,)).fetchone()
    assert row is not None and row["cnt"] == summary["imported_records"]
    # Verify the snapshot date is preserved.
    date_row = db.conn.execute("SELECT DISTINCT observation_date FROM price_observations WHERE source_event_id = ?", (SWIGGY_SOURCE_ID,)).fetchone()
    assert date_row is not None and date_row["observation_date"] == SWIGGY_SNAPSHOT_DATE.isoformat()

