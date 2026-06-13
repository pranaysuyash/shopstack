"""Renderer for the cook-tonight card on the Today dashboard.

A compact XSS-safe card showing the top recipe recommendations. The
service is in ``shopstack.services.recipes``; this module is a thin
adapter that turns dashboard state into HTML.

Defensive coding: numeric fields are coerced through ``_safe_int`` /
``_safe_float`` so the renderer never raises on a bad-type field from
older or future dashboard state shapes. The cost is a try/except per
field; the benefit is that the Today dashboard never goes blank because
of a single malformed recipe entry.
"""

from __future__ import annotations

from html import escape
from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def render_cook_tonight(matches: list[dict[str, Any]]) -> str:
    """Render the cook-tonight card from ``DashboardState.cook_tonight_matches``."""
    if not matches:
        return ""

    parts: list[str] = []
    for m in matches[:4]:
        name = escape(str(m.get("name", "")))
        cuisine = escape(str(m.get("cuisine", "")).replace("_", " ").title())
        serves = m.get("serves", "?")
        time_min = _safe_int(m.get("prep_minutes")) + _safe_int(m.get("cook_minutes"))
        completion = _safe_float(m.get("completion_pct"))
        missing_count = _safe_int(m.get("missing_count"))
        have_count = _safe_int(m.get("have_count"))
        use_soon_count = _safe_int(m.get("use_soon_count"))
        use_soon_names = m.get("use_soon_names", []) or []
        missing_names = m.get("missing_names", []) or []

        use_soon_badge = ""
        if use_soon_count > 0:
            formatted = ", ".join(
                escape(str(n).replace("_", " ").title()) for n in use_soon_names
            )
            use_soon_badge = (
                f"<div style='font-size:11px;color:var(--amber);margin-top:2px;'>"
                f"⏰ Uses expiring: {formatted}</div>"
            )

        missing_html = ""
        if missing_count > 0:
            formatted = ", ".join(
                escape(str(n).replace("_", " ").title()) for n in missing_names
            )
            missing_html = (
                f"<div style='font-size:11px;color:var(--red);margin-top:2px;'>"
                f"✗ Need: {formatted}</div>"
            )

        have_html = ""
        if have_count > 0 and missing_count > 0:
            have_html = (
                f"<div style='font-size:11px;color:var(--green);margin-top:2px;'>"
                f"✓ Have: {have_count} of {have_count + missing_count}"
                f"</div>"
            )

        parts.append(
            f"<div style='padding:6px 0;border-bottom:1px solid var(--border);'>"
            f"<div style='display:flex;justify-content:space-between;align-items:baseline;'>"
            f"<strong>{name}</strong>"
            f"<span style='font-size:10px;color:var(--text-dim);'>{cuisine} · {time_min} min · serves {serves}</span>"
            f"</div>"
            f"{use_soon_badge}"
            f"{have_html}"
            f"{missing_html}"
            f"<div style='font-size:10px;color:var(--text-dim);margin-top:4px;'>"
            f"Completion: {completion:.0f}%"
            f"</div>"
            f"</div>"
        )

    return (
        f"<div class='home-card' style='margin-bottom:12px;'>"
        f"<h3 style='margin:0 0 4px 0;'>🍳 Cook Tonight</h3>"
        f"<div style='font-size:11px;color:var(--text-dim);margin-bottom:6px;'>"
        f"Recipes that use what you have. ⏰ marks recipes that rescue expiring items."
        f"</div>"
        f"{''.join(parts)}"
        f"</div>"
    )


__all__ = ["render_cook_tonight"]
