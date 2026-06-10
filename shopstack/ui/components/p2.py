"""P2 Design System Components

SearchInput, FilterBar, PaginationFooter, Timeline, PriceChart wrapper,
LocationCard.  Every component returns an HTML string.  No Gradio
dependency in the signatures — callers pass rendered HTML or data.
"""

from __future__ import annotations

from html import escape
from typing import Any


# ══════════════════════════════════════════════════════════════════════
# SearchInput — styled wrapper for Gradio Textbox search
# ══════════════════════════════════════════════════════════════════════

def search_input(
    placeholder: str = "Search...",
    value: str = "",
    input_id: str = "search-input",
    *,
    show_clear: bool = True,
) -> str:
    """Return an HTML search input wrapper.

    This is a *visual* wrapper — the actual Gradio Textbox is still needed
    for interactivity.  Use this inside a gr.HTML block to provide a
    consistent search bar look.
    """
    clear_btn = ""
    if show_clear and value:
        clear_btn = (
            "<button type='button' class='search-clear' "
            "onclick=\"var el=document.getElementById('search-input');"
            "if(el){el.value='';el.dispatchEvent(new Event('input',{bubbles:true}));}\""
            " aria-label='Clear search'>&times;</button>"
        )
    return (
        "<div class='search-input-wrapper'>"
        "<span class='search-icon' aria-hidden='true'>&#9906;</span>"
        f"<input id='{escape(input_id)}' type='search' class='search-input-field' "
        f"placeholder='{escape(placeholder)}' value='{escape(value)}' "
        "autocomplete='off' spellcheck='false'>"
        f"{clear_btn}"
        "</div>"
    )


# ══════════════════════════════════════════════════════════════════════
# FilterBar — chip-based filter display
# ══════════════════════════════════════════════════════════════════════

def filter_bar(
    filters: list[dict[str, Any]],
    active_count: int = 0,
    *,
    on_clear_all: str = "",
) -> str:
    """Render a horizontal bar of filter chips.

    Args:
        filters: List of {label, key, active: bool, count: int | None}
        active_count: Total number of active filters
        on_clear_all: JavaScript for "Clear all" click (e.g. Gradio event trigger)
    """
    if not filters:
        return ""
    chips = "".join(
        "<button type='button' "
        f"class='filter-chip{' is-active' if f.get('active') else ''}' "
        f"data-filter-key='{escape(str(f.get('key', '')))}' "
        f"aria-pressed='{'true' if f.get('active') else 'false'}'>"
        f"{escape(str(f.get('label', '')))}"
        + (f"<span class='filter-chip-count'>{f['count']}</span>" if f.get("count") is not None else "")
        + "</button>"
        for f in filters
    )
    clear_all = ""
    if active_count > 0:
        clear_all = (
            "<button type='button' class='filter-clear-all' "
            f"onclick=\"{escape(on_clear_all)}\">"
            f"Clear all ({active_count})</button>"
        )
    return (
        "<div class='filter-bar'>"
        f"<div class='filter-chips'>{chips}</div>"
        f"{clear_all}"
        "</div>"
    )


# ══════════════════════════════════════════════════════════════════════
# PaginationFooter
# ══════════════════════════════════════════════════════════════════════

