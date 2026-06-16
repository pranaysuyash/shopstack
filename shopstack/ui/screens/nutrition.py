from __future__ import annotations


from shopstack.app_context import db, current_user_id
from shopstack.services.nutrition import (
    format_nutrition_html,
    get_inventory_nutrition_summary,
    lookup_nutrition_html,
)
from shopstack.ui.errors import safe_render_html


def nutrition_lookup_view(query: str) -> str:
    return safe_render_html(
        lambda: lookup_nutrition_html(query),
        user_message="Couldn't load nutrition lookup",
        help_tab="today",
    )


def nutrition_kitchen_view() -> str:
    return safe_render_html(
        lambda: format_nutrition_html(
            get_inventory_nutrition_summary(db, user_id=current_user_id())
        ),
        user_message="Couldn't load kitchen nutrition summary",
        help_tab="nutrition",
    )
