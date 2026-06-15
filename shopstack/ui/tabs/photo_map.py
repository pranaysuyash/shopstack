"""Photo Map tab — photo-anchored household location map.

Wraps :mod:`shopstack.ui.screens.photo_map` with Gradio components:
photo grid view, attach-photo form, clear-photo action (with 2-step
confirm pattern per §0.10 observability + §0.14 operator workflow),
and find-by-photo upload.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import (
    confirm_dialog,
    confirm_hide_updates,
    confirm_toggle_updates,
    empty_state_enhanced,
)
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

        gr.Markdown("### Clear photo from a location")
        gr.Markdown(
            "Type a location id (e.g. `pantry`, `fridge_top`) and click **Clear photo**. "
            "This is destructive — the photo is removed from storage. "
            "The 2-step confirm pattern below prevents accidental clicks."
        )
        with gr.Row():
            pm_clear_loc = gr.Textbox(
                label="Location ID to clear", placeholder="e.g. pantry", scale=3
            )
            pm_clear_btn = gr.Button("Clear photo", elem_classes="secondary", scale=0)
        with gr.Group(visible=False) as pm_clear_confirm_group:
            gr.HTML(
                confirm_dialog(
                    "Remove the photo from this location? This is hard to undo.",
                    confirm_label="Yes, Clear",
                    variant="danger",
                )
            )
            with gr.Row():
                pm_clear_yes_btn = gr.Button(
                    "Yes, Clear", variant="stop", scale=0
                )
                pm_clear_no_btn = gr.Button("Cancel", elem_classes="secondary", scale=0)
        pm_clear_result = gr.HTML("")

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
        # 2-step clear photo: first click shows confirm, second click fires
        pm_clear_btn.click(
            confirm_toggle_updates,
            None,
            [pm_clear_btn, pm_clear_confirm_group],
        )
        pm_clear_yes_btn.click(
            clear_location_photo,
            pm_clear_loc,
            pm_clear_result,
        ).then(
            confirm_hide_updates,
            None,
            [pm_clear_btn, pm_clear_confirm_group],
        )
        pm_clear_no_btn.click(
            confirm_hide_updates,
            None,
            [pm_clear_btn, pm_clear_confirm_group],
        )
        pm_search_btn.click(
            find_location_by_photo,
            pm_search_image,
            pm_search_result,
            api_name="photo_map_find",
            api_description="Find similar locations by photo",
        )
