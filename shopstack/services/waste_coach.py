"""Waste reduction coach — turns ``detect_waste_patterns`` observations into
actionable recommendations.

The existing waste detection returns *observations* ("you waste 30% of
tomatoes"). This service upgrades each observation to a *recommendation*
("buy 500g instead of 1kg, or buy tinned") so the Today dashboard closes
the loop from log → coach.

Pattern → hypothesis → action templates, by waste-risk category:

- **high** + overstocked: "Buy smaller next time, or freeze half"
- **high** + frequent repurchase: "Buy tinned/frozen instead of fresh"
- **medium** + overstocked: "Smaller pack next time"
- **medium** + frequent: "Plan around the next 2 days of use"

Returns XSS-safe HTML, intended for a Gradio ``HTML`` component on the
Today dashboard. The renderer preserves the existing "Waste Prevention"
header so the card slot in the dashboard layout stays consistent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from html import escape
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WasteRecommendation:
    """A coach recommendation for a single waste signal."""

    canonical_name: str
    display_name: str
    observation: str
    action: str
    severity: str  # "high" | "medium" | "low"
    action_kind: str  # "smaller_pack" | "freeze" | "tinned_swap" | "plan_around_use" | "skip"
    metadata: dict[str, Any] = field(default_factory=dict)


def coach_waste_signal(signal: dict[str, Any]) -> WasteRecommendation:
    """Convert one waste pattern observation into an actionable recommendation.

    The recommendation style is chosen based on the signal's metadata:
    overstocked + high-risk = "smaller_pack"; frequent + high-risk =
    "tinned_swap"; etc. Output is intentionally short and concrete.
    """
    cname = signal.get("canonical_name", "")
    display = signal.get("display_name", cname.replace("_", " ").title())
    current_qty = float(signal.get("current_quantity") or 0)
    unit = signal.get("unit", "unit")
    risk = signal.get("waste_risk", "unknown")
    avg_interval = signal.get("avg_interval_days")
    observation = signal.get("reason", "High waste pattern observed")

    overstocked = current_qty > 1.0
    frequent = avg_interval is not None and float(avg_interval) < 2

    if risk == "high" and overstocked and frequent:
        action = (
            f"You buy {display} every {avg_interval:.0f} day(s) AND you have "
            f"{current_qty:.0f} {unit} on hand. "
            f"Try tinned or frozen next time — same nutrition, no waste."
        )
        kind = "tinned_swap"
    elif risk == "high" and overstocked:
        action = (
            f"You have {current_qty:.0f} {unit} on hand. "
            f"Next time, buy half that — smaller pack, less waste."
        )
        kind = "smaller_pack"
    elif risk == "high" and frequent:
        action = (
            f"You buy {display} every {avg_interval:.0f} day(s). "
            f"Consider frozen or tinned to avoid the daily-fresh waste."
        )
        kind = "tinned_swap"
    elif risk == "high":
        action = (
            f"Use your existing {current_qty:.0f} {unit} before buying more. "
            f"Freeze leftovers if you can't use them in time."
        )
        kind = "freeze"
    elif risk == "medium" and overstocked:
        action = (
            f"You have {current_qty:.0f} {unit} on hand. "
            f"Smaller pack next time — medium waste risk on this produce."
        )
        kind = "smaller_pack"
    elif risk == "medium":
        action = (
            f"Plan to use the {current_qty:.0f} {unit} you have on hand "
            f"in the next 2-3 days before it spoils."
        )
        kind = "plan_around_use"
    else:
        # Unknown / low risk — no specific action, observation only
        action = "Watch for spoilage; consume soon if ripeness is changing."
        kind = "plan_around_use"

    return WasteRecommendation(
        canonical_name=cname,
        display_name=display,
        observation=observation,
        action=action,
        severity=risk,
        action_kind=kind,
        metadata={
            "current_quantity": current_qty,
            "unit": unit,
            "avg_interval_days": avg_interval,
            "overstocked": overstocked,
            "frequent": frequent,
        },
    )


def coach_waste_signals(signals: list[dict[str, Any]]) -> list[WasteRecommendation]:
    """Coach a batch of waste signals into recommendations."""
    return [coach_waste_signal(s) for s in (signals or [])]


# ─── HTML rendering ───────────────────────────────────────────────────────


def render_waste_coach_html(signals: list[dict[str, Any]]) -> str:
    """Render waste observations as actionable coach recommendations.

    Returns empty string when there are no signals so the caller can
    fall through to other widgets.
    """
    if not signals:
        return ""

    recs = coach_waste_signals(signals)
    if not recs:
        return ""

    severity_colors = {
        "high": "var(--red)",
        "medium": "var(--amber)",
        "low": "var(--text-dim)",
    }
    severity_icons = {
        "high": "⚠️",
        "medium": "💡",
        "low": "ℹ️",
    }

    rows: list[str] = []
    for r in recs[:4]:
        color = severity_colors.get(r.severity, "var(--text-dim)")
        icon = severity_icons.get(r.severity, "•")
        rows.append(
            f"<div style='padding:6px 0;border-bottom:1px solid var(--border);'>"
            f"<div style='font-size:12px;'>"
            f"<span style='color:{color};font-weight:600;'>{icon} "
            f"{escape(r.display_name)}</span>"
            f" <span style='color:var(--text-dim);font-size:10px;'>"
            f"· {escape(r.observation)}</span></div>"
            f"<div style='font-size:11px;color:var(--text);margin-top:2px;'>"
            f"<strong style='color:var(--green);'>→</strong> {escape(r.action)}"
            f"</div></div>"
        )

    return (
        f"<div class='home-card' style='margin-bottom:12px;'>"
        f"<h3 style='margin:0 0 4px 0;'>🌱 Waste Coach</h3>"
        f"<div style='font-size:11px;color:var(--text-dim);margin-bottom:6px;'>"
        f"Actionable fixes for the items you waste most."
        f"</div>"
        f"{''.join(rows)}"
        f"</div>"
    )


__all__ = [
    "WasteRecommendation",
    "coach_waste_signal",
    "coach_waste_signals",
    "render_waste_coach_html",
]
