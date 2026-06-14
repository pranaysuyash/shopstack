"""Restock next 7 days card — Phase 10 (focused new surface).

Pulls the household's restock predictions (already
computed by the dashboard service) and renders them as a
compact card on the Today tab. Each card has a "Add to my
list" button that turns a forecast into an action.

**Why a separate module:**

The dashboard service produces the *state*; this module
produces a *card view* with one-tap actions. Keeping them
separate means the restock card can be wired (or removed)
independently of the rest of the dashboard.

**Inputs:**

- ``dashboard_state.restock_predictions`` (a list of dicts
  with canonical_name, urgency, typical_qty, days_until, etc.).
- The household id (for the add-to-list action).

**Outputs:**

- XSS-safe HTML card with a list of restock predictions and
  a button to add each to the active shopping list.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.app_context import current_user_id, db
from shopstack.services.dashboard import build_dashboard_state
from shopstack.services.restock_action import add_prediction_to_list
from shopstack.ui.components.primitives import toast

logger = logging.getLogger(__name__)


def _urgency_color(days: float | int | None) -> str:
    if days is None:
        return "var(--text-dim, #6F6254)"
    if days <= 1:
        return "var(--red, #A63F31)"
    if days <= 3:
        return "var(--amber, #A76012)"
    return "var(--text-muted, #5F5144)"


def render_restock_card_html(predictions: list[dict[str, Any]]) -> str:
    """Render the restock card as XSS-safe HTML.

    Sorted by days_until_restock (soonest first). Top 8
    predictions are shown; the rest collapse into a
    "more..." summary.
    """
    if not predictions:
        return (
            "<div class='restock-card restock-empty'>"
            "🛒 No restock predictions yet. Add a few purchases to seed the engine."
            "</div>"
        )
    # Sort: soonest first, None last
    sorted_preds = sorted(
        predictions,
        key=lambda p: (
            p.get("days_until_restock") is None,
            p.get("days_until_restock") if isinstance(p.get("days_until_restock"), (int, float)) else 999,
            p.get("canonical_name", ""),
        ),
    )
    top = sorted_preds[:8]
    more = len(sorted_preds) - len(top)

    rows: list[str] = []
    for p in top:
        cname = str(p.get("canonical_name") or "")
        if not cname:
            continue
        display = cname.replace("_", " ").title()
        days = p.get("days_until_restock")
        days_str = (
            f"{int(days)}d" if isinstance(days, (int, float)) else "—"
        )
        qty = p.get("typical_qty") or 1
        unit = p.get("typical_unit") or "unit"
        color = _urgency_color(days if isinstance(days, (int, float)) else None)
        urgency = str(p.get("urgency", "due_soon"))
        rows.append(
            "<div class='restock-row' style='border-left:3px solid "
            f"{color};'>"
            f"<div class='restock-name'>{escape(display)}</div>"
            f"<div class='restock-meta'>"
            f"<span class='restock-days' style='color:{color};'>{days_str}</span>"
            f" · {qty:g} {escape(unit)} · {escape(urgency)}"
            "</div>"
            "</div>"
        )
    if more > 0:
        rows.append(
            f"<div class='restock-more'>+{more} more</div>"
        )
    return (
        "<div class='restock-card'>"
        "<div class='restock-card-head'>"
        "<span class='restock-card-title'>📦 Restock next 7 days</span>"
        f"<span class='restock-card-count'>{len(sorted_preds)} item(s)</span>"
        "</div>"
        + "".join(rows)
        + "</div>"
    )


def restock_card_screen(limit: int = 8) -> str:
    """Top-level screen wrapper that pulls the dashboard state and renders the card."""
    try:
        user_id = current_user_id() or ""
        state = build_dashboard_state(db, [], user_id=user_id)
        return render_restock_card_html(state.restock_predictions or [])
    except Exception as exc:
        logger.warning("restock_card_screen failed: %s", exc)
        return ""


def add_restock_to_list(canonical_name: str) -> str:
    """Add a single restock prediction to the active shopping list. Returns a toast."""
    try:
        user_id = current_user_id() or ""
        state = build_dashboard_state(db, [], user_id=user_id)
        match = next(
            (p for p in (state.restock_predictions or [])
             if p.get("canonical_name") == canonical_name),
            None,
        )
        if not match:
            return toast(f"Could not find prediction for {canonical_name}.", kind="error")
        result = add_prediction_to_list(db, match)
        if not result.get("added"):
            return toast(result.get("reason", "Failed to add to list."), kind="error")
        return toast(result.get("reason", "Added to shopping list."), kind="success")
    except Exception as exc:
        logger.warning("add_restock_to_list failed: %s", exc)
        return toast(f"Failed: {exc}", kind="error")


__all__ = [
    "add_restock_to_list",
    "render_restock_card_html",
    "restock_card_screen",
]
