from __future__ import annotations

from html import escape
import re
from typing import Any


def _safe_tab_id(tab_id: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "-", str(tab_id).lower())


def _tab_click_attr(tab_id: str) -> str:
    if not tab_id:
        return ""
    safe_tab = _safe_tab_id(tab_id)
    return (
        f" onclick=\"var el=document.querySelector('[data-testid=tab-{safe_tab}]');"
        f"if(el)el.click();\""
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
    return (
        f"<div class='home-card' style='text-align:left;{'' if compact else 'min-height:160px;'}'>"
        f"<h3>{escape(str(title))}</h3><div>{body}</div></div>"
    )


def render_hero_panel(title: str, subtitle: str, eyebrow: str = "Today") -> str:
    return (
        "<div class='home-card hero-panel'>"
        f"<div class='section-kicker'>{escape(str(eyebrow))}</div>"
        f"<h2>{escape(str(title))}</h2>"
        f"<p class='hero-copy'>{escape(str(subtitle))}</p>"
        "</div>"
    )


def render_action_tile(label: str, subtitle: str, tab_id: str, tone: str = "default") -> str:
    safe_tone = re.sub(r"[^a-z0-9_-]", "-", str(tone).lower()) or "default"
    return (
        f"<button type='button' class='action-tile action-tile-{safe_tone}'{_tab_click_attr(tab_id)}>"
        f"<span class='action-tile-label'>{escape(str(label))}</span>"
        f"<span class='action-tile-subtitle'>{escape(str(subtitle))}</span>"
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
        )
        for action in actions
    )
    return f"<div class='action-grid'>{tiles}</div>"


def empty_state(message: str) -> str:
    return (
        f"<div class='home-card' style='text-align:left;'>"
        f"<div class='muted'>{escape(str(message))}</div></div>"
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
        qty_line_markup = f"<div style='font-size:12px;margin-top:6px;'>{qty_line}</div>"
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
        "<div class='home-card item-card'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>"
        f"<strong>{safe_item_name}</strong>{badge}</div>"
        f"<div class='muted' style='font-size:13px;'>{safe_reason}</div>"
        f"{qty_line_markup}"
        f"<div class='muted' style='font-size:11px;margin-top:6px;'>Confidence: {confidence_pct:.0%}</div>"
        f"{action_line}"
        "</div>"
    )


def render_grouped_cards(title: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    rows = "".join(
        render_decision_card(
            item_name=item.get("canonical_name") or item.get("item_name", ""),
            decision=item.get("decision", "maybe"),
            reason=item.get("reason", ""),
            confidence=float(item.get("confidence", 0.0)),
            quantity=item.get("quantity", None),
            unit=item.get("unit", "unit"),
            show_actions=False,
        )
        for item in items
    )
    return card(title, rows)


def render_metric(name: str, value: str, hint: str = "", tab_id: str = "") -> str:
    click_attr = ""
    if tab_id:
        click_attr = (
            f" style='cursor:pointer;'"
            f"{_tab_click_attr(tab_id)}"
        )
    return (
        f"<div class='metric-card'{click_attr}>"
        f"<div class='metric-label'>{escape(str(name))}</div>"
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
    return (
        "<div class='home-card workflow-rail'>"
        "<div class='section-kicker'>Workflow Steps</div>"
        f"<div class='workflow-steps'>{rail}</div>"
        "</div>"
    )
