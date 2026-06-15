"""Vision preprocessor — crop/zoom for cluttered product photos.

motto_v3 §0.9, DR-030: when the v3 prompt is run on a cluttered
real photo (4+ products overlapping), Qwen3-VL-8B hits a recall
ceiling at ~64%. The synthetic bench showed 99% on single-product
images. The gap is that on cluttered photos, the model only sees
the most prominent item and ignores others.

The fix: split the photo into N×N grid crops, run Qwen3-VL on
each crop independently, and merge the results. This converts a
4-product recall problem into 4 single-product problems where
the model is known to score 99% (synthetic bench evidence).

**Design (first principles):**

1. **Pure preprocessor.** This module contains ONLY image
   manipulation (no model calls, no provider imports). It can be
   tested with PIL alone on any image.

2. **Caller composes preprocessor + provider.** The vision
   provider's `understand_with_crops()` method (or the calling
   code in `market_lens.py`) calls `split_into_crops()` first, then
   calls `understand()` for each crop, then merges with
   `dedupe_products()`. The preprocessor does NOT call the model.

3. **Configurable grid.** Default 2×2 (4 quadrants) for the
   real-photo kill test. 3×3 (9 cells) for larger shelves.
   1×1 means no cropping (single pass — same as the v3 prompt
   without pre-processing).

4. **Deduplication by canonical name.** The same product might
   appear in adjacent crops (e.g., a tall bottle that spans two
   quadrants). `dedupe_products()` keeps the first occurrence
   (highest-confidence pass).

**Why this approach (motto_v3 §0.1 missed-anything sweep):**

- Synthetic bench: 99% on single-product images. The model is
  capable when the photo is simple.
- Real bench: 64% on 4-product shelves. The model is hitting a
  perception ceiling on cluttered photos.
- v3 prompt engineering: 0% improvement over v2. The bottleneck
  is what the model CAN SEE, not how it's prompted.
- Crop/zoom: splits the cluttered problem into simple problems.
  This is a first-principles decomposition.

**Where the crops go:**

The preprocessor returns a list of `(crop_index, PIL.Image)` pairs.
The caller runs the model on each image and gets back a list of
predicted products. Then `dedupe_products()` merges them.

Per motto_v3 §7 (Supersession), the existing single-image
`understand()` method is preserved. `understand_with_crops()` is
the new path that uses the preprocessor.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image


def split_into_crops(
    image_path: str,
    grid_size: int = 2,
    overlap_px: int = 0,
) -> list[dict[str, Any]]:
    """Split an image into an N×N grid of crops.

    Args:
        image_path: Path to a local image file.
        grid_size: Number of rows and columns. 2 = 2×2 = 4 crops.
            1 = no split (single crop, full image). Default 2.
        overlap_px: Pixels of overlap between adjacent crops.
            Default 0 (clean grid). Useful when products span
            crop boundaries.

    Returns:
        List of crop dicts, each with:
            - index: (row, col) tuple
            - image: PIL.Image (RGB)
            - bbox: (left, top, right, bottom) in original-image pixels
            - label: human-readable label like "top-left", "top-right",
                     "bottom-left", "bottom-right", "center" (for odd grids)

    The crops are returned in row-major order (top-left first,
    bottom-right last).
    """
    if grid_size < 1:
        raise ValueError(f"grid_size must be >= 1, got {grid_size}")
    if overlap_px < 0:
        raise ValueError(f"overlap_px must be >= 0, got {overlap_px}")

    img = Image.open(image_path).convert("RGB")
    width, height = img.size

    crops: list[dict[str, Any]] = []
    if grid_size == 1:
        # No split — single crop, full image
        crops.append(
            {
                "index": (0, 0),
                "image": img,
                "bbox": (0, 0, width, height),
                "label": "full",
            }
        )
        return crops

    # Compute crop dimensions with overlap
    cell_w = width // grid_size
    cell_h = height // grid_size
    stride_w = max(1, cell_w - overlap_px)
    stride_h = max(1, cell_h - overlap_px)

    idx = 0
    for row in range(grid_size):
        for col in range(grid_size):
            left = col * stride_w
            top = row * stride_h
            right = min(width, left + cell_w)
            bottom = min(height, top + cell_h)

            crop_img = img.crop((left, top, right, bottom))
            label = _crop_label(row, col, grid_size)

            crops.append(
                {
                    "index": (row, col),
                    "image": crop_img,
                    "bbox": (left, top, right, bottom),
                    "label": label,
                }
            )
            idx += 1

    return crops


def _crop_label(row: int, col: int, grid_size: int) -> str:
    """Return a human-readable label for a crop position."""
    if grid_size == 1:
        return "full"
    if grid_size == 2:
        # 2x2: top-left, top-right, bottom-left, bottom-right
        v = "top" if row == 0 else "bottom"
        h = "left" if col == 0 else "right"
        return f"{v}-{h}"
    if grid_size == 3:
        # 3x3: top/middle/bottom × left/center/right
        v = ["top", "middle", "bottom"][row]
        h = ["left", "center", "right"][col]
        return f"{v}-{h}"
    # Generic for larger grids
    return f"r{row}c{col}"


def crop_to_bytes(crop: dict[str, Any], format: str = "PNG") -> bytes:
    """Serialize a crop's PIL.Image to bytes for transport/storage."""
    buf = io.BytesIO()
    crop["image"].save(buf, format=format)
    return buf.getvalue()


def dedupe_products(
    per_crop_results: list[list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Merge product lists from multiple crops, deduplicating.

    Args:
        per_crop_results: A list (one per crop) of product lists
            (each product is a dict with at least a "name" field).

    Returns:
        Merged product list, deduplicated by canonical name.
        First occurrence wins (highest-confidence pass).

    The dedup is intentionally simple: exact match on the lowercased
    name field. For more sophisticated dedup, the canonical
    shopstack.domain.product_matching module can be used.
    """
    seen: dict[str, dict[str, Any]] = {}
    for crop_products in per_crop_results:
        for product in crop_products:
            name = (product.get("name") or "").strip().lower()
            if not name:
                continue
            if name in seen:
                continue
            seen[name] = product
    return list(seen.values())


def split_and_dedupe(
    image_path: str,
    grid_size: int = 2,
    overlap_px: int = 0,
) -> list[dict[str, Any]]:
    """Convenience: split image into crops and return their bboxes/labels
    + a placeholder for the merged result.

    This is the "skeleton" the caller fills in by running the model
    on each crop and calling dedupe_products.

    Returns:
        {
            "crops": [crop dict, ...],   # each with index, image, bbox, label
            "grid_size": int,
            "image_size": (width, height),
        }

    The caller then iterates over crops, calls model.understand(crop),
    and finally dedupes with dedupe_products(per_crop_results).
    """
    crops = split_into_crops(image_path, grid_size, overlap_px)
    img = Image.open(image_path)
    return {
        "crops": crops,
        "grid_size": grid_size,
        "image_size": img.size,
    }
