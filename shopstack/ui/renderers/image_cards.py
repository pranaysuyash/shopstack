from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from typing import Any


@dataclass
class CardTheme:
    background: str = "#ffffff"
    accent: str = "#1A9E4A"
    text: str = "#1e293b"
    text_dim: str = "#64748b"
    success: str = "#1A9E4A"
    warning: str = "#C47D0A"
    danger: str = "#C53030"


DEFAULT_THEME = CardTheme()

_STATUS_COLORS: dict[str, str] = {
    "active": "#1A9E4A",
    "low": "#C47D0A",
    "expired": "#C53030",
    "use_soon": "#C47D0A",
    "unknown": "#64748b",
}

_DECISION_SVG_COLORS: dict[str, str] = {
    "buy": "#1A9E4A",
    "skip": "#595E66",
    "use_soon": "#C47D0A",
    "optional": "#2A6BC4",
    "compare": "#7345D0",
    "confirm": "#C53030",
    "watch": "#7F8C8D",
}

_FONT = "system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"

_SVG_OUTER_RE = re.compile(r"^<svg[^>]*>(.*)</svg>$", re.DOTALL)
_VIEWBOX_RE = re.compile(
    r'viewBox="([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)"'
)


def _wrap_text(text: str, max_chars: int = 20) -> list[str]:
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if len(test) <= max_chars:
            current = test
        else:
            if current:
                lines.append(current)
            current = word if len(word) <= max_chars else word[: max_chars - 1] + "\u2026"
    if current:
        lines.append(current)
    return lines[:3]


def _svg_text_block(
    text: str,
    x: float,
    y: float,
    max_chars: int = 20,
    font_size: float = 13,
    color: str = "#1e293b",
    bold: bool = False,
) -> str:
    lines = _wrap_text(text, max_chars)
    if not lines:
        return ""
    weight = "600" if bold else "400"
    tspans = []
    for i, line in enumerate(lines):
        dy = 0 if i == 0 else font_size * 1.35
        tspans.append(f'<tspan x="{x}" dy="{dy}">{escape(line)}</tspan>')
    return (
        f'<text x="{x}" y="{y}" font-size="{font_size}" fill="{color}" '
        f'font-family="{_FONT}" font-weight="{weight}">'
        f'{"".join(tspans)}</text>'
    )


def _svg_badge(
    text: str,
    x: float,
    y: float,
    bg: str,
    fg: str = "#ffffff",
    font_size: float = 9,
) -> str:
    w = max(len(text) * font_size * 0.62 + 10, 30)
    h = font_size + 8
    rx = h / 2
    return (
        f'<rect x="{x}" y="{y}" width="{w:.0f}" height="{h:.0f}" '
        f'rx="{rx:.0f}" fill="{bg}"/>'
        f'<text x="{x + w / 2:.1f}" y="{y + h / 2 + font_size * 0.35:.1f}" '
        f'text-anchor="middle" font-size="{font_size}" fill="{fg}" '
        f'font-family="{_FONT}" font-weight="600">{escape(text.upper())}</text>'
    )


def _svg_confidence_bar(
    value: float,
    x: float,
    y: float,
    width: float = 160,
    height: float = 4,
) -> str:
    clamped = max(0.0, min(1.0, value))
    fill_w = clamped * width
    color = "#1A9E4A" if clamped >= 0.7 else "#C47D0A" if clamped >= 0.4 else "#C53030"
    return (
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="2" fill="#e2e8f0"/>'
        f'<rect x="{x}" y="{y}" width="{fill_w:.1f}" height="{height}" rx="2" fill="{color}"/>'
    )


