"""Unified shopping screen — single-pass plan → classify → market → basket → substitutions.

Provides a Gradio-friendly interface over `run_unified_shopping_flow()`.
Renders items grouped by decision with market prices, deal scores,
and substitution suggestions inline.
"""

from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.app_context import db, tools, current_user_id
from shopstack.ui.screens._utils import safe_render

logger = logging.getLogger(__name__)

__all__ = [
    "run_unified_plan",
    "unified_plan_summary",
]


# ── Decision badge colours ──────────────────────────────────────────────────

_DECISION_STYLES: dict[str, str] = {
    "buy": "background:var(--green);color:#fff;",
    "skip": "background:var(--text-dim);color:#fff;",
    "use_soon": "background:var(--amber);color:#000;",
    "optional": "background:var(--blue);color:#fff;",
    "compare": "background:var(--blue);color:#fff;",
}

_DEAL_STYLES: dict[str, str] = {
    "great": "color:var(--green);font-weight:700;",
    "good": "color:var(--green);",
    "fair": "color:var(--text-dim);",
    "poor": "color:var(--red);font-weight:700;",
    "unknown": "color:var(--text-dim);",
}


def _decision_badge(decision: str) -> str:
    style = _DECISION_STYLES.get(decision, "background:var(--text-dim);color:#fff;")
    return (
        f"<span style='display:inline-block;padding:1px 8px;border-radius:10px;ont-size: 0.6875rem;font-weight:600;{style}'>{escape(decision.upper())}</span>"
    )


def _deal_badge(score: str, reason: str) -> str:
    if not score:
        return ""
    style = _DEAL_STYLES.get(score, "color:var(--text-dim);")
    return (
        f"<span style='font-size: 0.6875rem;{style}' title='{escape(reason)}'>[{escape(score.upper())}]</span>"
    )


def _price_str(price: float | None) -> str:
    if price is None:
        return "<span style='color:var(--text-dim);'>--</span>"
    return f"&#8377;{price:.0f}"


def _availability_tag(available: bool | None) -> str:
    if available is None:
        return ""
    if available:
        return "<span style='font-size: 0.625rem;color:var(--green);'>In stock</span>"
    return "<span style='font-size: 0.625rem;color:var(--red);'>Sold out</span>"


def _render_item_row(item: dict[str, Any]) -> str:
    name = escape(item.get("display_name", item.get("canonical_name", "")))
    decision = item.get("decision", "buy")
    reason = escape(item.get("reason", ""))
    price = item.get("market_price")
    per_kg = item.get("market_price_per_kg")
    available = item.get("market_available")
    deal_score = item.get("deal_score", "")
    deal_reason = item.get("deal_reason", "")
    subs = item.get("substitutions", [])

    price_html = _price_str(price)
    if per_kg:
        price_html += f" <span style='font-size: 0.625rem;color:var(--text-dim);'>({per_kg:.0f}/kg)</span>"

    avail_html = _availability_tag(available)
    deal_html = _deal_badge(deal_score, deal_reason)

    sub_html = ""
    if subs:
        sub_parts = []
        for s in subs[:3]:
            sub_name = escape(s.get("display_name", s.get("canonical_name", "")))
            sub_type = escape(s.get("type", "").replace("_", " ").title())
            sub_price = f" &#8377;{s['price_inr']:.0f}" if s.get("price_inr") else ""
            sub_reason = escape(s.get("reason", ""))
            sub_parts.append(
                f"<div style='margin-left:16px;font-size: 0.6875rem;padding:2px 0;'><strong>{sub_name}</strong> ({sub_type}){sub_price}"
                f" <span style='color:var(--text-dim);'>— {sub_reason}</span></div>"
            )
        sub_html = (
            "<div style='margin-top:4px;border-left:2px solid var(--border);padding-left:8px;'>"
            "<div style='font-size: 0.625rem;color:var(--text-dim);margin-bottom:2px;'>Substitutions</div>"
            + "".join(sub_parts) + "</div>"
        )

    return (
        f"<div style='padding:8px 0;border-bottom:1px solid var(--border);'><div style='display:flex;justify-content:space-between;align-items:center;'>"
        f"<div>{_decision_badge(decision)} <strong>{name}</strong> <span style='font-size: 0.6875rem;color:var(--text-dim);'>{escape(reason)}</span></div>"
        f"<div>{price_html} {avail_html} {deal_html}</div></div>"
        f"{sub_html}</div>"
    )


