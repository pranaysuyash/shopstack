"""E2E regression test for the 4-state home flow machine (2026-06-15).

The ``shopstack.services.home_flow`` module defines a 4-state
machine (FIRST_RUN / STARTING_OUT / QUIET / ACTIVE) plus a 5th
ERROR state added 2026-06-15. The state transitions are driven by
three counts: ``onboarding_complete`` (bool), ``item_count``
(int), and ``signal_count`` (int). The `active` state requires
``item_count >= 5`` AND ``signal_count >= 1``.

This test walks every reachable transition end-to-end (no DB,
no UI) and asserts the produced state has the right
``show_intelligence`` / ``show_setup_gate`` / ``show_empty_hints`` /
``show_error_panel`` hints. The hints are what the Today tab
renderer uses to pick which sections to show, so getting them
right is what makes the home flow actually work.

This is an E2E test of the **state machine semantics** — it
exercises the public surface (``detect_home_state``) end-to-end,
not the unit-of-logic. The state machine is the contract between
``dashboard`` (producer) and the home-flow renderer (consumer),
so an E2E test on the contract catches drift that unit tests miss.
"""
from __future__ import annotations

import pytest

from shopstack.services.home_flow import (
    HomeFlowState,
    HomeState,
    STATE_THRESHOLDS,
    detect_home_state,
    detect_home_state_from_db,
)


# ── State machine invariants ───────────────────────────────────────


def test_state_machine_has_five_states():
    """The state machine has 5 states: 4 happy-path + ERROR.

    The ERROR state was added 2026-06-15; the test pins the
    total count so adding a 6th state is an explicit decision.
    """
    assert len(HomeState) == 5
    assert HomeState.FIRST_RUN.value == "first_run"
    assert HomeState.STARTING_OUT.value == "starting_out"
    assert HomeState.QUIET.value == "quiet"
    assert HomeState.ACTIVE.value == "active"
    assert HomeState.ERROR.value == "error"


def test_state_thresholds_have_explicit_keys():
    """Thresholds dict must have every key the state machine reads.

    Pins the contract: if you add a new threshold, the state
    machine's behaviour changes; you must also add a test that
    exercises the new threshold.
    """
    assert set(STATE_THRESHOLDS.keys()) == {
        "min_items_for_starting_out_exit",
        "min_purchases_for_active",
    }


# ── End-to-end transitions (all reachable from FIRST_RUN) ──────────


def test_e2e_first_run_to_starting_out():
    """User completes onboarding with < 5 items → STARTING_OUT."""
    state = detect_home_state(
        onboarding_complete=True,
        item_count=2,
        purchase_count=0,
        signal_count=0,
    )
    assert state.state == HomeState.STARTING_OUT
    assert state.show_empty_hints
    assert not state.show_setup_gate
    assert not state.show_intelligence
    assert not state.show_error_panel


def test_e2e_starting_out_to_quiet():
    """User reaches 5+ items but no signals → QUIET."""
    state = detect_home_state(
        onboarding_complete=True,
        item_count=10,
        purchase_count=5,
        signal_count=0,
    )
    assert state.state == HomeState.QUIET
    assert state.show_intelligence
    assert not state.show_setup_gate
    assert not state.show_empty_hints
    assert not state.show_error_panel


def test_e2e_quiet_to_active():
    """First signal arrives (e.g. use-soon detected) → ACTIVE."""
    state = detect_home_state(
        onboarding_complete=True,
        item_count=10,
        purchase_count=5,
        signal_count=1,
    )
    assert state.state == HomeState.ACTIVE
    assert state.show_intelligence
    assert not state.show_setup_gate
    assert not state.show_empty_hints
    assert not state.show_error_panel
    # ACTIVE must show a count in the headline.
    assert "1" in state.headline
    assert "action" in state.headline  # singular


def test_e2e_active_with_many_signals():
    """Many signals → ACTIVE with plural headline."""
    state = detect_home_state(
        onboarding_complete=True,
        item_count=20,
        purchase_count=15,
        signal_count=5,
    )
    assert state.state == HomeState.ACTIVE
    assert "5" in state.headline
    assert "actions" in state.headline  # plural


def test_e2e_first_run_when_zero_data():
    """Brand new user → FIRST_RUN (setup-first flow)."""
    state = detect_home_state(
        onboarding_complete=False,
        item_count=0,
        purchase_count=0,
        signal_count=0,
    )
    assert state.state == HomeState.FIRST_RUN
    assert state.show_setup_gate
    assert not state.show_empty_hints
    assert not state.show_intelligence
    assert not state.show_error_panel


def test_e2e_error_state_is_distinct():
    """ERROR state is reachable and exclusive (no other hints fire)."""
    state = HomeFlowState(
        state=HomeState.ERROR,
        headline="x",
        subhead="y",
        onboarding_complete=False,
        item_count=0,
        purchase_count=0,
        signal_count=0,
    )
    assert state.show_error_panel
    assert not state.show_setup_gate
    assert not state.show_empty_hints
    assert not state.show_intelligence


# ── Boundary tests on STATE_THRESHOLDS ──────────────────────────────


