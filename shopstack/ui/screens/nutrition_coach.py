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
from shopstack.ui.components.primitives import home_card

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
    from shopstack.ui.errors import safe_render_html
    return safe_render_html(
        lambda: _nutrition_coach_inner(household_size, dietary, locale),
        user_message="Could not load nutrition coaching",
        help_tab="memory",
    )


def _nutrition_coach_inner(household_size: int, dietary: str, locale: str) -> str:
    user_id = current_user_id() or ""
    summary = get_inventory_nutrition_summary(db, user_id=user_id)
    profile = HouseholdProfile(size=household_size, dietary=dietary)
    coaching = build_coaching(summary, profile=profile)
    return render_coaching_html(coaching, locale=locale)


__all__ = ["nutrition_coach_screen"]
