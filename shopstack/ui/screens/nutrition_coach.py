"""Nutrition coach UI screen — Phase 8 #17 wiring.

A thin server-rendered panel that pulls the household's
nutrition summary from the inventory, runs the coaching
engine, and returns the HTML. Wired into the Memory tab's
Nutrition sub-tab.
"""
from __future__ import annotations

import logging
from typing import Any

from shopstack.app_context import current_user_id, db
from shopstack.services.i18n import DEFAULT_LOCALE, t
from shopstack.services.nutrition import get_inventory_nutrition_summary
from shopstack.services.nutrition_coach import (
    HouseholdProfile,
    build_coaching,
    render_coaching_html,
)

logger = logging.getLogger(__name__)


def nutrition_coach_screen(
    household_size: int = 4,
    dietary: str = "vegetarian",
    locale: str = DEFAULT_LOCALE,
) -> str:
    """Render the nutrition coaching panel for the active household.

    Pulls the inventory → nutrition summary → coaching → HTML
    pipeline in one call. Designed to be wired into a
    `gr.HTML` component with `every=NN` (Gradio's auto-refresh)
    or a manual refresh button.

    Args:
        household_size: Number of people in the household.
            Defaults to 4 (the most common Indian family).
        dietary: One of "vegetarian" / "vegan" / "omnivore".
            Defaults to vegetarian.
        locale: Translation locale for the headline.

    Returns:
        XSS-safe HTML for direct insertion into a Gradio
        component.
    """
    try:
        user_id = current_user_id() or ""
        summary = get_inventory_nutrition_summary(db, user_id=user_id)
        profile = HouseholdProfile(size=household_size, dietary=dietary)
        coaching = build_coaching(summary, profile=profile)
        return render_coaching_html(coaching, locale=locale)
    except Exception as exc:
        logger.debug("nutrition_coach_screen failed: %s", exc)
        return (
            "<div class='home-card' style='text-align:center;color:var(--text-dim);padding:16px;'>"
            "🥗 Add some inventory first to see nutrition coaching."
            "</div>"
        )


__all__ = ["nutrition_coach_screen"]
