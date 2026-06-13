"""Memory tab — Activity + Analytics sub-builders.

Extracted from ``build_memory_tab`` so the household activity log
(Phase 8 #26) and the spend/activity insights dashboard (Phase 8
Analytics) are independently testable and reusable.

Both sub-tabs share the same pattern: a single HTML card with a
refresh button. The screen functions live in
``shopstack.ui.screens.activity_log`` and ``shopstack.ui.screens.analytics``.
"""
from __future__ import annotations

import gradio as gr

from shopstack.ui.components.primitives import loading_skeleton
from shopstack.ui.tabs.context import TabContext


def _activity_screen() -> str:
    """Closure for the Activity Log screen."""
    from shopstack.ui.screens.activity_log import activity_log_screen
    return activity_log_screen()


def _analytics_screen() -> str:
    """Closure for the Analytics screen."""
    from shopstack.ui.screens.analytics import analytics_screen
    return analytics_screen()


def build_memory_activity(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Activity sub-tab inside the Memory tab.

    Aggregated view of the last 30 days: total actions, top action
    types, top items, and a per-day timeline. Single refresh button.

    Args:
        app: The root gr.Blocks instance — needed for ``app.load(...)``.
        ctx: Shared dependencies (unused in this sub-tab, kept for
            uniform signature).

    Returns:
        None. No cross-sub-tab references.
    """
    gr.Markdown("### 📊 Household activity")
    gr.Markdown(
        "Aggregated view of the last 30 days: total actions, top "
        "action types, top items, and a per-day timeline."
    )
    activity_html = gr.HTML(loading_skeleton("card"))
    activity_refresh = gr.Button("Refresh", elem_classes="secondary")
    activity_refresh.click(
        _activity_screen, outputs=activity_html,
        api_name="activity_log_refresh",
        api_description="Refresh household activity log",
    )
    app.load(_activity_screen, outputs=activity_html)


def build_memory_analytics(app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Analytics sub-tab inside the Memory tab.

    Monthly spend trend, top items by cost, top merchants, and a
    waste-rate estimate. Single refresh button.

    Args:
        app: The root gr.Blocks instance — needed for ``app.load(...)``.
        ctx: Shared dependencies (unused in this sub-tab, kept for
            uniform signature).

    Returns:
        None. No cross-sub-tab references.
    """
    gr.Markdown("### 📈 Spend & activity insights")
    gr.Markdown(
        "Monthly spend trend, top items by cost, top merchants, "
        "and a waste-rate estimate. The numbers come from your "
        "purchase traces — add receipts to see this populate."
    )
    analytics_html = gr.HTML(loading_skeleton("card"))
    analytics_refresh = gr.Button("Refresh", elem_classes="secondary")
    analytics_refresh.click(
        _analytics_screen, outputs=analytics_html,
        api_name="analytics_refresh",
        api_description="Refresh household analytics dashboard",
    )
    app.load(_analytics_screen, outputs=analytics_html)
