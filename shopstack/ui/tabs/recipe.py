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
        rc_snap = gr.Button("Snap & parse recipe", variant="primary")
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
