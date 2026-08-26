"""Renderer for the recurring shopping plan.

**Why this exists (motto_v3 first-principles / mode-portable):**

The recurring shopping plan is a list of ``DecisionResult``
objects (action=buy, with reasons/evidence). The plan is
already renderable via the existing decision-card renderer
(``render_unified_decision_card`` from
``shopstack.ui.components.cards``). The Why? toggle from Pass
19 also works on each card.

This module adds two adapters:

  1. ``render_recurring_plan_html(plan)`` — wraps the plan
     in a header + a list of decision cards. Used by the
     dashboard's recurring card.

  2. ``render_recurring_plan_text(plan)`` — plain-text
     rendering. Used by the CLI's ``--human`` output.

The mode-portability principle (motto_v3 §0) is preserved:
the plan is a list of ``DecisionResult``, the renderer is an
adapter. Any future front-end (mobile, web) reuses the
existing decision-card render path.
"""
from __future__ import annotations

from shopstack.schemas.models import DecisionResult
from shopstack.services.recurring_shopping import summarize_plan


def render_recurring_plan_html(
    plan: list[DecisionResult],
    *,
    include_cards: bool = True,
) -> str:
    """Render the recurring shopping plan as HTML.

    Args:
        plan: A list of ``DecisionResult`` objects (typically
            from ``build_recurring_shopping_plan``).
        include_cards: If True (default), each plan item is
            rendered as a decision card (with the Why? toggle
            from Pass 19). If False, only the header is rendered.

    The output is a single ``<section>`` with a header and
    (optionally) a list of decision cards. XSS-safe via the
    downstream card renderer (``render_unified_decision_card``
    uses ``html.escape``).
    """
    from shopstack.ui.components.cards import render_unified_decision_card

    summary = summarize_plan(plan)
    # Deferred import: cards.py is in shopstack.ui.components,
    # and this file is in shopstack.ui.renderers. Importing
    # cards at module-load time could cycle through
    # shopstack.ui.__init__.
    if not include_cards:
        return (
            f"<section class='recurring-plan' data-count='{len(plan)}'>"
            f"<h3 class='recurring-plan-header'>Your shopping rhythm</h3>"
            f"<p class='recurring-plan-summary'>{summary}</p>"
            f"</section>"
        )

    cards_html = "".join(render_unified_decision_card(d) for d in plan)
    return (
        f"<section class='recurring-plan' data-count='{len(plan)}'>"
        f"<h3 class='recurring-plan-header'>Your shopping rhythm</h3>"
        f"<p class='recurring-plan-summary'>{summary}</p>"
        f"{cards_html}"
        f"</section>"
    )


def render_recurring_plan_text(plan: list[DecisionResult]) -> str:
    """Render the plan as plain text (CLI --human mode)."""
    if not plan:
        return "No items due in your usual rhythm right now. Add more recurring purchases to see predictions."
    lines = [f"Your shopping rhythm ({len(plan)} items due):"]
    for d in plan:
        days_phrase = ""
        for r in d.reasons:
            if "due" in r:
                days_phrase = r
                break
        if not days_phrase:
            days_phrase = "due in your rhythm"
        # Convert 0.7 → "70%" for the console-friendly output.
        conf_pct = int(round(d.confidence * 100))
        lines.append(f"  - {d.display_name} ({conf_pct}% confidence) {days_phrase}")
    return "\n".join(lines)
