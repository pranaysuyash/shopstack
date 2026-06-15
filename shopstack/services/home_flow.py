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
    """The high-level states the Home page can be in.

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

    ERROR = "error"
    """2026-06-15: the state machine could not determine a safe
    state. Distinct from FIRST_RUN (which is a real "no data yet"
    state for a brand-new household) — ERROR means "we don't
    know, the data layer is failing, do not show onboarding copy
    to a returning user". Renders a "Something went wrong" panel
    with a retry button instead of misleading setup-first copy."""


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

    @property
    def show_error_panel(self) -> bool:
        """True if the page should render the "something went wrong" panel.

        2026-06-15 supersession (motto_v3 §6 pre-existing is not
        an excuse): the prior implementation silently fell back to
        ``FIRST_RUN`` on any DB exception, which caused a returning
        user with 200 items to see "Set up ShopStack in 2 minutes"
        when the data layer was failing. ERROR is a distinct state
        so the renderer can show a useful error + retry instead of
        misleading setup-first copy.
        """
        return self.state == HomeState.ERROR


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

    2026-06-15 (motto_v3 §6 + §0.14 product reality): the prior
    implementation silently returned ``FIRST_RUN`` on any DB
    exception, which was misleading for returning users (they saw
    "Set up ShopStack in 2 minutes" when the data layer was
    failing). We now distinguish three outcomes:

    1. **Success** — return the real state (FIRST_RUN /
       STARTING_OUT / QUIET / ACTIVE) computed from the DB.
    2. **No DB** — return FIRST_RUN with zero counts (this is the
       legitimate "no household yet" case).
    3. **DB exception** — return ``ERROR`` so the renderer can
       show a "Something went wrong" panel + retry, and log the
       exception at ``error`` level so operators can see it
       (previously ``debug``, which meant no one saw it).
    """
    if db is None:
        return detect_home_state(
            onboarding_complete=False,
            item_count=0,
            purchase_count=0,
            signal_count=0,
        )
    try:
        from shopstack.services.onboarding import is_onboarding_complete

        items = db.get_inventory(user_id=user_id)
        active_items = [lot for lot in items if getattr(lot, "status", "active") == "active"]
        return detect_home_state(
            onboarding_complete=is_onboarding_complete(db),
            item_count=len(active_items),
            purchase_count=0,  # dashboard service fills this in
            signal_count=0,    # dashboard service fills this in
        )
    except Exception as exc:  # noqa: BLE001
        # Log at error level so operators can see the failure.
        # Previously logger.debug, which meant production failures
        # were invisible.
        logger.error(
            "detect_home_state_from_db failed for user_id=%r: %s",
            user_id, exc,
            exc_info=True,
        )
        return HomeFlowState(
            state=HomeState.ERROR,
            headline="Something went wrong on our end",
            subhead=(
                "We couldn't read your data just now. Your inventory and "
                "shopping lists are safe — try the Refresh button on the "
                "Today tab. If it keeps happening, check back in a few minutes."
            ),
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
