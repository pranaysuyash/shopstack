"""Price drop alert service — surfaces items where current market price is
significantly below the household's historical price for that item.

Builds on ``shopstack.services.price_memory.PriceMemoryService``. For each
canonical name in the current market snapshot, we look up the household's
historical price summary and compute a drop % versus the median. Items with
a drop of 15% or more are flagged as alerts.

This is the Phase 1 #13 wire-up — the existing ``price_deals`` field on
``DashboardState`` is computed only for "buy" decisions. This service
covers the *full* market catalogue, so the user sees "tomatoes dropped 30%
this week" even if they didn't have tomatoes on their shopping list.

Output is XSS-safe HTML, intended for a Gradio ``HTML`` component on the
Today dashboard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from html import escape
from typing import Any

from shopstack.market.schema import MarketSnapshot
from shopstack.services.price_memory import PriceMemoryService

logger = logging.getLogger(__name__)


# Drop threshold (in percent). 15% is meaningful but not noisy; lower
# thresholds produce too many false positives on a small household sample.
_DROP_THRESHOLD_PCT = 15.0

# Cap on how many alerts to render, regardless of how many items dropped.
_MAX_ALERTS = 6


@dataclass
class PriceDropAlert:
    """One item where the current price is significantly below historical."""

    canonical_name: str
    display_name: str
    source: str
    current_price: float
    median_price: float
    drop_pct: float
    drop_amount: float
    last_seen: str = ""

    @property
    def is_meaningful(self) -> bool:
        return (
            self.current_price > 0
            and self.median_price > 0
            and self.drop_pct >= _DROP_THRESHOLD_PCT
        )


def detect_price_drops(
    market_snapshot: MarketSnapshot | None,
    price_memory: PriceMemoryService,
    *,
    min_observations: int = 2,
) -> list[PriceDropAlert]:
    """Detect price drops for items in the current market snapshot.

    Args:
        market_snapshot: Current market snapshot. ``None`` or empty
            ``normalized_records`` returns an empty list.
        price_memory: A ``PriceMemoryService`` for historical lookups.
        min_observations: Minimum number of historical observations
            required before flagging a drop. Default 2 — one observation
            isn't enough to call something a "drop".

    Returns:
        List of ``PriceDropAlert`` ordered by ``drop_pct`` descending. The
        top ``_MAX_ALERTS`` are intended for display.
    """
    if market_snapshot is None or not market_snapshot.normalized_records:
        return []

    # Group records by (canonical_name, source) — pick the cheapest per
    # source per item so we surface the most attractive source for each drop.
    by_key: dict[tuple[str, str], Any] = {}
    for r in market_snapshot.normalized_records:
        if not getattr(r, "is_available", False):
            continue
        if getattr(r, "is_combo", False) or getattr(r, "is_size_class", False):
            continue
        key = (r.canonical_name, r.source)
        existing = by_key.get(key)
        if existing is None or r.price_inr < existing.price_inr:
            by_key[key] = r

    alerts: list[PriceDropAlert] = []
    for (cname, source), record in by_key.items():
        try:
            summary = price_memory.get_summary(cname)
        except Exception as exc:
            logger.debug("Price drop lookup failed for %s: %s", cname, exc)
            continue

        if summary is None:
            continue
        if summary.observations < min_observations:
            continue
        if summary.median_price is None or summary.median_price <= 0:
            continue
        if summary.last_price is None or summary.last_price <= 0:
            continue

        current = float(record.price_inr)
        median = float(summary.median_price)
        if current >= median:
            continue
        drop_pct = round((median - current) / median * 100, 1)
        if drop_pct < _DROP_THRESHOLD_PCT:
            continue

        alerts.append(PriceDropAlert(
            canonical_name=cname,
            display_name=cname.replace("_", " ").title(),
            source=source,
            current_price=round(current, 2),
            median_price=round(median, 2),
            drop_pct=drop_pct,
            drop_amount=round(median - current, 2),
            last_seen=str(summary.last_seen) if summary.last_seen else "",
        ))

    alerts.sort(key=lambda a: a.drop_pct, reverse=True)
    return alerts


def list_price_drops(db, user_id: str = "") -> list[PriceDropAlert]:
    """High-level wrapper: fetch the current market snapshot and detect drops.

    Convenience function for UI screens (e.g. trip advisor) that have a
    ``Database`` instance and a user_id but no pre-built market snapshot or
    price memory service.

    Returns an empty list if no snapshot is available or no price drops are
    detected. Errors during snapshot/memory construction are logged and
    swallowed so the UI degrades gracefully.
    """
    from shopstack.market.sources.swiggy import load_snapshot
    from shopstack.services.price_memory import PriceMemoryService

    try:
        snapshot = load_snapshot()
    except Exception as exc:
        logger.debug("list_price_drops: snapshot load failed: %s", exc)
        return []

    if snapshot is None or not getattr(snapshot, "normalized_records", None):
        return []

    try:
        price_memory = PriceMemoryService(db)
    except Exception as exc:
        logger.debug("list_price_drops: price memory build failed: %s", exc)
        return []

    return detect_price_drops(snapshot, price_memory)


# ─── HTML rendering ───────────────────────────────────────────────────────


def render_price_drops_html(alerts: list[PriceDropAlert]) -> str:
    """Render the top price-drop alerts as a compact HTML block.

    Only meaningful alerts (≥15% drop) are rendered. If there are no
    drops, returns an empty string so the caller can fall through to
    other widgets.
    """
    actionable = [a for a in alerts if a.is_meaningful][: _MAX_ALERTS]
    if not actionable:
        return ""

    rows: list[str] = []
    for a in actionable:
        # Each row: item name, current price (green), median (dim), drop %
        rows.append(
            f"<div style='padding:5px 0;border-bottom:1px solid var(--border);'><strong>{escape(a.display_name)}</strong> "
            f"<span style='color:var(--text-dim);font-size: 0.625rem;'>at {escape(a.source.title())}</span>"
            f"<br><span style='color:var(--green);font-weight:600;'>"
            f"&#8377;{a.current_price:.0f}</span> <span style='color:var(--text-dim);font-size: 0.625rem;'>"
            f"(was &#8377;{a.median_price:.0f})</span> &middot; "
            f"<span style='color:var(--green);font-size: 0.625rem;'>↓ {a.drop_pct:.0f}% (save &#8377;{a.drop_amount:.0f})</span>"
            f"</div>"
        )

    return (
        f"<div class='home-card' style='margin-bottom:12px;'><h3 style='margin:0 0 4px 0;'>📉 Price Drops</h3>"
        f"<div style='font-size: 0.6875rem;color:var(--text-dim);margin-bottom:6px;'>Items currently priced noticeably below your historical median."
        f"</div>{''.join(rows)}"
        f"</div>"
    )


__all__ = [
    "PriceDropAlert",
    "detect_price_drops",
    "list_price_drops",
    "render_price_drops_html",
]
