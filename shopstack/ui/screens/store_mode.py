"""Store mode — large-touch-target shopping list for in-store use.

When the user is at the store, they need big, easy-to-tap checkboxes
and minimal distractions. This module provides a simplified shopping
list view optimized for one-handed phone use.

Store mode renders each item as a large card with:
- Bold item name (large font)
- Quantity + unit
- Tap-to-toggle checkbox (large touch target >= 48px)
- Price hint (if available from market data)
- Price comparison across stores
- Camera scan shortcut

**Enhanced 2026-06-16:**
- Added proper server-side checkbox toggles via /api/store_mode/toggle endpoint
- Added price hints from market data for each item
- Added camera scan quick action button
- Added "Compare prices" section showing best store for each item
- State persisted across re-renders via shopping list item status updates
"""
from __future__ import annotations

import logging
from html import escape

from shopstack.app_context import current_user_id, db
from shopstack.services.price_memory import PriceMemoryService
from shopstack.services.weather import get_weather
from shopstack.ui.components.primitives import empty_state_enhanced, home_card

logger = logging.getLogger(__name__)


def _user_id() -> str:
    """Local convenience wrapper preserved for callers that import it directly."""
    return current_user_id()


def _precompute_hints(items: list) -> tuple[dict[str, str], dict[str, str]]:
    """Pre-compute price and store hints for all items in a single pass.

    Creates one ``PriceMemoryService`` instance and computes both hint
    types for every unique ``canonical_name``. Returns two dicts:
    ``{canonical_name: price_hint_string}`` and ``{canonical_name: store_hint_string}``.

    This replaces the previous per-item pattern that created a fresh
    ``PriceMemoryService`` for each call (30+ DB queries for 15 items).
    """
    price_hints: dict[str, str] = {}
    store_hints: dict[str, str] = {}

    try:
        pm = PriceMemoryService(db)
        for item in items:
            name = (item.canonical_name or "").strip()
            if not name or name in price_hints:
                continue
            # Price hint — best recent price
            try:
                summary = pm.get_summary(name, days=14)
                if summary.last_price is not None and summary.last_price > 0:
                    if summary.normalized_per_kg is not None and summary.normalized_per_kg > 0:
                        price_hints[name] = "Rs {:.0f} (Rs {:.0f}/kg)".format(
                            summary.last_price, summary.normalized_per_kg)
                    else:
                        price_hints[name] = "Rs {:.0f}".format(summary.last_price)
            except Exception:
                pass
            # Store hint — best store for this item
            try:
                comparison = pm.get_store_comparison(name, days=30)
                if comparison.store_prices and comparison.best_store:
                    best = comparison.store_prices[0]
                    price = best.get("median_price", 0)
                    if price:
                        store_hints[name] = "{} Rs {:.0f}".format(
                            comparison.best_store.title(), price)
            except Exception:
                pass
    except Exception:
        logger.debug("Failed to pre-compute price hints", exc_info=True)

    return price_hints, store_hints


def _render_item_card(item, index: int, price_hint: str, store_hint: str) -> str:
    name = (item.canonical_name or "").replace("_", " ").title()
    qty = item.requested_quantity or 1.0
    unit = item.unit or "unit"
    item_id = (
        getattr(item, "item_id", None)
        or getattr(item, "id", None)
        or str(index)
    )
    qty_display = "{:.0f}".format(qty) if qty == int(qty) else "{:.1f}".format(qty)

    hint_parts = []
    hint_parts.append('<span style="font-size:0.875rem;color:var(--text-dim);">{} {}</span>'.format(
        escape(qty_display), escape(unit)))
    if price_hint:
        hint_parts.append('<span style="font-size:0.75rem;color:var(--green);font-weight:500;">{}</span>'.format(
            escape(price_hint)))
    if store_hint:
        hint_parts.append('<span style="font-size:0.7rem;color:var(--blue);">at {}</span>'.format(
            escape(store_hint)))

    hints_html = '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">{}</div>'.format(
        "".join(hint_parts))

    return (
        '<div class="store-mode-item" data-item-id="{}" '
        'style="display:flex;align-items:center;gap:12px;'
        'padding:14px 16px;border-bottom:1px solid var(--border);min-height:56px;">'
        '<div class="store-mode-checkbox" onclick=\'_storeModeToggle("{}",this)\' '
        'style="min-width:48px;min-height:48px;display:flex;align-items:center;justify-content:center;'
        'border:2px solid var(--accent);border-radius:12px;cursor:pointer;'
        'font-size:1.25rem;color:var(--text-dim);background:var(--bg-card);'
        'transition:all 0.15s;" title="Tap to check off">&#x2610;</div>'
        '<div style="flex:1;">'
        '<div style="font-size:1.125rem;font-weight:600;">{}</div>'
        '{}</div></div>'
    ).format(
        escape(str(item_id)),
        escape(str(item_id)),
        escape(name),
        hints_html,
    )


