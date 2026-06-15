"""Home flow renderer — the state-aware hero panel for the Today tab.

**Why this exists (motto_v3 §0.14 product reality):**

The legacy :mod:`shopstack.ui.screens.dashboard` module renders six
separate HTML fragments plus an "intelligence" block plus an empty
greeting. The user sees four overlapping surfaces and the renderer
duplicates the first-run logic in three places.

This module replaces that with a *single* state-aware hero:

* :func:`render_home_flow` — one entry point. Reads the household
  state from :func:`shopstack.services.home_flow.detect_home_state`
  and renders the appropriate hero (setup gate / starting-out /
  quiet / active). All existing screens are delegated to from this
  single render so we can never have a hero that disagrees with the
  detail panel below it.

**Architecture (motto_v3 §0.15 third-layer rule):**

* model — none.
* pipeline — :func:`detect_home_state` → :func:`render_home_flow` →
  single HTML string.
* data/config — :data:`_HEROES` maps :class:`HomeState` to a
  renderer. New states are added by extending the enum + adding a
  renderer here.

**Supersession (motto_v3 §7):**

The legacy :func:`shopstack.ui.screens.dashboard.today_dashboard`
function is *not* deleted. It continues to render the six-component
detail panel that the new tab builder still includes (for back-
compat with external callers and tests). The home flow is the new
canonical hero. Old ``_render_onboarding_gate`` / ``_render_today_*``
helpers in :mod:`dashboard` are kept; this module just supersedes
them as the single entry point.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape
from typing import Any

from shopstack.app_context import current_user_id, db, tools
from shopstack.services.dashboard import build_dashboard_state
from shopstack.services.home_flow import (
    HomeFlowState,
    HomeState,
    detect_home_state,
    detect_home_state_from_db,
)
from shopstack.services.intelligence_cards import (
    ConfidenceLabel,
    build_buy_soon_card,
    build_memory_card,
    build_price_drop_card,
    build_price_overpriced_card,
    build_restock_card,
    build_skip_card,
    build_trip_card,
    build_use_soon_card,
    render_intelligence_card,
)
from shopstack.services.today_intelligence import build_today_intelligence
from shopstack.ui.components.primitives import home_card

logger = logging.getLogger(__name__)


# ── Hero renderers per state ────────────────────────────────────────


def _render_hero(state: HomeFlowState) -> str:
    """The headline + subhead block at the top of the home flow panel."""
    return (
        "<div class='home-flow-hero'>"
        f"<h2 class='home-flow-headline'>{escape(state.headline)}</h2>"
        f"<p class='home-flow-subhead'>{escape(state.subhead)}</p>"
        "</div>"
    )


def _render_setup_gate(state: HomeFlowState) -> str:
    """First-run: large CTA pointing at the setup wizard."""
    body = (
        "<div class='home-flow-setup-cta'>"
        "<p>Setup takes about 2 minutes. We'll ask about:</p>"
        "<ul>"
        "<li>How many people are in your household</li>"
        "<li>What you usually buy</li>"
        "<li>Where you usually shop</li>"
        "<li>Your city (for weather-aware suggestions)</li>"
        "</ul>"
        "<button type='button' class='home-flow-primary-cta' "
        "onclick=\"var w=document.getElementById('onboarding-wizard');"
        "if(w){w.style.display='block';w.scrollIntoView({behavior:'smooth',block:'center'});}\">"
        "Set up my household"
        "</button>"
        "<button type='button' class='home-flow-secondary-cta' "
        "onclick=\"var el=document.getElementById('add-items-btn');if(el)el.click();\">"
        "Skip setup, add items manually"
        "</button>"
        "</div>"
    )
    return home_card(title="Welcome to ShopStack", body=body, extra_class="home-flow-card--setup")


def _render_starting_out(state: HomeFlowState) -> str:
    """Onboarding complete but no data: actionable 'add your first 5' card."""
    chips = [
        "milk", "bread", "eggs", "rice", "curd",
        "wheat_flour", "toor_dal", "onion", "tomato", "cooking_oil",
    ]
    chips_html = "".join(
        f"<button type='button' class='cmd-chip' data-chip='{escape(chip)}' "
        f"onclick=\"ssCommandFillChip('add '+this.getAttribute('data-chip'))\">"
        f"{escape(chip.replace('_', ' ').title())}</button>"
        for chip in chips
    )
    body = (
        "<p>Start with the 5 you buy most often. ShopStack starts predicting "
        "refill dates after a few purchases.</p>"
        f"<div class='home-flow-staples'>{chips_html}</div>"
        "<p style='font-size:0.8125rem;color:var(--text-dim);margin-top:12px;'>"
        "Or scan a receipt, import a Swiggy order, or type a free-form "
        "command in the box above."
        "</p>"
    )
    return home_card(title="Add your first 5 staples", body=body, extra_class="home-flow-card--starting-out")


def _render_quiet(state: HomeFlowState) -> str:
    """Household has data but no urgent signals."""
    body = (
        "<p style='color:var(--text-muted);'>"
        "Nothing needs attention right now. When something does, you'll see it here."
        "</p>"
        "<p style='font-size:0.8125rem;color:var(--text-dim);'>"
        "Use the command box above to add what you bought, or check the "
        "Pantry tab to see everything at home."
        "</p>"
    )
    return home_card(
        title="All caught up",
        body=body,
        extra_class="home-flow-card--quiet",
    )


def _render_active(state: HomeFlowState) -> str:
    """Household has data and signals: render the ranked intelligence cards."""
    try:
        user_id = state.item_count and (current_user_id() or "") or ""
        dashboard_state = build_dashboard_state(
            db, tools.inventory, user_id=user_id
        )
        intel = build_today_intelligence(dashboard_state, max_top=5)
        return _render_intel(intel)
    except Exception as exc:  # noqa: BLE001
        logger.warning("active home flow render failed: %s", exc)
        return home_card(
            title="Today",
            body=(
                "<p>Could not load the intelligence panel right now.</p>"
                f"<p style='color:var(--text-dim);font-size:0.75rem;'>{escape(str(exc)[:120])}</p>"
            ),
            extra_class="home-flow-card--active",
        )


def _render_intel(intel: Any) -> str:
    """Render a :class:`TodayIntelligence` as a stack of intelligence cards."""
    if not intel.top_actions and not intel.secondary:
        return _render_quiet(HomeFlowState(
            state=HomeState.QUIET,
            headline="Your kitchen is in good shape",
            subhead="No urgent restocks right now.",
            onboarding_complete=True,
            item_count=0,
            purchase_count=0,
            signal_count=0,
        ))
    cards: list[str] = []
    for action in intel.top_actions:
        cards.append(_action_to_card(action))
    secondary_html = ""
    if intel.secondary:
        secondary_cards = "".join(_action_to_card(a) for a in intel.secondary)
        secondary_html = (
            f"<details class='home-flow-secondary'><summary>"
            f"{len(intel.secondary)} more action"
            f"{'s' if len(intel.secondary) != 1 else ''}</summary>"
            f"{secondary_cards}</details>"
        )
    return (
        "<div class='home-flow-intel'>"
        + "".join(cards)
        + secondary_html
        + "</div>"
    )


def _action_to_card(action: Any) -> str:
    """Convert a :class:`TodayAction` into the appropriate intelligence card."""
    display = action.display_name
    confidence = ConfidenceLabel(
        level="medium",
        text="Based on your household's recent activity",
    )
    if action.action == "use_soon":
        return render_intelligence_card(
            build_use_soon_card(
                item=display,
                days_until_expiry=_safe_int(action.secondary),
                confidence=confidence,
                last_updated=datetime.now(timezone.utc),
            )
        )
    if action.action == "restock_due":
        return render_intelligence_card(
            build_restock_card(
                item=display,
                days_until=_safe_int(action.secondary),
                confidence=confidence,
                last_updated=datetime.now(timezone.utc),
            )
        )
    if action.action == "price_drop":
        return render_intelligence_card(
            build_price_drop_card(
                item=display,
                drop_pct=_safe_float(action.secondary) or 0.0,
                confidence=confidence,
            )
        )
    if action.action == "overpriced":
        return render_intelligence_card(
            build_price_overpriced_card(
                item=display,
                observed_price=0.0,
                community_median=0.0,
            )
        )
    if action.action == "trip":
        return render_intelligence_card(
            build_trip_card(
                label=display,
                reason=action.reason,
                secondary=action.secondary,
            )
        )
    # Fallback: render as a buy-soon card.
    return render_intelligence_card(
        build_buy_soon_card(item=display, confidence=confidence)
    )


def _safe_int(s: str) -> int | None:
    """Parse a string like '2d' or '2' into an int, or None."""
    if not s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit() or ch == "-")
    try:
        return int(digits)
    except ValueError:
        return None


def _safe_float(s: str) -> float | None:
    """Parse a string like '-12%' or '12' into a float, or None."""
    if not s:
        return None
    cleaned = s.replace("%", "").replace("-", "", 1) if s.startswith("-") else s.replace("%", "")
    if cleaned.startswith("-"):
        cleaned = "-" + cleaned.lstrip("-")
    try:
        return float(cleaned)
    except ValueError:
        return None


# ── State → hero dispatcher ─────────────────────────────────────────


_HEROES = {
    HomeState.FIRST_RUN: _render_setup_gate,
    HomeState.STARTING_OUT: _render_starting_out,
    HomeState.QUIET: _render_quiet,
    HomeState.ACTIVE: _render_active,
}


# ── Public entry point ─────────────────────────────────────────────


def render_home_flow(
    *,
    user_id: str = "",
    force_state: HomeState | None = None,
) -> str:
    """Render the full home flow panel (hero + state-specific body).

    Args:
        user_id: Active household id. Falls back to
            :func:`current_user_id` if empty.
        force_state: Optional state to render regardless of detection.
            Used by tests and by the Ask-via-state call site.

    Returns:
        XSS-safe HTML safe to inject via :class:`gr.HTML`.
    """
    try:
        if force_state is not None:
            state = _synthesise_state_for(force_state, user_id=user_id)
        else:
            state = _detect_state(user_id)
        hero = _render_hero(state)
        body_fn = _HEROES.get(state.state, _render_quiet)
        body = body_fn(state)
        return (
            "<div class='home-flow'>"
            f"{hero}"
            f"{body}"
            "</div>"
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("render_home_flow failed: %s", exc)
        return home_card(
            title="Today",
            body=(
                "<p>Could not load the home panel right now.</p>"
                f"<p style='color:var(--text-dim);font-size:0.75rem;'>{escape(str(exc)[:120])}</p>"
            ),
        )


def _detect_state(user_id: str) -> HomeFlowState:
    """Detect the current home state with rich signal_count."""
    base = detect_home_state_from_db(db, user_id=user_id)
    if base.state not in (HomeState.QUIET, HomeState.ACTIVE):
        return base
    # For QUIET/ACTIVE, compute signal_count from the dashboard.
    try:
        ds = build_dashboard_state(db, tools.inventory, user_id=user_id)
        use_soon = len(ds.use_soon_items)
        restock = len(ds.restock_predictions or [])
        drops = len(ds.price_drops or [])
        signal_count = use_soon + restock + drops
        if base.state == HomeState.QUIET and signal_count > 0:
            return detect_home_state(
                onboarding_complete=True,
                item_count=base.item_count,
                purchase_count=base.purchase_count,
                signal_count=signal_count,
            )
        if base.state == HomeState.ACTIVE and signal_count == 0:
            return detect_home_state(
                onboarding_complete=True,
                item_count=base.item_count,
                purchase_count=base.purchase_count,
                signal_count=0,
            )
        return detect_home_state(
            onboarding_complete=True,
            item_count=base.item_count,
            purchase_count=base.purchase_count,
            signal_count=signal_count,
        )
    except Exception:  # noqa: BLE001
        return base


def _synthesise_state_for(state: HomeState, *, user_id: str) -> HomeFlowState:
    """Build a state-matching :class:`HomeFlowState` without detection."""
    if state == HomeState.FIRST_RUN:
        return detect_home_state(
            onboarding_complete=False,
            item_count=0,
            purchase_count=0,
            signal_count=0,
        )
    if state == HomeState.STARTING_OUT:
        return detect_home_state(
            onboarding_complete=True,
            item_count=0,
            purchase_count=0,
            signal_count=0,
        )
    if state == HomeState.QUIET:
        return detect_home_state(
            onboarding_complete=True,
            item_count=5,
            purchase_count=1,
            signal_count=0,
        )
    return detect_home_state(
        onboarding_complete=True,
        item_count=10,
        purchase_count=5,
        signal_count=3,
    )


__all__ = ["render_home_flow"]
