"""Screen function: paste recipe ingredients → shopping list.

The Phase 3 #8 build (photo-of-recipe → shopping list) takes the form
of a *text input* in v1 — the user pastes the ingredients section
of a recipe, the parser (in ``shopstack.services.recipe_text_parser``)
turns it into structured rows, and the screen diffs against the
household's inventory to surface what's missing.

Future: extend the same screen with an image upload that runs the
existing OCR pipeline first and then feeds the OCR text into this same
parser. The screen's input is just text.
"""

from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.app_context import db, tools
from shopstack.repos.inventory import InventoryRepo
from shopstack.services.recipe_text_parser import parse_recipe_text
from shopstack.services.recipes import missing_to_shopping_items
from shopstack.ui.components.primitives import toast
from shopstack.persistence.database import Database as _Database
from shopstack.schemas.models import ShoppingListItem

logger = logging.getLogger(__name__)


def recipe_text_to_shopping_list(raw_text: str) -> str:
    """Parse pasted recipe text and return a shopping-list-ready HTML view.

    Output shows the parsed rows plus a "missing" subset (against current
    inventory). To actually create the list, the user can paste the
    missing list into the shopping-list form, or future work can wire a
    one-click "Add missing to list" button.
    """
    if not raw_text or not raw_text.strip():
        return (
            "<div class='home-card' style='text-align:center;padding:16px;color:var(--text-dim);'>"
            "Paste a recipe's ingredients section. Example:<br>"
            "<code style='font-size: 0.75rem;'>"
            "- 2 cups rice<br>- 1 cup chickpea<br>- 1 tsp turmeric"
            "</code></div>"
        )

    parsed = parse_recipe_text(raw_text)
    if not parsed:
        return toast("Couldn't parse any ingredients from that text.", kind="warning")

    # Build a lookup of what the household has on hand
    inventory_repo = InventoryRepo(db)
    lots = db.get_inventory(user_id=_active_household_id())
    have_map: dict[str, float] = {}
    for lot in lots:
        cname = (lot.canonical_name or "").strip().lower()
        if not cname:
            continue
        have_map[cname] = have_map.get(cname, 0.0) + float(lot.quantity or 0)

    # Build the rows
    rows: list[str] = []
    missing_count = 0
    have_count = 0
    for p in parsed:
        name = escape(p.canonical_name.replace("_", " ").title())
        have = have_map.get(p.canonical_name, 0.0)
        status = "have" if have > 0 else "missing"
        if have > 0:
            have_count += 1
        else:
            missing_count += 1
        status_color = "var(--green)" if status == "have" else "var(--red)"
        status_label = "✓ have" if status == "have" else "✗ need"
        rows.append(
            f"<tr>"
            f"<td style='padding:4px 8px;border-bottom:1px solid var(--border);'>{name}</td>"
            f"<td style='padding:4px 8px;border-bottom:1px solid var(--border);text-align:right;'>{p.quantity:g} {escape(p.unit)}</td>"
            f"<td style='padding:4px 8px;border-bottom:1px solid var(--border);text-align:right;color:{status_color};'>{status_label}</td>"
            f"</tr>"
        )

    return (
        f"<div class='home-card'>"
        f"<h3 style='margin:0 0 8px 0;'>📋 Recipe → Shopping List</h3>"
        f"<div style='font-size: 0.6875rem;color:var(--text-dim);margin-bottom:6px;'>"
        f"Parsed {len(parsed)} ingredient(s). {have_count} at home, "
        f"<strong style='color:var(--red);'>{missing_count} to buy</strong>."
        f"</div>"
        f"<table style='width:100%;font-size: 0.75rem;border-collapse:collapse;'>"
        f"<thead><tr style='border-bottom:2px solid var(--border);'>"
        f"<th style='text-align:left;padding:4px 8px;'>Item</th>"
        f"<th style='text-align:right;padding:4px 8px;'>Qty</th>"
        f"<th style='text-align:right;padding:4px 8px;'>Status</th>"
        f"</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        f"</table>"
        f"</div>"
    )


def _active_household_id() -> str:
    from shopstack.app_context import current_user_id
    return current_user_id()


__all__ = ["recipe_text_to_shopping_list"]
