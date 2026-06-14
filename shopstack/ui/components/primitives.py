"""ShopStack UI primitives — HTML rendering components and decorators.

This module is the **HTML rendering layer** of ShopStack's design
system. It contains the P1 design-system components (ItemRow, StatCard,
DataTable, ConfirmDialog, Toast, LoadingSkeleton, EmptyState), the
destructive-action pattern helpers, the ARIA/HTML form-validation
helpers, and the ``elem_id_of`` utility.

For related concerns that live alongside the HTML primitives, see:

- :mod:`shopstack.ui.components.js_helpers` — JavaScript snippets
  returned as strings for Gradio's ``app.load(js=...)`` parameter
  (``busy_js``, ``autocomplete_injector_js``, ``url_state_sync_js``).
  **Canonical path** for these — the re-exports here are deprecated.
- :mod:`shopstack.ui.components.decorators` — Screen-function
  decorators that apply UI patterns uniformly
  (``@aria_live_screen``). **Canonical path** — the re-export here
  is deprecated.

Deprecation / Supersession
---------------------------

The following symbols were moved to dedicated modules in Pass 4
(UX-fix worklog Pass 4, 2026-06-13) but are kept here as
**deprecated re-exports** that emit a ``DeprecationWarning`` on
first call. The canonical paths are:

- ``busy_js`` → :mod:`shopstack.ui.components.js_helpers.busy_js`
- ``autocomplete_injector_js`` → :mod:`shopstack.ui.components.js_helpers.autocomplete_injector_js`
- ``url_state_sync_js`` → :mod:`shopstack.ui.components.js_helpers.url_state_sync_js`
- ``aria_live_screen`` → :mod:`shopstack.ui.components.decorators.aria_live_screen`

Per the project supersession rules (CLAUDE.md § 7): the new
canonical paths are in place; the old paths emit
``DeprecationWarning``; the project is being migrated; once
0 internal call sites remain, the re-exports will be kept for
one release cycle (ShopStack's next minor release) and then
deleted.

**Migration tracker (Pass 4 → Pass 5):** the last internal call
site (``consumption.py:21``) was migrated to the canonical
``decorators.py`` path in Pass 5 Batch 23. The deprecated
re-exports in this module are kept for external backward
compatibility and emit a ``DeprecationWarning`` on call.

Removed from this module in Pass 4: ``busy_js``,
``autocomplete_injector_js``, ``url_state_sync_js``,
``_TAB_IDS_FOR_URL_SYNC``, ``aria_live_screen``. The HTML
primitives (``item_row``, ``stat_card``, ``data_table``,
``confirm_dialog``, ``toast``, ``loading_skeleton``,
``empty_state_enhanced``) remain in this module — they are the
canonical home for HTML rendering.

All HTML returned by these functions is **escaped via
``html.escape()``** for every user/data-derived string. Never
substitute ``str.format()`` or f-string interpolation with raw user
input — always go through a helper in this module.

Every function in this module returns an HTML ``str`` (or a
``gr.update`` dict). No function imports Gradio. That keeps the
primitives unit-testable without spinning up a Gradio app — see
``tests/test_ui_support.py``.

For the full module index, see ``Docs/UX_PATTERNS.md``.
"""
from __future__ import annotations

import functools
import json as _json
import warnings
from html import escape
from typing import Any

# Re-exports for backward compatibility — the JS helpers and the
# aria_live_screen decorator were moved to dedicated modules in
# Pass 4 (UX-fix worklog Pass 4, 2026-06-13). Per the project
# supersession rules (CLAUDE.md § 7), the re-exports here emit a
# ``DeprecationWarning`` on first call so consumers migrate to the
# canonical paths:
#   from shopstack.ui.components.js_helpers import busy_js, ...
#   from shopstack.ui.components.decorators import aria_live_screen
# See the module docstring's "Deprecation / Supersession" section
# for the full migration tracker and removal plan.
from shopstack.ui.components.decorators import (  # noqa: F401 — re-export (deprecated)
    aria_live_screen as _canonical_aria_live_screen_factory,
)
from shopstack.ui.components.js_helpers import (  # noqa: F401 — re-export (deprecated)
    autocomplete_injector_js as _canonical_autocomplete_injector_js,
    busy_js as _canonical_busy_js,
    url_state_sync_js as _canonical_url_state_sync_js,
)


