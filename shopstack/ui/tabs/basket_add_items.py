"""Basket tab — Add Items sub-tab sub-builder.

The Add Items sub-tab has two inner sub-tabs:

1. **Receipt** — OCR-based receipt scanning. The user uploads
   a receipt image (or .txt file) and clicks *Scan & Parse*.
   The system extracts text via the OCR pipeline, parses it
   into line items, and renders an editable ``gr.Dataframe``
   the user can review before clicking *Confirm & Add to
   Inventory*. The receipt service
   (``shopstack.services.receipt``) handles the file upload,
   OCR, parsing, and confirmation.
2. **From Recipe** — Recipe text → shopping list. The user
   pastes a recipe's ingredients section, clicks *Parse &
   Diff*, and the system shows which ingredients are missing
   from inventory. *Add missing to my list* pushes the missing
   ingredients into the active shopping list in one click.

Extracted from ``shopstack.ui.tabs.basket`` in Pass 8 so each
basket sub-tab lives in its own module (mirrors the
``memory_*`` sub-builder pattern).

**Pattern:** the sub-builder opens its own
``gr.Tab("Add Items")`` inside the parent's ``gr.Tabs()`` context
and a nested ``gr.Tabs()`` for the 2 inner sub-tabs. Adds the
UI and wires the event handlers. The function returns ``None``
(no cross-tab references exist).
"""
from __future__ import annotations

import gradio as gr

from shopstack.ui.components.primitives import (
    empty_state_enhanced,
    loading_skeleton,
    with_loading_state,
)
from shopstack.ui.components.js_helpers import busy_js
from shopstack.ui.screens import (
    recipe_text_add_missing_to_list,
    recipe_text_to_shopping_list,
    recipe_image_to_text,
)
from shopstack.ui.screens.receipt import (
    _load_ocr_model,
    receipt_confirm,
    receipt_export_txt,
    receipt_parse_text,
    receipt_scan_ocr,
)
from shopstack.ui.tabs.context import TabContext