def _render_summary_card(result: dict[str, Any]) -> str:
    summary = result.get("summary", {})
    total = summary.get("estimated_total", 0)
    buy_count = summary.get("buy", 0)
    skip_count = summary.get("skip", 0)
    use_soon_count = summary.get("use_soon", 0)
    sold_out_count = summary.get("sold_out", 0)

    return (
        "<div class='home-card' style='margin-bottom:12px;'>"
        "<h4>Plan Summary</h4>"
        "<div style='display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;'>"
        f"<div><strong>{buy_count}</strong> to buy</div><div><strong>{skip_count}</strong> to skip</div>"
        f"<div><strong>{use_soon_count}</strong> to use soon</div><div style='color:var(--red);'><strong>{sold_out_count}</strong> sold out</div>"
        f"<div>Estimated total: <strong>&#8377;{total:.0f}</strong></div>"
        "</div></div>"
    )


def _render_graph_projection(result: dict[str, Any]) -> str:
    projection = result.get("graph_projection") or {}
    if not projection:
        return ""
    summary = projection.get("summary", {})
    next_actions = ", ".join(projection.get("next_actions", [])[:3]) or "none"
    matched = ", ".join(projection.get("matched_names", [])[:4]) or "none"
    unmatched = ", ".join(projection.get("unmatched_names", [])[:4]) or "none"
    return (
        "<div class='home-card' style='margin-bottom:12px;'>"
        "<h4>Graph Projection</h4>"
        f"<div style='font-size: 0.75rem;color:var(--text-dim);margin-top:6px;'>{escape(projection.get('title', 'Unified Shopping'))}</div><div style='display:flex;gap:16px;flex-wrap:wrap;margin-top:8px;'>"
        f"<div><strong>{summary.get('items', 0)}</strong> clustered</div><div><strong>{summary.get('buy', 0)}</strong> buy</div>"
        f"<div><strong>{summary.get('compare', 0)}</strong> compare</div><div><strong>{summary.get('substitute', 0)}</strong> substitute</div>"
        "</div>"
        f"<div style='font-size: 0.75rem;color:var(--text-dim);margin-top:8px;'>Matched: {escape(matched)} · Missing: {escape(unmatched)}</div><div style='font-size: 0.75rem;color:var(--text-dim);margin-top:4px;'>Next: {escape(next_actions)}</div>"
        "</div>"
    )


@safe_render
def run_unified_plan(goal: str, items_text: str) -> tuple[str, str]:
    """Execute the unified shopping flow and return (summary_html, detail_html)."""
    goal = (goal or "").strip() or "Shopping"
    items_text = (items_text or "").strip()

    if not items_text:
        return (
            "<div class='home-card' style='text-align:center;padding:20px;color:var(--text-dim);'>"
            "Enter items to get a unified shopping plan.</div>",
            "",
        )

    from shopstack.services.unified_shopping import run_unified_shopping_flow

    uid = current_user_id()
    graph = None
    try:
        from shopstack.services.market_intelligence import build_market_intelligence_graph
        graph = build_market_intelligence_graph(db, tools.inventory, user_id=uid)
    except Exception as exc:
        logger.warning("Unified shopping graph projection unavailable: %s", exc)
    result = run_unified_shopping_flow(
        goal=goal,
        items_text=items_text,
        db=db,
        inventory=tools.inventory,
        graph=graph,
    )
    data = result.to_dict()

    summary_html = _render_summary_card(data) + _render_graph_projection(data)

    # Group items by decision
    grouped: dict[str, list[dict]] = {}
    for item in data.get("items", []):
        grouped.setdefault(item.get("decision", "buy"), []).append(item)

    detail_parts = []
    # Render buy first, then use_soon, optional, compare, skip
    for dec in ("buy", "use_soon", "optional", "compare", "skip"):
        items = grouped.get(dec, [])
        if not items:
            continue
        detail_parts.append(
            f"<div class='home-card' style='margin-bottom:10px;'><h4 style='margin-bottom:6px;'>{dec.replace('_', ' ').title()} ({len(items)})</h4>"
            + "".join(_render_item_row(i) for i in items)
            + "</div>"
        )

    detail_html = "".join(detail_parts)

    # Record trace
    try:
        from shopstack.traces.export import create_trace
        create_trace(
            db,
            input_type="text",
            user_goal=goal,
            redacted_user_request=f"unified plan: {items_text[:100]}",
            perception={"items": len(data.get("items", [])), "goal": goal},
            decision={"buy": len(grouped.get("buy", [])), "skip": len(grouped.get("skip", []))},
            proposed_tool_calls=[],
            final_response=f"{len(data.get('items', []))} items classified",
            human_confirmation="auto",
            user_id=uid,
        )
    except Exception as exc:
        logger.warning("Failed to record unified shopping trace: %s", exc)

    return summary_html, detail_html


@safe_render
def unified_plan_summary() -> str:
    """Return a quick summary of the most recent plan or empty state."""
    return (
        "<div class='home-card' style='text-align:center;padding:20px;color:var(--text-dim);'>"
        "Enter a goal and items above, then click <strong>Run Plan</strong> "
        "to get classified items with prices, deals, and substitutions."
        "</div>"
    )
