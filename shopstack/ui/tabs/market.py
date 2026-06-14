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
    shelf_scan_confirm,
    shelf_scan_process,
    shelf_scan_save_trace,
    shelf_scan_skip,
)
from shopstack.ui.components.primitives import (
    busy_js,
    empty_state_enhanced,
    loading_skeleton,
    with_loading_state,
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
        with gr.Tabs():
            with gr.Tab("While Shopping"):
                gr.Markdown("### Check a product before you buy it")
                gr.Markdown("Use a photo, camera, or voice note to compare what you are holding.")
                with gr.Row():
                    image_input = gr.Image(type="filepath", label="Camera / Photo")
                    audio_input = gr.Audio(type="filepath", label="Voice Note")
                with gr.Row():
                    scan_btn = gr.Button("Check and compare", variant="primary", elem_id="market-scan-btn")
                ml_results = gr.HTML(
                    loading_skeleton(variant="card")
                )
                ml_items = gr.Textbox(label="Detected Items", visible=False)
                ml_analysis = gr.Textbox(visible=False)
                ml_last_trace_id = gr.State("")
                ml_barcode_state = gr.State("[]")
                ml_action_result = gr.HTML(
                    empty_state_enhanced(
                        "After you scan, your confirm / skip / save choices will appear here.",
                        icon="🔎",
                    )
                )
                scan_btn.click(
                    market_lens_process,
                    [image_input, audio_input],
                    [ml_results, ml_items, ml_analysis, ml_last_trace_id, ml_barcode_state],
                    js=busy_js("market-scan-btn", original_label="Check and compare"),
                    api_name="market_scan",
                    api_description="Scan image or voice input to classify and compare products",
                ).then(
                    with_loading_state(scan_btn, [])[1],
                    outputs=[scan_btn],
                )
                with gr.Row():
                    ml_confirm_btn = gr.Button("Confirm BUY \u2192 Add to List", variant="primary")
                    ml_skip_btn = gr.Button("Skip Selected")
                    ml_save_btn = gr.Button("Save to History")
                    ml_barcode_add_btn = gr.Button("Add Barcode to Inventory")
                ml_confirm_btn.click(
                    market_lens_confirm_buy,
                    [ml_analysis, ml_last_trace_id],
                    ml_action_result,
                    api_name="market_confirm_buy",
                    api_description="Add confirmed BUY items from Market Lens to current shopping list",
                    js="() => showToast('Adding to list...', 'info')",
                )
                ml_skip_btn.click(
                    market_lens_skip,
                    [ml_analysis, ml_last_trace_id],
                    ml_action_result,
                    api_name="market_skip",
                    api_description="Record skip decision for Market Lens workflow",
                    js="() => showToast('Item skipped', 'info')",
                )
                ml_save_btn.click(
                    market_lens_save_trace,
                    [ml_analysis, ml_last_trace_id],
                    ml_action_result,
                    api_name="market_save_trace",
                    api_description="Save scan results to activity history",
                )
                ml_barcode_add_btn.click(
                    market_lens_barcode_add,
                    ml_barcode_state,
                    ml_action_result,
                    api_name="market_add_barcode",
                    api_description="Add detected barcode items to inventory",
                )

            with gr.Tab("Put Away"):
                gr.Markdown("### Scan a shelf, drawer, cabinet, bag, or box")
                gr.Markdown("Turn what you find at home into household memory.")
                with gr.Row():
                    hs_image_input = gr.Image(type="filepath", label="Shelf / Drawer Photo")
                    hs_audio_input = gr.Audio(type="filepath", label="Voice Correction")
                hs_scene_type = gr.Dropdown(
                    choices=[
                        "auto",
                        "fridge",
                        "pantry",
                        "shopping_bag",
                        "bathroom_cabinet",
                        "medicine_drawer",
                        "cleaning_cupboard",
                        "bedroom",
                        "documents",
                        "utility",
                    ],
                    value="auto",
                    label="Scene Type",
                )
                with gr.Row():
                    hs_scan_btn = gr.Button("Scan home area", variant="primary", elem_id="home-scan-btn")
                hs_results = gr.HTML(
                    loading_skeleton(variant="card")
                )
                hs_state = gr.State("")
                hs_trace_id = gr.State("")
                hs_annotated = gr.Image(type="filepath", label="Annotated Scan", visible=True)
                hs_action_result = gr.HTML(
                    empty_state_enhanced(
                        "After you scan, your confirm / skip / save choices will appear here.",
                        icon="🔎",
                    )
                )
                hs_scan_btn.click(
                    shelf_scan_process,
                    [hs_image_input, hs_audio_input, hs_scene_type],
                    [hs_results, hs_state, hs_trace_id, hs_annotated],
                    js=busy_js("home-scan-btn", original_label="Scan home area"),
                    api_name="home_scan",
                    api_description="Scan a shelf or household scene and return household memory updates",
                ).then(
                    with_loading_state(hs_scan_btn, [])[1],
                    outputs=[hs_scan_btn],
                )
                with gr.Row():
                    hs_confirm_btn = gr.Button("Confirm Updates", variant="primary")
                    hs_skip_btn = gr.Button("Skip Scan")
                    hs_save_btn = gr.Button("Save to History")
                hs_confirm_btn.click(
                    shelf_scan_confirm,
                    [hs_state, hs_trace_id],
                    hs_action_result,
                    api_name="home_scan_confirm",
                    api_description="Apply confirmed home-scan updates to inventory",
                    js="() => showToast('Applying updates...', 'info')",
                )
                hs_skip_btn.click(
                    shelf_scan_skip,
                    [hs_state, hs_trace_id],
                    hs_action_result,
                    api_name="home_scan_skip",
                    api_description="Skip applying the current home scan",
                    js="() => showToast('Scan skipped', 'info')",
                )
                hs_save_btn.click(
                    shelf_scan_save_trace,
                    [hs_state, hs_trace_id],
                    hs_action_result,
                    api_name="home_scan_save_trace",
                    api_description="Save shelf scan results to activity history",
                )
