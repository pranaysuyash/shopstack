"""Memory tab — Nutrition sub-builder.

Extracted from ``build_memory_tab`` so the nutrition lookup, kitchen
nutrition aggregate, and weekly nutrition coach (Phase 8 #17) are
independently testable and reusable.
"""
from __future__ import annotations

import gradio as gr

from shopstack.ui.components.primitives import (
    empty_state_enhanced,
    loading_skeleton,
)
from shopstack.ui.screens.nutrition import (
    nutrition_kitchen_view,
    nutrition_lookup_view,
)
from shopstack.ui.tabs.context import TabContext


def _coach_screen(household_size: int, dietary: str) -> str:
    """Closure for the Nutrition Coach screen.

    Defined at module scope (not inline in the sub-builder) so the
    sub-builder function stays short and the helper can be unit-tested
    in isolation. The actual logic lives in
    ``shopstack.ui.screens.nutrition_coach``.
    """
    from shopstack.ui.screens.nutrition_coach import nutrition_coach_screen
    try:
        return nutrition_coach_screen(
            household_size=int(household_size or 4),
            dietary=str(dietary or "vegetarian"),
        )
    except Exception as exc:
        return f"<div>Coach unavailable: {exc}</div>"


def build_memory_nutrition(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Nutrition sub-tab inside the Memory tab.

    Three sections:
    1. **Nutrition lookup** — search box + Look up button + result HTML.
    2. **My kitchen nutrition** — aggregate view + refresh button.
    3. **Nutrition coaching** (Phase 8 #17) — household size slider +
       dietary dropdown + refresh; renders a weekly 7-nutrient tracker
       with 🟢/🟡/🔴 status.

    Args:
        app: The root gr.Blocks instance — needed for ``app.load(...)``.
        ctx: Shared dependencies (unused in this sub-tab, kept for
            uniform signature).

    Returns:
        None. No cross-sub-tab references.
    """
    # ── Nutrition lookup ──
    gr.Markdown("### Nutrition lookup")
    nutrition_search = gr.Textbox(
        label="Search Item",
        placeholder="e.g. milk, atta, rice, chicken, doodh, dal…",
    )
    nutrition_search_btn = gr.Button("Look up")
    nutrition_result = gr.HTML(
        empty_state_enhanced(
            "Type an item and click Look up to see nutrition facts.",
            icon="🥗",
        )
    )
    nutrition_search_btn.click(
        nutrition_lookup_view,
        nutrition_search,
        nutrition_result,
        api_name="nutrition_lookup",
        api_description="Lookup nutrition for searched item",
    )
    nutrition_search.submit(
        nutrition_lookup_view,
        nutrition_search,
        nutrition_result,
        api_name="nutrition_lookup_submit",
        api_description="Lookup nutrition for submitted text",
    )

    # ── My kitchen nutrition ──
    gr.Markdown("### My kitchen nutrition")
    kitchen_nutrition = gr.HTML(loading_skeleton("card"))
    kitchen_refresh = gr.Button("Refresh Kitchen Nutrition", elem_classes="secondary")
    kitchen_refresh.click(
        nutrition_kitchen_view,
        outputs=kitchen_nutrition,
        api_name="nutrition_kitchen_refresh",
        api_description="Refresh kitchen nutrition aggregate view",
    )
    app.load(nutrition_kitchen_view, outputs=kitchen_nutrition)

    # ── Nutrition coaching (Phase 8 #17) ──
    gr.Markdown("---")
    gr.Markdown("### 🥗 Nutrition coaching")
    gr.Markdown(
        "Weekly household-target tracking across 7 key nutrients. "
        "🟢 = on track, 🟡 = boost, 🔴 = gaps to fill."
    )
    with gr.Row():
        coach_household_size = gr.Slider(
            label="Household size",
            minimum=1, maximum=12, step=1, value=4,
        )
        coach_dietary = gr.Dropdown(
            label="Dietary",
            choices=[("Vegetarian", "vegetarian"),
                     ("Vegan", "vegan"),
                     ("Omnivore", "omnivore")],
            value="vegetarian",
        )
        coach_refresh = gr.Button("Refresh", elem_classes="secondary")
    coach_html = gr.HTML(loading_skeleton("card"))
    coach_refresh.click(
        _coach_screen,
        [coach_household_size, coach_dietary],
        coach_html,
        api_name="memory_nutrition_coach_refresh",
        api_description="Refresh nutrition coaching for the active household",
    )
    app.load(
        _coach_screen, [coach_household_size, coach_dietary], coach_html,
    )
