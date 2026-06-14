"""Photo-Anchored Map — perceptual photo storage and matching for locations.

First principles:

1. **Locations are visual, not just textual.** A photo of the spice
   rack tells the user "this is the third shelf on the left" in a
   way that "kitchen_pantry_shelf_3" never can.

2. **Photos anchor spatial memory.** "Where did I put the passport?"
   is faster to answer by glancing at a photo of the desk drawer
   than by reading a list of location names.

3. **Find-by-photo is a real workflow.** The user is at a location
   they don't recognize (e.g. visiting a relative's house), takes a
   photo, and asks "do I have something stored here?" The system
   compares the photo to stored location photos and suggests matches.

This module owns:
- storing a photo for a location (file copy + DB write)
- computing a simple feature vector for matching
- comparing photos for "is this the same place?"

For first principles, we use:
- **Color histogram** (8-bin per channel, RGB) — fast, dependency-free
- **File size + dimensions** as coarse pre-filters
- **Cosine similarity** over normalized histograms

This is intentionally simple. The intent is to give users a "does
this look like a place I know" signal, not a high-fidelity image
matcher. A future migration to CLIP or DINOv2 embeddings can
swap in behind the same interface without breaking callers.
"""
from __future__ import annotations

import hashlib
import io
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

from shopstack.config import settings
from shopstack.persistence.database import Database

logger = logging.getLogger(__name__)


# ─── Storage paths ────────────────────────────────────────────────

#: Where location photos live on disk.
#: Lives under ``settings.data_dir`` so it follows the same
#: data-dir convention as the database. Each photo is stored as
#: ``<location_id>__<hash>.jpg`` to make collision-free filenames.
PHOTOS_SUBDIR = "location_photos"


def photos_root() -> Path:
    """Return the directory where location photos are stored.

    Created on first call. The directory is per-household in the
    future, but for now we use a single global dir keyed by
    ``location_id`` (which is itself household-scoped via
    ``inventory_lots.user_id``).
    """
    root = Path(settings.data_dir) / PHOTOS_SUBDIR
    root.mkdir(parents=True, exist_ok=True)
    return root


# ─── Feature extraction ────────────────────────────────────────────


@dataclass(frozen=True)
class PhotoFeatures:
    """A simple feature vector for a location photo.

    Attributes:
        location_id: which location this photo belongs to.
        path: absolute file path on disk.
        width: image width in pixels.
        height: image height in pixels.
        file_size: file size in bytes.
        color_histogram: 24 floats (8 bins × R/G/B), L1-normalized.
        file_hash: SHA-256 of the file bytes, for dedupe.
        captured_at: ISO timestamp of when the photo was stored.
    """
    location_id: str
    path: str
    width: int
    height: int
    file_size: int
    color_histogram: tuple[float, ...]
    file_hash: str
    captured_at: str


