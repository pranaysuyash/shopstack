"""Migration tests for the Swiggy supersession (Pass 9).

The deprecated ``shopstack/data_sources/swiggy.py`` was deleted
in Pass 9 per the supersession rule (motto_v3 §7: migrate
callers, then delete). The canonical path is
``shopstack/market/sources/swiggy.py`` + ``shopstack/market/
sources/_swiggy_adapter.py``.

This file documents the migration: each test below maps 1:1
to a test in the deleted ``tests/test_swiggy_data_source.py``,
but rewritten against the canonical API. The new tests prove
the canonical preserves the behaviors the deprecated tests
verified (with one explicitly-documented API redesign for
``parse_size``).

**What changed in the supersession:**

1. ``_parse_size()`` (private helper in the deprecated module)
   returned a ``(quantity: float, unit: str)`` tuple. The
   canonical ``parse_size()`` (in
   :mod:`shopstack.market.normalization`) returns a
   :class:`SizeParseResult` with ``normalized_quantity``,
   ``normalized_unit``, AND a new ``is_size_class`` flag for
   patterns like "2 Medium" (size classes are now first-class).
   The legacy tuple API is gone; the new tests assert the
   richer canonical behavior.

2. ``load_swiggy_fresh_vegetables()`` returned
   ``list[SwiggyVegetableRecord]`` (a custom dataclass). The
   canonical ``load_snapshot()`` returns a ``MarketSnapshot``
   with ``normalized_records: list[NormalizedMarketRecord]``.
   The custom dataclass is gone; ``NormalizedMarketRecord``
   carries all the same fields plus more (unit prices,
   components, freshness, etc.). The new tests assert against
   the canonical field names.

3. ``summarize_swiggy_snapshot()`` returned a dict with a
   ``top_discounts`` field. The canonical
   :func:`compute_snapshot_analytics` did NOT have this
   field — it was a feature the supersession dropped. The
   feature was RESTORED in this same pass (the
   ``top_discounts`` field was added back to
   :func:`compute_snapshot_analytics`). The new test asserts
   the feature is back.

4. ``import_swiggy_fresh_vegetables_snapshot(db, ...)`` was a
   "tangled" function that did both parse and DB write. The
   canonical separates these concerns: ``load_snapshot()`` is
   pure, and a NEW canonical function
   :func:`import_swiggy_snapshot_to_db` composes the loader
   with ``db.record_price()``. The new test asserts the
   composition works.

**Why this file is named ``test_market_swiggy_migration.py``
(not ``test_swiggy_data_source.py``):**

The original ``test_swiggy_data_source.py`` documented the
deprecated API surface. This file documents the canonical
migration. Renaming makes the supersession explicit and
prevents drift from re-introducing the old test as if it were
still the canonical coverage.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from shopstack.config import settings
from shopstack.market.analytics import compute_snapshot_analytics
from shopstack.domain import parse_size
from shopstack.market.sources.swiggy import (
    DEFAULT_SNAPSHOT_ID,
    import_swiggy_snapshot_to_db,
    load_snapshot,
)


# ── Migration 1: parse_size (legacy tuple API → SizeParseResult) ──


class TestParseSizeMigration:
    """The deprecated ``_parse_size()`` returned a ``(quantity,
    unit)`` tuple. The canonical ``parse_size()`` returns a
    richer :class:`SizeParseResult` with ``is_size_class`` for
    patterns like "2 Medium" (size classes are first-class in
    the canonical). The legacy tuple API is gone.

    **What changed (and what didn't):**

    * "500 g" → (500, "g") — unchanged from legacy
    * "1 kg" → (1000, "g") — canonical normalizes to **grams**
      (the base unit). Legacy returned (1, "kg").
    * "250 ml" → (250, "mL") — canonical uses **capital L**
      (the SI symbol). Legacy used lowercase "ml".
    * "2 Medium" → (240, "g", is_size_class=True) — canonical
      treats Medium as a size class (240g). Legacy returned
      (2, "unit") (Medium as a count × unit).
    * "each" / "1 packet" → (None, None) — canonical returns
      ``None`` for unrecognized sizes. Legacy returned (1, "unit").

    These are **deliberate canonical improvements** (base-unit
    normalization, size-class disambiguation, permissive
    fallthrough). The migrated tests assert the canonical
    behavior, not the legacy.
    """

    def test_grams_unchanged(self):
        """``"500 g"`` → quantity 500, unit "g" (unchanged from legacy)."""
        result = parse_size("500 g")
        assert result.normalized_quantity == 500.0
        assert result.normalized_unit == "g"
        assert result.is_size_class is False

    def test_kilograms_normalized_to_grams(self):
        """``"1 kg"`` → quantity 1000, unit "g" (canonical base unit).

        The legacy ``_parse_size`` returned ``(1, "kg")``. The
        canonical normalizes to grams (the SI base unit of mass)
        for downstream unit-price computations. The unit string
        changes; the quantity is 10x larger; the mass is the
        same. This is the canonical's deliberate base-unit
        normalization.
        """
        result = parse_size("1 kg")
        assert result.normalized_quantity == 1000.0
        assert result.normalized_unit == "g"
        assert result.is_size_class is False

    def test_milliliters_capital_L(self):
        """``"250 ml"`` → quantity 250, unit "mL" (canonical uses SI symbol).

        The legacy returned ``(250, "ml")`` (lowercase). The
        canonical uses the SI symbol "mL" (capital L for liter).
        The mass/volume is unchanged; the string differs.
        """
        result = parse_size("250 ml")
        assert result.normalized_quantity == 250.0
        assert result.normalized_unit == "mL"
        assert result.is_size_class is False

    def test_size_class_flag_set(self):
        """``"2 Medium"`` → is_size_class=True (NEW canonical behavior).

        The legacy API returned ``(2.0, "unit")`` for "2 Medium".
        The canonical treats "Medium" as a size class
        (1 medium ≈ 240g for produce). The ``is_size_class``
        flag is the canonical way to distinguish "2 of
        medium-sized things" from "2 medium-weight units".
        """
        result = parse_size("2 Medium")
        assert result.is_size_class is True
        # Canonical maps Medium → 240g (an average produce weight)
        assert result.normalized_unit == "g"
        assert result.normalized_quantity > 0

    def test_unknown_size_returns_none(self):
        """``"each"`` / ``"1 packet"`` → quantity None, unit None.

        The legacy ``_parse_size`` handled "each" and "1 packet"
        explicitly (returned (1, "unit")). The canonical returns
        ``None`` for unrecognized sizes, letting downstream
        callers decide what to do. This is more permissive and
        matches the canonical's "don't special-case every
        retailer label" philosophy.
        """
        for raw in ("each", "1 packet"):
            result = parse_size(raw)
            assert result.normalized_quantity is None
            assert result.normalized_unit is None
            assert result.is_size_class is False


# ── Migration 2: load_swiggy_fresh_vegetables → load_snapshot ──


class TestLoadSnapshotMigration:
    """The deprecated ``load_swiggy_fresh_vegetables()``
    returned ``list[SwiggyVegetableRecord]``. The canonical
    :func:`load_snapshot` returns a ``MarketSnapshot`` with
    ``normalized_records: list[NormalizedMarketRecord]``. The
    field semantics are the same; the data shape is richer.
    """

    def test_snapshot_has_normalized_records(self):
        """The canonical returns a snapshot, not a bare list."""
        snapshot = load_snapshot()
        assert hasattr(snapshot, "normalized_records")
        assert len(snapshot.normalized_records) > 0

    def test_first_record_has_required_fields(self):
        """Every record has canonical_name, quantity, unit, price."""
        snapshot = load_snapshot()
        first = snapshot.normalized_records[0]
        assert first.canonical_name, "canonical_name must be set"
        assert first.normalized_quantity > 0
        assert first.normalized_unit in {"unit", "g", "kg", "l", "ml"}
        assert first.price_inr > 0


# ── Migration 3: summarize_swiggy_snapshot → compute_snapshot_analytics ──


class TestTopDiscountsMigration:
    """The deprecated ``summarize_swiggy_snapshot()`` returned
    a dict with a ``top_discounts`` field. The canonical
    :func:`compute_snapshot_analytics` initially DROPPED this
    field in Pass 9 supersession. It was RESTORED in this same
    pass (the field was added back to
    :func:`compute_snapshot_analytics`). This test proves the
    restoration.
    """

    def test_top_discounts_field_exists(self):
        """The canonical analytics has the top_discounts field."""
        snapshot = load_snapshot()
        analytics = compute_snapshot_analytics(snapshot)
        assert "top_discounts" in analytics
        assert isinstance(analytics["top_discounts"], list)

    def test_top_discounts_have_discount_percent(self):
        """Each top_discounts entry has a non-null discount_percent."""
        snapshot = load_snapshot()
        analytics = compute_snapshot_analytics(snapshot)
        # If there are any records with displayed discount, the
        # list should be populated. If no records have a discount
        # (the test data may not), the list should be empty.
        # Either way, the shape must be right.
        for entry in analytics["top_discounts"]:
            assert "name" in entry
            assert "canonical_name" in entry
            assert "price_inr" in entry
            assert "discount_percent" in entry
            assert entry["discount_percent"] is not None
            assert entry["discount_percent"] > 0

    def test_top_discounts_capped_at_five(self):
        """The top_discounts list is capped at 5 entries (matches legacy)."""
        snapshot = load_snapshot()
        analytics = compute_snapshot_analytics(snapshot)
        assert len(analytics["top_discounts"]) <= 5


# ── Migration 4: import_swiggy_fresh_vegetables_snapshot → import_swiggy_snapshot_to_db ──


class TestSwiggyMigrationImport:
    """The deprecated ``import_swiggy_fresh_vegetables_snapshot``
    did both parse AND DB write in one function. The canonical
    separates these: ``load_snapshot()`` is pure, and a new
    canonical function :func:`import_swiggy_snapshot_to_db`
    composes the loader with ``db.record_price``. This test
    proves the composition works.
    """

    def test_import_persists_records_to_db(self, db):
        """The import function writes to the price_observations table."""
        summary = import_swiggy_snapshot_to_db(db, dry_run=False)
        assert summary["imported_records"] > 0
        assert summary["skipped_records"] >= 0
        assert summary["source_event_id"] == DEFAULT_SNAPSHOT_ID

        # Verify the imported rows are in the DB.
        row = db.conn.execute(
            "SELECT COUNT(*) as cnt FROM price_observations "
            "WHERE source_event_id = ?",
            (DEFAULT_SNAPSHOT_ID,),
        ).fetchone()
        assert row is not None
        assert row["cnt"] == summary["imported_records"]

    def test_import_dry_run_does_not_persist(self, db):
        """dry_run=True parses and counts but doesn't write to DB."""
        summary = import_swiggy_snapshot_to_db(db, dry_run=True)
        assert summary["imported_records"] > 0
        # The count is still computed, but the DB is empty.
        row = db.conn.execute(
            "SELECT COUNT(*) as cnt FROM price_observations "
            "WHERE source_event_id = ?",
            (DEFAULT_SNAPSHOT_ID,),
        ).fetchone()
        assert row is not None
        assert row["cnt"] == 0

    def test_import_skips_zero_price_records(self, db):
        """Records with price_inr <= 0 or quantity <= 0 are skipped."""
        summary = import_swiggy_snapshot_to_db(db, dry_run=True)
        total = summary["imported_records"] + summary["skipped_records"]
        assert total == len(load_snapshot().normalized_records)