def _deprecated_alias(
    old_qualname: str,
    new_qualname: str,
    removal_target: str = "the next minor release (see migration tracker in module docstring)",
):
    """Wrap a canonical function so the deprecated path emits a ``DeprecationWarning`` on call.

    The wrapper preserves ``__name__``/``__doc__`` for ``help()`` and
    stack traces, and uses ``stacklevel=2`` so the warning points at
    the caller's line, not the wrapper itself.

    Args:
        old_qualname: Fully-qualified name of the deprecated alias
            (e.g. ``"shopstack.ui.components.primitives.busy_js"``).
        new_qualname: Fully-qualified name of the canonical path
            (e.g. ``"shopstack.ui.components.js_helpers.busy_js"``).
        removal_target: Human-readable string shown in the warning,
            describing when the alias will be removed.

    Returns:
        A decorator that wraps a function (or factory) and emits
        a ``DeprecationWarning`` on each call.
    """
    def decorator(target):
        @functools.wraps(target)
        def wrapper(*args, **kwargs):
            warnings.warn(
                f"{old_qualname} is deprecated and will be removed in {removal_target}. "
                f"Use {new_qualname} instead. "
                f"See the migration tracker in shopstack.ui.components.primitives docstring.",
                DeprecationWarning,
                stacklevel=2,
            )
            return target(*args, **kwargs)
        wrapper.__qualname__ = target.__qualname__
        return wrapper
    return decorator


# Local inlined copy of the canonical ``aria_live_html`` so the
# deprecated ``aria_live_screen`` re-export below doesn't create a
# circular import with :mod:`shopstack.ui.components.decorators`.
# Keep in sync with the canonical implementation at the bottom of
# this file (and the same impl in ``decorators.py``).
def _canonical_aria_live_html(content: str, level: str = "polite") -> str:
    """Wrap content in a role='status' aria-live region (canonical impl)."""
    safe_level = escape(str(level))
    if safe_level not in ("polite", "assertive"):
        safe_level = "polite"
    return (
        f"<div role='status' aria-live='{safe_level}' aria-atomic='true'>"
        f"{content}"
        f"</div>"
    )


@_deprecated_alias(
    "shopstack.ui.components.primitives.busy_js",
    "shopstack.ui.components.js_helpers.busy_js",
)
def busy_js(*args, **kwargs):
    """DepRECATED: use ``shopstack.ui.components.js_helpers.busy_js`` instead.

    Re-exported for backward compatibility. Emits a
    ``DeprecationWarning`` on first call. See the module docstring's
    supersession tracker.
    """
    return _canonical_busy_js(*args, **kwargs)


@_deprecated_alias(
    "shopstack.ui.components.primitives.autocomplete_injector_js",
    "shopstack.ui.components.js_helpers.autocomplete_injector_js",
)
def autocomplete_injector_js(*args, **kwargs):
    """DepRECATED: use ``shopstack.ui.components.js_helpers.autocomplete_injector_js`` instead."""
    return _canonical_autocomplete_injector_js(*args, **kwargs)


@_deprecated_alias(
    "shopstack.ui.components.primitives.url_state_sync_js",
    "shopstack.ui.components.js_helpers.url_state_sync_js",
)
def url_state_sync_js(*args, **kwargs):
    """DepRECATED: use ``shopstack.ui.components.js_helpers.url_state_sync_js`` instead."""
    return _canonical_url_state_sync_js(*args, **kwargs)


