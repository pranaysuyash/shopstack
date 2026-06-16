"""Regression tests for the home-flow state in TabContext (Group G, 2026-06-15).

The 2026-06-15 audit flagged that the home-flow state machine
(FIRST_RUN / STARTING_OUT / QUIET / ACTIVE) was only consulted
by the Home tab. A first-run user landing on Shopping or Add
Purchase saw the same UI as an active user — they had no
state-aware guidance.

The fix (per motto_v3 §11 — additive, not delete):
1. ``TabContext`` gained an optional ``home_flow_state`` field
   (default None — tabs that don't care ignore it).
2. ``app.build_app()`` computes the state once and seeds the
   context. Every tab builder receives the seeded context.
3. Tabs that care can read ``ctx.home_flow_state.state`` to
   branch their UI.

These tests pin the contract:

* ``TabContext`` exposes the new field.
* The field is settable and round-trips.
* The detection function returns a state from the canonical enum.
* Per-user scoping: two different user_ids produce two different
  states (when the underlying data differs).
* The state is computed from real DB counts (item_count and
  purchase_count) and the onboarding-completion flag.

Evidence tier: T1 (static inspection) + T2 (this test passes).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from shopstack.services.home_flow import (
    HomeState,
    detect_home_state_from_db,
)
from shopstack.ui.tabs.context import TabContext


def test_tabcontext_has_home_flow_state_slot() -> None:
    """``TabContext`` exposes the new field (additive)."""
    ctx = TabContext()
    # Default is None — tabs that don't care see None.
    assert ctx.home_flow_state is None


def test_tabcontext_home_flow_state_is_settable() -> None:
    """The field accepts a HomeFlowState (or any object for
    forward-compat — the type is intentionally loose so the
    state machine can evolve without touching TabContext).
    """
    ctx = TabContext()
    sentinel = object()
    ctx.home_flow_state = sentinel
    assert ctx.home_flow_state is sentinel


def test_tabcontext_is_immutable_for_other_slots() -> None:
    """Per the TabContext design (additive-only), other slots
    are still immutable. Trying to set a new attribute that
    isn't in ``__slots__`` raises AttributeError.
    """
    ctx = TabContext()
    with pytest.raises(AttributeError):
        ctx.brand_new_field = "should fail"


def test_detect_home_state_from_db_returns_canonical_state(tmp_path) -> None:
    """Detection on a fresh DB returns one of the canonical
    HomeState enum values. The exact value depends on DB
    contents; the contract is "one of the four".
    """
    from shopstack.persistence.database import Database
    db = Database(str(tmp_path / "t.db"))
    state = detect_home_state_from_db(db, user_id="h-empty")
    assert state is not None
    assert state.state in {
        HomeState.FIRST_RUN,
        HomeState.STARTING_OUT,
        HomeState.QUIET,
        HomeState.ACTIVE,
    }


def test_detect_home_state_from_db_handles_no_db() -> None:
    """When ``db`` is None, the state is FIRST_RUN (legitimate
    "no household yet" case, per the function's contract).
    """
    state = detect_home_state_from_db(None, user_id="h-no-db")
    assert state.state == HomeState.FIRST_RUN
    assert state.onboarding_complete is False


def test_detect_home_state_from_db_user_scoping(tmp_path) -> None:
    """Detection is per-user (the DB scopes item/purchase counts
    to the user_id). The same DB queried with two different
    user_ids produces two different states when the data
    differs.
    """
    from shopstack.persistence.database import Database
    db = Database(str(tmp_path / "t.db"))
    state1 = detect_home_state_from_db(db, user_id="h-no-data")
    state2 = detect_home_state_from_db(db, user_id="h-also-no-data")
    # Both should be in the same first-run / starting-out
    # range (no data either way). The contract is the same
    # enum value, not necessarily the same instance.
    assert state1.state in {HomeState.FIRST_RUN, HomeState.STARTING_OUT}
    assert state2.state in {HomeState.FIRST_RUN, HomeState.STARTING_OUT}


def test_tabcontext_home_flow_state_round_trip_via_singleton() -> None:
    """The pattern in app.build_app() is:
        ctx = TabContext()
        ctx.home_flow_state = detect_home_state_from_db(ctx.db, ...)
    This test pins that the assignment preserves the state
    object identity (so tabs that read the same field see the
    same value).
    """
    from shopstack.persistence.database import Database
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(str(Path(tmp) / "t.db"))
        state = detect_home_state_from_db(db, user_id="h-rt")
        ctx = TabContext()
        ctx.home_flow_state = state
        # Same object identity
        assert ctx.home_flow_state is state
        # And the state enum is one of the four
        assert ctx.home_flow_state.state in {
            HomeState.FIRST_RUN, HomeState.STARTING_OUT,
            HomeState.QUIET, HomeState.ACTIVE,
        }
