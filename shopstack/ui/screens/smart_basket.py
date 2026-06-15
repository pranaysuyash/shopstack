"""Smart basket UI screen — Phase 9 wiring.

Thin server-rendered panel that takes a list of requested
items, looks up community medians + basket comparison, and
returns the smart basket HTML.
"""
from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.app_context import current_user_id, db, tools
from shopstack.services.community_price_map import community_median
from shopstack.services.smart_planner import (
    build_smart_basket,
    render_smart_basket_html,
)
from shopstack.ui.components.primitives import home_card


def smart_basket_screen(
    items: list[dict[str, Any]] | None = None,
    city: str = "",
) -> str:
    """Render the smart basket for the active household.

    Args:
        items: List of ``{"canonical_name": ..., "quantity": ...,
            "unit": ...}`` dicts. When ``None``, returns an
            empty-state HTML.
        city: City scope for the community median lookup.
    """
    try:
        if not items:
            return render_smart_basket_html(_empty_basket())
        # Build community medians
        medians: dict[str, float] = {}
        for it in items:
            cname = str(it.get("canonical_name") or "").strip().lower()
            if not cname:
                continue
            try:
                summary = community_median(cname, city=city, days=30)
            except Exception:
                summary = None
            if summary is None:
                continue
            medians[cname] = float(summary.get("median_price", 0) or 0)
        # Use-soon (best-effort)
        use_soon_items: list[dict[str, Any]] = []
        try:
            user_id = current_user_id() or ""
            use_soon_items = tools.inventory.get_use_soon(days=3, user_id=user_id).get("items", [])
        except Exception:
            use_soon_items = []
        basket = build_smart_basket(
            items,
            community_medians=medians,
            use_soon_items=use_soon_items,
        )
        return render_smart_basket_html(basket)
    except Exception as exc:
        logger.warning("smart_basket_screen failed: %s", exc)
        return home_card(
            style="text-align:center;padding:12px;",
            body=(
                "<div style='color:var(--amber);font-weight:600;'>Could not build smart basket</div>"
                f"<div style='font-size: 0.75rem;color:var(--text-dim);margin-top:4px;'>{escape(str(exc)[:120])}</div>"
            ),
        )


def _empty_basket():
    """Empty-state basket for the 'no items yet' case."""
    from shopstack.services.smart_planner import SmartBasket
    return SmartBasket(generated_at="")


__all__ = ["smart_basket_screen"]
