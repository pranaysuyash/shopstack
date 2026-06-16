from __future__ import annotations

from html import escape
import re
from typing import Any
from shopstack.schemas.models import DecisionResult, _ACTION_COLORS, _ACTION_ICONS
from shopstack.module_registry import tab_label
from shopstack.ui.components.primitives import home_card


_CARD_ID_COUNTER: int = 0


def _next_card_id() -> str:
    global _CARD_ID_COUNTER
    _CARD_ID_COUNTER += 1
    return f"card-{_CARD_ID_COUNTER}"


def _safe_tab_id(tab_id: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "-", str(tab_id).lower())


def _tab_click_attr(tab_id: str) -> str:
    if not tab_id:
        return ""
    safe_tab = _safe_tab_id(tab_id)
    target_label = tab_label(tab_id)
    return (
        " onclick=\"(function(){"
        f"var label={target_label!r};"
        "var tabs=Array.from(document.querySelectorAll('button[role=tab], [role=tab]'));"
        "var el=tabs.find(function(btn){return (btn.textContent||'').trim()===label;})"
        "||document.querySelector('[data-testid=tab-" + safe_tab + "]');"
        "if(el)el.click();"
        "})();\""
    )


def list_to_table(items: list[dict[str, Any]], cols: list[str] | None = None) -> list[list[str]]:
    if not items:
        return [["No data"]]
    if cols is None:
        cols = list(items[0].keys())
    header = [c.replace("_", " ").title() for c in cols]
    rows = [[str(item.get(c, "")) for c in cols] for item in items]
    return [header] + rows


def badge_html(label: str, variant: str = "neutral") -> str:
    classes = {
        "green": "badge-green",
        "amber": "badge-amber",
        "red": "badge-red",
        "blue": "badge-blue",
        "gray": "badge-gray",
    }
    cls = classes.get(variant, classes["gray"])
    return f"<span class='badge {cls}'>{escape(str(label))}</span>"


def card(title: str, body: str, *, compact: bool = True) -> str:
    safe_title = escape(str(title))
    card_id = _next_card_id()
    return (
        f"<div class='home-card' style='text-align:left;{'min-height:160px;' if not compact else ''}'"
        f" role='region' aria-labelledby='{card_id}'><h3 id='{card_id}'>{safe_title}</h3><div>{body}</div></div>"
    )


def render_hero_panel(title: str, subtitle: str, eyebrow: str = "Today") -> str:
    return home_card(
        extra_class="hero-panel",
        body=(
            f"<div class='section-kicker'>{escape(str(eyebrow))}</div><h2>{escape(str(title))}</h2>"
            f"<p class='hero-copy'>{escape(str(subtitle))}</p>"
        ),
    )


def render_action_tile(
    label: str,
    subtitle: str,
    tab_id: str = "",
    tone: str = "default",
    custom_onclick: str = "",
) -> str:
    """Render a single clickable tile (action button) for the action grid.

    Args:
        label: The button text (e.g., "Set up my household").
        subtitle: Helper text below the label.
        tab_id: The Gradio tab ID to jump to when clicked. Used by the
            default tab-jump onclick. Ignored if ``custom_onclick`` is
            provided.
        tone: Visual tone ("default" | "primary" | "secondary" | ...).
        custom_onclick: Optional raw JavaScript body that runs when the
            tile is clicked (instead of the default tab-jump). Use this
            for actions that need to toggle a hidden Gradio component
            (e.g., the onboarding wizard) or call an API. The string
            is inserted into ``onclick="(function(){ <body> })();"``.

    Returns:
        A string of HTML for a single ``<button>`` tile.
    """
    safe_tone = re.sub(r"[^a-z0-9_-]", "-", str(tone).lower()) or "default"
    safe_label = escape(str(label))
    if custom_onclick:
        # Per motto_v3 0.13 (scope expansion control), the custom
        # onclick body is escaped minimally: backslashes and quotes
        # are escaped so the resulting HTML attribute is well-formed.
        # The caller is responsible for using a safe API surface
        # (e.g., gr.update via the proper JS API, not arbitrary
        # innerHTML injection).
        safe_body = (
            str(custom_onclick)
            .replace("\\", "\\\\")
            .replace("\"", "\\\"")
        )
        onclick_attr = f" onclick=\"(function(){{{safe_body}}})();\""
    else:
        onclick_attr = _tab_click_attr(tab_id)
    return (
        f"<button type='button' class='action-tile action-tile-{safe_tone}' aria-label='{safe_label}: {escape(str(subtitle))}'{onclick_attr}>"
        f"<span class='action-tile-label'>{safe_label}</span><span class='action-tile-subtitle'>{escape(str(subtitle))}</span>"
        "</button>"
    )


