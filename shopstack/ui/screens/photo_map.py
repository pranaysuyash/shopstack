"""Photo-Anchored Map — visual browse + find-by-photo for locations.

Builds on the text-only household map by:
1. Attaching a photo to a location (or clearing it).
2. Displaying photos inline in the map (delegated to
   :func:`household_map.household_map_view`).
3. Find-by-photo: the user uploads a candidate photo, and the
   service returns the top-k most visually-similar stored location
   photos.

The matching is intentionally simple (color histogram + cosine
similarity). It is a "does this look familiar" signal, not a
high-fidelity image matcher. See
:mod:`shopstack.services.photo_search` for the implementation.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.app_context import db, current_user_id
from shopstack.services.photo_search import (
    clear_photo,
    find_similar_locations,
    store_photo,
)
from shopstack.ui.components.decorators import aria_live_screen
from shopstack.ui.components.primitives import home_card, stat_card
from shopstack.ui.screens._utils import safe_render

logger = logging.getLogger(__name__)



def photo_map_view() -> str:
    """Render the photo-anchored map: grid of locations, with photos."""
    from shopstack.ui.errors import safe_render_html
    return safe_render_html(
        lambda: _photo_map_view_inner(),
        user_message="Could not load photo map",
        help_tab="household",
        icon="🗺️",
    )


def _photo_map_view_inner() -> str:
    """Render the photo-anchored map: grid of locations, with photos."""
    locations = db.get_locations()
    inventory = db.get_inventory(user_id=current_user_id())
    with_photo = [loc for loc in locations if loc.photo_path]
    without_photo = [loc for loc in locations if not loc.photo_path]

    parts: list[str] = []
    parts.append("<h3>Photo-Anchored Map</h3>")
    parts.append(
        f"<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>{len(with_photo)} of {len(locations)} location(s) have photos. "
        f"Attach photos via the form below.</div>"
    )

    # Locations with photos
    if with_photo:
        parts.append("<div class='al-section-h'>Anchored locations</div>")
        parts.append("<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px;'>")
        for loc in with_photo:
            safe_name = escape(str(loc.name))
            safe_path = escape(str(loc.photo_path))
            parts.append(stat_card(
                style="text-align:left;margin-bottom:6px;",
                body_html=(
                    f"<div style='font-weight:600;font-size:0.85rem;'>{safe_name}</div>"
                    f"<img src='file={safe_path}' alt='{safe_name}' style='max-width:100%;max-height:120px;border-radius:6px;"
                    f"border:1px solid var(--border);display:block;margin-top:4px;' /><div style='font-size:0.625rem;color:var(--text-dim);margin-top:4px;'>"
                    f"{escape(str(loc.location_type))}</div>"
                ),
            ))
        parts.append("</div>")

    # Locations without photos
    if without_photo:
        parts.append("<div class='al-section-h'>Awaiting photos</div>")
        names = ", ".join(escape(loc.name) for loc in without_photo[:12])
        more = "" if len(without_photo) <= 12 else f" (+{len(without_photo) - 12} more)"
        parts.append(f"<div style='font-size:0.75rem;color:var(--text-dim);'>{names}{more}</div>")

    return "".join(parts)


@aria_live_screen()
def attach_photo_to_location(location_id: str, image_path: str) -> str:
    """Copy ``image_path`` into storage and attach it to a location.

    Args:
        location_id: Target location.
        image_path: Path to a readable image file.
    """
    if not (location_id or "").strip():
        return "<div style='color:var(--red);'>Location ID required.</div>"
    if not (image_path or "").strip():
        return "<div style='color:var(--red);'>Image path required.</div>"
    loc = db.get_location(location_id.strip())
    if not loc:
        return f"<div style='color:var(--red);'>Unknown location: {escape(location_id)}</div>"
    try:
        features = store_photo(image_path.strip(), location_id.strip(), db)
    except FileNotFoundError as exc:
        return f"<div style='color:var(--red);'>{escape(str(exc))}</div>"
    except Exception as exc:
        logger.exception("attach_photo_to_location failed")
        return f"<div style='color:var(--red);'>Failed to store photo: {escape(str(exc))}</div>"
    return (
        f"<div style='color:var(--green);'>Attached photo ({features.width}\u00d7{features.height}, "
        f"{features.file_size} bytes) to {escape(loc.name)}.</div>"
    )


@aria_live_screen()
def clear_location_photo(location_id: str) -> str:
    """Remove the photo from a location."""
    if not (location_id or "").strip():
        return "<div style='color:var(--red);'>Location ID required.</div>"
    removed = clear_photo(location_id.strip(), db)
    if not removed:
        return f"<div style='color:var(--text-dim);'>No photo to clear for {escape(location_id)} — add or scan a photo for this location first.</div>"
    return f"<div style='color:var(--green);'>Photo cleared for {escape(location_id)}.</div>"



def find_location_by_photo(image_path: str, top_k: int = 5) -> str:
    """Find the most similar stored location photos to ``image_path``.

    Returns HTML with the top matches (name + similarity %).
    """
    from shopstack.ui.errors import safe_render_html
    path, k = image_path, top_k
    return safe_render_html(
        lambda: _find_location_by_photo_inner(path, k),
        user_message="Photo search failed",
        help_tab="household",
        icon="🔍",
    )


def _find_location_by_photo_inner(image_path: str, top_k: int) -> str:
    """Inner: find the most similar stored location photos."""
    if not (image_path or "").strip():
        return home_card(
            style="text-align:center;padding:16px;color:var(--text-dim);",
            body="Upload a photo to find similar locations.",
        )
    try:
        matches = find_similar_locations(image_path.strip(), db, top_k=top_k)
    except Exception as exc:
        logger.exception("find_location_by_photo failed")
        return home_card(
            style="text-align:center;padding:16px;",
            body=(
                "<div style='color:var(--red);font-weight:600;'>Photo search failed</div>"
                f"<div style='font-size: 0.75rem;color:var(--text-dim);margin-top:4px;'>{escape(str(exc)[:120])}</div>"
            ),
        )
    if not matches:
        return home_card(
            style="text-align:center;padding:16px;color:var(--text-dim);",
            body="No matching locations. Attach photos first."
        )

    parts: list[str] = []
    parts.append(
        f"<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:6px;'>Top {len(matches)} match(es) for your photo"
        f"</div>"
    )
    for m in matches:
        bar_width = int(m.similarity * 100)
        parts.append(stat_card(
            style="text-align:left;margin-bottom:6px;",
            body_html=(
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<div style='font-weight:600;'>{escape(m.location_name)}</div><div style='font-size:0.75rem;color:var(--text-dim);'>{m.similarity:.0%}</div>"
                f"</div><div style='height:4px;background:var(--border);border-radius:2px;margin-top:4px;'>"
                f"<div style='height:100%;width:{bar_width}%;background:var(--blue);border-radius:2px;'></div></div>"
                f"<div style='font-size:0.625rem;color:var(--text-dim);margin-top:4px;'>{escape(m.location_id)}</div>"
            ),
        ))
    return "".join(parts)


__all__ = [
    "photo_map_view",
    "attach_photo_to_location",
    "clear_location_photo",
    "find_location_by_photo",
]
