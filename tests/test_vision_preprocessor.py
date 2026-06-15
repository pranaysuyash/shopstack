"""Unit tests for vision_preprocessor — crop/zoom for cluttered photos.

Per motto_v3 §0.1: every fix must have a regression test.

DR-033: crop/zoom pre-processing is the hardening path for the
vision recall gap (DR-030). These tests verify the pure preprocessor
behavior without requiring a model or GPU.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pytest
from PIL import Image

from shopstack.services.vision_preprocessor import (
    _crop_label,
    crop_to_bytes,
    dedupe_products,
    split_and_dedupe,
    split_into_crops,
)


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture()
def tmp_image_path(tmp_path: Path) -> str:
    """Create a 1000x800 test image (real-photo-ish aspect ratio)."""
    img = Image.new("RGB", (1000, 800), color=(255, 255, 255))
    # Add some structure so crops are visually distinct
    for i, color in enumerate([(255, 0, 0), (0, 0, 255), (0, 255, 0), (255, 255, 0)]):
        x = (i % 2) * 500
        y = (i // 2) * 400
        for px in range(100):
            for py in range(100):
                if x + px < 1000 and y + py < 800:
                    img.putpixel((x + px, y + py), color)
    path = tmp_path / "test_shelf.jpg"
    img.save(path, format="JPEG")
    return str(path)


# ── split_into_crops ────────────────────────────────────────────────────


class TestSplitIntoCrops:
    def test_grid_size_1_returns_single_full_image(self, tmp_image_path):
        crops = split_into_crops(tmp_image_path, grid_size=1)
        assert len(crops) == 1
        assert crops[0]["label"] == "full"
        assert crops[0]["bbox"] == (0, 0, 1000, 800)
        assert crops[0]["image"].size == (1000, 800)

    def test_grid_size_2_returns_4_quadrants(self, tmp_image_path):
        crops = split_into_crops(tmp_image_path, grid_size=2)
        assert len(crops) == 4
        labels = [c["label"] for c in crops]
        assert labels == ["top-left", "top-right", "bottom-left", "bottom-right"]
        # Quadrants are 500x400 each (1000/2 x 800/2)
        for crop in crops:
            assert crop["image"].size == (500, 400)

    def test_grid_size_3_returns_9_cells(self, tmp_image_path):
        crops = split_into_crops(tmp_image_path, grid_size=3)
        assert len(crops) == 9
        # Each cell is ~333x266
        for crop in crops:
            assert crop["image"].size[0] >= 333
            assert crop["image"].size[1] >= 266

    def test_bboxes_cover_full_image_no_overlap(self, tmp_image_path):
        """Without overlap, bboxes tile the full image exactly."""
        crops = split_into_crops(tmp_image_path, grid_size=2, overlap_px=0)
        # Quadrants: (0,0,500,400), (500,0,1000,400), (0,400,500,800), (500,400,1000,800)
        expected_bboxes = [
            (0, 0, 500, 400),
            (500, 0, 1000, 400),
            (0, 400, 500, 800),
            (500, 400, 1000, 800),
        ]
        actual_bboxes = [c["bbox"] for c in crops]
        assert actual_bboxes == expected_bboxes

    def test_bboxes_with_overlap_shifts_start(self, tmp_image_path):
        """With overlap_px, crops keep the same size but start earlier
        (stride is reduced by overlap_px). Adjacent crops overlap by
        overlap_px pixels."""
        crops = split_into_crops(tmp_image_path, grid_size=2, overlap_px=50)
        # cell_w = 500, cell_h = 400, stride_w = 450, stride_h = 350
        # First crop: (0, 0, 500, 400) — same as no-overlap
        assert crops[0]["bbox"] == (0, 0, 500, 400)
        # Second crop (top-right) starts at col=1 * stride_w = 450,
        # so it overlaps the first by 50px on the right
        assert crops[1]["bbox"] == (450, 0, 950, 400)

    def test_invalid_grid_size_raises(self, tmp_image_path):
        with pytest.raises(ValueError, match="grid_size must be >= 1"):
            split_into_crops(tmp_image_path, grid_size=0)
        with pytest.raises(ValueError, match="grid_size must be >= 1"):
            split_into_crops(tmp_image_path, grid_size=-1)

    def test_invalid_overlap_raises(self, tmp_image_path):
        with pytest.raises(ValueError, match="overlap_px must be >= 0"):
            split_into_crops(tmp_image_path, grid_size=2, overlap_px=-10)

    def test_row_major_order(self, tmp_image_path):
        """Crops are returned in row-major order (top-left first)."""
        crops = split_into_crops(tmp_image_path, grid_size=2)
        indices = [c["index"] for c in crops]
        assert indices == [(0, 0), (0, 1), (1, 0), (1, 1)]

    def test_crops_are_pil_images(self, tmp_image_path):
        crops = split_into_crops(tmp_image_path, grid_size=2)
        for crop in crops:
            assert isinstance(crop["image"], Image.Image)
            assert crop["image"].mode == "RGB"


# ── crop_to_bytes ───────────────────────────────────────────────────────


class TestCropToBytes:
    def test_returns_bytes(self, tmp_image_path):
        crops = split_into_crops(tmp_image_path, grid_size=2)
        result = crop_to_bytes(crops[0])
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_round_trip(self, tmp_image_path):
        """Bytes from crop_to_bytes can be loaded back into a PIL.Image."""
        crops = split_into_crops(tmp_image_path, grid_size=2)
        original = crops[0]["image"]
        b = crop_to_bytes(crops[0])
        reloaded = Image.open(io.BytesIO(b))
        assert reloaded.size == original.size
        assert reloaded.mode == "RGB"


# ── dedupe_products ────────────────────────────────────────────────────


class TestDedupeProducts:
    def test_empty_input(self):
        assert dedupe_products([]) == []
        assert dedupe_products([[], []]) == []

    def test_no_duplicates(self):
        result = dedupe_products([
            [{"name": "Milk"}, {"name": "Bread"}],
            [{"name": "Eggs"}],
        ])
        assert len(result) == 3
        names = {p["name"] for p in result}
        assert names == {"Milk", "Bread", "Eggs"}

    def test_dedupes_by_name(self):
        """Same product across multiple crops → one entry, first wins."""
        result = dedupe_products([
            [{"name": "Milk", "price_rupees": 60, "source": "crop1"}],
            [{"name": "Milk", "price_rupees": 60, "source": "crop2"}],
        ])
        assert len(result) == 1
        assert result[0]["source"] == "crop1"  # first wins

    def test_case_insensitive_match(self):
        """Lowercase comparison for dedup."""
        result = dedupe_products([
            [{"name": "Milk"}],
            [{"name": "milk"}],
            [{"name": "MILK"}],
        ])
        assert len(result) == 1

    def test_strips_whitespace(self):
        result = dedupe_products([
            [{"name": "  Milk  "}],
            [{"name": "Milk"}],
        ])
        assert len(result) == 1

    def test_skips_products_without_name(self):
        """Products with empty/None name are skipped (cannot dedup)."""
        result = dedupe_products([
            [{"name": "Milk"}, {"name": ""}, {"name": None}, {"brand": "X"}],
            [{"name": "Bread"}],
        ])
        names = {p["name"] for p in result}
        assert names == {"Milk", "Bread"}

    def test_preserves_extra_fields(self):
        """First occurrence keeps all its fields."""
        result = dedupe_products([
            [
                {"name": "Atta", "brand": "Aashirvaad", "quantity": 5},
                {"name": "Oil", "brand": "Fortune", "quantity": 1},
            ],
            [
                {"name": "Atta", "brand": "Different", "quantity": 10},  # duplicate
            ],
        ])
        assert len(result) == 2
        atta = next(p for p in result if p["name"] == "Atta")
        assert atta["brand"] == "Aashirvaad"  # first wins

    def test_realistic_4_product_scenario(self):
        """Simulate the 4-product scenario: each crop finds 1, dedupe merges."""
        # fresh_mart has 4 GT products. With 2x2 crops, each crop
        # should ideally find 1 product.
        per_crop = [
            [{"name": "Nescafe Classic Coffee", "brand": "Nescafe"}],
            [{"name": "Aashirvaad Atta", "brand": "Aashirvaad"}],
            [{"name": "Maggi Noodles", "brand": "Nestle"}],
            [{"name": "Surf Excel Detergent", "brand": "Surf Excel"}],
        ]
        result = dedupe_products(per_crop)
        assert len(result) == 4
        names = {p["name"] for p in result}
        assert names == {
            "Nescafe Classic Coffee",
            "Aashirvaad Atta",
            "Maggi Noodles",
            "Surf Excel Detergent",
        }


# ── split_and_dedupe (skeleton) ─────────────────────────────────────────


class TestSplitAndDedupe:
    def test_returns_skeleton(self, tmp_image_path):
        result = split_and_dedupe(tmp_image_path, grid_size=2)
        assert "crops" in result
        assert "grid_size" in result
        assert "image_size" in result
        assert result["grid_size"] == 2
        assert result["image_size"] == (1000, 800)
        assert len(result["crops"]) == 4


# ── _crop_label ────────────────────────────────────────────────────────


class TestCropLabel:
    def test_grid_1(self):
        assert _crop_label(0, 0, 1) == "full"

    def test_grid_2(self):
        assert _crop_label(0, 0, 2) == "top-left"
        assert _crop_label(0, 1, 2) == "top-right"
        assert _crop_label(1, 0, 2) == "bottom-left"
        assert _crop_label(1, 1, 2) == "bottom-right"

    def test_grid_3(self):
        assert _crop_label(0, 0, 3) == "top-left"
        assert _crop_label(1, 1, 3) == "middle-center"
        assert _crop_label(2, 2, 3) == "bottom-right"

    def test_grid_4_uses_generic(self):
        # 4x4 doesn't have a custom label format
        assert _crop_label(2, 3, 4) == "r2c3"