def pagination_footer(
    current_page: int,
    total_pages: int,
    total_items: int,
    page_size: int = 25,
    *,
    on_page_click: str = "",   # JS function name or expression
) -> str:
    """Render page navigation controls.

    Args:
        current_page: 1-indexed current page
        total_pages: Total number of pages
        total_items: Total number of items across all pages
        page_size: Items per page
        on_page_click: JavaScript to execute on page click (receives page number)
    """
    if total_pages <= 1:
        return ""

    start_item = (current_page - 1) * page_size + 1
    end_item = min(current_page * page_size, total_items)

    # Page number buttons (max 7 visible)
    pages: list[int | str] = []
    if total_pages <= 7:
        pages = list(range(1, total_pages + 1))
    else:
        pages.append(1)
        if current_page > 3:
            pages.append("...")
        for p in range(max(2, current_page - 1), min(total_pages, current_page + 2)):
            pages.append(p)
        if current_page < total_pages - 2:
            pages.append("...")
        pages.append(total_pages)

    page_buttons = "".join(
        "<button type='button' "
        f"class='page-btn{' is-current' if p == current_page else ''}' "
        + (f"onclick=\"{on_page_click.replace('{page}', str(p)) if on_page_click else ''}\" "
           if p != "..." and on_page_click else "")
        + (f"disabled" if p == "..." else "")
        + f">{p}</button>"
        for p in pages
    )

    prev_btn = (
        "<button type='button' class='page-btn' "
        f"onclick=\"{on_page_click.replace('{page}', str(current_page - 1)) if on_page_click else ''}\" "
        + ("disabled" if current_page <= 1 else "")
        + ">&lsaquo; Prev</button>"
    )
    next_btn = (
        "<button type='button' class='page-btn' "
        f"onclick=\"{on_page_click.replace('{page}', str(current_page + 1)) if on_page_click else ''}\" "
        + ("disabled" if current_page >= total_pages else "")
        + ">Next &rsaquo;</button>"
    )

    return (
        "<div class='pagination-footer'>"
        f"<span class='pagination-info'>Showing {start_item}&ndash;{end_item} of {total_items}</span>"
        f"<div class='pagination-controls'>{prev_btn}{page_buttons}{next_btn}</div>"
        "</div>"
    )


# ══════════════════════════════════════════════════════════════════════
# Timeline — trace step visualisation
# ══════════════════════════════════════════════════════════════════════

def timeline(
    steps: list[dict[str, str]],
    *,
    current_step: int = -1,
) -> str:
    """Render a vertical timeline of workflow steps.

    Args:
        steps: List of {label, value, status} where status is
               'complete' | 'active' | 'pending' | 'error'
        current_step: Index of the active step (-1 = all complete)
    """
    if not steps:
        return "<div class='muted'>No steps recorded.</div>"

    step_html = ""
    for i, step in enumerate(steps):
        label = escape(str(step.get("label", f"Step {i + 1}")))
        value = escape(str(step.get("value", "")))
        status = step.get("status", "pending")

        dot_class = {
            "complete": "tl-dot-complete",
            "active": "tl-dot-active",
            "error": "tl-dot-error",
            "pending": "tl-dot-pending",
        }.get(status, "tl-dot-pending")

        connector = ""
        if i < len(steps) - 1:
            next_status = steps[i + 1].get("status", "pending")
            connector_class = "tl-connector-complete" if status == "complete" else "tl-connector"
            connector = f"<div class='timeline-connector {connector_class}'></div>"

        step_html += (
            "<div class='timeline-step'>"
            f"<div class='timeline-dot {dot_class}'></div>"
            "<div class='timeline-content'>"
            f"<div class='timeline-label'>{label}</div>"
            f"<div class='timeline-value'>{value}</div>"
            "</div>"
            "</div>"
            f"{connector}"
        )

    return (
        "<div class='home-card' style='text-align:left;'>"
        "<h3>Workflow Timeline</h3>"
        f"<div class='timeline'>{step_html}</div>"
        "</div>"
    )


# ══════════════════════════════════════════════════════════════════════
# PriceChart — wrapper for Gradio LinePlot empty-state handling
# ══════════════════════════════════════════════════════════════════════

def price_chart_empty_state(item_name: str = "") -> str:
    """Return an empty-state placeholder for a price chart."""
    label = escape(item_name) if item_name else "this item"
    return (
        "<div class='home-card' style='text-align:center;padding:40px 20px;'>"
        "<div class='section-kicker'>Price Trend</div>"
        f"<div class='muted' style='font-size:14px;margin-top:8px;'>"
        f"No price data yet for {label}.</div>"
        "<div class='muted' style='font-size:12px;margin-top:4px;'>"
        "Record purchases with price to build trend history.</div>"
        "</div>"
    )


