"""Memory tab — What Happened (Trace History) sub-builder.

Extracted from ``build_memory_tab`` so the activity-records browser
(search by goal/type, select a record, see timeline, export redacted
JSONL) is independently testable and reusable.
"""
from __future__ import annotations

import gradio as gr

from shopstack.ui.components.primitives import empty_state_enhanced
from shopstack.ui.screens import (
    agent_trace_bootstrap,
    agent_trace_export_file,
    agent_trace_refresh,
    agent_trace_search_filter,
    agent_trace_view,
    trace_bundle,
)
from shopstack.ui.tabs.context import TabContext


def build_memory_history(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the What Happened (Trace History) sub-tab inside the Memory tab.

    Adds a Markdown header, search/filter controls, a recent-activity
    table, a record selector, timeline + raw HTML panels, and a
    download button. Wires:
    - ``trace_search.change`` and ``trace_type_filter.change`` →
      ``agent_trace_search_filter``
    - ``trace_selector.change`` → ``trace_bundle``
    - ``trace_refresh.click`` → ``agent_trace_refresh``
    - ``trace_export.click`` → ``agent_trace_export_file``
    - ``app.load`` → initial ``agent_trace_view`` and ``agent_trace_bootstrap``

    Args:
        app: The root gr.Blocks instance — needed for ``app.load(...)``.
        ctx: Shared dependencies (unused in this sub-tab, kept for
            uniform signature).

    Returns:
        None. No cross-sub-tab references.
    """
    gr.Markdown(
        "### Household history\n\n"
        "Browse household activity, inspect details, and export records "
        "when you need them."
    )
    with gr.Row():
        trace_search = gr.Textbox(
            label="Search",
            placeholder="Search by goal, type, or record ID",
            scale=2,
        )
        trace_type_filter = gr.Dropdown(
            label="Input type",
            choices=[("All", ""), ("Text", "text"), ("Voice", "voice"), ("Image", "image")],
            value="",
            allow_custom_value=False,
            scale=1,
        )
        trace_refresh = gr.Button("Refresh", elem_classes="secondary", scale=1)
    trace_table = gr.DataFrame(label="Recent Activity")
    with gr.Row():
        trace_selector = gr.Dropdown(
            label="Select a record",
            choices=[("No activity yet", "")],
            value="",
            allow_custom_value=False,
        )
    trace_timeline = gr.HTML(
        empty_state_enhanced(
            "Select a record above to see the timeline and details.",
            icon="📜",
        )
    )
    trace_raw = gr.HTML("")
    with gr.Row():
        trace_export = gr.Button("Download activity record")
        trace_file = gr.File(
            file_count="single",
            visible=True,
            label="Download record (private info removed)",
        )
    trace_bootstrap_state = gr.State("")

    trace_search.change(
        agent_trace_search_filter,
        [trace_search, trace_type_filter],
        [trace_selector, trace_timeline, trace_raw],
        api_name="trace_search",
        api_description="Search and filter traces",
    )
    trace_type_filter.change(
        agent_trace_search_filter,
        [trace_search, trace_type_filter],
        [trace_selector, trace_timeline, trace_raw],
        api_name="trace_filter",
        api_description="Filter traces by input type",
    )
    trace_selector.change(
        trace_bundle,
        trace_selector,
        [trace_timeline, trace_raw],
        api_name="trace_select",
        api_description="Load timeline and redacted payload for selected trace",
    )
    trace_refresh.click(
        agent_trace_refresh,
        outputs=[trace_selector, trace_timeline, trace_raw, trace_bootstrap_state,
                 trace_table],
        api_name="trace_refresh",
        api_description="Refresh trace list and selected timeline",
    )
    trace_export.click(
        agent_trace_export_file,
        trace_selector,
        trace_file,
        api_name="trace_export",
        api_description="Export selected record as redacted JSONL",
    )
    app.load(lambda: agent_trace_view()[0], outputs=trace_table)
    app.load(
        lambda: agent_trace_bootstrap(),
        outputs=[trace_selector, trace_timeline, trace_raw, trace_bootstrap_state],
    )