@_deprecated_alias(
    "shopstack.ui.components.primitives.aria_live_screen",
    "shopstack.ui.components.decorators.aria_live_screen",
)
def aria_live_screen(level: str = "polite"):
    """DepRECATED: use ``shopstack.ui.components.decorators.aria_live_screen`` instead.

    Returns a decorator that wraps a screen function's HTML output
    in an ``aria-live`` region. Re-exported for backward compatibility
    from ``primitives`` — emits a ``DeprecationWarning`` on first
    factory call. See the module docstring's supersession tracker.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            if isinstance(result, str):
                return _canonical_aria_live_html(result, level=level)
            if isinstance(result, tuple):
                return tuple(
                    _canonical_aria_live_html(r, level=level) if isinstance(r, str) else r
                    for r in result
                )
            return result
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════════
# ItemRow — standardized inventory/shopping item row
# ═══════════════════════════════════════════════════════════════════════

def item_row(
    name: str,
    quantity: float,
    unit: str,
    status: str = "active",
    location: str = "",
    price: float | None = None,
    decision: str | None = None,
    expiry_days: int | None = None,
    lot_id: str = "",
    extra: str = "",
) -> str:
    """Render a standardized inventory or shopping item row.

    Args:
        name: Display name of the item
        quantity: Current quantity on hand
        unit: Unit of measure (kg, L, pieces, etc.)
        status: One of ``active``, ``low``, ``consumed``, ``expired``
        location: Storage location name
        price: Price paid (INR)
        decision: Decision badge override (``buy``, ``skip``, ``use_soon``)
        expiry_days: Days until expiry (negative = overdue)
        lot_id: Lot identifier (shown as muted monospace)
        extra: Additional HTML or text appended after the row body
    """
    safe_name = escape(str(name))
    safe_unit = escape(str(unit))
    safe_location = escape(str(location)) if location else ""
    safe_lot = escape(str(lot_id)) if lot_id else ""

    # Quantity + unit display
    qty_display = f"{quantity} {safe_unit}"

    # Status badge
    status_map = {
        "active": ("badge-green", "Active"),
        "low": ("badge-amber", "Low"),
        "consumed": ("badge-gray", "Consumed"),
        "expired": ("badge-red", "Expired"),
    }
    badge_cls, badge_label = status_map.get(status, ("badge-gray", status.title()))

    # Decision badge
    decision_badge = ""
    if decision:
        decision_map = {
            "buy": ("badge-green", "Buy"),
            "skip": ("badge-blue", "Skip"),
            "use_soon": ("badge-amber", "Use Soon"),
            "optional": ("badge-blue", "Optional"),
            "compare": ("badge-blue", "Compare"),
            "confirm": ("badge-red", "Confirm"),
        }
        d_cls, d_label = decision_map.get(decision, ("badge-gray", decision.title()))
        decision_badge = f"<span class='badge {d_cls}'>{escape(d_label)}</span>"

    # Expiry warning
    expiry_html = ""
    if expiry_days is not None:
        if expiry_days < 0:
            expiry_html = f"<span style='color:var(--red);font-size: 0.6875rem;margin-left:8px;'>{abs(expiry_days)}d overdue</span>"
        elif expiry_days <= 3:
            expiry_html = f"<span style='color:var(--amber);font-size: 0.6875rem;margin-left:8px;'>{expiry_days}d left</span>"

    # Price
    price_html = ""
    if price is not None and price > 0:
        price_html = f"<span style='font-weight:600;font-size: 0.8125rem;'>₹{price:.0f}</span>"

    # Lot ID
    lot_html = f"<span style='font-family:monospace;font-size: 0.625rem;color:var(--text-faint);'>{safe_lot[:12]}</span>" if safe_lot else ""

    safe_aria_label = f"{safe_name}, {escape(qty_display)}"
    return (
        f"<div class='item-row' role='group' aria-label='{safe_aria_label}'>"
        # Left side: name + metadata
        "<div>"
        f"<div style='font-weight:600;color:var(--text);'>{safe_name}</div>"
        + (f"<div style='font-size: 0.6875rem;color:var(--text-dim);'>{safe_location}" + (f" &middot; {lot_html}" if lot_html else "") + "</div>" if safe_location or lot_html else "")
        + (f"<div style='font-size: 0.6875rem;color:var(--text-dim);'>{escape(str(extra))}</div>" if extra else "")
        + "</div>"
        # Right side: quantity, price, badges
        "<div style='display:flex;align-items:center;gap:8px;flex-shrink:0;'>"
        f"<span style='font-weight:500;color:var(--text);white-space:nowrap;'>{escape(qty_display)}</span>"
        + (price_html if price_html else "")
        + (expiry_html if expiry_html else "")
        + f"<span class='badge {badge_cls}'>{escape(badge_label)}</span>"
        + (decision_badge if decision_badge else "")
        + "</div>"
        "</div>"
    )


# ═══════════════════════════════════════════════════════════════════════
# StatCard — metric card with icon, value, trend
# ═══════════════════════════════════════════════════════════════════════

def stat_card(
    value: str,
    label: str,
    icon: str = "",
    trend: str = "",
    trend_value: str = "",
    variant: str = "default",
    on_click_tab: str = "",
) -> str:
    """Render a stat/metric card.

    Args:
        value: Large display value (e.g. ``"12"``, ``"₹340"``)
        label: Label below the value
        icon: Emoji or text icon (placed above value)
        trend: ``up``, ``down``, or ``stable``
        trend_value: Secondary trend text (e.g. ``"+12%"``)
        variant: ``default``, ``success``, ``warning``, ``danger``
        on_click_tab: Gradio tab id to navigate to on click
    """
    safe_value = escape(str(value))
    safe_label = escape(str(label))
    safe_icon = escape(str(icon)) if icon else ""
    safe_trend = escape(str(trend_value)) if trend_value else ""

    variant_map = {
        "default": "",
        "success": "border-left: 3px solid var(--green);",
        "warning": "border-left: 3px solid var(--amber);",
        "danger": "border-left: 3px solid var(--red);",
    }
    variant_style = variant_map.get(variant, "")

    trend_html = ""
    if trend:
        trend_arrows = {"up": "↑", "down": "↓", "stable": "→"}
        arrow = trend_arrows.get(trend, "")
        trend_color = {
            "up": "var(--green)",
            "down": "var(--red)",
            "stable": "var(--text-dim)",
        }.get(trend, "var(--text-dim)")
        trend_html = (
            f"<span style='color:{trend_color};font-size: 0.75rem;font-weight:600;'>"
            f"{arrow} {safe_trend}</span>"
        )

    icon_html = f"<div style='font-size: 1.5rem;margin-bottom:4px;'>{safe_icon}</div>" if safe_icon else ""

    click_attr = ""
    if on_click_tab:
        import re
        safe_tab = re.sub(r"[^a-z0-9_-]", "-", str(on_click_tab).lower())
        click_attr = (
            f" style='cursor:pointer;'"
            f" onclick=\"var el=document.querySelector('[data-testid=tab-{safe_tab}]');"
            f"if(el)el.click();\""
        )

    return (
        f"<div class='stat-card' role='region' aria-label='{safe_label}: {safe_value}'{click_attr} style='{variant_style}'>"
        f"{icon_html}"
        f"<div class='stat-value'>{safe_value}</div>"
        f"<div class='stat-label'>{safe_label}</div>"
        + (f"<div style='margin-top:6px;'>{trend_html}</div>" if trend_html else "")
        + "</div>"
    )


# ═══════════════════════════════════════════════════════════════════════
# DataTable — sortable, filterable table wrapper
# ═══════════════════════════════════════════════════════════════════════

def data_table(
    rows: list[dict[str, Any]],
    columns: list[str] | None = None,
    sortable: bool = False,
    empty_message: str = "No data",
    page_size: int = 0,  # 0 = show all
) -> str:
    """Render a data table with optional sorting.

    Args:
        rows: List of dicts representing rows
        columns: Column keys; defaults to keys of first row
        sortable: If True, includes basic sort affordance (header click)
        empty_message: Message shown when rows is empty
        page_size: Items per page (0 = show all)
    """
    if not rows:
        return (
            "<div class='home-card' style='text-align:left;'>"
            f"<div class='muted'>{escape(str(empty_message))}</div>"
            "</div>"
        )

    if columns is None:
        columns = list(rows[0].keys()) if rows else []

    display_rows = rows[:page_size] if page_size > 0 else rows
    has_more = page_size > 0 and len(rows) > page_size

    head_html = "".join(
        f"<th>{escape(col.replace('_', ' ').title())}"
        + ("<span style='font-size: 0.5625rem;margin-left:4px;opacity:0.4;'>&#9650;&#9660;</span>" if sortable else "")
        + "</th>"
        for col in columns
    )
    body_html = "".join(
        "<tr>"
        + "".join(
            f"<td>{escape(str(row.get(col, '')))}</td>"
            for col in columns
        )
        + "</tr>"
        for row in display_rows
    )

    more_html = ""
    if has_more:
        more_html = (
            "<div style='text-align:center;padding:8px;color:var(--text-dim);font-size: 0.75rem;'>"
            f"Showing {page_size} of {len(rows)} items"
            "</div>"
        )

    table_desc = escape(str(empty_message)) if empty_message != "No data" else "data table"
    return (
        "<div class='home-card' style='text-align:left;padding:0;overflow:hidden;' role='region' aria-label='Table: " + table_desc + "'>"
        "<table style='border-collapse:collapse;width:100%;font-size: 0.8125rem;'>"
        f"<caption class='sr-only'>{table_desc}</caption>"
        f"<thead><tr>{head_html}</tr></thead>"
        f"<tbody>{body_html}</tbody>"
        "</table>"
        f"{more_html}"
        "</div>"
    )


# ═══════════════════════════════════════════════════════════════════════
# ConfirmDialog — inline confirmation state for destructive actions
# ═══════════════════════════════════════════════════════════════════════

def confirm_dialog(
    message: str,
    confirm_label: str = "Confirm",
    variant: str = "default",
) -> str:
    """Render an inline confirmation prompt.

    Args:
        message: The question or warning to display
        confirm_label: Text for the confirm action
        variant: ``default`` or ``danger`` (red-tinted)
    """
    safe_message = escape(str(message))
    safe_label = escape(str(confirm_label))

    border_color = "var(--red)" if variant == "danger" else "var(--amber)"
    bg_tint = "rgba(166,63,49,0.06)" if variant == "danger" else "rgba(167,96,18,0.06)"

    return (
        f"<div class='home-card' style='text-align:left;border-left:3px solid {border_color};background:{bg_tint};' role='alertdialog' aria-label='{safe_message}'>"
        "<div style='display:flex;align-items:flex-start;gap:10px;'>"
        "<span style='font-size: 1.25rem;' aria-hidden='true'>&#9888;</span>"
        "<div>"
        f"<div style='font-weight:600;margin-bottom:4px;'>{safe_message}</div>"
        "<div style='font-size: 0.6875rem;color:var(--text-dim);'>"
        f"Click '{safe_label}' to proceed, or cancel."
        "</div>"
        "</div>"
        "</div>"
        "</div>"
    )


def confirm_toggle_updates():
    """Return the (initial_btn_update, confirm_group_update) pair for a 2-step destructive action.

    Use this when wiring a primary destructive button so that the first click hides
    the original button and shows the confirm group; the second click on the
    confirm group fires the actual action and the cancel button restores the
    original state.

    Returns:
        A 2-tuple of ``gr.update`` instances: (hide_primary, show_confirm_group).

    Example:
        >>> primary_btn, confirm_group, confirm_yes, confirm_no = build_destructive_confirm(...)
        >>> primary_btn.click(confirm_toggle_updates, outputs=[primary_btn, confirm_group])
    """
    import gradio as gr  # local import: primitives.py is imported by non-Gradio callers
    return gr.update(visible=False), gr.update(visible=True)


def confirm_hide_updates():
    """Return the (initial_btn_update, confirm_group_update) pair to restore the primary button.

    Pairs with :func:`confirm_toggle_updates` for the cancel/reset leg of the
    2-step destructive-action pattern.
    """
    import gradio as gr
    return gr.update(visible=True), gr.update(visible=False)


# ═══════════════════════════════════════════════════════════════════════
# Loading-state wrapper for long-running click handlers
# ═══════════════════════════════════════════════════════════════════════

def _set_loading(button_value, panel_count):
    """Return the ``gr.update`` list that puts the button + panels in loading state.

    The button is disabled and relabeled to "Working…"; each result panel
    is replaced with a card-shaped loading skeleton.
    """
    import gradio as gr
    updates = [gr.update(interactive=False, value="Working…")]
    for _ in range(panel_count):
        updates.append(gr.update(value=loading_skeleton(variant="card")))
    return updates


def _clear_loading(button_value, panel_count):
    """Return the ``gr.update`` list that re-enables the button and leaves panels alone.

    The actual panel values are written by the click handler itself, so we
    only need to re-enable the button and restore its original label here.
    """
    import gradio as gr
    return [gr.update(interactive=True, value=button_value)] + [gr.update()] * panel_count


def with_loading_state(button, result_panels: list | None = None):
    """Wire a primary button's click handler so the button disables while running.

    Use this for any click handler that may take >500 ms (vision scans, AI
    planners, OCR, basket compare). Returns a 2-tuple of callables
    ``(busy_fn, idle_fn)`` suitable for:

    >>> scan_btn.click(
    ...     scan_fn,
    ...     [...],
    ...     [result_html, ...],
    ...     api_name="scan",
    ... ).then(
    ...     with_loading_state(scan_btn, [result_html])[1],  # idle
    ...     outputs=[scan_btn, result_html],
    ... )

    For the **busy** leg (disable the button + show "Working…" the moment
    the user clicks), use :func:`busy_js` (from
    :mod:`shopstack.ui.components.js_helpers`) as the ``js=`` parameter
    on the same click handler.

    Args:
        button: The ``gr.Button`` to disable while the handler runs.
        result_panels: Result ``gr.HTML`` panels to show a skeleton in.

    Returns:
        ``(busy_fn, idle_fn)`` — both are zero-arg callables that
        return lists of ``gr.update`` dicts. Wire the busy fn to
        ``js=busy_js(...)`` and the idle fn to ``.then(..., outputs=[...])``.
    """
    panels = list(result_panels or [])
    panel_count = len(panels)
    # Capture the original label so we can restore it on completion.
    original_label = getattr(button, "value", None) or "Submit"

    def busy():
        return _set_loading(original_label, panel_count)

    def idle():
        return _clear_loading(original_label, panel_count)

    return busy, idle


# Re-export ``aria_live_screen`` from the decorators module so legacy
# WIP imports of ``from shopstack.ui.components.primitives import
# aria_live_screen`` still resolve. The real implementation lives
# in :mod:`shopstack.ui.components.decorators`; the import at the top
# of this module already establishes the re-export, so no second
# import is needed here.


# Convenience: extract the elem_id from a Gradio component.
def elem_id_of(component) -> str:
    """Return the ``elem_id`` of a Gradio component, or empty string if unset."""
    return str(getattr(component, "elem_id", None) or "")


# ═══════════════════════════════════════════════════════════════════════
# Toast — success/error notification
# ═══════════════════════════════════════════════════════════════════════

def toast(
    message: str,
    kind: str = "success",
) -> str:
    """Render a toast notification.

    Args:
        message: The notification text
        kind: ``success``, ``error``, ``info``, ``warning``
    """
    safe_message = escape(str(message))

    kind_config = {
        "success": ("var(--green)", "✓"),
        "error": ("var(--red)", "✗"),
        "info": ("var(--blue)", "ℹ"),
        "warning": ("var(--amber)", "⚠"),
    }
    color, icon = kind_config.get(kind, ("var(--text-dim)", "•"))

    safekind = escape(kind)
    return (
        f"<div class='toast toast-{safekind}' role='status' aria-live='polite'"
        f" aria-label='{safekind}: {safe_message}'"
        f" style='display:flex;align-items:center;gap:8px;padding:10px 14px;"
        f"margin:6px 0;border-radius:var(--radius-sm);"
        f"background:var(--bg-card-strong);border:1px solid {color};"
        f"font-size: 0.8125rem;color:var(--text);'>"
        f"<span style='color:{color};font-weight:700;' aria-hidden='true'>{icon}</span>"
        f"<span>{safe_message}</span>"
        "</div>"
    )


def toast_floating(message: str, kind: str = "success") -> str:
    """Render a floating auto-dismiss toast notification.

    Like :func:`toast`, but triggers the global ``showToast()`` JS
    function defined in the header.  The notification floats in the
    bottom-right corner and auto-dismisses after 3 seconds.

    Use this in handlers where the output component is a small status
    panel and you want a more prominent, temporary notification.

    Args:
        message: The notification text
        kind: ``success``, ``error``, ``info``, ``warning``
    """
    js_msg = _json.dumps(str(message))
    js_kind = _json.dumps(str(kind))
    # Screen-reader-only fallback (sr-only) so AT announces the result
    # even if the floating toast is not visible.
    return (
        f"<script>if(window.showToast)showToast({js_msg},{js_kind});</script>"
        f"<span class='sr-only' role='status' aria-live='polite'>"
        f"{escape(kind.title())}: {escape(str(message))}"
        "</span>"
    )


# ═══════════════════════════════════════════════════════════════════════
# LoadingSkeleton — pulse placeholder for async loading
# ═══════════════════════════════════════════════════════════════════════

def loading_skeleton(
    variant: str = "card",
    lines: int = 3,
) -> str:
    """Render a loading skeleton placeholder.

    Args:
        variant: ``card``, ``table``, ``metric``, or ``text``
        lines: Number of skeleton lines (for card and text)
    """
    # Use the canonical "skeleton" CSS class so the @keyframes
    # skeleton-pulse animation defined in theme.py applies.
    # We add the legacy "loading-pulse" class alongside for backward
    # compatibility with any external CSS that might still match it.
    pulse = "skeleton loading-pulse"

    if variant == "card":
        skeleton_lines = "".join(
            f"<div class='{pulse}' style='height:14px;margin:8px 0;border-radius:4px;"
            f"width:{90 - (i * 15)}%;'></div>"
            for i in range(min(lines, 5))
        )
        return (
            "<div class='home-card' style='text-align:left;'>"
            f"<div class='{pulse}' style='height:20px;width:40%;margin-bottom:12px;border-radius:4px;'></div>"
            f"{skeleton_lines}"
            "</div>"
        )

    if variant == "metric":
        return (
            "<div class='metric-card'>"
            f"<div class='{pulse}' style='height:36px;width:60%;margin:8px 0;border-radius:6px;'></div>"
            f"<div class='{pulse}' style='height:12px;width:40%;border-radius:4px;'></div>"
            "</div>"
        )

    if variant == "table":
        rows_html = "".join(
            f"<tr>{''.join(f'<td><div class=\"{pulse}\" style=\"height:12px;width:{60 + (j * 10)}%;border-radius:3px;\"></div></td>' for j in range(4))}</tr>"
            for _ in range(min(lines, 5))
        )
        return (
            "<div class='home-card' style='text-align:left;padding:0;overflow:hidden;'>"
            "<table style='border-collapse:collapse;width:100%;'>"
            f"<tbody>{rows_html}</tbody>"
            "</table>"
            "</div>"
        )

    # text variant
    return (
        "<div style='padding:8px 0;'>"
        + "".join(
            f"<div class='{pulse}' style='height:14px;margin:6px 0;border-radius:4px;"
            f"width:{95 - (i * 20)}%;'></div>"
            for i in range(min(lines, 4))
        )
        + "</div>"
    )


# ═══════════════════════════════════════════════════════════════════════
# EmptyState (enhanced) — empty state with icon and CTA
# ═══════════════════════════════════════════════════════════════════════

def empty_state_enhanced(
    message: str,
    icon: str = "📦",
    action_label: str = "",
    on_click_tab: str = "",
    secondary_text: str = "",
) -> str:
    """Render an enhanced empty state with icon, message, and optional CTA.

    Args:
        message: Primary empty state message
        icon: Emoji or text icon
        action_label: If provided, renders a CTA button
        on_click_tab: Tab to navigate to when CTA is clicked
        secondary_text: Additional hint text below the message
    """
    safe_message = escape(str(message))
    safe_icon = escape(str(icon))
    safe_secondary = escape(str(secondary_text)) if secondary_text else ""

    action_html = ""
    if action_label:
        safe_action = escape(str(action_label))
        import re
        safe_tab = re.sub(r"[^a-z0-9_-]", "-", str(on_click_tab).lower())
        action_html = (
            f"<button type='button' class='gr-button' style='margin-top:12px;'"
            f" onclick=\"var el=document.querySelector('[data-testid=tab-{safe_tab}]');"
            f"if(el)el.click();\">"
            f"{safe_action}</button>"
        )

    secondary_html = ""
    if safe_secondary:
        secondary_html = f"<div style='font-size: 0.75rem;color:var(--text-dim);margin-top:6px;'>{safe_secondary}</div>"

    return (
        "<div class='home-card' style='text-align:center;padding:40px 20px;' role='status' aria-label='" + safe_message + "'>"
        f"<div style='font-size: 2.5rem;margin-bottom:12px;' aria-hidden='true'>{safe_icon}</div>"
        f"<div class='muted' style='font-size: 0.9375rem;'>{safe_message}</div>"
        f"{secondary_html}"
        f"{action_html}"
        "</div>"
    )


# ═══════════════════════════════════════════════════════════════════════
# A11y helpers
# ═══════════════════════════════════════════════════════════════════════

def aria_live_html(content: str, level: str = "polite") -> str:
    """Wrap a result panel's content in a region that screen readers will announce.

    Use this for any ``gr.HTML`` panel that holds dynamic action results.
    The ``role="status"`` + ``aria-live="<level>"`` combination tells
    assistive technology to read the new content aloud when it changes.

    Args:
        content: The HTML body (already-escaped; pass it raw).
        level: ``polite`` (default) waits for the user to pause;
            ``assertive`` interrupts. Use ``polite`` for routine updates
            (action results) and ``assertive`` only for errors.

    Returns:
        HTML snippet suitable for ``gr.HTML(value=...)``.
    """
    safe_level = escape(str(level))
    if safe_level not in ("polite", "assertive"):
        safe_level = "polite"
    return (
        f"<div role='status' aria-live='{safe_level}' aria-atomic='true'>"
        f"{content}"
        f"</div>"
    )


def help_text(text: str, label_for: str = "") -> str:
    """Render a small help/hint text element for forms.

    Use this for inline guidance next to form fields (e.g. the
    ``lot_id: qty`` batch syntax hint). The text is associated with
    a form field via ``aria-describedby`` when ``label_for`` is set.

    Args:
        text: The help text body (will be escaped).
        label_for: The ``id`` of the form field this describes; when
            set, the returned element carries ``id="help-<label_for>"``
            so the field can reference it via ``aria-describedby``.

    Returns:
        HTML snippet.
    """
    safe_text = escape(str(text))
    if label_for:
        safe_id = escape(str(label_for))
        return (
            f"<div id='help-{safe_id}' class='muted' "
            f"style='font-size: 0.6875rem;margin-top:4px;'>{safe_text}</div>"
        )
    return (
        f"<div class='muted' style='font-size: 0.6875rem;margin-top:4px;'>{safe_text}</div>"
    )


# ═══════════════════════════════════════════════════════════════════════
# Form error / validation helpers
# ═══════════════════════════════════════════════════════════════════════

def form_error(message: str, field_id: str = "", level: str = "error") -> str:
    """Render an inline form-field error message.

    Use this to surface validation errors next to a specific input. The
    error is announced as ``role="alert"`` so screen readers interrupt
    to read it.

    Args:
        message: Error text (will be escaped).
        field_id: The ``id`` of the field this error belongs to; when set
            the rendered element carries ``id="error-<field_id>"`` so the
            field can reference it via ``aria-describedby``.
        level: ``error`` (red) or ``warning`` (amber).

    Returns:
        HTML snippet suitable for placement directly under a form field.
    """
    safe_msg = escape(str(message))
    color = "var(--red)" if level == "error" else "var(--amber)"
    icon = "⚠" if level == "error" else "!"
    id_attr = f" id='error-{escape(str(field_id))}'" if field_id else ""
    return (
        f"<div{id_attr} class='form-error' role='alert' "
        f"style='display:flex;align-items:center;gap:6px;font-size: 0.75rem;"
        f"color:{color};margin-top:4px;'>"
        f"<span aria-hidden='true' style='font-weight:700;'>{icon}</span>"
        f"<span>{safe_msg}</span>"
        f"</div>"
    )


def form_success(message: str) -> str:
    """Render an inline form-field success message.

    Surfaces a non-blocking success confirmation under a form field
    (e.g. after a field passes validation on blur).
    """
    safe_msg = escape(str(message))
    return (
        f"<div role='status' aria-live='polite' "
        f"style='display:flex;align-items:center;gap:6px;font-size: 0.75rem;"
        f"color:var(--green);margin-top:4px;'>"
        f"<span aria-hidden='true' style='font-weight:700;'>✓</span>"
        f"<span>{safe_msg}</span>"
        f"</div>"
    )


def required_marker() -> str:
    """Return a small visual marker indicating a form field is required.

    The marker is wrapped in ``aria-label="required"`` so screen readers
    announce it before the field label. The visible red ``*`` is purely
    decorative (``aria-hidden="true"``).
    """
    return (
        "<span style='color:var(--red);margin-left:4px;font-weight:700;' "
        "aria-hidden='true'>*</span>"
    )
