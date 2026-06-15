"""Workflow UI utilities — steps, headers, title bars.

These are shared between the composition layer (app.py) and screen modules.
Extracted here to break the circular import between components and screens._utils.

Canonical home for WORKFLOW_STEPS, WORKFLOW_ACTION_STEPS, workflow_header(),
and workflow_title_bar(). shopstack.ui.screens._utils re-exports these
(motto_v3 §7 supersession — see Docs/REMAINING_WORK.md) rather than
redefining them.
"""

from __future__ import annotations

from html import escape

from shopstack.ui.components.primitives import home_card

WORKFLOW_STEPS: tuple[str, ...] = (
    "Input",
    "Perception/Parsing",
    "Inventory Context",
    "Decision",
    "Proposed Actions",
    "Human Confirmation",
    "Saved Trace",
)

WORKFLOW_ACTION_STEPS: tuple[str, ...] = (
    "Input",
    "Perception",
    "Inventory Context",
    "Decision",
    "Proposed Actions",
    "Human Confirmation",
    "Saved Trace",
)


def workflow_header(steps: tuple[str, ...], current_step: int | None = None) -> str:
    """Render the workflow step rail as an HTML snippet.

    Delegates to the shared render_workflow_rail component.
    Import is deferred to avoid circular dependencies at module level.
    """
    from shopstack.ui.components.cards import render_workflow_rail

    return render_workflow_rail(list(steps), current_step=current_step)


def workflow_title_bar(title: str, subtitle: str = "") -> str:
    """Render a simple title + subtitle bar as an HTML snippet."""
    return home_card(
        style="margin-bottom:10px;",
        body=(
            f"<h2>{escape(title)}</h2>"
            + (f"<div style='color:var(--text-dim);'>{escape(subtitle)}</div>" if subtitle else "")
        ),
    )