def render_item_card(
    item_name: str,
    quantity: float,
    unit: str,
    status: str = "active",
    category: str = "",
    price: float | None = None,
    theme: CardTheme | None = None,
) -> str:
    t = theme or DEFAULT_THEME
    accent = _STATUS_COLORS.get(status, t.text_dim)
    qty_str = f"{quantity:g} {escape(unit)}" if unit else f"{quantity:g}"
    safe_name = escape(item_name)
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 140" '
        f'width="220" height="140" role="img" aria-label="Item: {safe_name} ({status})">',
        f'<rect width="220" height="140" rx="8" fill="{t.background}"/>',
        f'<rect x="0" y="0" width="4" height="140" rx="2" fill="{accent}"/>',
    ]
    if category:
        parts.append(_svg_badge(category, 155, 10, "#e2e8f0", t.text_dim, 8))
    parts.append(
        _svg_text_block(
            item_name, 16, 42, max_chars=18, font_size=15, color=t.text, bold=True
        )
    )
    parts.append(
        f'<text x="16" y="72" font-size="12" fill="{t.text_dim}" '
        f'font-family="{_FONT}">{qty_str}</text>'
    )
    parts.append(_svg_badge(status, 16, 106, accent, "#ffffff", 9))
    if price is not None:
        parts.append(
            f'<text x="204" y="122" text-anchor="end" font-size="14" '
            f'fill="{t.success}" font-family="{_FONT}" '
            f'font-weight="600">\u20b9{price:.0f}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def render_use_soon_card(
    items: list[dict[str, Any]],
    theme: CardTheme | None = None,
) -> str:
    t = theme or DEFAULT_THEME
    row_h = 24
    header_h = 36
    max_items = min(len(items), 5)
    total_h = header_h + max(max_items, 1) * row_h + 16
    item_count = len(items)
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 {total_h}" '
        f'width="220" height="{total_h}" role="img" aria-label="Use soon: {item_count} items">',
        f'<rect width="220" height="{total_h}" rx="8" fill="#fffbeb"/>',
        f'<rect x="0" y="0" width="4" height="{total_h}" rx="2" fill="{t.warning}"/>',
        f'<text x="16" y="24" font-size="13" fill="{t.warning}" '
        f'font-family="{_FONT}" font-weight="600">Use Soon</text>',
        f'<text x="204" y="24" text-anchor="end" font-size="11" fill="{t.text_dim}" '
        f'font-family="{_FONT}">'
        f'{item_count} item{"s" if item_count != 1 else ""}</text>',
    ]
    if not items:
        parts.append(
            f'<text x="16" y="{header_h + 20}" font-size="11" fill="{t.text_dim}" '
            f'font-family="{_FONT}">No items expiring soon</text>'
        )
    y = header_h + 12
    for item in items[:max_items]:
        name = str(item.get("display_name", item.get("name", "")))
        reason = str(item.get("reason", ""))
        parts.append(
            f'<text x="16" y="{y}" font-size="12" fill="{t.text}" '
            f'font-family="{_FONT}" font-weight="500">{escape(name[:22])}</text>'
        )
        if reason:
            parts.append(
                f'<text x="204" y="{y}" text-anchor="end" font-size="10" '
                f'fill="{t.text_dim}" font-family="{_FONT}">'
                f'{escape(reason[:20])}</text>'
            )
        y += row_h
    parts.append("</svg>")
    return "".join(parts)


def render_decision_card(
    item_name: str,
    decision: str,
    reason: str,
    confidence: float,
    theme: CardTheme | None = None,
) -> str:
    t = theme or DEFAULT_THEME
    color = _DECISION_SVG_COLORS.get(decision, t.text_dim)
    clamped_conf = max(0.0, min(1.0, confidence))
    safe_item = escape(item_name)
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 160" '
        f'width="220" height="220" style="max-width:100%;" role="img" '
        f'aria-label="Decision: {safe_item} - {decision}">',
        f'<rect width="220" height="160" rx="8" fill="{t.background}"/>',
        f'<rect x="0" y="0" width="4" height="160" rx="2" fill="{color}"/>',
        _svg_badge(decision, 12, 10, color, "#ffffff", 9),
        _svg_text_block(
            item_name, 16, 62, max_chars=18, font_size=15, color=t.text, bold=True
        ),
        _svg_text_block(reason, 16, 102, max_chars=28, font_size=10, color=t.text_dim),
        _svg_confidence_bar(clamped_conf, 16, 134),
        f'<text x="204" y="148" text-anchor="end" font-size="9" fill="{t.text_dim}" '
        f'font-family="{_FONT}">{clamped_conf:.0%}</text>',
        "</svg>",
    ]
    return "".join(parts)


