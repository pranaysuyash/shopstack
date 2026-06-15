from __future__ import annotations

import logging
from html import escape

from shopstack.app_context import db, current_user_id
from shopstack.memory.waste_patterns import get_waste_insights
from shopstack.ui.screens.price_memory import price_intelligence_view
from shopstack.ui.screens._utils import safe_render

logger = logging.getLogger(__name__)

_VALID_SIGNAL_TYPES = ("staple", "disliked", "often_wasted", "brand_preferred", "pack_size", "discount_only")
_DISPLAY_NAMES = {
    "staple": "Staple (always buy)",
    "disliked": "Disliked (avoid buying)",
    "often_wasted": "Often wasted",
    "brand_preferred": "Brand preferred",
    "pack_size": "Pack size preference",
    "discount_only": "Buy only on discount",
}


@safe_render
def get_intelligence_dashboard():
    """Return HTML for Waste, Preferences, and Price intelligence."""
    uid = current_user_id()

    # 1. Waste Patterns
    try:
        waste_data = get_waste_insights(db)
        if waste_data:
            waste_items = []
            for w in waste_data:
                rate = w["waste_rate"] * 100
                if rate > 0:
                    waste_items.append(
                        f"<li><strong>{escape(w['canonical_name'].title())}</strong>: {w['wasted_qty']} wasted out of {w['wasted_qty']+w['consumed_qty']} ({rate:.0f}% waste rate)</li>"
                    )

            if waste_items:
                waste_html = "<div class='home-card' style='border-left:4px solid var(--red);'>" \
                             "<h4>High Waste Items</h4><ul>" + "".join(waste_items[:10]) + "</ul></div>"
            else:
                waste_html = "<div class='home-card'>No waste patterns detected yet. Great job!</div>"
        else:
            waste_html = "<div class='home-card'>No waste data available.</div>"
    except Exception as e:
        logger.warning("Error loading waste insights: %s", e)
        waste_html = "<div class='home-card'>Error loading waste insights.</div>"

    # 2. Preferences (enhanced with delete capability)
    pref_html = _render_preferences(uid)

    # 3. Price Intelligence
    try:
        price_html = price_intelligence_view()
    except Exception as e:
        logger.warning("Error loading price intelligence: %s", e)
        price_html = "<div class='home-card'>Error loading price intelligence.</div>"

    return waste_html, pref_html, price_html


def _render_preferences(user_id: str) -> str:
    """Render preferences list with delete buttons and add form."""
    from shopstack.services.preference import PreferenceService
    service = PreferenceService(db)
    prefs = service.get_preferences(user_id=user_id)

    # Group by signal_type for organized display
    by_type: dict[str, list] = {}
    for p in prefs:
        by_type.setdefault(p.signal_type, []).append(p)

    sections: list[str] = []
    for stype in _VALID_SIGNAL_TYPES:
        items = by_type.get(stype, [])
        if not items:
            continue
        label = _DISPLAY_NAMES.get(stype, stype.replace("_", " ").title())
        rows = []
        for p in items:
            name = escape(p.canonical_name.replace("_", " ").title())
            value = escape(str(p.value))
            source = escape(p.source or "")
            confidence = f"{p.confidence:.0%}" if p.confidence else ""
            rows.append(
                f"<div style='display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid var(--border);'><span><strong>{name}</strong> &rarr; {value}"
                f" <span style='font-size: 0.625rem;color:var(--text-dim);'>({source}, {confidence})</span></span><button onclick=\"fetch('/api/preference_delete?signal_id={p.signal_id}')"
                f".then(r=>r.json()).then(d=>{{if(d.ok){{this.parentElement.remove();}}}})\""
                f" style='font-size: 0.625rem;padding:2px 6px;border:1px solid var(--red);color:var(--red);background:none;border-radius:3px;cursor:pointer;'>Remove</button></div>"
            )
        sections.append(
            f"<div style='margin-bottom:12px;'><h5 style='margin:4px 0;color:var(--blue);'>{label} ({len(items)})</h5>"
            + "".join(rows) + "</div>"
        )

    if not sections:
        return "<div class='home-card'>No preference signals learned yet. Complete more shopping trips or add preferences manually below.</div>"

    return (
        "<div class='home-card'><h4>Learned Preferences</h4>"
        + "".join(sections) + "</div>"
    )


@safe_render
def add_preference(canonical_name: str, signal_type: str, value: str) -> str:
    """Add a new preference signal."""
    if not canonical_name or not canonical_name.strip():
        return "<div style='color:var(--red);'>Item name is required.</div>"
    if signal_type not in _VALID_SIGNAL_TYPES:
        return f"<div style='color:var(--red);'>Invalid signal type: {escape(signal_type)}</div>"

    from shopstack.services.preference import PreferenceService
    service = PreferenceService(db)
    uid = current_user_id()
    signal = service.record_signal(
        canonical_name=canonical_name.strip().lower(),
        signal_type=signal_type,
        value=value.strip() or signal_type,
        source="explicit",
        confidence=1.0,
        user_id=uid,
    )
    display = signal.canonical_name.replace("_", " ").title()
    return f"<div style='color:var(--green);'>Added {escape(signal_type)} preference for {escape(display)}.</div>"


@safe_render
def delete_preference(signal_id: str) -> str:
    """Delete a preference signal by ID."""
    if not signal_id:
        return "<div style='color:var(--red);'>No signal ID provided.</div>"

    from shopstack.services.preference import PreferenceService
    service = PreferenceService(db)
    deleted = service.delete_signal(signal_id.strip())
    if deleted:
        return "<div style='color:var(--green);'>Preference removed.</div>"
    return "<div style='color:var(--red);'>Signal not found.</div>"


@safe_render
def refresh_preferences() -> str:
    """Refresh the preferences display."""
    uid = current_user_id()
    return _render_preferences(uid)
