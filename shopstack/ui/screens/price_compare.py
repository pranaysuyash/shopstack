"""Cross-source price comparison screen — compares prices across Swiggy, Blinkit, Zepto, DMart.

Provides:
- multi_source_price_view: full comparison dashboard for all registered market sources
- single_item_compare: price comparison for one item across sources
"""

from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.market.sources import (
    build_registry,
    compare_across_sources,
    format_cross_source_html,
)

logger = logging.getLogger(__name__)

_registry = None


def _get_registry():
    global _registry
    if _registry is None:
        try:
            _registry = build_registry()
        except Exception as exc:
            logger.warning("Failed to build source registry: %s", exc)
            _registry = None
    return _registry


def _all_snapshots_loaded(registry) -> bool:
    """Check if at least 2 sources have snapshots available."""
    try:
        snaps = registry.all_snapshots()
        available = [sid for sid, snap in snaps.items() if snap and snap.normalized_records]
        return len(available) >= 2
    except Exception:
        return False


def multi_source_price_view() -> str:
    """Build the full multi-source price comparison dashboard.

    Returns:
        HTML string displaying side-by-side prices from all registered market sources.
        Falls back to an informative message if insufficient data is available.
    """
    registry = _get_registry()
    if registry is None:
        return (
            "<div class='home-card' style='text-align:left;'>"
            "<h3>Multi-Source Price Comparison</h3>"
            "<div class='muted'>Source registry could not be initialised. "
            "Market data files may be missing.</div>"
            "</div>"
        )

    if not _all_snapshots_loaded(registry):
        registered = registry.registered()
        if not registered:
            return (
                "<div class='home-card' style='text-align:left;'>"
                "<h3>Multi-Source Price Comparison</h3>"
                "<div class='muted'>No market sources registered. "
                "Add Swiggy, Blinkit, Zepto, or DMart data to get started.</div>"
                "</div>"
            )
        return (
            "<div class='home-card' style='text-align:left;'>"
            "<h3>Multi-Source Price Comparison</h3>"
            "<div class='muted'>Loading snapshots for "
            f"{', '.join(escape(s) for s in registered)}... "
            "Check that data files are present.</div>"
            "</div>"
        )

    # Build a set of all canonical names across all sources
    all_snapshots = registry.all_snapshots()
    all_names: set[str] = set()
    for sid, snap in all_snapshots.items():
        if snap and snap.normalized_records:
            for rec in snap.normalized_records:
                if rec.canonical_name:
                    all_names.add(rec.canonical_name)

    if not all_names:
        return (
            "<div class='home-card' style='text-align:left;'>"
            "<h3>Multi-Source Price Comparison</h3>"
            "<div class='muted'>No items found in market snapshots.</div>"
            "</div>"
        )

    # Compare each item across sources
    comparisons = []
    for cname in sorted(all_names):
        comp = compare_across_sources(registry, cname)
        if comp is not None:
            comparisons.append(comp)

    if not comparisons:
        return (
            "<div class='home-card' style='text-align:left;'>"
            "<h3>Multi-Source Price Comparison</h3>"
            "<div class='muted'>Not enough items with prices across multiple sources to compare. "
            "Try adding more market data.</div>"
            "</div>"
        )

    # Sources header
    source_ids: set[str] = set()
    for c in comparisons:
        source_ids.update(c.prices.keys())
    sorted_sources = sorted(source_ids)

    source_labels = {
        "swiggy": "Swiggy Instamart",
        "blinkit": "Blinkit",
        "zepto": "Zepto",
        "dmart": "DMart",
    }

    # Show freshness badges for each source
    freshness_html = ""
    for sid in sorted_sources:
        try:
            f = registry.freshness_of(sid)
            label = f.get("label", "")
            is_stale = f.get("is_stale", False)
            color = "#ef4444" if is_stale else "var(--text-dim)"
            freshness_html += (
                f"<span style='font-size:10px;color:{color};margin-right:12px;'>"
                f"{escape(source_labels.get(sid, sid))}: {escape(label)}</span>"
            )
        except Exception:
            pass

    freshness_section = ""
    if freshness_html:
        freshness_section = (
            f"<div style='font-size:10px;margin-bottom:8px;'>{freshness_html}</div>"
        )

    savings_count = sum(1 for c in comparisons if c.savings_pct > 5)
    total = sum(c.savings_pct for c in comparisons if c.savings_pct > 0)

    summary_bar = (
        f"<div style='display:flex;gap:16px;margin-bottom:12px;flex-wrap:wrap;'>"
        f"<span style='font-size:12px;color:var(--text-dim);'>Items compared: {len(comparisons)}</span>"
        f"<span style='font-size:12px;color:var(--green);'>Sources: {len(sorted_sources)} ({', '.join(escape(source_labels.get(s, s)) for s in sorted_sources)})</span>"
        f"<span style='font-size:12px;color:var(--amber);'>Best deals found: {savings_count} items with 5%+ savings</span>"
        f"</div>"
    )

    body = format_cross_source_html(comparisons)

    return (
        f"<div class='home-card' style='text-align:left;margin-bottom:12px;'>"
        f"<h3>Multi-Source Price Comparison</h3>"
        f"{summary_bar}"
        f"{freshness_section}"
        f"{body}"
        f"</div>"
    )


def single_item_compare(item_name: str) -> str:
    """Compare a single item across all market sources.

    Args:
        item_name: The canonical item name to compare.

    Returns:
        HTML string showing side-by-side prices for this item.
    """
    registry = _get_registry()
    if registry is None:
        return (
            "<div class='muted'>Source registry not available.</div>"
        )

    try:
        from shopstack.market.normalization import canonicalize_name
        canonical, _, _ = canonicalize_name(item_name)
    except Exception:
        canonical = item_name.strip().lower().replace(" ", "_")

    comp = compare_across_sources(registry, canonical)
    if comp is None:
        display = escape(canonical.replace("_", " ").title())
        return (
            "<div class='muted'>"
            f"No multi-source pricing available for <strong>{display}</strong>. "
            "Try a different item name or check market data.</div>"
        )

    result = format_cross_source_html([comp])

    return (
        f"<div style='text-align:left;margin-bottom:12px;'>{result}</div>"
    )


def refresh_source_registry() -> str:
    """Force-rebuild the source registry and return status.

    Returns:
        HTML string with registration status.
    """
    global _registry
    try:
        _registry = build_registry()
        registered = _registry.registered()
        snapshots = _registry.all_snapshots()
        loaded = len([s for s in snapshots.values() if s and s.normalized_records])
        return (
            "<div style='color:var(--green);font-size:13px;'>"
            f"Registry refreshed: {len(registered)} sources registered, "
            f"{loaded} snapshots loaded."
            "</div>"
        )
    except Exception as exc:
        return (
            "<div style='color:var(--red);font-size:13px;'>"
            f"Failed to refresh registry: {escape(str(exc))}"
            "</div>"
        )
