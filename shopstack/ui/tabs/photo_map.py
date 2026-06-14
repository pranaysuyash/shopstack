"""Photo Map tab — photo-anchored household location map.

Wraps :mod:`shopstack.ui.screens.photo_map` with Gradio components:
photo grid view, attach-photo form, clear-photo action, and
find-by-photo upload.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import empty_state_enhanced
from shopstack.ui.screens.photo_map import (
    attach_photo_to_location,
    clear_location_photo,
    find_location_by_photo,
    photo_map_view,
)
from shopstack.ui.tabs.context import TabContext


def build_photo_map_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Photo Map tab."""
    with gr.Tab(_tab_label("photo_map"), id="photo_map"):
        gr.Markdown("### Photo-Anchored Map")
        pm_map = gr.HTML(empty_state_enhanced("Loading map...", icon="\U0001f5fa"))

        gr.Markdown("### Attach photo to a location")
        with gr.Row():
            pm_loc = gr.Textbox(label="Location ID", placeholder="e.g. pantry, fridge_top", scale=2)
            pm_image = gr.Image(label="Photo", type="filepath", scale=2)
            pm_attach = gr.Button("Attach", scale=0)
        pm_attach_result = gr.HTML("")

        gr.Markdown("### Find location by photo")
        with gr.Row():
            pm_search_image = gr.Image(label="Upload a photo to find", type="filepath", scale=2)
            pm_search_btn = gr.Button("Find similar", scale=0)
        pm_search_result = gr.HTML("")

        app.load(photo_map_view, outputs=pm_map)
        pm_attach.click(
            attach_photo_to_location,
            [pm_loc, pm_image],
            pm_attach_result,
            api_name="photo_map_attach",
            api_description="Attach a photo to a household location",
        )
        pm_search_btn.click(
            find_location_by_photo,
            pm_search_image,
            pm_search_result,
            api_name="photo_map_find",
            api_description="Find similar locations by photo",
        )
