from __future__ import annotations

import logging
import re
from html import escape
from typing import Any

from shopstack.domain import normalize_item_name
from shopstack.ui.components.cards import card as ui_card
from shopstack.ui.components.primitives import home_card, stat_card
from shopstack.ui.components.workflow import (
    WORKFLOW_ACTION_STEPS,
    WORKFLOW_STEPS,
    workflow_header,
    workflow_title_bar,
)

logger = logging.getLogger(__name__)


def source_freshness_html(source_id: str = "swiggy") -> str:
    """Load a market source snapshot and return an HTML freshness note.

    Returns an empty string if the source data is unavailable.
    """
    try:
        if source_id == "swiggy":
            from shopstack.market.sources.swiggy import load_snapshot, snapshot_freshness
            freshness = snapshot_freshness(load_snapshot())
        else:
            from shopstack.market.sources import build_registry
            registry = build_registry()
            freshness = registry.freshness_of(source_id)
    except Exception:
        return ""
    color = "var(--red)" if freshness.get("is_stale") else "var(--text-dim)"
    label = freshness.get("label", "")
    prefix = "Market data may be stale" if freshness.get("is_stale") else "Market snapshot"
    return (
        f"<div style='font-size: 0.6875rem;color:{color};margin-top:6px;'>{escape(prefix)}: {escape(label)}. Prices and availability are point-in-time signals."
        f"</div>"
    )

from shopstack.module_registry import tab_order as _tab_order  # noqa: E402 — deferred to avoid circular import

# Derive workflow navigation labels from the module registry.
# These map to tab IDs in the UI and stay in sync automatically.
WORKFLOW_NAV: tuple[str, ...] = tuple(label for _tid, label in _tab_order())


def rows_to_html(rows: list[dict[str, Any]], headers: list[str]) -> str:
    if not rows:
        return "<div style='color:var(--text-dim);'>No entries.</div>"

    head_html = "".join(
        f"<th style='text-align:left;border-bottom:1px solid var(--border);padding:6px 8px;'>{escape(str(header))}</th>"
        for header in headers
    )
    body_html = ""
    for row in rows:
        body_html += (
            "<tr>"
            + "".join(
                f"<td style='border-bottom:1px solid var(--border);padding:6px 8px'>{escape(str(row.get(col, '')))}</td>"
                for col in headers
            )
            + "</tr>"
        )
    return (
        "<table style='border-collapse:collapse;width:100%;font-size: 0.75rem;'>"
        f"<tr>{head_html}</tr>{body_html}"
        "</table>"
    )


def parse_shopping_text(items_text: str) -> list[str]:
    if not items_text:
        return []
    normalized = re.sub(r"\b(and|&)\b", ",", items_text.lower(), flags=re.IGNORECASE)
    chunks = [t.strip() for t in re.split(r"[,;\n]", normalized) if t.strip()]
    parsed: list[str] = []
    for chunk in chunks:
        candidate = chunk.strip()
        m = re.match(r"^\s*([a-z].*?)\s+\d", candidate)
        if m:
            candidate = m.group(1)
        if candidate:
            parsed.append(normalize_item_name(candidate))
    return parsed


def extract_query_for_action(question: str, keyword: str) -> str:
    q = question.lower()
    for stop in ("do we have", "kya", "hai", "kharidna", "should i buy", "what about", "where is", "where's", "where are", "kahan hai", "kahan"):
        q = q.replace(stop, " ")
    q = re.sub(r"\b(what|should|do|need|today|today's|for|can|you|tell|me)\b", " ", q)
    q = re.sub(r"[^\w\s]", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    if not q and keyword:
        return keyword
    return q or keyword


def render_home_advice(active_inv: list, low_items: list, use_soon_items: list[dict[str, Any]]) -> str:
    buy = []
    skip = []
    use_soon_names = {item.get("canonical_name", "") for item in use_soon_items}
    for lot in active_inv:
        if lot.status == "low" or lot.quantity <= 0.4:
            buy.append(f"Buy {lot.display_name}")
        if lot.quantity > 0.7 and lot.canonical_name not in use_soon_names:
            skip.append(f"You already have {lot.display_name}")
    for item in use_soon_items[:2]:
        buy.append(f"Use {item.get('display_name', item.get('canonical_name', ''))} before buying more")
    if not buy and not skip:
        return ui_card("Today's note", "Your pantry looks healthy. No immediate action needed.")
    body = ""
    if buy:
        body += "<div style='margin-bottom:10px;'><strong>Buy</strong><ul>" + "".join(
            f"<li>{escape(str(line))}</li>" for line in buy[:3]
        ) + "</ul></div>"
    if skip:
        body += "<div><strong>Skip</strong><ul>" + "".join(
            f"<li>{escape(str(line))}</li>" for line in skip[:3]
        ) + "</ul></div>"
    return ui_card("Today\u2019s Shopping Advice", body)


def render_list_summary(sl) -> str:
    if not sl:
        return stat_card(
            style="text-align:left;margin-bottom:12px;",
            body_html='<h3>Shopping List</h3><div style="color:var(--text-dim);">No active list.</div>',
        )
    items = sl.items or []
    if not items:
        return stat_card(
            style="text-align:left;margin-bottom:12px;",
            body_html=(
                '<h3>Shopping List</h3>'
                '<div style="color:var(--text-dim);">'
                'List is empty. Add items from Pantry, '
                'Ask ShopStack, or the command input to plan a trip.'
                '</div>'
            ),
        )
    rows_str = "".join(
        f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);">'
        f'<span>{escape(str(i.canonical_name))}</span>'
        f'<span class="badge badge-blue">{escape(str(i.status))}</span>'
        f'</div>'
        for i in items[:8]
    )
    return stat_card(
        style="text-align:left;margin-bottom:12px;",
        body_html=f"<h3>Shopping List ({len(items)} items)</h3>{rows_str}",
    )


def render_low_stock(items) -> str:
    if not items:
        return ""
    return "".join(
        f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);">'
        f'<span>{escape(str(lot.display_name))}</span>'
        f'<span style="color:var(--red);">{escape(str(lot.quantity))} {escape(str(lot.unit))}</span>'
        f'</div>'
        for lot in items[:5]
    )


def render_recent_purchases(purchases) -> str:
    if not purchases:
        return ""
    return "".join(
        f'<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border);">'
        f'<span>{escape(str(p.canonical_name))}</span>'
        f'<span>\u20b9{p.total_price:.0f}</span>'
        f'</div>'
        for p in purchases[:5]
    )
