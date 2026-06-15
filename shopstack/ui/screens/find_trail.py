"""Object Trail View — the "Find" screen with movement intelligence.

Renders a unified view of where an item is, where it has been, where it
likely is now, where it's NOT, who owns it, and a search plan.
"""
from __future__ import annotations

import logging
from datetime import datetime
from html import escape

from shopstack.app_context import db, tools, current_user_id
from shopstack.schemas.models import FindFeedback, HouseholdObject, ObjectNote, ObjectSighting
from shopstack.ui.components.decorators import aria_live_screen
from shopstack.ui.screens._utils import safe_render

logger = logging.getLogger(__name__)


# ── Color palette ──────────────────────────────────────────────────────

_COLOR_GREEN = "var(--green)"
_COLOR_RED = "var(--red)"
_COLOR_AMBER = "var(--amber)"
_COLOR_BLUE = "var(--blue)"
_COLOR_TEXT = "var(--text)"
_COLOR_DIM = "var(--text-dim)"
_COLOR_BORDER = "var(--border)"
_CARD_STYLE = "text-align:left;margin-bottom:10px;"
_BADGE_STYLE = (
    "display:inline-block;padding:2px 8px;border-radius:10px;"
    "font-size:0.625rem;font-weight:600;margin-left:6px;vertical-align:middle;"
)


# ── Public API (Gradio-facing) ─────────────────────────────────────────


@safe_render
def find_trail_view(query: str) -> str:
    """Main entry: search for an item and render its full trail card."""
    if not (query or "").strip():
        return _empty_state()
    uid = current_user_id()
    result_set = tools.inventory._shopfind().find_anything(query.strip(), user_id=uid)
    if not result_set.results:
        return _no_results(query)
    cards = []
    for result in result_set.results[:5]:
        cards.append(_render_trail_card(result))
    header = _render_header(result_set)
    return f"{header}<div style='display:flex;flex-direction:column;gap:10px;'>{''.join(cards)}</div>"


@aria_live_screen()
def add_negative_memory(lot_id: str, location_id: str) -> str:
    """Mark an item as confirmed NOT at a location."""
    if not lot_id or not location_id:
        return "<div style='color:var(--red);'>Lot ID and Location ID required.</div>"
    uid = current_user_id()
    tools._app_inventory().db.add_negative_memory(
        lot_id=lot_id,
        location_id=location_id,
        user_id=uid,
    )
    return f"<div style='color:var(--green);'>Marked as confirmed NOT at {escape(location_id)}.</div>"


@aria_live_screen()
def add_person_association(lot_id: str, person_name: str, relationship: str = "owner") -> str:
    """Associate a person with an item."""
    if not lot_id or not person_name:
        return "<div style='color:var(--red);'>Lot ID and person name required.</div>"
    uid = current_user_id()
    person_id = f"person_{person_name.strip().lower().replace(' ', '_')}"
    tools._app_inventory().db.add_person_association(
        lot_id=lot_id,
        person_id=person_id,
        person_name=person_name.strip(),
        relationship=relationship,
        user_id=uid,
    )
    return f"<div style='color:var(--green);'>Associated {escape(person_name)} with item.</div>"


@aria_live_screen()
def create_find_object(
    name: str,
    object_type: str,
    home_location_id: str,
    owner_name: str = "",
    notes: str = "",
) -> str:
    """Create a durable ShopFind object with separate home/current state."""
    clean_name = (name or "").strip()
    if not clean_name:
        return "<div style='color:var(--red);'>Object name is required.</div>"
    uid = current_user_id()
    obj = db.add_household_object(HouseholdObject(
        canonical_name=clean_name.lower(),
        display_name=clean_name,
        object_type=(object_type or "other"),
        category=(object_type or "other"),
        owner_name=(owner_name or "").strip() or None,
        home_location_id=(home_location_id or "").strip() or None,
        current_location_id=(home_location_id or "").strip() or None,
        notes=(notes or "").strip() or None,
    ), user_id=uid)
    return (
        f"<div style='color:var(--green);'>Created findable object "
        f"{escape(obj.display_name)} ({escape(obj.object_id)}).</div>"
    )


