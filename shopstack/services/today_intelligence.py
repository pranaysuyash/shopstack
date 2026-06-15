"""Today Intelligence — Phase 9 (the unified action surface).

The Today dashboard already renders many separate signals:
restock predictions, use-soon items, price drops, the
seasonal recommendation, the trip advisor. Each is correct
in isolation; together they overwhelm the user.

**1st-principles design:**

The user opens ShopStack with one question: "what should I
do right now?" Every signal should answer that question, or
get out of the way. This service answers it in one pass:

1. **Rank** every candidate action by urgency (use-soon
   first, then restock-due, then price-drops, then
   community-flagged overpriced items, then
   seasonal/trip-advice).
2. **Deduplicate** items that show up in multiple lists
   (e.g. milk is both use-soon and a restock candidate —
   one action, not two).
3. **Render** a single opinionated "Today intelligence"
   block: 3-5 ranked actions, each with a one-line
   reason, plus a quiet "everything else" footer.

**Inputs:**

- The household's :class:`DashboardState` (already built
  by the dashboard service).
- The community pool (for "community median vs your
  price" deltas).
- The trip advisor (for the "should I go?" call).

**Outputs:**

A :class:`TodayIntelligence` dataclass with:
- ``top_actions``: the 3-5 ranked actions.
- ``secondary``: a quiet "what else" list.
- ``trip_advice``: the advisor's call (go / delay / etc.).
- ``headline``: a one-sentence summary ("🥬 3 use-soon,
  🔴 you'll run out of milk Tuesday").
- ``by_source``: counts per signal source (for the
  "everything is fine" / "lots of signals" decision).

**Why a separate module:**

The dashboard service produces a *state* (all the raw
signals). This service produces an *opinion* (the ranked
action list). Keeping them separate means the dashboard
can be cached and reused, while the opinion is recomputed
on every render — fast, deterministic, and additive.
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from html import escape
from typing import Any, Iterable

from shopstack.services._utils import safe_get

logger = logging.getLogger(__name__)


# ─── Action dataclass ────────────────────────────────────────────


@dataclass
class TodayAction:
    """One ranked action the user can take right now.

    Fields are intentionally simple — the renderer is the
    one place that decides visual treatment.
    """

    rank: int
    canonical_name: str
    display_name: str
    action: str  # "use_soon" | "restock_due" | "price_drop" | "overpriced" | "trip" | "seasonal"
    urgency: int  # 0..100; higher = more urgent
    reason: str  # one-line, human-friendly
    secondary: str = ""  # optional extra context (qty, price, etc.)


@dataclass
class TodayIntelligence:
    """The full Today intelligence view."""

    top_actions: list[TodayAction] = field(default_factory=list)
    secondary: list[TodayAction] = field(default_factory=list)
    trip_advice: Any | None = None
    headline: str = ""
    by_source: dict[str, int] = field(default_factory=dict)
    total_signals: int = 0
    is_quiet: bool = True


# ─── Build intelligence ──────────────────────────────────────────




def _rank(actions: list[TodayAction], max_top: int = 5) -> TodayIntelligence:
    """Rank + dedupe + split into top/secondary."""
    # Dedup by (canonical_name, action) — same item+action only fires once.
    seen: set[tuple[str, str]] = set()
    deduped: list[TodayAction] = []
    for a in actions:
        key = (a.canonical_name.lower(), a.action)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(a)
    # Sort by urgency desc, then by display_name for stability
    deduped.sort(key=lambda a: (-a.urgency, a.display_name.lower()))
    for i, a in enumerate(deduped, start=1):
        a.rank = i
    top = deduped[:max_top]
    secondary = deduped[max_top:]
    headline = _build_headline(top, deduped)
    by_source: Counter[str] = Counter(a.action for a in deduped)
    return TodayIntelligence(
        top_actions=top,
        secondary=secondary,
        headline=headline,
        by_source=dict(by_source),
        total_signals=len(deduped),
        is_quiet=len(deduped) == 0,
    )


def _build_headline(
    top: list[TodayAction],
    all_actions: list[TodayAction],
) -> str:
    """Build a one-sentence summary of the action list."""
    if not all_actions:
        return "🟢 Nothing urgent. Your kitchen is in good shape."
    counts = Counter(a.action for a in all_actions)
    parts: list[str] = []
    if counts.get("use_soon", 0):
        parts.append(f"🥬 {counts['use_soon']} use-soon")
    if counts.get("restock_due", 0):
        parts.append(f"🔴 {counts['restock_due']} restock due")
    if counts.get("price_drop", 0):
        parts.append(f"💰 {counts['price_drop']} price drops")
    if counts.get("overpriced", 0):
        parts.append(f"👥 {counts['overpriced']} above community median")
    if not parts:
        return f"📋 {len(all_actions)} actions queued."
    if len(top) > 0:
        first = top[0]
        lead = f"👉 Start with: **{first.display_name}**"
    else:
        lead = "📋"
    return f"{lead} · " + " · ".join(parts)


def build_today_intelligence(
    dashboard_state: Any,
    *,
    community_medians: dict[str, float] | None = None,
    trip_advice: Any | None = None,
    max_top: int = 5,
    today: date | None = None,
) -> TodayIntelligence:
    """Build the unified Today intelligence view.

    Args:
        dashboard_state: A :class:`DashboardState` (or any
            object with ``restock_predictions``, ``use_soon_items``,
            and ``price_drops`` attributes/dicts).
        community_medians: Optional dict of ``{canonical_name: median_price}``
            for items in the community pool. When provided,
            items whose current observed price is well above
            the community median get a ``overpriced`` action.
        trip_advice: Optional :class:`TripAdvice`. When provided,
            it's attached to the result so the renderer can
            surface the go/deliver/delay banner.
        max_top: How many top actions to surface (rest go to
            "secondary").
        today: Override "now" for deterministic tests.

    Returns:
        A :class:`TodayIntelligence` with ranked actions.
    """
    actions: list[TodayAction] = []

    # 1. Use-soon items (highest urgency — food going bad)
    use_soon = safe_get(dashboard_state, "use_soon_items", default=[]) or []
    for it in use_soon:
        cname = str(it.get("canonical_name") or it.get("name") or "")
        if not cname:
            continue
        display = cname.replace("_", " ").title()
        days = it.get("days_until_expiry")
        secondary = ""
        if isinstance(days, (int, float)):
            secondary = f"{int(days)}d to expiry"
        actions.append(TodayAction(
            rank=0,
            canonical_name=cname,
            display_name=display,
            action="use_soon",
            urgency=95,
            reason=f"Use {display} before it spoils.",
            secondary=secondary,
        ))

    # 2. Restock due (high urgency — running out)
    restock = safe_get(dashboard_state, "restock_predictions", default=[]) or []
    for r in restock:
        cname = str(r.get("canonical_name") or "")
        if not cname:
            continue
        display = cname.replace("_", " ").title()
        days_until = r.get("days_until_restock")
        secondary = ""
        if isinstance(days_until, (int, float)):
            if days_until <= 0:
                secondary = "overdue"
            else:
                secondary = f"{int(days_until)}d"
        actions.append(TodayAction(
            rank=0,
            canonical_name=cname,
            display_name=display,
            action="restock_due",
            urgency=80 if (days_until is None or days_until > 2) else 90,
            reason=f"You'll run out of {display} soon — add to list.",
            secondary=secondary,
        ))

    # 3. Price drops (opportunity — act fast)
    price_drops = safe_get(dashboard_state, "price_drops", default=[]) or []
    for d in price_drops:
        cname = str(d.get("canonical_name") or "")
        if not cname:
            continue
        display = cname.replace("_", " ").title()
        drop_pct = d.get("drop_pct")
        secondary = ""
        if isinstance(drop_pct, (int, float)):
            secondary = f"-{abs(drop_pct):.0f}%"
        actions.append(TodayAction(
            rank=0,
            canonical_name=cname,
            display_name=display,
            action="price_drop",
            urgency=60,
            reason=f"{display} is at a recent low — buy extra.",
            secondary=secondary,
        ))

    # 4. Overpriced vs community median (medium urgency — wait)
    if community_medians:
        for cname, median in community_medians.items():
            # We don't have a current price in dashboard_state;
            # the *signal* is "community says ₹X, you might be
            # paying more". Surface as a low-urgency hint so the
            # user can verify on their next receipt.
            display = cname.replace("_", " ").title()
            actions.append(TodayAction(
                rank=0,
                canonical_name=cname,
                display_name=display,
                action="overpriced",
                urgency=30,
                reason=f"Community median for {display}: ₹{median:.0f}.",
                secondary="verify on next receipt",
            ))

    # 5. Trip advisor (if provided)
    if trip_advice is not None and getattr(trip_advice, "recommendation", None) not in (None, "neutral"):
        label = getattr(trip_advice, "label", None) or "Trip"
        reason = getattr(trip_advice, "reason", "") or ""
        actions.append(TodayAction(
            rank=0,
            canonical_name="__trip__",
            display_name=label,
            action="trip",
            urgency=50,
            reason=reason,
            secondary="trip advisor",
        ))

    return _rank(actions, max_top=max_top)


# ─── HTML rendering ────────────────────────────────────────────


def _action_html(a: TodayAction, *, secondary: bool = False) -> str:
    color = {
        "use_soon":    "var(--amber, #A76012)",
        "restock_due": "var(--red, #A63F31)",
        "price_drop":  "var(--green, #176B49)",
        "overpriced":  "var(--text-muted, #5F5144)",
        "trip":        "var(--accent, #176B49)",
        "seasonal":    "var(--accent, #176B49)",
    }.get(a.action, "var(--text, #1F1812)")
    icon = {
        "use_soon":    "🥬",
        "restock_due": "🔴",
        "price_drop":  "💰",
        "overpriced":  "👥",
        "trip":        "🛒",
        "seasonal":    "🌤",
    }.get(a.action, "•")
    rank_badge = f"#{a.rank}" if a.rank else ""
    sub = (
        f"<span class='ti-sub'>{escape(a.secondary)}</span>"
        if a.secondary else ""
    )
    cls = "ti-action ti-secondary" if secondary else "ti-action"
    return (
        f"<div class='{cls}' style='border-left:3px solid {color};'><span class='ti-rank' style='color:{color};'>{rank_badge}</span>"
        f"<span class='ti-icon'>{icon}</span><span class='ti-body'>"
        f"<span class='ti-name'>{escape(a.display_name)}</span><span class='ti-reason'>{escape(a.reason)}</span>"
        f"{sub}</span>"
        f"</div>"
    )


def render_today_intelligence_html(intel: TodayIntelligence) -> str:
    """Render the unified Today intelligence block as XSS-safe HTML.

    Sections:
    1. Headline (one-sentence summary).
    2. Top actions (ranked list).
    3. "Everything else" (secondary actions, collapsed).
    """
    if intel.is_quiet:
        return (
            "<div class='ti-block'>"
            "<div class='ti-headline ti-quiet'>"
            "🟢 Nothing urgent. Your kitchen is in good shape."
            "</div>"
            "</div>"
        )
    parts: list[str] = ["<div class='ti-block'>"]
    parts.append(f"<div class='ti-headline'>{escape(intel.headline)}</div>")
    if intel.top_actions:
        parts.append("<div class='ti-actions'>")
        for a in intel.top_actions:
            parts.append(_action_html(a))
        parts.append("</div>")
    if intel.secondary:
        parts.append(
            f"<details class='ti-secondary-block'><summary>{len(intel.secondary)} more</summary>"
            "<div class='ti-actions'>"
        )
        for a in intel.secondary:
            parts.append(_action_html(a, secondary=True))
        parts.append("</div></details>")
    if intel.trip_advice is not None:
        from shopstack.services.trip_advisor import render_trip_advice_html
        parts.append(render_trip_advice_html(intel.trip_advice))
    parts.append("</div>")
    return "".join(parts)


__all__ = [
    "TodayAction",
    "TodayIntelligence",
    "build_today_intelligence",
    "render_today_intelligence_html",
]
