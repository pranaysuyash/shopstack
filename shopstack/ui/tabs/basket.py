"""Basket tab — composition only.

This is the "what should I buy / skip / compare?" tab. It composes
4 sub-tabs by delegating each to its own sub-builder module:

  1. **Plan**           → ``basket_plan.build_basket_plan``
     (unified shopping plan + smart basket)
  2. **Best Basket**    → ``screens.basket.build_basket_screen``
     (basket optimizer — already a sub-builder, no extraction needed)
  3. **Shopping List**  → ``basket_shopping_list.build_basket_shopping_list``
     (list view, poster export, reconciliation, mark purchased)
  4. **Compare**        → ``basket_compare.build_basket_compare``
     (Stores / Market Graph / Price History, 3 inner sub-tabs)
  5. **Add Items**      → ``basket_add_items.build_basket_add_items``
     (Receipt / From Recipe, 2 inner sub-tabs)

The sub-builder pattern is documented at the module level of each
sub-builder. The composition here is intentionally minimal — just the
``gr.Tabs`` container, the trip-advisor banner (above the sub-tabs),
and calls to the sub-builders.

**Trip advisor banner:**

The trip advisor sits *above* the sub-tabs, not inside any of them.
It's a top-level concern (it spans all sub-tabs: active list size,
use-soon count, price-drop count, etc.). Kept inline in this file
because:

  * It's small (~15 lines).
  * It doesn't have its own sub-tab (it's a banner, not a screen).
  * Moving it to its own module would be cargo-culting.

If it grows past ~30 lines or acquires a sub-tab of its own, it
should be extracted to ``shopstack/ui/tabs/basket_trip_advisor.py``
following the same pattern as the 4 sub-tab builders.
"""
from __future__ import annotations

import gradio as gr

from shopstack.module_registry import tab_label as _tab_label
from shopstack.ui.screens.basket import build_basket_screen
from shopstack.ui.tabs.basket_add_items import build_basket_add_items
from shopstack.ui.tabs.basket_compare import build_basket_compare
from shopstack.ui.tabs.basket_plan import build_basket_plan
from shopstack.ui.tabs.basket_shopping_list import build_basket_shopping_list
from shopstack.ui.tabs.context import TabContext


def build_basket_tab(blocks: gr.Blocks, app: gr.Blocks, ctx: TabContext) -> None:
    """Build the Basket tab inside the parent's ``gr.Tabs`` context.

    Composes 5 sub-tabs by delegating each to its own sub-builder.
    No business logic lives in this function — all wiring is in
    the sub-builder modules. The trip-advisor banner is the only
    inline UI; it spans all sub-tabs so it lives at this level.

    Args:
        blocks: Alias for the parent gr.Blocks. Kept for symmetry
            with other tab builders.
        app: The root gr.Blocks instance — passed to each sub-builder
            for ``app.load(...)`` handlers.
        ctx: Shared dependencies (currently unused by any sub-builder,
            but part of the uniform builder signature for symmetry).

    Returns:
        None. The Basket tab is self-contained: no components are
        referenced by other parts of the app, so no TabHandles
        dataclass is needed.
    """
    with gr.Tab(_tab_label("basket"), id="basket"):
        # ── Trip Advisor banner (sits above sub-tabs) ──
        from shopstack.ui.screens.trip_advisor import trip_advisor_screen

        def _trip_advisor() -> str:
            from shopstack.ui.errors import safe_render_html
            return safe_render_html(
                trip_advisor_screen,
                user_message="Could not load trip advisor.",
                help_tab="basket",
            )

        trip_advisor_html = gr.HTML(_trip_advisor())
        trip_advisor_refresh = gr.Button(
            "🔄 Refresh trip advisor", elem_classes="secondary", size="sm"
        )
        trip_advisor_refresh.click(
            _trip_advisor,
            outputs=trip_advisor_html,
            api_name="basket_trip_advisor_refresh",
            api_description="Refresh trip advisor banner",
        )
        app.load(_trip_advisor, outputs=trip_advisor_html)

        with gr.Tabs():
            # ── Plan ──
            build_basket_plan(app=app, ctx=ctx)

            # ── Best Basket (optimizer) — already a sub-builder ──
            with gr.Tab("Best Basket"):
                build_basket_screen()

            # ── Shopping List ──
            build_basket_shopping_list(app=app, ctx=ctx)

            # ── Compare (3 inner sub-tabs) ──
            build_basket_compare(app=app, ctx=ctx)

            # ── Add Items (2 inner sub-tabs) ──
            build_basket_add_items(app=app, ctx=ctx)