@aria_live_screen()
def record_object_sighting(object_id: str, location_id: str, context: str = "", notes: str = "") -> str:
    """Record that a durable object was seen at a location."""
    if not object_id or not location_id:
        return "<div style='color:var(--red);'>Object ID and location ID are required.</div>"
    uid = current_user_id()
    obj = db.get_household_object(object_id, user_id=uid)
    if obj is None:
        return f"<div style='color:var(--red);'>Object {escape(object_id)} not found.</div>"
    sighting = db.record_object_sighting(ObjectSighting(
        object_id=object_id,
        location_id=location_id,
        context=(context or "").strip() or None,
        notes=(notes or "").strip() or None,
    ), user_id=uid)
    return (
        f"<div style='color:var(--green);'>Recorded sighting for "
        f"{escape(obj.display_name)} at {escape(sighting.location_id)}.</div>"
    )


@aria_live_screen()
def add_object_note(object_id: str, note_text: str, tags: str = "") -> str:
    """Add searchable human memory to a durable object."""
    if not object_id or not (note_text or "").strip():
        return "<div style='color:var(--red);'>Object ID and note are required.</div>"
    uid = current_user_id()
    obj = db.get_household_object(object_id, user_id=uid)
    if obj is None:
        return f"<div style='color:var(--red);'>Object {escape(object_id)} not found.</div>"
    tag_list = [tag.strip() for tag in (tags or "").split(",") if tag.strip()]
    db.add_object_note(ObjectNote(object_id=object_id, note_text=note_text.strip(), tags=tag_list), user_id=uid)
    return f"<div style='color:var(--green);'>Added note to {escape(obj.display_name)}.</div>"


@aria_live_screen()
def record_find_feedback(query: str, object_or_lot_id: str, actual_location_id: str, feedback: str = "found") -> str:
    """Record ShopFind feedback so the memory system can learn."""
    if not (query or "").strip() or not (object_or_lot_id or "").strip():
        return "<div style='color:var(--red);'>Query and object/lot ID are required.</div>"
    uid = current_user_id()
    object_id = object_or_lot_id.strip()
    lot_id = None
    if db.get_household_object(object_id, user_id=uid) is None:
        lot_id = object_id
        object_id = None
    tools.inventory._shopfind().record_feedback(FindFeedback(
        query=query.strip(),
        feedback=feedback or "found",
        object_id=object_id,
        lot_id=lot_id,
        actual_location_id=(actual_location_id or "").strip() or None,
    ), user_id=uid)
    return "<div style='color:var(--green);'>Feedback recorded.</div>"


# ── Private renderers ──────────────────────────────────────────────────


def _empty_state() -> str:
    return (
        "<div class='stat-card' style='text-align:center;padding:30px;'>"
        "<div style='font-size:1.5rem;margin-bottom:8px;'>🔍</div>"
        "<div style='font-weight:600;'>Search for any item</div>"
        "<div style='font-size:0.75rem;color:var(--text-dim);margin-top:4px;'>"
        "Enter an item name to see its trail — where it is, where it's been, and where to look next."
        "</div></div>"
    )


def _no_results(query: str) -> str:
    return (
        f"<div class='stat-card' style='text-align:center;padding:20px;'>"
        f"<div style='font-weight:600;'>No results for '{escape(query)}'</div>"
        f"<div style='font-size:0.75rem;color:var(--text-dim);margin-top:4px;'>"
        f"Try a different search term or add this item to inventory."
        f"</div></div>"
    )


def _render_header(result_set) -> str:
    count = result_set.count
    label = "result" if count == 1 else "results"
    return (
        f"<div class='stat-card' style='{_CARD_STYLE}'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
        f"<div><span style='font-weight:600;'>'{escape(result_set.query)}'</span>"
        f"<span style='font-size:0.75rem;color:var(--text-dim);margin-left:8px;'>"
        f"{count} {label}</span></div>"
        f"</div></div>"
    )


def _render_trail_card(result) -> str:
    """Render a single FindResult as a trail card."""
    title = escape(result.title)
    confidence = result.confidence
    entity_id = ""
    if result.household_object:
        entity_id = result.household_object.get("object_id", "")
    elif result.lot:
        entity_id = result.lot.get("lot_id", "")
    badge_color = _COLOR_GREEN if confidence >= 0.8 else (_COLOR_AMBER if confidence >= 0.5 else _COLOR_RED)
    confidence_label = f"{confidence:.0%}"

    sections = []
    sections.append(_render_location_section(result))
    sections.append(_render_likely_locations(result))
    sections.append(_render_movement_trail(result))
    sections.append(_render_negative_memory(result))
    sections.append(_render_person_associations(result))
    sections.append(_render_search_plan(result))
    sections.append(_render_actions(result))

    body = "".join(s for s in sections if s)
    return (
        f"<div class='stat-card' style='{_CARD_STYLE}'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
        f"<div><div style='font-weight:600;font-size:1rem;'>{title}</div>"
        f"<div style='font-size:0.625rem;color:var(--text-dim);'>{escape(str(result.entity_type))} · {escape(str(entity_id))}</div></div>"
        f"<span style='{_BADGE_STYLE}background:{badge_color};color:#fff;'>{confidence_label}</span>"
        f"</div>"
        f"{body}"
        f"</div>"
    )