def build_basket_add_items(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Add Items sub-tab inside the parent's ``gr.Tabs()`` context.

    Opens a ``gr.Tab("Add Items")`` with a nested ``gr.Tabs()``
    containing the 2 inner sub-tabs (Receipt, From Recipe).
    Adds the UI and wires the event handlers. The OCR model
    is loaded on page load via ``app.load(_load_ocr_model, ...)``
    so the first scan doesn't pay the model-load cost.

    Args:
        app: The root ``gr.Blocks`` instance — needed for
            ``app.load(_load_ocr_model, ...)`` (preload OCR model
            on first page render).
        ctx: Shared dependencies (unused in this sub-tab, kept
            for the uniform builder signature).

    Returns:
        None. The Add Items sub-tab is self-contained: no
        components are referenced by other parts of the app.
    """
    with gr.Tab("Add Items"):
        with gr.Tabs():
            # ── Receipt scanning ──
            with gr.Tab("Receipt"):
                receipt_status = gr.HTML(loading_skeleton("text"))
                gr.Markdown("### Scan a receipt")
                gr.Markdown(
                    "Upload a receipt image (OCR) or a text file containing the receipt text."
                )
                with gr.Row():
                    receipt_file = gr.File(
                        label="Upload Receipt (image or .txt)",
                        file_count="single",
                    )
                    receipt_scan_btn = gr.Button(
                        "Scan & Parse", variant="primary", elem_id="receipt-scan-btn"
                    )
                receipt_raw_text = gr.Textbox(
                    label="Raw OCR Text / Paste Receipt Text",
                    lines=6,
                    placeholder=(
                        "Paste receipt text here, or upload a file above "
                        "and click Scan & Parse..."
                    ),
                )

                receipt_df = gr.Dataframe(
                    headers=["Item", "Quantity", "Unit", "Price"],
                    datatype=["str", "number", "str", "number"],
                    column_count=4,
                    interactive=True,
                    label="Editable Receipt Draft",
                )
                with gr.Row():
                    receipt_merchant = gr.Textbox(
                        label="Store Name", interactive=True
                    )
                    receipt_date = gr.Textbox(
                        label="Purchase Date (YYYY-MM-DD)", interactive=True
                    )

                with gr.Row():
                    receipt_confirm_btn = gr.Button(
                        "Confirm & Add to Inventory", variant="primary"
                    )
                    receipt_export_btn = gr.Button(
                        "💾 Save as .txt", elem_id="receipt-export-btn"
                    )
                receipt_export_out = gr.Textbox(
                    label="Receipt .txt (copy or paste into a notes app)",
                    lines=10,
                    interactive=False,
                    visible=False,
                )
                receipt_result = gr.HTML(
                    empty_state_enhanced(
                        "Receipt confirmation will appear here.",
                        icon="✅",
                    )
                )
                receipt_scan_btn.click(
                    receipt_scan_ocr,
                    receipt_file,
                    [
                        receipt_df, receipt_merchant, receipt_date,
                        receipt_raw_text, receipt_status,
                    ],
                    js=busy_js("receipt-scan-btn", original_label="Scan & Parse"),
                    api_name="receipt_scan",
                    api_description="Extract receipt text from uploaded file",
                ).then(
                    with_loading_state(receipt_scan_btn, [receipt_df])[1],
                    outputs=[receipt_scan_btn, receipt_df],
                )
                receipt_raw_text.change(
                    receipt_parse_text,
                    receipt_raw_text,
                    [receipt_df, receipt_merchant, receipt_date],
                    api_name="receipt_parse",
                    api_description=(
                        "Parse pasted or OCR'd receipt text into item suggestions"
                    ),
                )
                receipt_confirm_btn.click(
                    receipt_confirm,
                    [receipt_df, receipt_merchant, receipt_date, receipt_raw_text],
                    receipt_result,
                    api_name="receipt_confirm",
                    api_description=(
                        "Confirm parsed receipt lines and add items to inventory"
                    ),
                    js="() => showToast('Adding receipt items to inventory...', 'info')",
                )
                # "Save as .txt" button: renders the receipt as a
                # plain-text snippet the user can copy or paste
                # into a notes app / WhatsApp / email. The textbox
                # is hidden by default and shown on click so the
                # receipt sub-tab doesn't get cluttered.
                def _show_export(text: str) -> tuple[str, gr.update]:
                    return text, gr.update(visible=True)
                receipt_export_btn.click(
                    receipt_export_txt,
                    [receipt_merchant, receipt_date, receipt_raw_text],
                    receipt_export_out,
                    api_name="receipt_export_txt",
                    api_description=(
                        "Render the most-recently-confirmed receipt "
                        "as a plain-text snippet for sharing/audit."
                    ),
                ).then(
                    _show_export,
                    receipt_export_out,
                    [receipt_export_out, receipt_export_out],
                )
                app.load(_load_ocr_model, outputs=receipt_status)

            # ── Recipe to shopping list ──
            with gr.Tab("From Recipe"):
                gr.Markdown("### Recipe to shopping list")
                gr.Markdown(
                    "Either **snap a photo** of a recipe (or upload a .txt), "
                    "or **paste the ingredients** section. The system parses the "
                    "text, diffs against your inventory, and shows what's missing. "
                    "Use **Add missing to my list** to push the missing items into "
                    "your active shopping list in one click."
                )
                # v2 (added 2026-06-13): photo / .txt upload that runs
                # through the OCR pipeline and pre-fills recipe_input.
                with gr.Row():
                    recipe_file = gr.File(
                        label="Upload recipe image or .txt",
                        file_count="single",
                        file_types=[
                            "image",
                            ".txt",
                            ".csv",
                            ".md",
                        ],
                    )
                    recipe_ocr_btn = gr.Button(
                        "Snap & parse recipe",
                        variant="primary",
                        elem_id="recipe-ocr-btn",
                    )
                recipe_input = gr.Textbox(
                    label="Recipe ingredients",
                    placeholder=(
                        "- 2 cups rice\n"
                        "- 1 cup chickpea\n"
                        "- 1 tsp turmeric\n"
                        "- 1 onion, chopped\n"
                        "- 2 tomatoes, pureed\n"
                        "- Salt to taste"
                    ),
                    lines=10,
                )
                with gr.Row():
                    recipe_btn = gr.Button(
                        "Parse & Diff", variant="primary", elem_id="recipe-parse-btn"
                    )
                    recipe_add_btn = gr.Button(
                        "Add missing to my list", elem_id="recipe-add-btn"
                    )
                recipe_result = gr.HTML(
                    empty_state_enhanced(
                        "Recipe diff will appear here.",
                        icon="🍳",
                    )
                )
                recipe_status = gr.HTML("")
                recipe_btn.click(
                    recipe_text_to_shopping_list,
                    recipe_input,
                    recipe_result,
                    js=busy_js("recipe-parse-btn", original_label="Parse & Diff"),
                    api_name="recipe_to_list",
                    api_description=(
                        "Parse pasted recipe text and diff against inventory"
                    ),
                ).then(
                    with_loading_state(recipe_btn, [recipe_result])[1],
                    outputs=[recipe_btn, recipe_result],
                )
                recipe_add_btn.click(
                    recipe_text_add_missing_to_list,
                    recipe_input,
                    recipe_status,
                    api_name="recipe_add_missing",
                    api_description=(
                        "Add the missing ingredients from the parsed recipe "
                        "into the active shopping list"
                    ),
                )
                # v2 (added 2026-06-13): snap a recipe photo and pre-fill
                # the textbox via the OCR pipeline. The user can then click
                # Parse & Diff / Add missing to my list without re-pasting.
                recipe_ocr_btn.click(
                    recipe_image_to_text,
                    recipe_file,
                    [recipe_input, recipe_status],
                    js=busy_js(
                        "recipe-ocr-btn", original_label="Snap & parse recipe"
                    ),
                    api_name="recipe_image_to_text",
                    api_description=(
                        "Extract recipe text from an uploaded image (OCR) or "
                        ".txt file. Pre-fills the recipe textbox."
                    ),
                ).then(
                    with_loading_state(recipe_ocr_btn, [recipe_status])[1],
                    outputs=[recipe_ocr_btn, recipe_status],
                )
