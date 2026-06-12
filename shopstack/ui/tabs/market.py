"""Market Lens tab — scan items via camera/photo/voice, compare to inventory.

The "ShopLens" module in the product architecture. Single-screen tab that:
- Accepts a camera/photo image and/or a voice note
- Runs object detection + OCR + speech recognition
- Compares detected items to household inventory
- Records trace, confirm-buy/skip/save actions

All `app.load` handlers (none in this tab) and event handlers register
here. No cross-tab references.
"""
from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.screens import (
    market_lens_barcode_add,
    market_lens_confirm_buy,
    market_lens_process,
    market_lens_save_trace,
    market_lens_skip,
)
from shopstack.ui.tabs.context import TabContext


def build_market_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Market Lens tab inside the parent's `gr.Tabs` context.

    Args:
        blocks: Alias for the parent gr.Blocks. Kept for symmetry with other
            tab builders.
        app: The root gr.Blocks instance — needed for `app.load(...)` handlers.
        ctx: Shared dependencies (unused in this tab, but part of the
            uniform builder signature).

    Returns:
        None. The Market Lens tab is self-contained.
    """
    with gr.Tab(_tab_label("market"), id="market"):
        gr.Markdown("### Point your camera or upload a photo \u2014 or speak what you see")
        with gr.Row():
            image_input = gr.Image(type="filepath", label="Camera / Photo")
            audio_input = gr.Audio(type="filepath", label="Voice Note")
        with gr.Row():
            scan_btn = gr.Button("Scan & Compare to Inventory", variant="primary")
        ml_results = gr.HTML("")
        ml_items = gr.Textbox(label="Detected Items", visible=False)
        ml_analysis = gr.Textbox(visible=False)
        ml_last_trace_id = gr.State("")
        ml_barcode_state = gr.State("[]")
        ml_action_result = gr.HTML("")
        scan_btn.click(
            market_lens_process,
            [image_input, audio_input],
            [ml_results, ml_items, ml_analysis, ml_last_trace_id, ml_barcode_state],
            api_name="market_scan",
            api_description="Scan image or voice input to classify and compare products",
        )
        with gr.Row():
            ml_confirm_btn = gr.Button("Confirm BUY \u2192 Add to List", variant="primary")
            ml_skip_btn = gr.Button("Skip Selected")
            ml_save_btn = gr.Button("Save Trace")
            ml_barcode_add_btn = gr.Button("Add Barcode to Inventory")
        ml_confirm_btn.click(
            market_lens_confirm_buy,
            [ml_analysis, ml_last_trace_id],
            ml_action_result,
            api_name="market_confirm_buy",
            api_description="Add confirmed BUY items from Market Lens to current shopping list",
        )
        ml_skip_btn.click(
            market_lens_skip,
            [ml_analysis, ml_last_trace_id],
            ml_action_result,
            api_name="market_skip",
            api_description="Record skip decision for Market Lens workflow",
        )
        ml_save_btn.click(
            market_lens_save_trace,
            [ml_analysis, ml_last_trace_id],
            ml_action_result,
            api_name="market_save_trace",
            api_description="Save Market Lens trace output",
        )
        ml_barcode_add_btn.click(
            market_lens_barcode_add,
            ml_barcode_state,
            ml_action_result,
            api_name="market_add_barcode",
            api_description="Add detected barcode items to inventory",
        )