def _render_location_section(result) -> str:
    """Render normal home + current believed location."""
    normal_home = result.normal_home_location_name
    current = result.current_believed_location_name

    if not normal_home and not current:
        return ""

    rows = ""
    if normal_home:
        rows += (
            f"<div style='display:flex;align-items:center;gap:8px;margin-top:6px;'>"
            f"<span style='font-size:0.625rem;color:var(--text-dim);min-width:100px;'>Normal Home</span>"
            f"<span style='font-weight:500;'>{escape(normal_home)}</span>"
            f"</div>"
        )
    if current and current != normal_home:
        rows += (
            f"<div style='display:flex;align-items:center;gap:8px;margin-top:4px;'>"
            f"<span style='font-size:0.625rem;color:var(--text-dim);min-width:100px;'>Believed Now</span>"
            f"<span style='font-weight:500;color:var(--green);'>{escape(current)}</span>"
            f"</div>"
        )

    return (
        f"<div style='margin-top:10px;padding-top:8px;border-top:1px solid {_COLOR_BORDER};'>"
        f"<div style='font-size:0.6875rem;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;'>Location</div>"
        f"{rows}</div>"
    )


def _render_likely_locations(result) -> str:
    """Render ranked likely locations with scores."""
    locs = result.likely_locations
    if not locs:
        return ""

    rows = ""
    for loc in locs[:4]:
        score = loc.score
        bar_width = int(score * 100)
        color = _COLOR_GREEN if score >= 0.7 else (_COLOR_AMBER if score >= 0.4 else _COLOR_DIM)
        reasons = ", ".join(loc.reasons[:2]) if loc.reasons else ""
        decay = loc.confidence_decay
        decay_badge = ""
        if decay < 0.8:
            decay_badge = (
                f"<span style='font-size:0.625rem;color:var(--amber);margin-left:4px;'>"
                f"⏰ {decay:.0%}</span>"
            )
        rows += (
            f"<div style='margin-top:6px;'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<span style='font-size:0.75rem;font-weight:500;'>{escape(loc.location_name)}</span>"
            f"<span style='font-size:0.6875rem;color:var(--text-dim);'>{score:.0%}{decay_badge}</span>"
            f"</div>"
            f"<div style='height:4px;background:var(--border);border-radius:2px;margin-top:3px;'>"
            f"<div style='height:100%;width:{bar_width}%;background:{color};border-radius:2px;'></div>"
            f"</div>"
            f"<div style='font-size:0.625rem;color:var(--text-dim);margin-top:2px;'>{escape(reasons)}</div>"
            f"</div>"
        )

    return (
        f"<div style='margin-top:10px;padding-top:8px;border-top:1px solid {_COLOR_BORDER};'>"
        f"<div style='font-size:0.6875rem;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;'>Likely Locations</div>"
        f"{rows}</div>"
    )


def _render_movement_trail(result) -> str:
    """Render movement history as a timeline."""
    trail = result.movement_trail
    if not trail:
        return ""

    rows = ""
    for i, movement in enumerate(trail[:5]):
        from_name = movement.get("from_location_name") or movement.get("from_location_id") or "?"
        to_name = movement.get("to_location_name") or movement.get("to_location_id") or "?"
        ts = movement.get("timestamp", "")
        source = movement.get("source", "manual")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            time_str = dt.strftime("%b %d, %H:%M")
        except Exception:
            time_str = ts[:16] if ts else "?"
        connector = "↓" if i < len(trail) - 1 else "●"
        rows += (
            f"<div style='display:flex;gap:10px;margin-top:4px;'>"
            f"<div style='min-width:20px;text-align:center;font-size:0.75rem;color:var(--text-dim);'>{connector}</div>"
            f"<div style='flex:1;'>"
            f"<div style='font-size:0.75rem;'>"
            f"<span style='color:var(--text-dim);'>{escape(str(from_name))}</span>"
            f" → <span style='font-weight:500;'>{escape(str(to_name))}</span>"
            f"</div>"
            f"<div style='font-size:0.625rem;color:var(--text-dim);'>{escape(time_str)} · {escape(source)}</div>"
            f"</div></div>"
        )

    return (
        f"<div style='margin-top:10px;padding-top:8px;border-top:1px solid {_COLOR_BORDER};'>"
        f"<div style='font-size:0.6875rem;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;'>Movement Trail</div>"
        f"{rows}</div>"
    )