def price_summary_card(
    item_name: str,
    latest_price: float | None,
    best_price: float | None,
    best_store: str = "",
    observation_count: int = 0,
    direction: str = "",  # "up" | "down" | "stable"
) -> str:
    """Render a summary card for price intelligence."""
    safe_name = escape(item_name)
    if not latest_price or observation_count == 0:
        return (
            "<div class='home-card' style='text-align:left;'>"
            f"<h3>{safe_name}</h3>"
            "<div class='muted'>No price observations yet.</div>"
            "</div>"
        )

    direction_icon = {"up": "&#8593;", "down": "&#8595;", "stable": "&#8594;"}.get(direction, "")
    direction_color = {
        "up": "var(--red)", "down": "var(--green)", "stable": "var(--text-dim)"
    }.get(direction, "var(--text-dim)")

    parts = [
        "<div class='home-card' style='text-align:left;'>",
        f"<h3>{safe_name}</h3>",
        "<div style='display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;'>",
        f"<div><div class='stat-value'>"
        f"&pound;{latest_price:.0f}</div>"
        f"<div class='stat-label'>Latest price</div></div>",
    ]
    if best_price is not None:
        parts.append(
            f"<div><div class='stat-value'>"
            f"&pound;{best_price:.0f}</div>"
            f"<div class='stat-label'>Best ({escape(best_store[:15]) if best_store else 'all stores'})</div></div>"
        )
    parts.append(
        f"<div><div class='stat-value' style='color:{direction_color};'>"
        f"{direction_icon}</div>"
        f"<div class='stat-label'>Trend</div></div>"
    )
    parts.append(
        f"<div><div class='stat-value'>{observation_count}</div>"
        f"<div class='stat-label'>Observations</div></div>"
    )
    parts.append("</div></div>")
    return "".join(parts)


# ══════════════════════════════════════════════════════════════════════
# LocationCard — household location display
# ══════════════════════════════════════════════════════════════════════

def location_card(
    location_name: str,
    location_type: str = "",
    item_count: int = 0,
    items_preview: list[str] | None = None,
    parent_name: str = "",
    *,
    is_expanded: bool = False,
) -> str:
    """Render a household location card.

    Args:
        location_name: Display name of the location
        location_type: e.g. 'fridge', 'pantry', 'cabinet'
        item_count: Number of items stored at this location
        items_preview: List of item descriptions (name + quantity)
        parent_name: Parent location name for hierarchy display
        is_expanded: Whether to show item preview expanded
    """
    safe_name = escape(location_name)
    safe_type = escape(location_type)
    safe_parent = escape(parent_name)

    type_badge = ""
    type_icons = {
        "fridge": "&#10053;", "freezer": "&#10053;",
        "pantry": "&#9783;", "cabinet": "&#9776;",
        "drawer": "&#9776;", "shelf": "&#9783;",
    }
    icon = type_icons.get(location_type.lower(), "")
    if icon or location_type:
        type_badge = (
            f"<span class='chip' style='font-size:10px;'>"
            f"{icon} {safe_type}</span>"
        )

    hierarchy = f"<span style='color:var(--text-dim);font-size:11px;'>&#x2192; {safe_parent}</span>" if parent_name else ""

    count_badge = ""
    if item_count > 0:
        count_badge = f"<span class='badge badge-blue'>{item_count} items</span>"
    else:
        count_badge = "<span class='badge badge-gray'>empty</span>"

    items_html = ""
    if items_preview:
        items_html = (
            "<div style='margin-top:8px;font-size:11px;color:var(--text-dim);'>"
            + "".join(f"<div class='item-row' style='padding:2px 0;'>{escape(item)}</div>" for item in items_preview[:8])
            + (
                f"<div class='muted' style='margin-top:4px;'>"
                f"... and {len(items_preview) - 8} more</div>"
                if len(items_preview) > 8
                else ""
            )
            + "</div>"
        )

    expand_attr = ""
    if items_preview and len(items_preview) > 0:
        expand_attr = " style='cursor:pointer;'"

    return (
        "<div class='home-card' style='text-align:left;margin-bottom:8px;'>"
        "<div style='display:flex;justify-content:space-between;align-items:center;'>"
        "<div>"
        f"<div style='font-weight:600;color:var(--text);'>{safe_name}</div>"
        f"<div style='font-size:11px;color:var(--text-dim);'>{type_badge} {hierarchy}</div>"
        "</div>"
        f"<div>{count_badge}</div>"
        "</div>"
        f"{items_html}"
        "</div>"
    )
