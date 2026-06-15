"""Renderer for the seasonal / weather-aware shopping recommendation card.

Adapts the seasonal service's ``SeasonalRecommendation`` dict (from
``DashboardState.seasonal_recommendation``) into a compact XSS-safe
card on the Today dashboard.
"""

from __future__ import annotations

from html import escape
from typing import Any


_SEVERITY_COLOR = {
    "info": "var(--blue)",
    "warning": "var(--amber)",
    "danger": "var(--red)",
    "opportunity": "var(--green)",
}


def render_seasonal(rec: dict[str, Any] | None) -> str:
    """Render a single seasonal recommendation as XSS-safe HTML.

    Returns empty string if ``rec`` is empty / missing.
    """
    if not rec:
        return ""

    icon = escape(str(rec.get("icon", "")))
    title = escape(str(rec.get("title", "")))
    body = escape(str(rec.get("body", "")))
    action = str(rec.get("action", "") or "")
    severity = str(rec.get("severity", "info"))
    color = _SEVERITY_COLOR.get(severity, "var(--text-dim)")

    action_html = ""
    if action:
        action_html = (
            f"<div style='font-size: 0.75rem;color:var(--text-dim);margin-top:6px;'><strong>Suggested:</strong> {escape(action)}</div>"
        )

    return (
        f"<div class='home-card' style='margin-bottom:12px;'><h3 style='margin:0 0 4px 0;color:{color};'>{icon} {title}</h3>"
        f"<div style='font-size: 0.8125rem;color:var(--text);'>{body}</div>{action_html}"
        f"</div>"
    )


__all__ = ["render_seasonal"]