def _render_negative_memory(result) -> str:
    """Render places where the item is confirmed NOT to be."""
    mems = result.negative_memory
    if not mems:
        return ""

    rows = ""
    for mem in mems[:3]:
        rows += (
            f"<div style='display:flex;align-items:center;gap:6px;margin-top:4px;'>"
            f"<span style='color:var(--red);font-size:0.75rem;'>✗</span>"
            f"<span style='font-size:0.75rem;'>{escape(mem.location_name)}</span>"
            f"<span style='font-size:0.625rem;color:var(--text-dim);'>— {escape(mem.source)}</span>"
            f"</div>"
        )

    return (
        f"<div style='margin-top:10px;padding-top:8px;border-top:1px solid {_COLOR_BORDER};'>"
        f"<div style='font-size:0.6875rem;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;'>Confirmed NOT At</div>"
        f"{rows}</div>"
    )


def _render_person_associations(result) -> str:
    """Render who owns/uses this item."""
    persons = result.person_associations
    if not persons:
        return ""

    rows = ""
    for pa in persons[:3]:
        emoji = "👤" if pa.relationship == "owner" else "👤"
        rows += (
            f"<div style='display:flex;align-items:center;gap:6px;margin-top:4px;'>"
            f"<span style='font-size:0.75rem;'>{emoji}</span>"
            f"<span style='font-size:0.75rem;font-weight:500;'>{escape(pa.person_name)}</span>"
            f"<span style='font-size:0.625rem;color:var(--text-dim);'>— {escape(pa.relationship)}</span>"
            f"</div>"
        )

    return (
        f"<div style='margin-top:10px;padding-top:8px;border-top:1px solid {_COLOR_BORDER};'>"
        f"<div style='font-size:0.6875rem;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;'>Associated People</div>"
        f"{rows}</div>"
    )


def _render_search_plan(result) -> str:
    """Render ordered search plan."""
    plan = result.search_plan
    if not plan:
        return ""

    rows = ""
    for i, step in enumerate(plan[:5]):
        rows += (
            f"<div style='display:flex;align-items:center;gap:8px;margin-top:4px;'>"
            f"<span style='min-width:18px;height:18px;border-radius:50%;background:var(--blue);color:#fff;"
            f"display:flex;align-items:center;justify-content:center;font-size:0.625rem;font-weight:700;'>"
            f"{i + 1}</span>"
            f"<span style='font-size:0.75rem;'>{escape(step)}</span>"
            f"</div>"
        )

    return (
        f"<div style='margin-top:10px;padding-top:8px;border-top:1px solid {_COLOR_BORDER};'>"
        f"<div style='font-size:0.6875rem;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;'>Search Plan</div>"
        f"{rows}</div>"
    )


def _render_actions(result) -> str:
    """Render available actions as pills."""
    actions = result.actions
    if not actions:
        return ""

    labels = {
        "mark_found": "✓ Found",
        "move_item": "↗ Move",
        "add_note": "+ Note",
        "add_negative_memory": "✗ Not Here",
        "add_person_association": "👤 Assign Person",
        "add_sighting": "👁 Seen Here",
        "set_home_location": "🏠 Set Home",
    }

    pills = ""
    for action in actions[:5]:
        label = labels.get(action, action)
        pills += (
            f"<span style='display:inline-block;padding:3px 10px;border-radius:12px;"
            f"background:var(--border);font-size:0.6875rem;margin-right:6px;margin-top:4px;cursor:pointer;'>"
            f"{escape(label)}</span>"
        )

    return (
        f"<div style='margin-top:10px;padding-top:8px;border-top:1px solid {_COLOR_BORDER};'>"
        f"<div style='font-size:0.6875rem;font-weight:600;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.5px;'>Actions</div>"
        f"<div>{pills}</div></div>"
    )
