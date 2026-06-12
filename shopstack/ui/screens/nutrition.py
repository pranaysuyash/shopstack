from __future__ import annotations


from shopstack.app_context import db, current_user_id
from shopstack.services.nutrition import (
    format_nutrition_html,
    get_inventory_nutrition_summary,
    lookup_nutrition_html,
)
from shopstack.ui.screens._utils import safe_render


@safe_render
def nutrition_lookup_view(query: str) -> str:
    return lookup_nutrition_html(query)


@safe_render
def nutrition_kitchen_view() -> str:
    summary = get_inventory_nutrition_summary(db, user_id=current_user_id())
    return format_nutrition_html(summary)
