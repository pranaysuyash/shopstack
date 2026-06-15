"""Home flow state — what state is the household in, what should Today show?

**Why this exists (motto_v3 §0.14 product reality):**

A user opening ShopStack for the first time has no data. The
"intelligence" sections (restock, use-soon, price-drop) need real
purchase history to be useful. The previous Home screen showed all
of those sections regardless, with zeros and "no predictions yet"
copy. Result: a new user saw an empty debug dashboard instead of a
guided "let me help you get set up" experience.

This module answers two questions for the renderer:

1. **What state is the household in?** (first-run / starting-out /
   quiet / active). The state is a single enum that the renderer
   reads to pick which sections to show.

2. **What headline + subhead should the page show?** (one short
   sentence for the user, then one explanatory sentence).

**Architecture (motto_v3 §0.15 third-layer rule):**

* model — none. The state is computed from DB counts and the
  onboarding completion flag.
* pipeline — :func:`detect_home_state` → :class:`HomeFlowState` →
  consumed by the dashboard renderer.
* data/config — the threshold counts live in :data:`STATE_THRESHOLDS`.
  New states are added by widening the enum + adding a new threshold.

**Supersession (motto_v3 §7):**

The existing "first-run onboarding gate" inline in
:mod:`shopstack.ui.screens.dashboard._render_onboarding_gate` is
*not* deleted. The new :func:`detect_home_state` is the canonical
source of truth, and `_render_onboarding_gate` now delegates to it.
Old direct-imports continue to work; new code should use
:func:`detect_home_state` directly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ── State enum ──────────────────────────────────────────────────────


class HomeState(str, Enum):
    """The four high-level states the Home page can be in.

    Values are stable strings — they appear in CSS class names and
    in tests.
    """

    FIRST_RUN = "first_run"
    """Onboarding incomplete + zero data. Show the setup-first flow."""

    STARTING_OUT = "starting_out"
    """Onboarding complete but < 5 items or 0 purchases. Show the
    'add your first 5 staples' guidance."""

    QUIET = "quiet"
    """Household has data but no urgent actions. Show 'all caught up'."""

    ACTIVE = "active"
    """Household has data and active signals. Show full intelligence."""


# ── State thresholds (single source of truth) ─────────────────────


STATE_THRESHOLDS: dict[str, dict[str, int]] = {
    "min_items_for_starting_out_exit": {"items": 5},
    "min_purchases_for_active": {"purchases": 3},
    # "active" requires at least one signal *and* at least one signal
    # with non-empty content; we don't try to predict that here.
}


# ── State dataclass ────────────────────────────────────────────────


@dataclass(frozen=True)
class HomeFlowState:
    """Computed state of the home page for a given household.

    Attributes:
        state: The high-level enum value.
        headline: One short sentence the page should display as its
            hero header (e.g. "Your kitchen is in good shape.").
        subhead: One sentence explaining the headline (e.g. "No
            urgent restocks. 3 items worth checking this week.").
        onboarding_complete: True if the household finished setup.
        item_count: Number of active inventory items.
        purchase_count: Number of purchase history rows.
        signal_count: Total number of actionable signals (use-soon,
            restock-due, price-drop, etc.) — set by the dashboard
            service, not by this module.
    """

    state: HomeState
    headline: str
    subhead: str
    onboarding_complete: bool
    item_count: int
    purchase_count: int
    signal_count: int

    @property
    def show_intelligence(self) -> bool:
        """True if the page should render the full intelligence block."""
        return self.state in (HomeState.ACTIVE, HomeState.QUIET)

    @property
    def show_setup_gate(self) -> bool:
        """True if the page should render the setup-first hero."""
        return self.state == HomeState.FIRST_RUN

    @property
    def show_empty_hints(self) -> bool:
        """True if the page should render the 'add your first 5 staples' card."""
        return self.state == HomeState.STARTING_OUT


# ── State detection ────────────────────────────────────────────────


def detect_home_state(
    *,
    onboarding_complete: bool,
    item_count: int,
    purchase_count: int,
    signal_count: int = 0,
) -> HomeFlowState:
    """Pick a :class:`HomeFlowState` from raw household metrics.

    The rules are intentionally simple so the state machine is
    auditable in one read:

        first_run       → onboarding incomplete (any data state)
        starting_out    → onboarding complete, but < 5 items
        quiet           → 5+ items, 0 signals
        active          → 5+ items, 1+ signals

    The order of checks matters: the *first* matching rule wins.
    """
    if not onboarding_complete:
        return HomeFlowState(
            state=HomeState.FIRST_RUN,
            headline="Set up ShopStack in 2 minutes",
            subhead=(
                "Tell us about your household so we can start making useful "
                "suggestions — what to buy, what to use, and what to skip."
            ),
            onboarding_complete=False,
            item_count=item_count,
            purchase_count=purchase_count,
            signal_count=signal_count,
        )

    if item_count < STATE_THRESHOLDS["min_items_for_starting_out_exit"]["items"]:
        return HomeFlowState(
            state=HomeState.STARTING_OUT,
            headline="Add a few staples to unlock intelligence",
            subhead=(
                "Add 5 common items you buy often — milk, bread, rice, eggs, "
                "curd. ShopStack will start predicting refill dates after a "
                "few purchases."
            ),
            onboarding_complete=True,
            item_count=item_count,
            purchase_count=purchase_count,
            signal_count=signal_count,
        )

    if signal_count <= 0:
        return HomeFlowState(
            state=HomeState.QUIET,
            headline="Your kitchen is in good shape",
            subhead=(
                "No urgent restocks right now. Add a few more items or check "
                "the Memory tab for what ShopStack has learned so far."
            ),
            onboarding_complete=True,
            item_count=item_count,
            purchase_count=purchase_count,
            signal_count=signal_count,
        )

    return HomeFlowState(
        state=HomeState.ACTIVE,
        headline=(
            f"{signal_count} action{'s' if signal_count != 1 else ''} worth your attention"
        ),
        subhead=(
            "Your next best shopping actions, ranked by urgency, price, "
            "and household usage."
        ),
        onboarding_complete=True,
        item_count=item_count,
        purchase_count=purchase_count,
        signal_count=signal_count,
    )


def detect_home_state_from_db(
    db: Any,
    user_id: str = "",
) -> HomeFlowState:
    """Convenience wrapper: build a :class:`HomeFlowState` from the DB.

    Best-effort: any exception returns a :class:`HomeState.FIRST_RUN`
    with zero counts. We never want a missing state to crash the page
    render.
    """
    try:
        from shopstack.services.onboarding import is_onboarding_complete

        items = db.get_inventory(user_id=user_id) if db else []
        active_items = [lot for lot in items if getattr(lot, "status", "active") == "active"]
        return detect_home_state(
            onboarding_complete=is_onboarding_complete(db) if db else False,
            item_count=len(active_items),
            purchase_count=0,  # dashboard service fills this in
            signal_count=0,    # dashboard service fills this in
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("detect_home_state_from_db failed: %s", exc)
        return detect_home_state(
            onboarding_complete=False,
            item_count=0,
            purchase_count=0,
            signal_count=0,
        )


__all__ = [
    "HomeFlowState",
    "HomeState",
    "STATE_THRESHOLDS",
    "detect_home_state",
    "detect_home_state_from_db",
]
