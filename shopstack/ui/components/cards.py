from __future__ import annotations

from typing import Any


def badge_html(label: str, variant: str = "neutral") -> str:
    classes = {
        "green": "badge-green",
        "amber": "badge-amber",
        "red": "badge-red",
        "blue": "badge-blue",
        "gray": "badge-gray",
    }
    cls = classes.get(variant, classes["gray"])
    return f"<span class='badge {cls}'>{label}</span>"


def card(title: str, body: str, *, compact: bool = True) -> str:
    return (
        f"<div class='home-card' style='text-align:left;{'' if compact else 'min-height:160px;'}'>"
        f"<h3>{title}</h3><div>{body}</div></div>"
    )


def empty_state(message: str) -> str:
    return (
        f"<div class='home-card' style='text-align:left;'>"
        f"<div style='color:var(--text-dim);'>{message}</div></div>"
    )


def render_rows(rows: list[tuple[str, str]]) -> str:
    if not rows:
        return "<div style='color:var(--text-dim);'>No entries</div>"
    return "".join(
        "<div class='item-row'>"
        f"<div>{label}</div><div>{value}</div></div>"
        for label, value in rows
    )


def render_decision_card(
    item_name: str,
    decision: str,
    reason: str,
    confidence: float,
    quantity: float | None = None,
    unit: str = "unit",
    show_actions: bool = True,
) -> str:
    decision_upper = decision.upper()
    badge_map = {
        "buy": "green",
        "skip": "blue",
        "maybe": "amber",
        "use_soon": "amber",
        "optional": "blue",
        "low": "red",
    }
    badge = badge_html(decision_upper, badge_map.get(decision, "gray"))
    qty_line = f"{quantity} {unit} suggested" if quantity else ""
    action_line = (
        "<div style='margin-top:8px;display:flex;gap:8px;flex-wrap:wrap;'>"
        "<span class='chip'>Add to list</span>"
        "<span class='chip'>Skip</span>"
        "<span class='chip'>Correct item</span>"
        "</div>"
        if show_actions
        else ""
    )
    return (
        "<div class='home-card item-card'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;'>"
        f"<strong>{item_name}</strong>{badge}</div>"
        f"<div style='font-size:13px;color:var(--text-dim);'>{reason}</div>"
        f"{f'<div style=\"font-size:12px;margin-top:6px;\">{qty_line}</div>' if qty_line else ''}"
        f"<div style='font-size:11px;margin-top:6px;color:var(--text-dim);'>Confidence: {confidence:.0%}</div>"
        f"{action_line}"
        "</div>"
    )


def render_grouped_cards(title: str, items: list[dict[str, Any]]) -> str:
    if not items:
        return ""
    rows = "".join(
        render_decision_card(
            item=item.get("canonical_name") or item.get("item_name", ""),
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


def render_metric(name: str, value: str, hint: str = "") -> str:
    return (
        "<div class='metric-card'>"
        f"<div style='font-size:11px;color:var(--text-dim);text-transform:uppercase;letter-spacing:0.4px'>{name}</div>"
        f"<div style='font-size:34px;font-weight:700;margin-top:6px'>{value}</div>"
        + (f"<div style='color:var(--text-dim);font-size:11px;margin-top:6px'>{hint}</div>" if hint else "")
        + "</div>"
    )

