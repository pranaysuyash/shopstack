"""Shelf Scan tab — scan pantry/shelf with camera, audio, or image.

Thin tab builder wrapping :mod:`shopstack.ui.screens.shelf_scan` with
Gradio components: image upload, video upload, audio upload, scene-type
dropdown, scan/confirm/skip/save buttons, and a results display.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import empty_state_enhanced, loading_skeleton
from shopstack.ui.screens.shelf_scan import (
    shelf_scan_confirm,
    shelf_scan_process,
    shelf_scan_skip,
    shelf_scan_save_trace,
)
from shopstack.ui.tabs.context import TabContext


def build_scanner_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Shelf Scan tab.

    Args:
        blocks: Alias for the parent gr.Blocks.
        app: The root gr.Blocks instance for ``app.load(...)`` handlers.
        ctx: Shared dependencies (unused, part of uniform builder signature).
    """
    with gr.Tab(_tab_label("scanner"), id="scanner"):
        gr.Markdown("### Shelf / Pantry Scan")
        gr.HTML(
            "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
            "Capture a photo, video, or voice note of your shelf. The system "
            "detects visible items, compares against inventory, and proposes"
            " actions (add, update quantity, mark use-soon, move location)."
            "</div>"
        )
        with gr.Row():
            ss_image = gr.Image(
                label="Photo of shelf",
                type="filepath",
                scale=2,
            )
            ss_video = gr.Video(
                label="Video of shelf",
                scale=2,
            )
        with gr.Row():
            ss_audio = gr.Audio(
                label="Voice note (optional)",
                type="filepath",
                scale=2,
            )
            ss_scene = gr.Dropdown(
                label="Image type",
                choices=["auto", "pantry", "fridge", "freezer", "spice_rack", "medicine"],
                value="auto",
                scale=1,
            )
        ss_scan_btn = gr.Button("Scan", variant="primary")
        ss_state = gr.Textbox(visible=False, label="Scan State")
        ss_trace = gr.Textbox(visible=False, label="Internal ref")
        ss_annotated = gr.Image(
            label="Annotated image",
            type="filepath",
            visible=True,
        )
        ss_results = gr.HTML(
            empty_state_enhanced(
                "Upload a photo or video of your shelf and click Scan.",
                icon="\U0001f50d",
            )
        )
        with gr.Row():
            ss_confirm = gr.Button("Confirm & apply", variant="primary", scale=1)
            ss_save = gr.Button("Save to history", scale=1)
            ss_skip = gr.Button("Skip", scale=1)

        ss_scan_btn.click(
            shelf_scan_process,
            [ss_image, ss_video, ss_audio, ss_scene],
            [ss_results, ss_state, ss_trace, ss_annotated],
            api_name="shelf_scan",
            api_description="Scan a shelf or pantry scene",
        )
        ss_confirm.click(
            shelf_scan_confirm,
            [ss_state, ss_trace],
            ss_results,
            api_name="shelf_scan_confirm",
            api_description="Confirm and apply shelf scan updates",
        )
        ss_skip.click(
            shelf_scan_skip,
            [ss_state, ss_trace],
            ss_results,
            api_name="shelf_scan_skip",
            api_description="Skip shelf scan without applying",
        )
        ss_save.click(
            shelf_scan_save_trace,
            [ss_state, ss_trace],
            ss_results,
            api_name="shelf_scan_save",
            api_description="Save shelf scan to activity history",
        )