def _color_histogram(image: Image.Image, bins: int = 8) -> tuple[float, ...]:
    """Compute a normalized color histogram for an image.

    Args:
        image: a PIL.Image in RGB mode.
        bins: bins per channel. Default 8 → 8×8×8 = 512-bin
            RGB histogram. We further reduce to 8 bins per channel
            (8×3 = 24 floats) by averaging adjacent bins to keep the
            feature vector small and robust to noise.

    Returns:
        A tuple of 24 floats summing to 1.0 (L1-normalized).
    """
    # Resize to a small thumbnail to make histogram cheap + position-invariant
    thumb = image.copy()
    thumb.thumbnail((128, 128))
    rgb = thumb.convert("RGB")
    raw = rgb.histogram()  # 256 bins per channel
    # Reduce 256 → `bins` by averaging adjacent bins
    reduced: list[float] = []
    for channel_offset in range(0, len(raw), 256):
        channel = raw[channel_offset: channel_offset + 256]
        for b in range(bins):
            start = b * (256 // bins)
            end = (b + 1) * (256 // bins)
            reduced.append(float(sum(channel[start:end])))
    total = sum(reduced) or 1.0
    return tuple(v / total for v in reduced)


def extract_features(image_path: str, location_id: str) -> PhotoFeatures:
    """Read an image from disk and extract its feature vector.

    Args:
        image_path: Absolute or relative path to a readable image file.
        location_id: The location to associate the photo with.

    Returns:
        A :class:`PhotoFeatures` instance.

    Raises:
        FileNotFoundError: if the file does not exist.
        PIL.UnidentifiedImageError: if the file is not a valid image.
    """
    p = Path(image_path)
    if not p.is_file():
        raise FileNotFoundError(f"Image not found: {image_path}")
    file_bytes = p.read_bytes()
    with Image.open(io.BytesIO(file_bytes)) as img:
        width, height = img.size
        hist = _color_histogram(img)
    file_hash = hashlib.sha256(file_bytes).hexdigest()[:16]
    return PhotoFeatures(
        location_id=location_id,
        path=str(p.resolve()),
        width=width,
        height=height,
        file_size=len(file_bytes),
        color_histogram=hist,
        file_hash=file_hash,
        captured_at=datetime.now().isoformat(timespec="seconds"),
    )


# ─── Similarity ───────────────────────────────────────────────────


def cosine_similarity(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Cosine similarity in [-1, 1]. For L1-normalized histograms, this
    is in [0, 1] where 1.0 = identical distributions."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


# ─── Storage ──────────────────────────────────────────────────────


def store_photo(
    source_path: str,
    location_id: str,
    db: Database,
) -> PhotoFeatures:
    """Copy ``source_path`` into the photos root and persist the path.

    Args:
        source_path: Path to the source image (anywhere readable).
        location_id: Location to attach the photo to.
        db: Database to update.

    Returns:
        A :class:`PhotoFeatures` describing the stored photo.

    Notes:
        - Overwrites any existing photo for the same location. The
          old file is removed to avoid disk bloat.
        - The DB column ``household_locations.photo_path`` is set
          to the absolute path of the new file.
    """
    src = Path(source_path)
    if not src.is_file():
        raise FileNotFoundError(f"Source photo not found: {source_path}")
    file_bytes = src.read_bytes()
    file_hash = hashlib.sha256(file_bytes).hexdigest()[:16]
    # Build collision-free filename
    suffix = src.suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".jpg"
    dest = photos_root() / f"{location_id}__{file_hash}{suffix}"
    # Remove any older photo for this location
    _remove_existing_photo_files(location_id, keep=[])
    # Copy bytes
    dest.write_bytes(file_bytes)
    # Update DB
    db.update_location_photo(location_id, str(dest.resolve()))
    # Return features
    return extract_features(str(dest), location_id)


def _remove_existing_photo_files(location_id: str, keep: list[Path] | None = None) -> None:
    """Best-effort: remove any files in photos_root whose name starts
    with ``<location_id>__`` and that aren't in the ``keep`` list."""
    keep_set = {p.resolve() for p in (keep or [])}
    for path in photos_root().iterdir():
        if not path.is_file():
            continue
        if path.name.startswith(f"{location_id}__") and path.resolve() not in keep_set:
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("Failed to remove old photo %s: %s", path, exc)


def clear_photo(location_id: str, db: Database) -> bool:
    """Remove the photo for a location.

    Returns:
        True if a photo was removed, False if there was none.
    """
    loc = db.get_location(location_id)
    if not loc or not getattr(loc, "photo_path", None):
        return False
    path = Path(loc.photo_path)
    db.update_location_photo(location_id, None)
    if path.is_file():
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("Failed to remove photo %s: %s", path, exc)
    return True


# ─── Search ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class PhotoMatch:
    """A candidate match returned by :func:`find_similar_locations`."""
    location_id: str
    location_name: str
    similarity: float
    photo_path: str


def find_similar_locations(
    query_path: str,
    db: Database,
    top_k: int = 5,
    min_similarity: float = 0.5,
) -> list[PhotoMatch]:
    """Return the top-k most similar location photos to ``query_path``.

    Args:
        query_path: Path to the candidate photo.
        db: Database to read location rows from.
        top_k: Max number of matches to return.
        min_similarity: Drop matches below this cosine similarity.

    Returns:
        A list of :class:`PhotoMatch` sorted by similarity (highest
        first). An empty list means no locations had photos, or none
        met the threshold.
    """
    try:
        query_feats = extract_features(query_path, location_id="__query__")
    except (FileNotFoundError, Image.UnidentifiedImageError) as exc:
        logger.warning("Could not load query photo %s: %s", query_path, exc)
        return []
    candidates: list[PhotoMatch] = []
    for loc in db.get_locations():
        if not loc.photo_path:
            continue
        try:
            cand_feats = extract_features(loc.photo_path, location_id=loc.location_id)
        except (FileNotFoundError, Image.UnidentifiedImageError):
            continue
        sim = cosine_similarity(query_feats.color_histogram, cand_feats.color_histogram)
        if sim < min_similarity:
            continue
        candidates.append(PhotoMatch(
            location_id=loc.location_id,
            location_name=loc.name,
            similarity=round(sim, 4),
            photo_path=loc.photo_path,
        ))
    candidates.sort(key=lambda m: m.similarity, reverse=True)
    return candidates[:top_k]


__all__ = [
    "PhotoFeatures",
    "PhotoMatch",
    "photos_root",
    "extract_features",
    "cosine_similarity",
    "store_photo",
    "clear_photo",
    "find_similar_locations",
]
