"""Find / Object Trail tab — search for items and see their movement history.

Wraps :mod:`shopstack.ui.screens.find_trail` with Gradio components:
search input, results view, negative-memory action, person association.
"""

from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.components.primitives import empty_state_enhanced
from shopstack.ui.screens.find_trail import (
    add_negative_memory,
    add_person_association,
    find_trail_view,
)
from shopstack.ui.tabs.context import TabContext


def build_find_trail_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Find / Object Trail tab."""
    with gr.Tab(_tab_label("find_trail"), id="find_trail"):
        gr.Markdown("### Find an item")
        gr.HTML(
            "<div style='font-size:0.75rem;color:var(--text-dim);margin-bottom:8px;'>"
            "Search by item name, and see where it is, where it has been, "
            "and where to look next."
            "</div>"
        )
        with gr.Row():
            ft_query = gr.Textbox(
                label="Search", placeholder="e.g. passport, milk, charger", scale=3
            )
            ft_search = gr.Button("Search", scale=0)
        ft_result = gr.HTML(empty_state_enhanced(
            "Enter an item name to see its trail.", icon="\U0001f50d"
        ))

        gr.Markdown("---")
        gr.Markdown("### Actions")
        with gr.Row():
            ft_neg_lot = gr.Textbox(label="Batch", placeholder="batch ID or prefix", scale=2)
            ft_neg_loc = gr.Textbox(label="Location", placeholder="location_id", scale=2)
            ft_neg_btn = gr.Button("Mark NOT here", scale=0)
        ft_neg_result = gr.HTML("")
        with gr.Row():
            ft_person_lot = gr.Textbox(label="Batch", placeholder="batch ID or prefix", scale=2)
            ft_person_name = gr.Textbox(label="Person name", placeholder="e.g. Ravi", scale=2)
            ft_person_rel = gr.Dropdown(
                label="Relationship",
                choices=["owner", "shared", "guest"],
                value="owner",
                scale=1,
            )
            ft_person_btn = gr.Button("Assign person", scale=0)
        ft_person_result = gr.HTML("")

        ft_search.click(find_trail_view, ft_query, ft_result,
                        api_name="find_trail_search",
                        api_description="Search for an item and display its object trail (locations, movement history, search plan)")
        ft_neg_btn.click(add_negative_memory, [ft_neg_lot, ft_neg_loc], ft_neg_result,
                         api_name="add_negative_memory",
                         api_description="Mark a location where an item is NOT, creating a negative memory to exclude it from future searches")
        ft_person_btn.click(add_person_association, [ft_person_lot, ft_person_name, ft_person_rel],
                           ft_person_result, api_name="add_person_association",
                           api_description="Associate a person with an inventory lot (owner, shared, or guest relationship)")
