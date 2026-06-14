"""Tests for the Photo-Anchored Map service and screen."""
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from shopstack.services.photo_search import (
    PhotoFeatures,
    PhotoMatch,
    clear_photo,
    cosine_similarity,
    extract_features,
    find_similar_locations,
    photos_root,
    store_photo,
)
from shopstack.ui.screens.photo_map import (
    attach_photo_to_location,
    clear_location_photo,
    find_location_by_photo,
    photo_map_view,
)


# ─── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture()
def sample_photo_red() -> str:
    """A 64x64 mostly-red image saved to a temp file."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    img = Image.new("RGB", (64, 64), color=(220, 30, 30))
    img.save(path, "PNG")
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture()
def sample_photo_blue() -> str:
    """A 64x64 mostly-blue image saved to a temp file."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    img = Image.new("RGB", (64, 64), color=(30, 30, 220))
    img.save(path, "PNG")
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture()
def sample_photo_mixed() -> str:
    """A 64x64 image with mixed colors."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        path = f.name
    img = Image.new("RGB", (64, 64))
    pixels = img.load()
    for x in range(64):
        for y in range(64):
            pixels[x, y] = (x * 4 % 256, y * 4 % 256, (x + y) * 2 % 256)
    img.save(path, "PNG")
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


# ─── Feature extraction tests ────────────────────────────────────


class TestExtractFeatures:
    def test_extract_features_returns_correct_dimensions(self, sample_photo_red):
        feats = extract_features(sample_photo_red, location_id="loc1")
        assert feats.width == 64
        assert feats.height == 64
        assert feats.file_size > 0
        assert feats.location_id == "loc1"
        assert len(feats.color_histogram) == 24
        # Histogram should be L1-normalized (sums to ~1.0)
        assert abs(sum(feats.color_histogram) - 1.0) < 1e-6

    def test_extract_features_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            extract_features("/nonexistent/path.jpg", location_id="loc1")

    def test_extract_features_invalid_image(self):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"not an image")
            path = f.name
        try:
            with pytest.raises(Exception):  # PIL.UnidentifiedImageError
                extract_features(path, location_id="loc1")
        finally:
            os.unlink(path)

    def test_extract_features_file_hash_unique(self, sample_photo_red, sample_photo_blue):
        f1 = extract_features(sample_photo_red, "loc1")
        f2 = extract_features(sample_photo_blue, "loc2")
        assert f1.file_hash != f2.file_hash

    def test_extract_features_file_hash_stable(self, sample_photo_red):
        f1 = extract_features(sample_photo_red, "loc1")
        f2 = extract_features(sample_photo_red, "loc2")
        assert f1.file_hash == f2.file_hash


# ─── Cosine similarity tests ──────────────────────────────────────


class TestCosineSimilarity:
    def test_identical_histograms_have_similarity_one(self):
        hist = (0.1, 0.2, 0.3, 0.4) * 6  # 24 values
        assert abs(cosine_similarity(hist, hist) - 1.0) < 1e-6

    def test_orthogonal_histograms_have_similarity_zero(self):
        a = (1.0, 0.0) * 12
        b = (0.0, 1.0) * 12
        assert abs(cosine_similarity(a, b)) < 1e-6

    def test_mismatched_lengths_returns_zero(self):
        a = (0.5, 0.5) * 12
        b = (0.5, 0.5) * 11
        assert cosine_similarity(a, b) == 0.0

    def test_empty_histograms_returns_zero(self):
        assert cosine_similarity((), ()) == 0.0

    def test_similar_colors_score_high(self, sample_photo_red):
        # Same image should match itself
        feats1 = extract_features(sample_photo_red, "loc1")
        feats2 = extract_features(sample_photo_red, "loc2")
        sim = cosine_similarity(feats1.color_histogram, feats2.color_histogram)
        assert sim > 0.99

    def test_different_colors_score_low(self, sample_photo_red, sample_photo_blue):
        feats_red = extract_features(sample_photo_red, "loc1")
        feats_blue = extract_features(sample_photo_blue, "loc2")
        sim = cosine_similarity(feats_red.color_histogram, feats_blue.color_histogram)
        # Different dominant colors should produce low similarity
        assert sim < 0.5


# ─── Store and clear tests ────────────────────────────────────────


class TestStorePhoto:
    def test_store_photo_copies_file_and_updates_db(
        self, db, sample_photo_red, tmp_path
    ):
        # Create a location
        db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES (?, ?, NULL, 'shelf', '')",
            ("loc1", "Test Location"),
        )
        db.conn.commit()

        feats = store_photo(sample_photo_red, "loc1", db)
        assert feats.location_id == "loc1"
        assert Path(feats.path).is_file()

        # DB should have the photo_path set
        loc = db.get_location("loc1")
        assert loc is not None
        assert loc.photo_path is not None
        assert loc.photo_path == feats.path

    def test_store_photo_replaces_existing(
        self, db, sample_photo_red, sample_photo_blue
    ):
        db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES (?, ?, NULL, 'shelf', '')",
            ("loc1", "Test Location"),
        )
        db.conn.commit()

        # Store first photo
        feats1 = store_photo(sample_photo_red, "loc1", db)
        # Store second photo (replaces first)
        feats2 = store_photo(sample_photo_blue, "loc1", db)

        # First file should be gone, second should remain
        assert not Path(feats1.path).is_file() or feats1.path == feats2.path
        assert Path(feats2.path).is_file()

    def test_store_photo_nonexistent_source_raises(self, db):
        with pytest.raises(FileNotFoundError):
            store_photo("/nonexistent/file.jpg", "loc1", db)

    def test_store_photo_unknown_location_returns_features_but_no_db_update(
        self, db, sample_photo_red
    ):
        # Storing to a non-existent location should still work but
        # the DB update will silently no-op
        feats = store_photo(sample_photo_red, "ghost_loc", db)
        assert feats.location_id == "ghost_loc"


class TestClearPhoto:
    def test_clear_photo_removes_file_and_db_entry(
        self, db, sample_photo_red
    ):
        db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES (?, ?, NULL, 'shelf', '')",
            ("loc1", "Test Location"),
        )
        db.conn.commit()
        store_photo(sample_photo_red, "loc1", db)
        assert db.get_location("loc1").photo_path is not None

        removed = clear_photo("loc1", db)
        assert removed is True
        loc = db.get_location("loc1")
        assert loc.photo_path is None

    def test_clear_photo_no_existing_returns_false(self, db):
        db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES (?, ?, NULL, 'shelf', '')",
            ("loc1", "Test Location"),
        )
        db.conn.commit()
        removed = clear_photo("loc1", db)
        assert removed is False

    def test_clear_photo_unknown_location_returns_false(self, db):
        assert clear_photo("ghost_loc", db) is False


# ─── Find similar tests ──────────────────────────────────────────


class TestFindSimilarLocations:
    def test_find_similar_returns_matches_above_threshold(
        self, db, sample_photo_red, sample_photo_blue
    ):
        # Two locations, each with a different color photo
        db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_red', 'Red Place', NULL, 'shelf', '')"
        )
        db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_blue', 'Blue Place', NULL, 'shelf', '')"
        )
        db.conn.commit()
        store_photo(sample_photo_red, "loc_red", db)
        store_photo(sample_photo_blue, "loc_blue", db)

        # Query with the red photo — should match red location
        matches = find_similar_locations(sample_photo_red, db, top_k=2, min_similarity=0.5)
        assert len(matches) >= 1
        # Red location should be the top match
        top = matches[0]
        assert top.location_id == "loc_red"
        assert top.similarity > 0.9

    def test_find_similar_empty_db_returns_empty(self, db, sample_photo_red):
        matches = find_similar_locations(sample_photo_red, db)
        assert matches == []

    def test_find_similar_min_similarity_filter(self, db, sample_photo_red, sample_photo_blue):
        db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_red', 'Red', NULL, 'shelf', '')"
        )
        db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_blue', 'Blue', NULL, 'shelf', '')"
        )
        db.conn.commit()
        store_photo(sample_photo_red, "loc_red", db)
        store_photo(sample_photo_blue, "loc_blue", db)

        # With a high threshold, only the red should match
        matches = find_similar_locations(sample_photo_red, db, top_k=5, min_similarity=0.99)
        assert len(matches) == 1
        assert matches[0].location_id == "loc_red"

    def test_find_similar_top_k_limits_results(
        self, db, sample_photo_red, sample_photo_blue
    ):
        for i in range(3):
            db.conn.execute(
                f"INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_{i}', 'Loc {i}', NULL, 'shelf', '')"
            )
        db.conn.commit()
        # All three get a different photo (some duplicates)
        store_photo(sample_photo_red, "loc_0", db)
        store_photo(sample_photo_red, "loc_1", db)
        store_photo(sample_photo_blue, "loc_2", db)

        matches = find_similar_locations(sample_photo_red, db, top_k=2)
        assert len(matches) == 2

    def test_find_similar_nonexistent_query_returns_empty(self, db):
        matches = find_similar_locations("/nonexistent/file.jpg", db)
        assert matches == []

    def test_find_similar_skips_locations_without_photo(
        self, db, sample_photo_red
    ):
        # Two locations, only one has a photo
        db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_with', 'With', NULL, 'shelf', '')"
        )
        db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_without', 'Without', NULL, 'shelf', '')"
        )
        db.conn.commit()
        store_photo(sample_photo_red, "loc_with", db)

        matches = find_similar_locations(sample_photo_red, db)
        assert len(matches) == 1
        assert matches[0].location_id == "loc_with"


# ─── Screen tests ────────────────────────────────────────────────


class TestPhotoMapScreen:
    def test_photo_map_view_renders_with_photos(self, sample_photo_red):
        # The screen uses the app's singleton db (from app_context),
        # so we need to use it too. We do this by importing the
        # app's db directly.
        from shopstack.app_context import db as app_db
        app_db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc1', 'Anchored', NULL, 'shelf', '')"
        )
        app_db.conn.commit()
        try:
            store_photo(sample_photo_red, "loc1", app_db)
            html = photo_map_view()
            assert "Anchored" in html
            assert "Anchored locations" in html
        finally:
            # Clean up
            app_db.conn.execute("DELETE FROM household_locations WHERE location_id = 'loc1'")
            app_db.conn.commit()
            clear_photo("loc1", app_db)

    def test_photo_map_view_renders_without_photos(self):
        from shopstack.app_context import db as app_db
        # The "Awaiting photos" section shows the first 12 location
        # names; the test location is at the end, so we just verify
        # the section is present.
        app_db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_nophoto_test', 'NPNLoc', NULL, 'shelf', '')"
        )
        app_db.conn.commit()
        try:
            html = photo_map_view()
            assert "Awaiting photos" in html
            assert "of " in html  # counts present
        finally:
            app_db.conn.execute("DELETE FROM household_locations WHERE location_id = 'loc_nophoto_test'")
            app_db.conn.commit()

    def test_attach_photo_to_location_success(self, sample_photo_red):
        from shopstack.app_context import db as app_db
        app_db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_attach_test', 'AttachTest', NULL, 'shelf', '')"
        )
        app_db.conn.commit()
        try:
            result = attach_photo_to_location("loc_attach_test", sample_photo_red)
            assert "Attached photo" in result
            assert "AttachTest" in result
        finally:
            app_db.conn.execute("DELETE FROM household_locations WHERE location_id = 'loc_attach_test'")
            app_db.conn.commit()
            clear_photo("loc_attach_test", app_db)

    def test_attach_photo_to_location_unknown(self, sample_photo_red):
        result = attach_photo_to_location("ghost_unknown_loc", sample_photo_red)
        assert "Unknown location" in result

    def test_attach_photo_to_location_missing_inputs(self):
        result = attach_photo_to_location("", "")
        assert "required" in result.lower()

    def test_attach_photo_to_location_nonexistent_file(self):
        from shopstack.app_context import db as app_db
        app_db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_attach_err', 'ErrLoc', NULL, 'shelf', '')"
        )
        app_db.conn.commit()
        try:
            result = attach_photo_to_location("loc_attach_err", "/nonexistent/file.jpg")
            assert "not found" in result.lower()
        finally:
            app_db.conn.execute("DELETE FROM household_locations WHERE location_id = 'loc_attach_err'")
            app_db.conn.commit()

    def test_clear_location_photo_removes(self, sample_photo_red):
        from shopstack.app_context import db as app_db
        app_db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_clear_test', 'ClearTest', NULL, 'shelf', '')"
        )
        app_db.conn.commit()
        try:
            store_photo(sample_photo_red, "loc_clear_test", app_db)
            result = clear_location_photo("loc_clear_test")
            assert "cleared" in result.lower()
        finally:
            app_db.conn.execute("DELETE FROM household_locations WHERE location_id = 'loc_clear_test'")
            app_db.conn.commit()
            clear_photo("loc_clear_test", app_db)

    def test_clear_location_photo_none_exists(self):
        from shopstack.app_context import db as app_db
        app_db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_clear_empty', 'ClearEmpty', NULL, 'shelf', '')"
        )
        app_db.conn.commit()
        try:
            result = clear_location_photo("loc_clear_empty")
            assert "no photo" in result.lower()
        finally:
            app_db.conn.execute("DELETE FROM household_locations WHERE location_id = 'loc_clear_empty'")
            app_db.conn.commit()

    def test_find_location_by_photo_renders_matches(self, sample_photo_red):
        from shopstack.app_context import db as app_db
        app_db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_match_test', 'MatchPlace', NULL, 'shelf', '')"
        )
        app_db.conn.commit()
        try:
            store_photo(sample_photo_red, "loc_match_test", app_db)
            html = find_location_by_photo(sample_photo_red)
            assert "MatchPlace" in html
        finally:
            app_db.conn.execute("DELETE FROM household_locations WHERE location_id = 'loc_match_test'")
            app_db.conn.commit()
            clear_photo("loc_match_test", app_db)

    def test_find_location_by_photo_empty_query(self):
        html = find_location_by_photo("")
        assert "Upload a photo" in html

    def test_find_location_by_photo_no_matches(self, sample_photo_red):
        from shopstack.app_context import db as app_db
        app_db.conn.execute(
            "INSERT INTO household_locations (location_id, name, parent_location_id, location_type, notes) VALUES ('loc_nomatch', 'NoMatchLoc', NULL, 'shelf', '')"
        )
        app_db.conn.commit()
        try:
            html = find_location_by_photo(sample_photo_red)
            assert "No matching" in html
        finally:
            app_db.conn.execute("DELETE FROM household_locations WHERE location_id = 'loc_nomatch'")
            app_db.conn.commit()
