"""Renderer for the weekly meal plan (Pass 21).

**Why this exists (motto_v3 first-principles / mode-portable):**

The meal plan is a list of ``DayPlan`` objects (from
``shopstack.services.meal_planning``). This module is the
HTML / text adapter: it turns the plan into a 7-day grid
for the Gradio UI, and into a plain-text summary for the
CLI ``--human`` mode.

The grid is XSS-safe (every dynamic string passes through
``html.escape``). The structure uses semantic HTML5
(``<section>``, ``<article>``, ``<dl>``) so screen readers
and the browser dev tools can navigate it.
"""
from __future__ import annotations

from html import escape
from typing import Any

from shopstack.services.meal_planning import DayPlan, summarize_meal_plan


# ── CSS color tokens (from shopstack.ui.theme) ──────────────────────
#
# The confidence label maps to a color so the user can
# scan the grid and see at a glance which days are
# well-planned (high) vs marginal (low).

_CONFIDENCE_COLORS = {
    "high": "var(--green)",
    "medium": "var(--amber)",
    "low": "var(--red)",
}


_DAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
]


def _day_name(date_iso: str) -> str:
    """Return the day-of-week name for an ISO date string.

    Returns the ISO date itself if parsing fails (defensive).
    """
    from datetime import date
    try:
        d = date.fromisoformat(date_iso)
        return _DAY_NAMES[d.weekday()]
    except (ValueError, AttributeError):
        return date_iso


def render_meal_plan_html(plan: list[DayPlan]) -> str:
    """Render the meal plan as a 7-day grid HTML string.

    The output is a single ``<section>`` with one
    ``<article>`` per day. The article has:
      - The day name + date (e.g. "Monday, 2026-06-16")
      - The recipe name (or "No recipe" for empty days)
      - The cuisine + cook time (if recipe)
      - A list of ingredients used + missing
      - A one-line rationale

    XSS-safe: every dynamic string is ``html.escape``-d.
    """
    summary = summarize_meal_plan(plan)
    days_html = "".join(_render_day_html(d) for d in plan)
    return (
        f"<section class='meal-plan' data-days='{len(plan)}'>"
        f"<h3 class='meal-plan-header'>Your meal plan</h3>"
        f"<p class='meal-plan-summary'>{escape(summary)}</p>"
        f"{days_html}"
        f"</section>"
    )


def _render_day_html(d: DayPlan) -> str:
    """Render a single day as an article element."""
    if d.recipe_name is None:
        # Empty day: show a "nothing planned" card.
        return (
            f"<article class='day-card day-empty' data-date='{escape(d.date)}'>"
            f"<header class='day-header'>"
            f"<span class='day-name'>{escape(_day_name(d.date))}</span>"
            f"<span class='day-date muted'>{escape(d.date)}</span>"
            f"</header>"
            f"<p class='day-recipe muted'>{escape(d.rationale or 'Nothing planned.')}</p>"
            f"</article>"
        )

    confidence_color = _CONFIDENCE_COLORS.get(d.confidence, "var(--text)")
    cuisine = f" · {escape(d.cuisine)}" if d.cuisine else ""
    cook_time = f" · {d.cook_minutes} min" if d.cook_minutes else ""
    score_str = f"{d.score:.1f}" if d.score is not None else "—"

    used_list = "".join(
        f"<li>{escape(name.replace('_', ' '))}</li>"
        for name in d.ingredients_used
    )
    missing_list = "".join(
        f"<li>{escape(name.replace('_', ' '))}</li>"
        for name in d.ingredients_missing
    )

    used_section = (
        f"<details class='day-ingredients'>"
        f"<summary>{len(d.ingredients_used)} on hand</summary>"
        f"<ul>{used_list}</ul>"
        f"</details>"
    ) if d.ingredients_used else ""
    missing_section = (
        f"<details class='day-missing'>"
        f"<summary>{len(d.ingredients_missing)} to buy</summary>"
        f"<ul>{missing_list}</ul>"
        f"</details>"
    ) if d.ingredients_missing else ""

    return (
        f"<article class='day-card' data-date='{escape(d.date)}' "
        f"data-recipe-id='{escape(d.recipe_id or '')}'>"
        f"<header class='day-header'>"
        f"<span class='day-name'>{escape(_day_name(d.date))}</span>"
        f"<span class='day-date muted'>{escape(d.date)}</span>"
        f"</header>"
        f"<h4 class='day-recipe'>{escape(d.recipe_name)}</h4>"
        f"<p class='day-meta muted'>{cuisine}{cook_time}</p>"
        f"<p class='day-rationale'>{escape(d.rationale)}</p>"
        f"<p class='day-confidence'>"
        f"<span class='confidence-label' style='color:{confidence_color};'>{escape(d.confidence)}</span>"
        f" (score {score_str})"
        f"</p>"
        f"{used_section}{missing_section}"
        f"</article>"
    )


def render_meal_plan_text(plan: list[DayPlan]) -> str:
    """Render the plan as plain text (CLI --human mode)."""
    if not plan:
        return "No meal plan available."
    lines = [f"Your meal plan ({len(plan)} days):", ""]
    for d in plan:
        day = _day_name(d.date)
        if d.recipe_name is None:
            lines.append(f"  {day}, {d.date}: (empty - {d.rationale})")
        else:
            lines.append(
                f"  {day}, {d.date}: {d.recipe_name} ({d.confidence})"
            )
            if d.ingredients_missing:
                missing = ", ".join(d.ingredients_missing[:3])
                lines.append(f"    needs: {missing}")
            if d.ingredients_used:
                used = ", ".join(d.ingredients_used[:3])
                lines.append(f"    on hand: {used}")
    return "\n".join(lines)
