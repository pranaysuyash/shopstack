"""Recipe Scan tab — paste recipe text or upload a photo to extract ingredients.

Wraps :mod:`shopstack.ui.screens.recipe_text` with Gradio components:
text input, file upload, parse/diff/add-missing buttons.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.services.empty_states import (
    build_household_context,
    render,
)
from shopstack.ui.components.primitives import empty_state_enhanced
from shopstack.ui.screens.recipe_text import (
    recipe_image_to_text,
    recipe_text_add_missing_to_list,
    recipe_text_to_shopping_list,
)
from shopstack.ui.tabs.context import TabContext
from shopstack.services.i18n import load_locale_preference, t
from shopstack.app_context import current_user_id


def _render_mealplan() -> str:
    """Render the weekly meal plan as HTML for the Recipes tab.

    Pass 22 (item 2): the Recipes tab surfaces the meal
    plan built by ``shopstack.services.meal_planning.build_weekly_meal_plan``
    (Pass 21). The plan reuses the existing
    ``find_recipes_for_inventory`` scoring + the
    ``render_meal_plan_html`` adapter (Pass 21).

    Mode-portable: the same ``DayPlan`` data flows through
    the CLI (``python -m shopstack.cli mealplan``), the
    HTTP endpoint (``GET /api/mealplan``), and the Recipes
    tab. This function is the Gradio-specific adapter.
    """
    from shopstack.app_context import db
    from shopstack.services.meal_planning import build_weekly_meal_plan
    from shopstack.ui.renderers.meal_plan import render_meal_plan_html

    uid = current_user_id() or ""
    plan = build_weekly_meal_plan(db, user_id=uid, days=7)
    return render_meal_plan_html(plan)


def build_recipe_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Recipe Scan tab."""
    # Pass 18 §2.5: rich empty-state for the "Paste ingredients or
    # upload a recipe image" placeholder. The previous generic
    # one-liner (line 44 before Pass 18) was a static "no input
    # yet" state. The rich service + i18n keys turn it into a
    # 3-line card with an icon and an example format.
    household_ctx = build_household_context(ctx.db)
    recipe_empty_state = render(
        "recipe.no_input", household=household_ctx
    )
    with gr.Tab(_tab_label("recipe"), id="recipe"):
        gr.Markdown("### Recipe to Shopping List")
        gr.HTML(
            "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
            "Upload a photo of a recipe or paste ingredients. The system "
            "extracts items, compares against your inventory, and shows "
            "what's missing."
            "</div>"
        )

        rc_upload = gr.File(label="Upload recipe image or .txt", file_types=[".png", ".jpg", ".jpeg", ".webp", ".txt"])
        rc_snap = gr.Button(t("button.snap_and_parse", load_locale_preference(current_user_id() or "")), variant="primary")
        rc_ocr_text = gr.Textbox(label="Extracted text", lines=4, placeholder="OCR result will appear here...")
        rc_ocr_status = gr.HTML("")

        gr.Markdown("### Or paste ingredients directly")
        rc_input = gr.Textbox(label="Recipe ingredients", lines=5,
                              placeholder="- 2 cups rice\n- 1 cup chickpea flour\n- 1 tsp turmeric")
        with gr.Row():
            rc_parse = gr.Button("Parse & diff", scale=1)
            rc_add = gr.Button("Add missing to my list", variant="primary", scale=1)
        rc_output = gr.HTML(recipe_empty_state)

        rc_snap.click(recipe_image_to_text, rc_upload, [rc_ocr_text, rc_ocr_status],
                      api_name="recipe_snap",
                      api_description="Extract text from an uploaded recipe image using OCR")
        rc_parse.click(recipe_text_to_shopping_list, rc_input, rc_output,
                       api_name="recipe_parse_diff",
                       api_description="Parse pasted recipe ingredients and compare against current inventory")
        rc_add.click(recipe_text_add_missing_to_list, rc_input, rc_output,
                     api_name="recipe_tab_add_missing",
                     api_description="Add all missing recipe ingredients to the active shopping list")

        # ── 2026-06-15 (Pass 22 item 2): Weekly meal plan section ──
        # The Recipes tab surfaces the meal plan built by
        # ``build_weekly_meal_plan`` (Pass 21). The plan picks
        # a recipe per day, avoiding repeats. No recipe appears
        # twice. The data is mode-portable: same DayPlan schema
        # flows through CLI / HTTP / Recipes tab.
        gr.Markdown("---")
        gr.Markdown("### Your weekly meal plan")
        gr.Markdown(
            "ShopStack suggests a recipe for each day based on "
            "your current pantry. Recipes that use up your "
            "use-soon items are prioritized (waste reduction). "
            "No recipe appears twice in the plan."
        )
        mealplan_html = gr.HTML(value=_render_mealplan())
        mealplan_refresh = gr.Button("Refresh plan", size="sm")
        mealplan_refresh.click(
            _render_mealplan,
            outputs=mealplan_html,
            api_name="recipe_mealplan_refresh",
            api_description="Refresh the weekly meal plan",
        )
        app.load(_render_mealplan, outputs=mealplan_html)