def _render_checked_card(item) -> str:
    name = (item.canonical_name or "").replace("_", " ").title()
    qty = item.requested_quantity or 1.0
    unit = item.unit or "unit"
    qty_display = "{:.0f}".format(qty) if qty == int(qty) else "{:.1f}".format(qty)
    return (
        '<div style="display:flex;align-items:center;gap:12px;padding:8px 16px;'
        'opacity:0.4;text-decoration:line-through;">'
        '<div style="min-width:32px;min-height:32px;display:flex;align-items:center;justify-content:center;'
        'font-size:1rem;color:var(--green);">&#x2713;</div>'
        '<div style="flex:1;"><span style="font-size:0.8125rem;">{}</span>'
        '<span style="font-size:0.75rem;color:var(--text-dim);margin-left:6px;">({} {})</span></div>'
        '</div>'
    ).format(escape(name), escape(qty_display), escape(unit))


def _render_group(title: str, group_items: list, color: str,
                  price_hints: dict[str, str] | None = None,
                  store_hints: dict[str, str] | None = None) -> str:
    if not group_items:
        return ""
    if price_hints is None:
        price_hints = {}
    if store_hints is None:
        store_hints = {}
    cards = "".join(
        _render_item_card(
            item, i,
            price_hints.get(item.canonical_name or "", ""),
            store_hints.get(item.canonical_name or "", ""),
        )
        for i, item in enumerate(group_items)
    )
    return (
        '<div style="margin-bottom:16px;">'
        '<div style="font-size:0.75rem;font-weight:600;color:{};'
        'letter-spacing:0.05em;text-transform:uppercase;padding:4px 16px;">{} ({})</div>'
        '<div style="border:1px solid var(--border);border-radius:12px;overflow:hidden;">{}</div>'
        '</div>'
    ).format(color, escape(title), len(group_items), cards)