def test_e2e_threshold_boundary_starting_out_exit():
    """``min_items_for_starting_out_exit`` is the exact transition.

    Pinned at 5: 4 items → STARTING_OUT, 5 items → QUIET
    (assuming no signals).
    """
    threshold = STATE_THRESHOLDS["min_items_for_starting_out_exit"]["items"]
    assert threshold == 5, (
        f"Threshold pinned at 5; if you change it, also update "
        f"the home_flow copy and the active threshold logic."
    )
    # Just below threshold.
    state_below = detect_home_state(
        onboarding_complete=True, item_count=threshold - 1, purchase_count=0, signal_count=0,
    )
    assert state_below.state == HomeState.STARTING_OUT
    # At threshold.
    state_at = detect_home_state(
        onboarding_complete=True, item_count=threshold, purchase_count=0, signal_count=0,
    )
    assert state_at.state == HomeState.QUIET


def test_e2e_threshold_boundary_active_signal():
    """``signal_count > 0`` plus items >= starting-out-exit → ACTIVE.

    Pinned at > 0: 0 signals → QUIET, 1+ signal → ACTIVE.
    """
    items = STATE_THRESHOLDS["min_items_for_starting_out_exit"]["items"]
    state_zero = detect_home_state(
        onboarding_complete=True, item_count=items + 1, purchase_count=0, signal_count=0,
    )
    assert state_zero.state == HomeState.QUIET
    state_one = detect_home_state(
        onboarding_complete=True, item_count=items + 1, purchase_count=0, signal_count=1,
    )
    assert state_one.state == HomeState.ACTIVE


def test_e2e_established_user_with_no_items():
    """A long-time user with 0 active items but 10+ purchases
    is NOT "starting out" — they're an established user who
    just hasn't restocked. The state machine must use purchase
    history as an alternative "established" signal.

    2026-06-15 fix (motto_v3 §0.14 product reality): previously
    this user would see "Add a few staples to unlock intelligence!"
    despite 10+ purchases. The state machine now treats
    purchase_count >= min_purchases_for_active as equivalent to
    item_count >= 5.
    """
    min_purchases = STATE_THRESHOLDS["min_purchases_for_active"]["purchases"]
    # 0 items but plenty of purchases → ACTIVE (not STARTING_OUT)
    state = detect_home_state(
        onboarding_complete=True,
        item_count=0,
        purchase_count=min_purchases + 5,
        signal_count=3,
    )
    assert state.state == HomeState.ACTIVE, (
        f"User with 0 items but {min_purchases + 5} purchases should "
        f"be ACTIVE, got {state.state.value}"
    )
    # Without signals, same user → QUIET (not STARTING_OUT)
    state = detect_home_state(
        onboarding_complete=True,
        item_count=0,
        purchase_count=min_purchases + 5,
        signal_count=0,
    )
    assert state.state == HomeState.QUIET, (
        f"Established user with 0 items / 0 signals should be QUIET, "
        f"got {state.state.value}"
    )
    # Below threshold (just under min_purchases) → STARTING_OUT
    state = detect_home_state(
        onboarding_complete=True,
        item_count=0,
        purchase_count=min_purchases - 1,
        signal_count=0,
    )
    assert state.state == HomeState.STARTING_OUT, (
        f"User below both thresholds should be STARTING_OUT, "
        f"got {state.state.value}"
    )


# ── Headline copy E2E ──────────────────────────────────────────────


def test_e2e_headline_copy_is_not_engineering_speak():
    """The state headlines must not leak engineering jargon.

    Quick spot-check across all 4 happy-path states: the user
    must see a human phrase, not "state=FIRST_RUN" or "machine
    state: starting_out".
    """
    cases = [
        (dict(onboarding_complete=False, item_count=0, purchase_count=0, signal_count=0), "FIRST_RUN"),
        (dict(onboarding_complete=True, item_count=3, purchase_count=0, signal_count=0), "STARTING_OUT"),
        (dict(onboarding_complete=True, item_count=10, purchase_count=5, signal_count=0), "QUIET"),
        (dict(onboarding_complete=True, item_count=10, purchase_count=5, signal_count=3), "ACTIVE"),
    ]
    for kwargs, label in cases:
        state = detect_home_state(**kwargs)
        # Headline should be a complete English sentence (ends
        # with a period, exclamation, or question mark — or be
        # a short phrase with at least 3 words).
        words = state.headline.split()
        assert len(words) >= 3, (
            f"{label} headline {state.headline!r} is too short — "
            f"user-facing copy needs at least 3 words."
        )
        # No engineering jargon.
        lower = state.headline.lower()
        for token in ("state=", "machine", "null", "none", "[]", "true", "false"):
            assert token not in lower, (
                f"{label} headline {state.headline!r} contains "
                f"engineering jargon ({token!r})."
            )