def render_action_grid(actions: list[dict[str, str]]) -> str:
    if not actions:
        return ""
    tiles = "".join(
        render_action_tile(
            action.get("label", ""),
            action.get("subtitle", ""),
            action.get("tab_id", ""),
            action.get("tone", "default"),
            action.get("custom_onclick", ""),
        )
        for action in actions
    )
    return f"<div class='action-grid'>{tiles}</div>"


def empty_state(message: str) -> str:
    return home_card(
        style="text-align:left;",
        body=f"<div class='muted'>{escape(str(message))}</div>",
    )


def render_rows(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return "<div class='muted'>No entries</div>"
    return "".join(
        "<div class='item-row'>"
        f"<div>{escape(str(label))}</div><div>{escape(str(value))}</div></div>"
        for label, value in rows
    )


def render_decision_card(
    item_name: str,
    decision: str,
    reason: str,
    confidence: float,
    quantity: float | None = None,
    unit: str = "unit",
    show_actions: bool = False,
) -> str:
    decision_upper = str(decision).upper()
    badge_map = {
        "buy": "green",
        "skip": "blue",
        "maybe": "amber",
        "use_soon": "amber",
        "optional": "blue",
        "low": "red",
    }
    badge = badge_html(decision_upper, badge_map.get(str(decision), "gray"))
    safe_unit = escape(str(unit))
    qty_line = f"{quantity} {safe_unit} suggested" if quantity else ""
    qty_line_markup = ""
    if qty_line:
        qty_line_markup = f"<div style='font-size: 0.75rem;margin-top:6px;'>{qty_line}</div>"
    confidence_pct = max(0.0, min(1.0, float(confidence)))
    action_line = (
        "<div style='margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;'>"
        "<span class='chip'>Action requires confirmation</span>"
        "</div>"
        if show_actions
        else ""
    )
    safe_item_name = escape(str(item_name))
    safe_reason = escape(str(reason))
    return (
        f"<div class='home-card item-card' role='article' aria-label='{safe_item_name}: {decision_upper}'><div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>"
        f"<strong>{safe_item_name}</strong>{badge}</div><div class='muted' style='font-size: 0.8125rem;'>{safe_reason}</div>"
        f"{qty_line_markup}<div class='muted' style='font-size: 0.6875rem;margin-top:6px;'>Confidence: {confidence_pct:.0%}</div>"
        f"{action_line}"
        "</div>"
    )

def render_unified_decision_card(d: DecisionResult) -> str:
    color = _ACTION_COLORS.get(d.action, "var(--text-dim)")
    icon = _ACTION_ICONS.get(d.action, "")
    badge = (
        f"<span style='background:{color}20;color:{color};padding:2px 8px;border-radius:4px;font-size: 0.6875rem;font-weight:600;'>"
        f"{icon} {d.action.upper()}</span>"
    )
    
    price_info = f" \u20b9{d.market_price_per_kg:.0f}/kg" if d.market_price_per_kg else ""
    reason = escape(d.reason) if d.reason else "No reason"
    
    warnings_html = ""
    for w in d.warnings:
        warnings_html += f"<div style='font-size: 0.6875rem;color:var(--red);margin-top:4px;'>\u26A0 {escape(w.message)}</div>"
        
    stale_html = ""
    if d.data_freshness == "stale":
        # Brand-aligned stale warning.  Use the bright red text variant in
        # dark mode (--red-text token) because the dark --red is too dim
        # against the 10%-alpha red tinted background.
        stale_html = (
            f"<div style='font-size: 0.75rem;color:var(--red-text, var(--red));font-weight:bold;margin-top:6px;padding:4px;background-color:rgba(166,63,49,0.10);border-radius:4px;'>"
            f"&#9888; WARNING: {escape(d.data_freshness_label or 'Stale Market Data (Older than 24h)')}</div>"
        )
        
    evidence_html = ""
    if d.evidence:
        ev_list = ", ".join(f"{escape(str(e.source))}: {escape(str(e.value))}" for e in d.evidence[:2])
        evidence_html = f"<div style='font-size: 0.6875rem;color:var(--text-dim);margin-top:4px;'>Evidence: {ev_list}</div>"

    action_btn = ""
    if d.action in ("buy", "optional", "compare", "use_soon"):
        # Visual affordance button — Gradio interactions are driven by gr.Button components,
        # not inline JS. This button surfaces the recommended action with a data-action
        # attribute for accessibility and future JS wiring without alert() stubs.
        action_label = d.action.replace("_", " ").title()
        action_btn = (
            f"<div style='margin-top:8px;'><button type='button' class='action-tile action-tile-default'"
            f" style='padding:4px 8px;font-size: 0.6875rem;cursor:default;' data-action='{escape(d.action)}'"
            f" data-canonical='{escape(d.canonical_name)}' aria-label='{escape(action_label)} {escape(d.display_name)}'"
            f">{escape(action_label)} →</button></div>"
        )

    return home_card(
        style=f"margin-bottom:10px;border-left:4px solid {color};",
        body=(
            f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<strong style='font-size: 0.875rem;'>{escape(d.display_name)}</strong>{badge}</div><div style='font-size: 0.8125rem;margin-top:4px;'>{reason}{price_info}</div>"
            f"{evidence_html}{warnings_html}{stale_html}{action_btn}"
        ),
    )


def render_grouped_cards(title: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    from shopstack.schemas.models import DecisionResult
    
    rows = ""
    for item in items:
        dr = DecisionResult(
            canonical_name=item.get("canonical_name") or item.get("item_name", ""),
            display_name=item.get("display_name") or item.get("canonical_name") or item.get("item_name", ""),
            action=item.get("decision", "maybe"),
            confidence=float(item.get("confidence", 0.0)),
            reasons=[item.get("reason", "")],
            unit=item.get("unit", "unit")
        )
        # If there are any stale warnings or evidence in the dict, map them if possible
        if item.get("data_freshness"):
            dr.data_freshness = item["data_freshness"]
        if item.get("data_freshness_label"):
            dr.data_freshness_label = item["data_freshness_label"]
            
        rows += render_unified_decision_card(dr)

    return card(title, rows)


def render_metric(name: str, value: str, hint: str = "", tab_id: str = "") -> str:
    click_attr = ""
    if tab_id:
        click_attr = (
            f" style='cursor:pointer;'{_tab_click_attr(tab_id)}"
        )
    return (
        f"<div class='metric-card'{click_attr}><div class='metric-label'>{escape(str(name))}</div>"
        f"<div class='metric-value'>{escape(str(value))}</div>"
        + (f"<div class='metric-hint'>{escape(str(hint))}</div>" if hint else "")
        + "</div>"
    )


def render_workflow_rail(steps: list[str], current_step: int | None = None) -> str:
    step_markers: list[str] = []
    total = len(steps)
    active = total - 1 if current_step is None else max(0, min(current_step, total - 1))
    for index, step in enumerate(steps):
        state_class = "is-complete" if current_step is None or index <= active else "is-pending"
        label = escape(str(step).upper())
        step_markers.append(
            f"<span class='workflow-step {state_class}'>{label}</span>"
        )
    rail = "".join(
        step + ("<span class='workflow-arrow'>→</span>" if idx + 1 < len(step_markers) else "")
        for idx, step in enumerate(step_markers)
    )
    return home_card(
        extra_class="workflow-rail",
        body=(
            "<div class='section-kicker'>Workflow Steps</div>"
            f"<div class='workflow-steps'>{rail}</div>"
        ),
    )