def render_shopping_summary_card(
    items_bought: int,
    items_skipped: int,
    total_saved: float,
    theme: CardTheme | None = None,
) -> str:
    t = theme or DEFAULT_THEME
    total = items_bought + items_skipped
    pct = (items_skipped / total * 100) if total > 0 else 0
    col_w = 64
    parts: list[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 130" '
        'width="220" height="130" role="img" aria-label="Shopping summary: '
        f'{items_bought} bought, {items_skipped} skipped, {total_saved:.0f} saved">',
        f'<rect width="220" height="130" rx="8" fill="{t.background}"/>',
        f'<rect x="0" y="0" width="4" height="130" rx="2" fill="{t.success}"/>',
        f'<text x="16" y="24" font-size="13" fill="{t.text}" '
        f'font-family="{_FONT}" font-weight="600">Shopping Summary</text>',
    ]
    for i, (val, label, color) in enumerate(
        [
            (str(items_bought), "Bought", t.success),
            (str(items_skipped), "Skipped", t.text_dim),
            (f"\u20b9{total_saved:.0f}", "Saved", t.success),
        ]
    ):
        cx = 16 + i * col_w + col_w // 2
        parts.append(
            f'<text x="{cx}" y="58" text-anchor="middle" font-size="20" '
            f'fill="{color}" font-family="{_FONT}" font-weight="700">{val}</text>'
        )
        parts.append(
            f'<text x="{cx}" y="74" text-anchor="middle" font-size="9" '
            f'fill="{t.text_dim}" font-family="{_FONT}">{label}</text>'
        )
    parts.append(_svg_confidence_bar(pct / 100.0, 16, 92, width=188, height=6))
    parts.append(
        f'<text x="110" y="118" text-anchor="middle" font-size="10" '
        f'fill="{t.text_dim}" font-family="{_FONT}">'
        f'{pct:.0f}% waste prevention</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def render_price_comparison_card(
    item_name: str,
    prices: dict[str, float],
    theme: CardTheme | None = None,
) -> str:
    t = theme or DEFAULT_THEME
    sorted_prices = sorted(prices.items(), key=lambda x: x[1])
    best_store = sorted_prices[0][0] if sorted_prices else ""
    max_items = min(len(sorted_prices), 5)
    row_h = 26
    header_h = 40
    total_h = header_h + max(max_items, 1) * row_h + 12
    safe_item = escape(item_name)
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 220 {total_h}" '
        f'width="220" height="{total_h}" role="img" aria-label="Price compare: {safe_item}">',
        f'<rect width="220" height="{total_h}" rx="8" fill="{t.background}"/>',
        f'<rect x="0" y="0" width="4" height="{total_h}" rx="2" fill="#7345D0"/>',
        _svg_text_block(
            item_name, 16, 28, max_chars=22, font_size=13, color=t.text, bold=True
        ),
    ]
    if not sorted_prices:
        parts.append(
            f'<text x="16" y="{header_h + 20}" font-size="11" fill="{t.text_dim}" '
            f'font-family="{_FONT}">No price data</text>'
        )
    y = header_h + 8
    for store, price in sorted_prices[:max_items]:
        is_best = store == best_store and len(sorted_prices) > 1
        if is_best:
            parts.append(
                f'<rect x="12" y="{y - 14}" width="196" height="22" rx="4" '
                f'fill="#f0fdf4"/>'
            )
        price_color = t.success if is_best else t.text
        star = " \u2605" if is_best else ""
        parts.append(
            f'<text x="16" y="{y}" font-size="11" fill="{t.text}" '
            f'font-family="{_FONT}">{escape(store[:20])}{star}</text>'
        )
        parts.append(
            f'<text x="204" y="{y}" text-anchor="end" font-size="12" '
            f'fill="{price_color}" font-family="{_FONT}" '
            f'font-weight="600">\u20b9{price:.0f}</text>'
        )
        y += row_h
    parts.append("</svg>")
    return "".join(parts)


def _extract_svg_body(svg_str: str) -> str:
    m = _SVG_OUTER_RE.match(svg_str.strip())
    return m.group(1) if m else svg_str


def _extract_viewbox_size(svg_str: str) -> tuple[float, float]:
    m = _VIEWBOX_RE.search(svg_str)
    if m:
        return float(m.group(3)), float(m.group(4))
    return 220.0, 160.0


def cards_to_grid(cards: list[str], columns: int = 3) -> str:
    if not cards:
        return ""
    gap = 12
    card_w = 220.0
    rows_markup: list[str] = []
    total_h = 0.0
    for i in range(0, len(cards), columns):
        row_cards = cards[i : i + columns]
        row_parts: list[str] = []
        max_h = 0.0
        for j, card_svg in enumerate(row_cards):
            x = j * (card_w + gap)
            body = _extract_svg_body(card_svg)
            _, h = _extract_viewbox_size(card_svg)
            if h > max_h:
                max_h = h
            row_parts.append(f'<g transform="translate({x:.0f},0)">{body}</g>')
        rows_markup.append(
            f'<g transform="translate(0,{total_h:.0f})">'
            f'{"".join(row_parts)}</g>'
        )
        total_h += max_h + gap
    num_cols = min(len(cards), columns)
    grid_w = num_cols * card_w + (num_cols - 1) * gap
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {grid_w:.0f} {total_h:.0f}" '
        f'width="100%" style="max-width:{grid_w:.0f}px;" '
        f'role="img" aria-label="Card grid: {len(cards)} cards">'
        f'{"".join(rows_markup)}'
        f"</svg>"
    )
