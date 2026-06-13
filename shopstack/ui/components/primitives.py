"""P1 Design System Components

ItemRow, StatCard, DataTable, ConfirmDialog, Toast, LoadingSkeleton.

Every component returns an HTML string. No Gradio dependencies.
All user/data-derived strings are escaped via html.escape().
"""

from __future__ import annotations

from html import escape
from typing import Any


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
            expiry_html = f"<span style='color:var(--red);font-size:11px;margin-left:8px;'>{abs(expiry_days)}d overdue</span>"
        elif expiry_days <= 3:
            expiry_html = f"<span style='color:var(--amber);font-size:11px;margin-left:8px;'>{expiry_days}d left</span>"

    # Price
    price_html = ""
    if price is not None and price > 0:
        price_html = f"<span style='font-weight:600;font-size:13px;'>₹{price:.0f}</span>"

    # Lot ID
    lot_html = f"<span style='font-family:monospace;font-size:10px;color:var(--text-faint);'>{safe_lot[:12]}</span>" if safe_lot else ""

    safe_aria_label = f"{safe_name}, {escape(qty_display)}"
    return (
        f"<div class='item-row' role='group' aria-label='{safe_aria_label}'>"
        # Left side: name + metadata
        "<div>"
        f"<div style='font-weight:600;color:var(--text);'>{safe_name}</div>"
        + (f"<div style='font-size:11px;color:var(--text-dim);'>{safe_location}" + (f" &middot; {lot_html}" if lot_html else "") + "</div>" if safe_location or lot_html else "")
        + (f"<div style='font-size:11px;color:var(--text-dim);'>{escape(str(extra))}</div>" if extra else "")
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
        value: Large display value (e.g. ``\"12\"``, ``\"₹340\"``)
        label: Label below the value
        icon: Emoji or text icon (placed above value)
        trend: ``up``, ``down``, or ``stable``
        trend_value: Secondary trend text (e.g. ``\"+12%\"``)
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
            f"<span style='color:{trend_color};font-size:12px;font-weight:600;'>"
            f"{arrow} {safe_trend}</span>"
        )

    icon_html = f"<div style='font-size:24px;margin-bottom:4px;'>{safe_icon}</div>" if safe_icon else ""

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
        + ("<span style='font-size:9px;margin-left:4px;opacity:0.4;'>&#9650;&#9660;</span>" if sortable else "")
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
            "<div style='text-align:center;padding:8px;color:var(--text-dim);font-size:12px;'>"
            f"Showing {page_size} of {len(rows)} items"
            "</div>"
        )

    table_desc = escape(str(empty_message)) if empty_message != "No data" else "data table"
    return (
        "<div class='home-card' style='text-align:left;padding:0;overflow:hidden;' role='region' aria-label='Table: " + table_desc + "'>"
        "<table style='border-collapse:collapse;width:100%;font-size:13px;'>"
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
        "<span style='font-size:20px;' aria-hidden='true'>&#9888;</span>"
        "<div>"
        f"<div style='font-weight:600;margin-bottom:4px;'>{safe_message}</div>"
        "<div style='font-size:11px;color:var(--text-dim);'>"
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

    safe_kind = escape(kind)
    return (
        f"<div class='toast toast-{safe_kind}' role='status' aria-live='polite'"
        f" aria-label='{safe_kind}: {safe_message}'"
        f" style='display:flex;align-items:center;gap:8px;padding:10px 14px;"
        f"margin:6px 0;border-radius:var(--radius-sm);"
        f"background:var(--bg-card-strong);border:1px solid {color};"
        f"font-size:13px;color:var(--text);'>"
        f"<span style='color:{color};font-weight:700;' aria-hidden='true'>{icon}</span>"
        f"<span>{safe_message}</span>"
        "</div>"
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
    pulse = "loading-pulse"

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
        secondary_html = f"<div style='font-size:12px;color:var(--text-dim);margin-top:6px;'>{safe_secondary}</div>"

    return (
        "<div class='home-card' style='text-align:center;padding:40px 20px;' role='status' aria-label='" + safe_message + "'>"
        f"<div style='font-size:40px;margin-bottom:12px;' aria-hidden='true'>{safe_icon}</div>"
        f"<div class='muted' style='font-size:15px;'>{safe_message}</div>"
        f"{secondary_html}"
        f"{action_html}"
        "</div>"
    )
