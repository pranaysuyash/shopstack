from __future__ import annotations

from html import escape
import re
from typing import Any


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


def empty_state(message: str) -> str:
    return (
        f"<div class='home-card' style='text-align:left;'>"
        f"<div style='color:var(--text-dim);'>{escape(str(message))}</div></div>"
    )


def render_rows(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return "<div style='color:var(--text-dim);'>No entries</div>"
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
        f"<div style='font-size:13px;color:var(--text-dim);'>{safe_reason}</div>"
        f"{qty_line_markup}"
        f"<div style='font-size:11px;margin-top:6px;color:var(--text-dim);'>Confidence: {confidence_pct:.0%}</div>"
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
        safe_tab = re.sub(r"[^a-z0-9_-]", "-", tab_id.lower())
        click_attr = (
            f" style='cursor:pointer;'"
            f" onclick=\"var el=document.querySelector('[data-testid=tab-{safe_tab}]');"
            f"if(el)el.click();\""
        )
    return (
        f"<div class='metric-card'{click_attr}>"
        f"<div style='font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.4px'>{escape(str(name))}</div>"
        f"<div style='font-size:34px;font-weight:700;margin-top:6px'>{escape(str(value))}</div>"
        + (f"<div style='color:var(--text-dim);font-size:11px;margin-top:6px'>{escape(str(hint))}</div>" if hint else "")
        + "</div>"
    )


def render_workflow_rail(steps: list[str], current_step: int | None = None) -> str:
    step_markers: list[str] = []
    total = len(steps)
    active = total - 1 if current_step is None else max(0, min(current_step, total - 1))
    for index, step in enumerate(steps):
        if current_step is None or index <= active:
            dot = "●"
            tone = "var(--green)"
        else:
            dot = "○"
            tone = "var(--text-dim)"
        label = escape(str(step).upper())
        step_markers.append(
            f"<span style='display:inline-flex;align-items:center;gap:6px;color:{tone};font-size:11px;font-weight:600;'>"
            f"{dot} {label}</span>"
        )
    rail = "".join(
        f"{step}{'→' if idx + 1 < len(step_markers) else ''}"
        for idx, step in enumerate(step_markers)
    )
    return (
        "<div class='home-card' style='text-align:left;padding:12px 14px;'>"
        f"<div style='font-size:12px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.4px;margin-bottom:6px;'>"
        "Workflow Steps</div>"
        f"<div style='display:flex;flex-wrap:wrap;gap:8px;align-items:center;'>{rail}</div>"
        "</div>"
    )
