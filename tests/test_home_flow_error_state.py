"""Regression tests for the home-flow state machine (2026-06-15).

Background
==========

``shopstack.services.home_flow`` defines a 4-state machine that
the Today tab uses to render the right hero for a given household:

  FIRST_RUN    → "Set up ShopStack in 2 minutes"
  STARTING_OUT → "Add a few staples to unlock intelligence"
  QUIET        → "Your kitchen is in good shape"
  ACTIVE       → "N actions worth your attention"

Bug fixed on 2026-06-15
=======================

Prior to this fix, ``detect_home_state_from_db`` silently caught
**every** exception and returned ``FIRST_RUN`` with zero counts.
This caused a returning user with 200 items to see
"Set up ShopStack in 2 minutes" when the data layer was failing
(DB lock, schema migration, transient connection drop, etc.).
The exception was logged at ``debug`` level, so no operator ever
saw it.

The fix adds a fifth state, ``HomeState.ERROR``, that:

1. Renders a "Something went wrong" panel + retry, NOT the
   misleading setup-first copy.
2. Logs the exception at ``error`` level with ``exc_info`` so
   operators can see the traceback.
3. Distinguishes "no DB" (legitimate, no household yet) from
   "DB exception" (a real failure that needs attention).

This test guards the bug from re-appearing — specifically:

* The ``ERROR`` state must exist and be reachable.
* The fallback must not silently return ``FIRST_RUN`` on a DB
  exception.
* The exception must be logged at ``error`` level (not ``debug``).
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from shopstack.services.home_flow import (
    HomeState,
    detect_home_state,
    detect_home_state_from_db,
)


# ── Pure-state machine (no DB) ──────────────────────────────────────


def test_first_run_when_onboarding_incomplete():
    assert detect_home_state(
        onboarding_complete=False, item_count=0, purchase_count=0, signal_count=0,
    ).state == HomeState.FIRST_RUN


def test_starting_out_when_few_items():
    assert detect_home_state(
        onboarding_complete=True, item_count=3, purchase_count=0, signal_count=0,
    ).state == HomeState.STARTING_OUT


def test_quiet_when_items_but_no_signals():
    assert detect_home_state(
        onboarding_complete=True, item_count=10, purchase_count=5, signal_count=0,
    ).state == HomeState.QUIET


def test_active_when_items_and_signals():
    assert detect_home_state(
        onboarding_complete=True, item_count=10, purchase_count=5, signal_count=3,
    ).state == HomeState.ACTIVE


# ── The bug: silent fallback used to mask DB failures ───────────────


def test_no_db_returns_first_run_legitimately():
    """db=None means "no household yet" — that's a real FIRST_RUN.

    Not the bug: this is the legitimate path for callers without
    a DB connection. The error-state must NOT fire here.
    """
    state = detect_home_state_from_db(db=None, user_id="")
    assert state.state == HomeState.FIRST_RUN


def test_db_exception_returns_error_state_not_first_run():
    """DB exception returns HomeState.ERROR, NOT FIRST_RUN.

    2026-06-15 regression guard: the prior implementation
    returned FIRST_RUN on any exception, which was misleading
    for a returning user. A real DB failure must surface as
    ERROR so the renderer shows a useful "Something went wrong"
    panel + retry, not setup-first copy.
    """
    db = MagicMock()
    db.get_inventory.side_effect = RuntimeError("database is locked")
    db.get_active_shopping_list.return_value = None

    state = detect_home_state_from_db(db=db, user_id="u1")
    assert state.state == HomeState.ERROR, (
        f"DB exception must return HomeState.ERROR (so the renderer "
        f"shows a 'something went wrong' panel + retry), not "
        f"HomeState.FIRST_RUN. Got: {state.state!r}. The pre-2026-06-15 "
        f"bug returned FIRST_RUN for a returning user with 200 items "
        f"when the DB was failing, which was misleading."
    )
    assert state.show_error_panel
    assert not state.show_setup_gate
    assert not state.show_empty_hints
    assert not state.show_intelligence


def test_db_exception_logs_at_error_level_not_debug(caplog):
    """The exception must be logged at error level (operator-visible).

    Pre-2026-06-15: logger.debug, which meant no one saw the
    failure in production. Post-fix: logger.error with exc_info
    so the traceback is captured.
    """
    db = MagicMock()
    db.get_inventory.side_effect = RuntimeError("database is locked")

    with caplog.at_level(logging.ERROR, logger="shopstack.services.home_flow"):
        detect_home_state_from_db(db=db, user_id="u1")

    error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert error_records, (
        "DB exception was not logged at ERROR level. Operators need to see "
        "production failures; pre-2026-06-15 the failure was at DEBUG level "
        "and therefore invisible."
    )
    # The log record should mention the failure cause
    assert any("database is locked" in r.getMessage() for r in error_records), (
        "Log record must include the original exception message. "
        "Without it, operators see 'something failed' but not what failed."
    )


def test_onboarding_check_failure_also_returns_error():
    """If the onboarding check itself raises, return ERROR.

    Belt-and-suspenders: the prior implementation also caught
    the onboarding check, which silently returned
    ``onboarding_complete=False`` (FIRST_RUN) for a returning
    user whose onboarding check was broken. Same bug, different
    code path.
    """
    db = MagicMock()
    db.get_inventory.return_value = []
    # Simulate onboarding check failing.
    with pytest.MonkeyPatch.context() as mp:
        from shopstack.services import onboarding as onboarding_mod
        mp.setattr(
            onboarding_mod, "is_onboarding_complete",
            MagicMock(side_effect=RuntimeError("onboarding service down")),
        )
        state = detect_home_state_from_db(db=db, user_id="u1")
    assert state.state == HomeState.ERROR


# ── Renderer hints ──────────────────────────────────────────────────


def test_error_state_properties():
    """ERROR state exposes show_error_panel=True, all other hints False."""
    state = detect_home_state(
        onboarding_complete=True,  # even with a real household
        item_count=200,             # and lots of data
        purchase_count=10,
        signal_count=0,
    )
    # Sanity: this is a real QUIET/ACTIVE state, not ERROR.
    assert state.state in (HomeState.ACTIVE, HomeState.QUIET)
    assert not state.show_error_panel

    error = HomeState.ERROR
    # Manually construct an ERROR state for the property checks:
    from shopstack.services.home_flow import HomeFlowState
    err = HomeFlowState(
        state=HomeState.ERROR,
        headline="x",
        subhead="y",
        onboarding_complete=False,
        item_count=0,
        purchase_count=0,
        signal_count=0,
    )
    assert err.show_error_panel
    assert not err.show_setup_gate
    assert not err.show_empty_hints
    assert not err.show_intelligence


def test_error_state_distinct_from_first_run_in_db_present_case():
    """When a DB IS present, a returning user with items must NOT
    see FIRST_RUN even if the lookup throws. The error state is
    the only safe fallback in this case.
    """
    db = MagicMock()
    db.get_inventory.side_effect = RuntimeError("transient connection drop")

    state = detect_home_state_from_db(db=db, user_id="returning-user-with-200-items")
    assert state.state != HomeState.FIRST_RUN, (
        "Returning user with 200 items must NEVER see FIRST_RUN when the "
        "DB is failing — the error state is the only safe fallback. "
        "Pre-2026-06-15 this was the bug."
    )
    assert state.state == HomeState.ERROR
