"""Basket tab — Plan sub-tab sub-builder.

The Plan sub-tab has two pieces:

1. **Unified Plan** — Turn a rough goal ("Weekly groceries") + an items
   list into a structured plan: classify (must-buy / optional /
   skip), price each item, suggest substitutes, and score the
   basket as a whole. Renders a summary card + a detailed
   per-item breakdown.
2. **Smart basket** (Phase 9) — Community-pool-aware basket
   evaluator. Items significantly above the community median get
   a **wait** verdict; use-soon items get a **buy now** verdict
   even when overpriced. The user enters a comma-separated list
   of items, the system parses them into canonical names, and
   the smart-basket service renders an HTML verdict.

Extracted from ``shopstack.ui.tabs.basket`` in Pass 8 so each
basket sub-tab lives in its own module (mirrors the
``memory_*`` sub-builder pattern).

**Pattern:** this sub-builder opens its own ``gr.Tab("Plan")``
inside the parent's ``gr.Tabs()`` context, adds the UI, and
returns a :class:`BasketPlanHandles` dataclass exposing the
output components for any future cross-tab references (today
none exist; the dataclass is there for symmetry with
``ask_panel`` and ``cookbook_filter``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import gradio as gr

from shopstack.ui.components.primitives import (
    empty_state_enhanced,
    loading_skeleton,
    with_loading_state,
)
from shopstack.ui.components.js_helpers import busy_js
from shopstack.ui.screens import run_unified_plan, unified_plan_summary
from shopstack.ui.screens.smart_basket import smart_basket_screen
from shopstack.ui.tabs.context import TabContext


@dataclass
class BasketPlanHandles:
    """Components that other parts of the app may reference after the Plan sub-tab builds.

    Today no cross-tab references exist. The dataclass exposes
    the 7 main components for future use (e.g. clearing the
    smart-basket input on household switch).
    """

    run_btn: gr.Button
    goal_input: gr.Textbox
    items_input: gr.Textbox
    summary_html: gr.HTML
    detail_html: gr.HTML
    smart_basket_btn: gr.Button
    smart_basket_html: gr.HTML


def build_basket_plan(app: gr.Blocks, ctx: TabContext) -> BasketPlanHandles:
    """Build the Plan sub-tab inside the parent's ``gr.Tabs()`` context.

    Opens a ``gr.Tab("Plan")``, adds the unified-plan UI + the
    smart-basket UI, and wires the event handlers. The page-load
    handler (``app.load``) renders the initial summary.

    Args:
        app: The root ``gr.Blocks`` instance — needed for
            ``app.load(...)`` handlers.
        ctx: Shared dependencies (unused in this sub-tab, kept
            for the uniform builder signature).

    Returns:
        BasketPlanHandles: the 7 main components that future
        cross-tab references might need.
    """
    with gr.Tab("Plan"):
        gr.Markdown("### Plan groceries")
        gr.Markdown(
            "Turn a rough idea into a list, then see what to buy, skip, or compare."
        )
        with gr.Row():
            goal_input = gr.Textbox(
                label="Goal", placeholder="Weekly groceries", scale=1
            )
            items_input = gr.Textbox(
                label="Items (comma or newline separated)",
                placeholder="milk, bread, tomato, onion, rice, egg",
                lines=3,
                scale=2,
            )
        run_btn = gr.Button(
            "Run Plan", variant="primary", elem_id="run-plan-btn"
        )
        summary_html = gr.HTML(loading_skeleton("card"))
        detail_html = gr.HTML(
            empty_state_enhanced(
                "Detailed plan results will appear here after you run a plan.",
                icon="📑",
            )
        )
        run_btn.click(
            run_unified_plan,
            [goal_input, items_input],
            [summary_html, detail_html],
            js=busy_js("run-plan-btn", original_label="Run Plan"),
            api_name="unified_plan",
            api_description=(
                "Run unified shopping plan: classify, price, substitute, score deals"
            ),
        ).then(
            with_loading_state(run_btn, [])[1],
            outputs=[run_btn],
        )
        app.load(unified_plan_summary, outputs=summary_html)

        # ── Phase 9 Smart basket (community-pool-aware) ──
        gr.Markdown("---")
        gr.Markdown("### 🧠 Smart basket")
        gr.Markdown(
            "Community-pool-aware: items significantly above the "
            "community median get a **wait** verdict; use-soon "
            "items get a **buy now** verdict even when overpriced."
        )

        def _smart_basket_for_input(items_text: str) -> str:
            if not items_text or not items_text.strip():
                return smart_basket_screen()
            # Parse the items: assume the same format as the
            # unified plan — comma- or newline-separated
            # canonical_name list.
            raw_items: list[dict[str, Any]] = []
            for token in items_text.replace("\n", ",").split(","):
                t = token.strip().lower().replace(" ", "_")
                if not t:
                    continue
                raw_items.append({
                    "canonical_name": t,
                    "quantity": 1.0,
                    "unit": "unit",
                })
            return smart_basket_screen(items=raw_items)

        smart_basket_items = gr.Textbox(
            label="Items to evaluate",
            placeholder="milk, bread, rice, onion…",
            value="milk, bread, rice, onion",
            lines=2,
        )
        smart_basket_btn = gr.Button(
            "Run smart basket", variant="primary",
        )
        smart_basket_html = gr.HTML(loading_skeleton("card"))
        smart_basket_btn.click(
            _smart_basket_for_input,
            smart_basket_items,
            smart_basket_html,
            api_name="smart_basket_run",
            api_description=(
                "Evaluate the basket against the community pool + use-soon data"
            ),
        )
        app.load(
            _smart_basket_for_input,
            smart_basket_items,
            smart_basket_html,
        )

    return BasketPlanHandles(
        run_btn=run_btn,
        goal_input=goal_input,
        items_input=items_input,
        summary_html=summary_html,
        detail_html=detail_html,
        smart_basket_btn=smart_basket_btn,
        smart_basket_html=smart_basket_html,
    )
