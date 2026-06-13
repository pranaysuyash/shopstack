"""Trip advisor UI screen — Phase 8 #25 wiring.

Thin server-rendered banner that pulls the active shopping
list size, use-soon count, and price-drop count, then runs
the trip advisor's decision tree. Wired into the top of the
Basket tab.
"""
from __future__ import annotations

import logging
from typing import Any

from shopstack.app_context import current_user_id, db
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
    try:
        user_id = current_user_id() or ""
        # Active list size
        try:
            lists = db.get_shopping_lists(user_id=user_id) or []
            active_list_size = sum(
                len(db.get_shopping_list_items(list_id=l.get("list_id") or l.get("id", "")) or [])
                for l in lists
            )
        except Exception:
            active_list_size = 0
        # Use-soon count (items expiring in 2-3 days)
        try:
            use_soon = db.get_use_soon_items(user_id=user_id) or []
            use_soon_count = len(use_soon)
        except Exception:
            use_soon_count = 0
        # Price drops: full detection needs a market snapshot, which
        # the trip advisor panel doesn't have. Use 0 (the seasonal
        # engine and use-soon signal are the primary decision inputs).
        price_drop_count = 0
        # Weather (best-effort; may use the mock fallback)
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
    except Exception as exc:
        logger.debug("trip_advisor_screen failed: %s", exc)
        return ""  # graceful degradation — no banner if everything fails


__all__ = ["trip_advisor_screen"]
