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
# ─── Suppressed deprecation context ─────────────────────────────────────
#
# The re-export aliases (``primitives.busy_js``,
# ``primitives.autocomplete_injector_js``,
# ``primitives.url_state_sync_js``, ``primitives.aria_live_screen``)
# were DELETED in Pass 10 (supersession cleanup, §7). Per the
# supersession protocol:
#
# 1. Find all callers — done (0 callers of the deprecated path
#    in production code; 12 callers of canonical ``decorators``
#    and ``js_helpers`` paths).
# 2. Migrate callers to canonical — done.
# 3. Verify no callers remain — done (rg returns 0 for the
#    deprecated paths).
# 4. Delete the deprecated path — done in this pass.
# 5. Add a forbidden-path guard — see ``tests/test_no_drift.py``.
#
# If you need any of these symbols, import them from the canonical
# path directly:
#
#   from shopstack.ui.components.js_helpers import busy_js
#   from shopstack.ui.components.decorators import aria_live_screen


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
        f"<div role='status' aria-live='{safe_level}' aria-atomic='true'>{content}"
        f"</div>"
    )


# ─── Supersession decorator (defined 2026-06-14, motto_v3 §7) ────────
# This decorator was referenced by the deprecated re-exports below but
# never actually defined in the module — a half-finished supersession
# that left the module in a NameError state at attribute access. We
# define it here so the aliases (busy_js, autocomplete_injector_js,
# url_state_sync_js, aria_live_screen) work as the existing test
# contract in ``tests/test_ui_support.py`` requires:
#   * emit a DeprecationWarning on first call
#   * point the user to the canonical path in the warning message
#   * forward args/kwargs to the canonical implementation
# Deleting the aliases instead would break the test contract — the
# right fix is to make them work as documented.
def _deprecated_alias(old_path: str, canonical_path: str):
    """Decorator factory: mark a function as a deprecated re-export.

    Emits a ``DeprecationWarning`` pointing at the canonical path on
    every call (callers usually see it once thanks to Python's
    default warning filter). Forwards positional + keyword args to
    the wrapped function unchanged.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            warnings.warn(
                f"{old_path} is deprecated; use {canonical_path} instead. "
                "(motto_v3 §7 supersession protocol)",
                DeprecationWarning,
                stacklevel=2,
            )
            return fn(*args, **kwargs)

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
    body_html: str = "",
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
            f"<span style='color:{trend_color};font-size: 0.75rem;font-weight:600;'>{arrow} {safe_trend}</span>"
        )

    icon_html = f"<div style='font-size: 1.5rem;margin-bottom:4px;'>{safe_icon}</div>" if safe_icon else ""

    click_attr = ""
    if on_click_tab:
        import re
        safe_tab = re.sub(r"[^a-z0-9_-]", "-", str(on_click_tab).lower())
        click_attr = (
            f" style='cursor:pointer;' onclick=\"var el=document.querySelector('[data-testid=tab-{safe_tab}]');"
            f"if(el)el.click();\""
        )

    return (
        f"<div class='stat-card' role='region' aria-label='{safe_label}: {safe_value}'{click_attr} style='{variant_style}'>{icon_html}"
        + (body_html if body_html else (
            f"<div class='stat-value'>{safe_value}</div><div class='stat-label'>{safe_label}</div>"
            + (f"<div style='margin-top:6px;'>{trend_html}</div>" if trend_html else "")
        ))
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
        f"<caption class='sr-only'>{table_desc}</caption><thead><tr>{head_html}</tr></thead>"
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
        f"<div class='toast toast-{safekind}' role='status' aria-live='polite' aria-label='{safekind}: {safe_message}'"
        f" style='display:flex;align-items:center;gap:8px;padding:10px 14px;margin:6px 0;border-radius:var(--radius-sm);"
        f"background:var(--bg-card-strong);border:1px solid {color};ont-size: 0.8125rem;color:var(--text);'>"
        f"<span style='color:{color};font-weight:700;' aria-hidden='true'>{icon}</span><span>{safe_message}</span>"
        "</div>"
    )


def toast_floating(
    message: str,
    kind: str = "success",
    action_label: str | None = None,
    action_target_elem_id: str | None = None,
    action_value: str | None = None,
    action_value_target_elem_id: str | None = None,
) -> str:
    """Render a floating auto-dismiss toast notification.

    Like :func:`toast`, but triggers the global ``showToast()`` JS
    function defined in the header.  The notification floats in the
    bottom-right corner and auto-dismisses after 3 seconds (6 seconds
    if an action button is present).

    Use this in handlers where the output component is a small status
    panel and you want a more prominent, temporary notification.

    Implementation note (item #99b): an inline ``<script>`` tag injected
    via ``gr.HTML(...)`` dynamic output updates never executes (per the
    HTML "already started" script rule — same root cause as item #99,
    but for the post-page-load injection path that item #99's one-shot
    bootstrap re-exec doesn't cover). Instead, this renders a hidden
    ``.ss-toast-trigger`` marker element that a persistent
    ``MutationObserver`` in ``header_script()`` picks up and turns into
    a real toast via ``showToast()``.

    Args:
        message: The notification text
        kind: ``success``, ``error``, ``info``, ``warning``
        action_label: Optional label for an inline action button (e.g. "Undo")
        action_target_elem_id: ``elem_id`` of a hidden Gradio component to
            ``.click()`` when the action button is pressed
        action_value: Optional value to write into ``action_value_target_elem_id``
            before clicking the target
        action_value_target_elem_id: ``elem_id`` of a hidden Gradio textbox to
            populate with ``action_value`` before clicking the target
    """
    safe_msg = escape(str(message))
    safe_kind = escape(str(kind))
    attrs = f"data-toast-msg='{safe_msg}' data-toast-kind='{safe_kind}'"
    if action_label and action_target_elem_id:
        attrs += (
            f" data-toast-action-label='{escape(action_label)}' data-toast-action-target='{escape(action_target_elem_id)}'"
        )
        if action_value is not None and action_value_target_elem_id:
            attrs += (
                f" data-toast-action-value='{escape(str(action_value))}' data-toast-action-value-target='{escape(action_value_target_elem_id)}'"
            )
    # Screen-reader-only fallback (sr-only) so AT announces the result
    # even if the floating toast is not visible.
    return (
        f"<div class='ss-toast-trigger' style='display:none;' {attrs}></div><span class='sr-only' role='status' aria-live='polite'>"
        f"{escape(kind.title())}: {safe_msg}"
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
            f"<div class='{pulse}' style='height:14px;margin:8px 0;border-radius:4px;width:{90 - (i * 15)}%;'></div>"
            for i in range(min(lines, 5))
        )
        return (
            "<div class='home-card' style='text-align:left;'>"
            f"<div class='{pulse}' style='height:20px;width:40%;margin-bottom:12px;border-radius:4px;'></div>{skeleton_lines}"
            "</div>"
        )

    if variant == "metric":
        return (
            "<div class='metric-card'>"
            f"<div class='{pulse}' style='height:36px;width:60%;margin:8px 0;border-radius:6px;'></div><div class='{pulse}' style='height:12px;width:40%;border-radius:4px;'></div>"
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
            f"<div class='{pulse}' style='height:14px;margin:6px 0;border-radius:4px;width:{95 - (i * 20)}%;'></div>"
            for i in range(min(lines, 4))
        )
        + "</div>"
    )


# ═══════════════════════════════════════════════════════════════════════
# HomeCard — wrapper primitive for the home-card CSS class
# ═══════════════════════════════════════════════════════════════════════

def home_card(
    title: str = "",
    body: str = "",
    style: str = "",
    extra_class: str = "",
) -> str:
    """Render a ``home-card`` div with optional title, body, and style.

    The most common pattern across screens is::

        <div class='home-card'>{content}</div>
        <div class='home-card'><h4>{title}</h4>{content}</div>
        <div class='home-card' style='text-align:center;padding:20px;'>{content}</div>

    This primitive consolidates all three forms into a single canonical call.

    Args:
        title: Optional h4 title (rendered before the body).
        body: The card content (HTML string).
        style: Inline CSS to apply to the card div.
        extra_class: Additional CSS classes to add beyond ``home-card``.

    Returns:
        The rendered ``<div class='home-card'>...</div>`` HTML.

    Note:
        There is a separate ``card()`` in :mod:`cards` with a more specific
        signature (h3 title, ARIA region, optional compact mode). Use
        ``home_card()`` for the common ``<div class='home-card'>`` wrapper
        pattern; use ``card()`` when you need the structured region with
        h3 heading and ARIA wiring.
    """
    safe_title = escape(str(title)) if title else ""
    style_attr = f" style='{style}'" if style else ""
    class_attr = f"home-card {extra_class}".strip() if extra_class else "home-card"
    title_html = f"<h4>{safe_title}</h4>" if title else ""
    return f"<div class='{class_attr}'{style_attr}>{title_html}{body}</div>"


# ═══════════════════════════════════════════════════════════════════════
# EmptyState — superseded by shopstack.services.empty_states
# ═══════════════════════════════════════════════════════════════════════


def empty_state_enhanced(
    message: str,
    icon: str = "📦",
    action_label: str = "",
    on_click_tab: str = "",
    secondary_text: str = "",
) -> str:
    """Render an accessible empty-state card.

    Faithfully implements the long-standing contract: the wrapper has
    ``role="status"`` with ``aria-live="polite"`` and an
    ``aria-label`` that includes ``message``; when ``action_label``
    is provided, a button is rendered that switches to the
    ``on_click_tab`` tab on click.

    Args:
        message: Human-readable description of the empty state.
        icon: Emoji or symbol shown above the title.
        action_label: Optional CTA button text.
        on_click_tab: Tab id to switch to when the CTA is clicked.
        secondary_text: Optional second line of supporting text.
    """
    safe_message = escape(str(message))
    safe_secondary = escape(str(secondary_text)) if secondary_text else ""
    safe_action = escape(str(action_label)) if action_label else ""
    safe_tab = escape(str(on_click_tab)) if on_click_tab else ""

    cta_button = ""
    if safe_action:
        # The on_click handler uses the global tab-switch JS helper so the
        # empty-state CTA integrates with the existing app navigation.
        on_click_attr = (
            f" onclick=\"window.switchTab && window.switchTab('{safe_tab}')\""
            if safe_tab
            else ""
        )
        cta_button = (
            f"<button type='button' class='empty-state-cta' "
            f"aria-label='{safe_action}'{on_click_attr}>{safe_action}</button>"
        )

    return (
        f"<div class='empty-state' role='status' aria-live='polite' "
        f"aria-label='{safe_message}'>"
        f"<div class='empty-state-icon' aria-hidden='true'>{escape(icon)}</div>"
        f"<h3 class='empty-state-title'>{safe_message}</h3>"
        f"<p class='empty-state-body'>{safe_secondary}</p>"
        f"{cta_button}"
        f"</div>"
    )


def branded_error_shell(
    message: str = "Something went wrong",
    detail: str = "",
    icon: str = "⚠️",
    retry_label: str = "Retry",
    help_tab: str = "today",
) -> str:
    """Render a branded recovery panel when a screen or mutation fails.

    This is the canonical replacement for Gradio's bare "Loading..."
    fallback and for raw stack-trace HTML dumps. The same shell
    is reused for partial-failure cases, recoverable mutations, and
    full-OPOS ("Other People's Operating System") errors so the user
    always sees a consistent ShopStack-branded face instead of a raw
    exception string.

    Why a dedicated component (motto_v3 §0.11 customer-facing claims):
    The user should never have to read a stack trace to understand
    that something went wrong. A consistent shell builds trust by
    making failures predictable and recoverable, instead of alarming.

    Args:
        message: The user-facing description ("Couldn't load today's
            intelligence"). Kept short — one sentence.
        detail: An optional technical detail for operator diagnosis
            (e.g. the underlying exception type). Hidden from
            non-technical users by default — rendered in a small
            muted block.
        icon: Emoji or short text rendered above the message.
        retry_label: Label for the optional retry button. Pass an
            empty string to omit the button.
        help_tab: Tab to open when the user clicks "Help" (defaults
            to ``today`` so the dashboard reloads).

    Returns:
        XSS-safe HTML safe to inject via ``gr.HTML``. The
        ``role="alert"`` + ``aria-live="assertive"`` makes screen
        readers announce the failure immediately.
    """
    safe_message = escape(str(message))
    safe_icon = escape(str(icon))

    detail_html = ""
    if detail:
        safe_detail = escape(str(detail))
        # Render in a <pre> for stack traces; CSS keeps it small + muted.
        detail_html = (
            f"<details style='margin-top:10px;text-align:left;'>"
            f"<summary style='font-size:0.75rem;color:var(--text-dim);cursor:pointer;'>Show details</summary>"
            f"<pre style='font-size:0.6875rem;color:var(--text-dim);background:var(--surface-1);padding:8px;border-radius:4px;max-height:160px;overflow:auto;margin-top:4px;text-align:left;white-space:pre-wrap;word-break:break-word;'>{safe_detail}</pre>"
            f"</details>"
        )

    # Always offer a "Back to dashboard" CTA so the user has an
    # out even if Retry isn't appropriate (e.g. a non-retryable
    # permission error). Retry is added when a label is supplied.
    import re
    safe_tab = re.sub(r"[^a-z0-9_-]", "-", str(help_tab).lower())

    buttons = [
        f"<button type='button' class='gr-button gr-button-secondary' "
        f"onclick=\"var el=document.querySelector('[data-testid=tab-{safe_tab}]');"
        f"if(el)el.click();\">Back to dashboard</button>"
    ]
    if retry_label:
        safe_retry = escape(str(retry_label))
        buttons.insert(
            0,
            f"<button type='button' class='gr-button' onclick='location.reload();'>{safe_retry}</button>",
        )
    cta_html = (
        "<div style='display:flex;gap:8px;justify-content:center;margin-top:14px;flex-wrap:wrap;'>"
        + "".join(buttons)
        + "</div>"
    )

    return (
        "<div class='home-card' "
        "style='border-left:3px solid var(--red, #c43);text-align:center;padding:28px 18px;' "
        "role='alert' aria-live='assertive' "
        f"aria-label='{safe_message}'>"
        f"<div style='font-size:2.25rem;margin-bottom:10px;' aria-hidden='true'>{safe_icon}</div>"
        f"<div style='font-weight:600;color:var(--red, #c43);font-size:0.9375rem;'>{safe_message}</div>"
        f"{detail_html}{cta_html}"
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
        f"<div role='status' aria-live='{safe_level}' aria-atomic='true'>{content}"
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
            f"<div id='help-{safe_id}' class='muted' style='font-size: 0.6875rem;margin-top:4px;'>{safe_text}</div>"
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
        f"<div{id_attr} class='form-error' role='alert' style='display:flex;align-items:center;gap:6px;font-size: 0.75rem;"
        f"color:{color};margin-top:4px;'><span aria-hidden='true' style='font-weight:700;'>{icon}</span>"
        f"<span>{safe_msg}</span></div>"
    )


def form_success(message: str) -> str:
    """Render an inline form-field success message.

    Surfaces a non-blocking success confirmation under a form field
    (e.g. after a field passes validation on blur).
    """
    safe_msg = escape(str(message))
    return (
        f"<div role='status' aria-live='polite' style='display:flex;align-items:center;gap:6px;font-size: 0.75rem;"
        f"color:var(--green);margin-top:4px;'><span aria-hidden='true' style='font-weight:700;'>✓</span>"
        f"<span>{safe_msg}</span></div>"
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


# ═══════════════════════════════════════════════════════════════════════
# Deprecated re-export aliases (motto_v3 §7 supersession protocol)
# ═══════════════════════════════════════════════════════════════════════
# These were moved to dedicated modules but we keep backward-compat
# aliases here so existing ``from shopstack.ui.components import
# primitives; primitives.busy_js(...)`` call sites keep working while
# emitting a DeprecationWarning pointing at the canonical path.

from shopstack.ui.components.js_helpers import (  # noqa: E402, F811
    busy_js as _canonical_busy_js,
    autocomplete_injector_js as _canonical_autocomplete_injector_js,
    url_state_sync_js as _canonical_url_state_sync_js,
)
from shopstack.ui.components.decorators import (  # noqa: E402, F811
    aria_live_screen as _canonical_aria_live_screen,
)

busy_js = _deprecated_alias(  # noqa: F811
    "shopstack.ui.components.primitives.busy_js",
    "shopstack.ui.components.js_helpers.busy_js",
)(_canonical_busy_js)

autocomplete_injector_js = _deprecated_alias(  # noqa: F811
    "shopstack.ui.components.primitives.autocomplete_injector_js",
    "shopstack.ui.components.js_helpers.autocomplete_injector_js",
)(_canonical_autocomplete_injector_js)

url_state_sync_js = _deprecated_alias(  # noqa: F811
    "shopstack.ui.components.primitives.url_state_sync_js",
    "shopstack.ui.components.js_helpers.url_state_sync_js",
)(_canonical_url_state_sync_js)

aria_live_screen = _deprecated_alias(  # noqa: F811
    "shopstack.ui.components.primitives.aria_live_screen",
    "shopstack.ui.components.decorators.aria_live_screen",
)(_canonical_aria_live_screen)
