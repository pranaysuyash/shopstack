"""Store mode — large-touch-target shopping list for in-store use.

When the user is at the store, they need big, easy-to-tap checkboxes
and minimal distractions. This module provides a simplified shopping
list view optimized for one-handed phone use.

Store mode renders each item as a large card with:
- Bold item name (large font)
- Quantity + unit
- Tap-to-toggle checkbox (large touch target ≥ 48px)
- Price hint (if available from market data)
"""
from __future__ import annotations

import logging
from html import escape

from shopstack.app_context import db
from shopstack.ui.components.primitives import empty_state_enhanced

logger = logging.getLogger(__name__)


def _user_id() -> str:
    from shopstack.app_context import current_user_id
    return current_user_id()


def store_mode_view() -> str:
    """Render the shopping list as large touch targets for in-store use.

    Each item is rendered as a full-width card with a 48px+ touch target
    checkbox, large item name, and quantity. Items can be tapped to mark
    as bought.
    """
    sl = db.get_active_shopping_list(user_id=_user_id())
    if not sl or not sl.items:
        return empty_state_enhanced(
            "No active shopping list. Create one before you head to the store.",
            icon="🛒",
        )

    items = [
        lot for lot in sl.items
        if lot.status not in ("bought", "skipped")
    ]
    if not items:
        return (
            "home_card(body='"\n            "<h3>✅ All done!</h3>"\n            "<div class=\'muted\'>Every item on your list has been checked off.', style='text-align:center;padding:24px;')"
            "</div>"
        )

    # Group by priority
    must_buy = [i for i in items if i.priority == "must_buy"]
    optional = [i for i in items if i.priority == "optional"]
    other = [i for i in items if i.priority not in ("must_buy", "optional")]

    def _render_item_card(item, index: int) -> str:
        name = (item.canonical_name or "").replace("_", " ").title()
        qty = item.requested_quantity or 1.0
        unit = item.unit or "unit"
        qty_display = f"{qty:.0f}" if qty == int(qty) else f"{qty:.1f}"

        return (
            f"<div class='store-mode-item' "
            f"style='display:flex;align-items:center;gap:12px;"
            f"padding:14px 16px;border-bottom:1px solid var(--border);"
            f"min-height:56px;cursor:pointer;' "
            f"onclick='this.style.opacity=\"0.4\";this.style.textDecoration=\"line-through\"'>"
            f"<div style='min-width:48px;min-height:48px;display:flex;align-items:center;"
            f"justify-content:center;border:2px solid var(--border);border-radius:12px;"
            f"font-size:1.25rem;color:var(--text-dim);'>☐</div>"
            f"<div style='flex:1;'>"
            f"<div style='font-size:1.125rem;font-weight:600;'>{escape(name)}</div>"
            f"<div style='font-size:0.875rem;color:var(--text-dim);'>{escape(qty_display)} {escape(unit)}</div>"
            f"</div>"
            f"</div>"
        )

    def _render_group(title: str, group_items: list, color: str) -> str:
        if not group_items:
            return ""
        cards = "".join(_render_item_card(item, i) for i, item in enumerate(group_items))
        return (
            f"<div style='margin-bottom:16px;'>"
            f"<div style='font-size:0.75rem;font-weight:600;color:{color};"
            f"letter-spacing:0.05em;text-transform:uppercase;padding:4px 16px;'>"
            f"{escape(title)} ({len(group_items)})</div>"
            f"<div style='border:1px solid var(--border);border-radius:12px;overflow:hidden;'>"
            f"{cards}"
            f"</div>"
            f"</div>"
        )

    remaining = len(items)
    progress_pct = 0
    if sl.items:
        total = len([i for i in sl.items if i.status not in ("bought", "skipped")])
        done = len([i for i in sl.items if i.status in ("bought",)])
        if total + done > 0:
            progress_pct = int(done / (total + done) * 100)

    return (
        f"<div style='text-align:left;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;'>"
        f"<div>"
        f"<h3 style='margin:0;'>🛒 In-store mode</h3>"
        f"<div class='muted' style='font-size:0.8125rem;'>{remaining} item{'s' if remaining != 1 else ''} left</div>"
        f"</div>"
        f"<div style='text-align:right;'>"
        f"<div style='font-size:0.75rem;color:var(--text-dim);'>Progress</div>"
        f"<div style='font-size:1.5rem;font-weight:700;'>{progress_pct}%</div>"
        f"</div>"
        f"</div>"
        f"<div style='height:4px;background:var(--border);border-radius:2px;margin-bottom:16px;'>"
        f"<div style='height:100%;width:{progress_pct}%;background:var(--green);border-radius:2px;transition:width 0.3s;'></div>"
        f"</div>"
        f"{_render_group('Must buy', must_buy, 'var(--green)')}"
        f"{_render_group('Optional', optional, 'var(--blue)')}"
        f"{_render_group('Other', other, 'var(--text-dim)')}"
        f"<div style='text-align:center;margin-top:16px;padding:12px;font-size:0.75rem;color:var(--text-dim);'>"
        f"Tap an item to mark it as checked"
        f"</div>"
        f"</div>"
    )