def store_mode_view() -> str:
    """Render the shopping list as large touch targets for in-store use.

    Each item is rendered as a full-width card with a 48px+ touch target
    checkbox, large item name, and quantity. Items can be tapped to mark
    as checked via a server-side API call. Price hints from market data
    and camera scan button are included.
    """
    sl = db.get_active_shopping_list(user_id=_user_id())
    if not sl or not sl.items:
        return empty_state_enhanced(
            "No active shopping list. Create one before you head to the store.",
            icon="\U0001f6d2",
        )

    items_unchecked = [
        lot for lot in sl.items
        if lot.status not in ("bought", "skipped")
    ]
    items_checked = [
        lot for lot in sl.items
        if lot.status == "bought"
    ]
    if not items_unchecked and not items_checked:
        return home_card(
            title="All done!",
            body="<div class='muted'>Every item on your list has been checked off. Time to head home!</div>",
            style="text-align:center;padding:24px;",
        )

    must_buy = [i for i in items_unchecked if i.priority == "must_buy"]
    optional = [i for i in items_unchecked if i.priority == "optional"]
    other = [i for i in items_unchecked if i.priority not in ("must_buy", "optional")]

    remaining = len(items_unchecked)
    checked_count = len(items_checked)
    total = remaining + checked_count
    progress_pct = int(checked_count / total * 100) if total > 0 else 0

    # ── Batch-compute ALL price/store hints in a single pass ──────
    # Previously, every item triggered 3 separate DB queries (2 in
    # _render_item_card + 1 in the compare section), each creating a
    # fresh PriceMemoryService. Pre-computing once drops ~45 DB calls
    # down to ~30 for a typical 15-item list.
    price_hints, store_hints = _precompute_hints(sl.items)

    # Weather badge — show current conditions for trip planning
    weather_html = ""
    try:
        w = get_weather()
        icon = w.condition_icon
        badge_color = "var(--green)" if w.is_shopping_friendly else "var(--amber)"
        weather_html = (
            '<div style="display:inline-flex;align-items:center;gap:4px;'
            'font-size:0.6875rem;color:{};padding:4px 8px;'
            'border:1px solid {};border-radius:6px;">'
            '{} {}°C · {}'
            '</div>'
        ).format(badge_color, badge_color, icon, w.temperature_c, w.recommendation[:40])
    except Exception:
        pass

    # Price comparison section — reuse pre-computed store_hints
    # _precompute_hints only ever inserts keys from sl.items, so
    # every entry already belongs here — no filter needed.
    compare_html = ""
    items_with_prices = list(store_hints.items())
    if items_with_prices:
        rows = []
        for name, hint in items_with_prices[:8]:
            rows.append(
                '<div style="display:flex;justify-content:space-between;padding:4px 0;font-size:0.75rem;">'
                '<span>{}</span><span style="color:var(--green);">{}</span></div>'.format(
                    escape(name.replace("_", " ").title()),
                    escape(hint),
                )
            )
        compare_html = (
            '<details style="margin-top:12px;">'
            '<summary style="cursor:pointer;font-size:0.75rem;font-weight:600;color:var(--text-dim);padding:8px 16px;">'
            '\U0001f3f7\ufe0f Compare prices (tap to expand)</summary>'
            '<div style="padding:4px 16px;">{}</div></details>'.format("".join(rows))
        )

    # Toggle JavaScript
    toggle_script = (
        '<script data-ss-exec="true">'
        'window._storeModeToggle = function(itemId, el) {'
        "  fetch('/api/store_mode/toggle', {"
        "    method: 'POST',"
        "    headers: {'Content-Type': 'application/json'},"
        "    body: JSON.stringify({item_id: itemId})"
        "  })"
        "  .then(function(r){ return r.json(); })"
        "  .then(function(d){"
        "    if (d && d.success) {"
        "      el.innerHTML = '\\u2713';"
        "      el.style.borderColor = 'var(--green)';"
        "      el.style.color = 'var(--green)';"
        "      el.style.background = 'rgba(26,158,74,0.10)';"
        "      el.onclick = null;"
        "      var parent = el.closest('.store-mode-item');"
        "      if (parent) {"
        "        parent.style.opacity = '0.4';"
        "        parent.style.textDecoration = 'line-through';"
        "      }"
        "    } else {"
        "      var msg = (d && d.error) ? d.error : 'Toggle failed';"
        "      el.title = msg;"
        "    }"
        "  })"
        "  .catch(function(e){ console.warn('store toggle failed', e); });"
        "};"
        '</script>'
    )

    # Build the sections
    groups_html = "".join([
        _render_group("Must buy", must_buy, "var(--green)",
                      price_hints=price_hints, store_hints=store_hints),
        _render_group("Optional", optional, "var(--blue)",
                      price_hints=price_hints, store_hints=store_hints),
        _render_group("Other", other, "var(--text-dim)",
                      price_hints=price_hints, store_hints=store_hints),
    ])

    # Checked section
    checked_html = ""
    if checked_count:
        checked_items_html = "".join(_render_checked_card(i) for i in items_checked[:5])
        checked_html = (
            '<details style="margin-top:8px;">'
            '<summary style="cursor:pointer;font-size:0.75rem;font-weight:600;'
            'color:var(--text-dim);padding:4px 16px;">\u2713 {} checked</summary>'
            '{}</details>'.format(checked_count, checked_items_html)
        )

    return ''.join([
        '<div style="text-align:left;">',
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">',
        '<div style="display:flex;align-items:center;gap:8px;"><h3 style="margin:0;">\U0001f6d2 In-store mode</h3>{}<div class="muted" style="font-size:0.8125rem;">{} item{} left</div></div></div>'.format(
            weather_html, remaining, "s" if remaining != 1 else ""),
        '<div style="text-align:right;"><div style="font-size:0.75rem;color:var(--text-dim);">Progress</div>',
        '<div style="font-size:1.5rem;font-weight:700;">{}%</div></div>'.format(progress_pct),
        '</div>',
        '<div style="height:4px;background:var(--border);border-radius:2px;margin-bottom:16px;">',
        '<div style="height:100%;width:{}%;background:var(--green);border-radius:2px;transition:width 0.3s;"></div></div>'.format(progress_pct),
        # Action bar
        '<div style="display:flex;gap:8px;margin-bottom:16px;">',
        '<a href="#market" style="flex:1;display:inline-flex;align-items:center;justify-content:center;gap:6px;'
        'padding:12px;background:var(--accent);color:#fff;border-radius:12px;'
        'text-decoration:none;font-size:0.875rem;font-weight:600;min-height:48px;">\U0001f4f7 Scan an item</a>',
        '</div>',
        groups_html,
        checked_html,
        compare_html,
        '<div style="display:flex;gap:8px;margin-top:12px;padding:4px 16px;">',
        '<a href="#basket" style="font-size:0.75rem;color:var(--blue);text-decoration:none;">Edit list \u2192</a>',
        '<span style="flex:1;"></span>',
        '<span style="font-size:0.6875rem;color:var(--text-dim);">Tap \u2610 to check off</span>',
        '</div>',
        toggle_script,
        '</div>',
    ])