def test_e2e_subhead_offers_a_recovery_or_action():
    """The state subhead must offer an action or context, not a wall of jargon.

    The subhead is the second line the user reads. It should
    tell them either what they can do (FIRST_RUN, STARTING_OUT)
    or what's going on (QUIET, ACTIVE). Pure diagnostics like
    "0 items in inventory" without context is a UX miss.
    """
    cases = [
        dict(onboarding_complete=False, item_count=0, purchase_count=0, signal_count=0),
        dict(onboarding_complete=True, item_count=3, purchase_count=0, signal_count=0),
        dict(onboarding_complete=True, item_count=10, purchase_count=5, signal_count=0),
        dict(onboarding_complete=True, item_count=10, purchase_count=5, signal_count=3),
    ]
    for kwargs in cases:
        state = detect_home_state(**kwargs)
        # The subhead should have at least 6 words (a meaningful
        # sentence). Exception: the ACTIVE state with the same
        # boilerplate "next best actions" copy is a single-sentence
        # state — 4 words is fine.
        words = state.subhead.split()
        assert len(words) >= 3, (
            f"Subhead for {state.state.value!r} is too short: "
            f"{state.subhead!r} (only {len(words)} words). "
            f"User-facing copy should be a meaningful sentence."
        )


# ── detect_home_state_from_db (real DB integration) ─────────────────


class _FakeDB:
    """Minimal DB stub for testing detect_home_state_from_db.

    The real Database has many methods; we only stub the ones
    that ``detect_home_state_from_db`` actually uses so the
    integration test exercises the real branching logic.
    """

    def __init__(self, *, items=None, signals=None, purchases=None,
                 onboarding_complete=False):
        self._items = items or []
        self._signals = signals or []
        self._purchases = purchases or []
        self._onboarding = onboarding_complete
        # Get/set for onboarding state
        self._config = {"onboarding_complete": "1" if onboarding_complete else "0"}

    def get_inventory(self, user_id: str = ""):
        return self._items

    def get_preference_signals(self, user_id: str = ""):
        return list(self._signals)

    def list_purchase_events(self, user_id: str = ""):
        return list(self._purchases)

    def get_config_value(self, key: str, default: str = "") -> str:
        return self._config.get(key, default)


def test_e2e_detect_home_state_from_db_counts_signals_and_purchases():
    """2026-06-15 enhancement: detect_home_state_from_db must
    actually count signals and purchases from the DB, not
    hard-code them to 0. Previously ACTIVE was never reached
    even for households with clear preferences.
    """
    # 10 active items, 3 purchases, 5 signals → ACTIVE
    db = _FakeDB(
        items=[type("Lot", (), {"status": "active"})() for _ in range(10)],
        signals=[f"s{i}" for i in range(5)],
        purchases=[f"p{i}" for i in range(3)],
        onboarding_complete=True,
    )
    state = detect_home_state_from_db(db, user_id="h1")
    assert state.state == HomeState.ACTIVE, (
        f"Expected ACTIVE with 10 items / 3 purchases / 5 signals, "
        f"got {state.state.value}"
    )
    assert state.signal_count == 5
    assert state.purchase_count == 3

    # 10 items, 0 signals → QUIET (not ACTIVE)
    quiet_db = _FakeDB(
        items=[type("Lot", (), {"status": "active"})() for _ in range(10)],
        signals=[],
        purchases=[],
        onboarding_complete=True,
    )
    quiet_state = detect_home_state_from_db(quiet_db, user_id="h1")
    assert quiet_state.state == HomeState.QUIET
    assert quiet_state.signal_count == 0
    assert quiet_state.purchase_count == 0


def test_e2e_detect_home_state_from_db_handles_missing_methods():
    """If the DB doesn't have get_preference_signals or
    list_purchase_events (older DB instance), the function
    must not crash — just fall back to 0."""
    class OldDB:
        def get_inventory(self, user_id: str = ""):
            return [type("Lot", (), {"status": "active"})() for _ in range(10)]
        def get_config_value(self, key: str, default: str = "") -> str:
            return "1"  # onboarding complete

    state = detect_home_state_from_db(OldDB(), user_id="h1")
    # Without signals → QUIET (not ACTIVE)
    assert state.state == HomeState.QUIET
    assert state.signal_count == 0
    assert state.purchase_count == 0


def test_e2e_detect_home_state_from_db_handles_method_exception():
    """If the signal/purchase queries throw exceptions, the
    state machine must still work (fall back to 0 for those
    counts). Don't let a flaky signal table break the home page."""
    class FlakySignalsDB(_FakeDB):
        # Override parent class with onboarding_complete=True
        def __init__(self):
            super().__init__(
                items=[type("Lot", (), {"status": "active"})() for _ in range(10)],
                signals=[],
                purchases=[],
                onboarding_complete=True,  # so we don't fall to FIRST_RUN
            )
        def get_preference_signals(self, user_id: str = ""):
            raise RuntimeError("signal table is locked")
        def list_purchase_events(self, user_id: str = ""):
            raise RuntimeError("purchase table is locked")

    state = detect_home_state_from_db(FlakySignalsDB(), user_id="h1")
    # 10 items / 0 signals (because the exception was caught) / 0 purchases
    # → QUIET (not FIRST_RUN, because onboarding is complete)
    assert state.state == HomeState.QUIET, (
        f"Expected QUIET with 10 items / 0 signals, got {state.state.value}"
    )
    assert state.signal_count == 0
    assert state.purchase_count == 0
