"""Cross-source price comparison screen — compares available market snapshots.

Provides:
- multi_source_price_view: full comparison dashboard for all registered market sources
- single_item_compare: price comparison for one item across sources
- basket_compare_view: per-source totals for a multi-item basket
"""

from __future__ import annotations

import logging
from html import escape
from typing import Any

from shopstack.market.sources import (
    compare_across_sources,
    format_cross_source_html,
)
from shopstack.services.basket_compare import (
    compare_basket_across_sources,
    parse_basket_input,
    render_basket_comparison_html,
)
from shopstack.services.market_sources import load_market_registry, source_status_report
from shopstack.ui.components.primitives import empty_state_enhanced, stat_card, toast

logger = logging.getLogger(__name__)

_registry = None
_registry_errors: dict[str, str] = {}


def _get_registry():
    global _registry
    global _registry_errors
    if _registry is None:
        try:
            _registry, _registry_errors = load_market_registry(force=False)
        except Exception as exc:
            logger.warning("Failed to build source registry: %s", exc)
            _registry = None
            _registry_errors = {}
    return _registry


def _all_snapshots_loaded(registry) -> bool:
    """Check if at least one source has a loaded snapshot."""
    try:
        snaps = registry.all_snapshots()
        available = [sid for sid, snap in snaps.items() if snap and snap.normalized_records]
        return len(available) >= 1
    except Exception as exc:
        logger.debug("_all_snapshots_loaded check failed: %s", exc)
        return False


def multi_source_price_view() -> str:
    """Build the full multi-source price comparison dashboard.

    Returns:
        HTML string displaying side-by-side prices from all registered market sources.
        Falls back to an informative message if insufficient data is available.
    """
    registry = _get_registry()
    if registry is None:
        status = source_status_report(force=False)
        if status:
            return empty_state_enhanced(
                "Registry loaded, but no active sources yet. "
                f"Available sources: {', '.join(escape(s) for s in status)}",
                icon="📊",
            )
        return empty_state_enhanced(
            "Source registry could not be initialised. Market data files may be missing.",
            icon="🔌",
        )

    if not _all_snapshots_loaded(registry):
        registered = registry.registered()
        if not registered:
            return empty_state_enhanced(
                "No market sources registered. Add Swiggy, Blinkit, Zepto, or DMart data to get started.",
                icon="📊",
            )
        status = source_status_report(force=False)
        missing = [name for name in registered if not status.get(name, {}).get("snapshot_id")]
        if missing:
            available = [name for name in registered if name not in missing]
            if available:
                availability = f"Available snapshots: {', '.join(escape(name) for name in available)} loaded."
            else:
                availability = "No snapshots loaded."
            missing_label = ", ".join(escape(name) for name in missing)
            return empty_state_enhanced(
                f"{availability} Missing or stale: {missing_label}.",
                icon="⏳",
            )
        if any(_registry_errors.get(name) for name in registered):
            reason = "; ".join(
                f"{escape(name)}: {escape(_registry_errors[name])}"
                for name in registered
                if _registry_errors.get(name)
            )
            return empty_state_enhanced(
                f"Some sources failed to load: {reason}",
                icon="⚠️",
            )
        return empty_state_enhanced(
            f"Loading snapshots for {', '.join(escape(s) for s in registered)}... Check that data files are present.",
            icon="⏳",
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
        return empty_state_enhanced("No items found in market snapshots.", icon="🔍")

    # Compare each item across sources
    comparisons = []
    for cname in sorted(all_names):
        comp = compare_across_sources(registry, cname)
        if comp is not None:
            comparisons.append(comp)

    if not comparisons:
        return empty_state_enhanced(
            "Not enough items with prices across multiple sources to compare. Try adding more market data.",
            icon="📉",
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
            color = "var(--red)" if is_stale else "var(--text-dim)"
            freshness_html += (
                f"<span style='font-size: 0.625rem;color:{color};margin-right:12px;'>{escape(source_labels.get(sid, sid))}: {escape(label)}</span>"
            )
        except Exception as exc:
            logger.debug("freshness check failed for %s: %s", sid, exc)

    freshness_section = ""
    if freshness_html:
        freshness_section = (
            f"<div style='font-size: 0.625rem;margin-bottom:8px;'>{freshness_html}</div>"
        )

    savings_count = sum(1 for c in comparisons if c.savings_pct > 5)
    summary_cards = (
        stat_card(value=str(len(comparisons)), label="Items Compared", icon="📦")
        + stat_card(value=str(len(sorted_sources)), label="Sources", icon="🏪")
        + stat_card(value=str(savings_count), label="Best Deals (5%+)", icon="💰", variant="success")
    )

    body = format_cross_source_html(comparisons)

    return (
        f"<div style='display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap;'>{summary_cards}</div>{freshness_section}"
        f"{body}"
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
        return empty_state_enhanced("Source registry not available.", icon="🔌")

    try:
        from shopstack.domain import canonicalize_name
        canonical, _, _ = canonicalize_name(item_name)
    except Exception as exc:
        logger.debug("single_item_compare: canonicalize failed: %s", exc)
        canonical = item_name.strip().lower().replace(" ", "_")

    comp = compare_across_sources(registry, canonical)
    if comp is None:
        display = canonical.replace("_", " ").title()
        return empty_state_enhanced(
            f"No multi-source pricing available for {display}. Try a different item name or check market data.",
            icon="🔍",
        )

    return format_cross_source_html([comp])


def refresh_source_registry() -> str:
    """Force-rebuild the source registry and return status.

    Returns:
        HTML string with registration status.
    """
    global _registry
    try:
        _registry, _registry_errors = load_market_registry(force=True)
        registered = _registry.registered()
        snapshots = _registry.all_snapshots()
        loaded = len([s for s in snapshots.values() if s and s.normalized_records])
        return toast(
            f"Registry refreshed: {len(registered)} sources registered, {loaded} snapshots loaded.",
            kind="success",
        )
    except Exception as exc:
        return toast("Couldn't refresh the registry. Please try again.", kind="error")


def basket_compare_view(items_text: str) -> str:
    """Compare a multi-item basket's total across all registered market sources.

    Accepts one item per line, e.g.::

        2kg onions
        1L milk
        500g tomatoes
        12 eggs

    Returns:
        HTML string showing per-source totals, cheapest source, total savings,
        and a per-item line breakdown. Falls back to an informative empty state
        when fewer than 2 sources have data, or when no items are entered.
    """
    registry = _get_registry()
    if registry is None:
        return empty_state_enhanced(
            "Source registry could not be initialised. Market data files may be missing.",
            icon="🔌",
        )

    requested = parse_basket_input(items_text)
    if not requested:
        return empty_state_enhanced(
            "Enter at least one item — one per line, with quantity and unit if needed. "
            "Example: `2kg onions` or `1L milk`.",
            icon="🛒",
        )

    comparison = compare_basket_across_sources(registry, requested)
    return render_basket_comparison_html(comparison)
