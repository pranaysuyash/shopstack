"""Community price map UI screens — Phase 8 #15 wiring.

Thin server-rendered panels for:
- **Opt-in toggle** — show the household's opt-in status and
  let the user flip it.
- **Community median badge** — small "👥 ₹X" badge for one
  canonical item.
- **Status banner** — overall pool stats.

Wired into the household settings accordion + price memory
rows.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.app_context import current_user_id
from shopstack.services.community_price_map import (
    is_opted_in,
    pool_stats,
    render_community_indicator_html,
    render_opt_in_toggle_html,
    set_opt_in,
)

logger = logging.getLogger(__name__)


def community_status_screen() -> str:
    """Render the opt-in status line for the household settings."""
    try:
        return render_opt_in_toggle_html(current_user_id() or "")
    except Exception as exc:
        logger.warning("community_status_screen failed: %s", exc)
        return "<span style='color:var(--amber);'>Community status unavailable</span>"


def community_pool_stats_screen() -> str:
    """Render a small "X observations, Y items, Z anon ids" stat line."""
    try:
        stats = pool_stats()
        if not stats.get("size"):
            return (
                "<div class='home-card' style='font-size: 0.6875rem;color:var(--text-dim);padding:8px;'>"
                "👥 Local community pool is empty. Opt in to start sharing prices."
                "</div>"
            )
        return (
            "<div class='home-card' style='font-size: 0.6875rem;color:var(--text-muted, #5F5144);padding:8px;'>"
            f"👥 Local pool: <strong>{stats['size']}</strong> observations, "
            f"<strong>{stats['distinct_items']}</strong> items, "
            f"<strong>{stats['distinct_anon']}</strong> anonymized contributors"
            + (f" · newest: {stats['newest']}" if stats.get("newest") else "")
            + "</div>"
        )
    except Exception as exc:
        logger.warning("community_pool_stats_screen failed: %s", exc)
        return (
            "<div class='home-card' style='font-size: 0.6875rem;color:var(--text-dim);padding:8px;'>"
            "<span style='color:var(--amber);'>Community pool stats unavailable</span>"
            "</div>"
        )


def community_indicator_for(
    canonical_name: str,
    own_price: float | None = None,
    city: str = "",
) -> str:
    """Render the "👥 ₹X community median" badge for one item."""
    try:
        return render_community_indicator_html(
            canonical_name=canonical_name,
            own_price=own_price,
            city=city,
        )
    except Exception as exc:
        logger.warning("community_indicator_for failed: %s", exc)
        return ""


def set_opt_in_screen(opt_in: bool) -> str:
    """Set the household's opt-in flag. Returns the new status HTML."""
    try:
        set_opt_in(current_user_id() or "", bool(opt_in))
        return community_status_screen()
    except Exception as exc:
        logger.debug("set_opt_in_screen failed: %s", exc)
        return f"<span style='color:var(--red, #A63F31);'>Failed: {escape(str(exc))}</span>"


__all__ = [
    "community_indicator_for",
    "community_pool_stats_screen",
    "community_status_screen",
    "set_opt_in_screen",
]
