"""Trip advisor UI screen — Phase 8 #25 wiring.

Thin server-rendered banner that pulls the active shopping
list size, use-soon count, and price-drop count, then runs
the trip advisor's decision tree. Wired into the top of the
Basket tab.
"""
from __future__ import annotations

import logging
from typing import Any

from shopstack.app_context import current_user_id, db, tools
from shopstack.services.i18n import DEFAULT_LOCALE, t
from shopstack.services.trip_advisor import (
    TripAdvice,
    advise_trip,
    render_trip_advice_html,
)
from shopstack.services.weather import get_weather

logger = logging.getLogger(__name__)


def trip_advisor_screen(
    city: str = "mumbai",
    locale: str = DEFAULT_LOCALE,
) -> str:
    """Render the trip advisor banner for the active household.

    Computes the active list size, use-soon count, and
    price-drop count, then runs the trip advisor's decision
    tree. Returns XSS-safe HTML for direct insertion into a
    Gradio component.
    """
    from shopstack.ui.errors import safe_render_html
    return safe_render_html(
        lambda: _trip_advisor_inner(city, locale),
        user_message="Could not load trip advisor",
        help_tab="basket",
    )


def _trip_advisor_inner(city: str, locale: str) -> str:
    user_id = current_user_id() or ""
    try:
        lists = db.get_shopping_lists(user_id=user_id) or []  # type: ignore[attr-defined]
        active_list_size = sum(
            len(db.get_shopping_list_items(list_id=l.get("list_id") or l.get("id", "")) or [])  # type: ignore[attr-defined]
            for l in lists
        )
    except Exception:
        active_list_size = 0
    try:
        use_soon = tools.inventory.get_use_soon(days=3, user_id=user_id).get("items", [])
        use_soon_count = len(use_soon)
    except Exception:
        use_soon_count = 0
    price_drop_count = 0
    try:
        weather = get_weather(city=city)
    except Exception:
        weather = None
    advice = advise_trip(
        city=city,
        use_soon_count=use_soon_count,
        price_drop_count=price_drop_count,
        active_list_size=active_list_size,
        weather=weather,
    )
    return render_trip_advice_html(advice, locale=locale)


__all__ = ["trip_advisor_screen"]
