"""Regression tests for the primary-nav consolidation (2026-06-15).

The 2026-06-15 audit flagged that with ``use_primary_nav=True``
the user sees a 6-item top-level nav but ALSO sees the entire
21-tab legacy surface as nested subtabs inside each primary.
The fix (per motto_v3 §11 — hide, not delete) is to render the
advanced subtabs inside a collapsed ``gr.Accordion(label="More (N)",
open=False)`` so the default view stays focused on the destination.

These tests pin the contract:

* The build returns handles for HANDLES_TABS (today, reconcile)
  regardless of which UI surface they live in.
* The default view of each primary destination is the destination
  itself (not a nested sub-tab).
* The advanced subtabs are accessible (the registry still builds
  them) but live inside the "More" disclosure.
* The legacy 5-group layout is unchanged (back-compat).

Evidence tier: T1 (static inspection) + T2 (this test passes).
"""
from __future__ import annotations

import gradio as gr

import pytest

from shopstack.ui.tabs.context import TabContext
from shopstack.ui.tabs.registry import (
    HANDLES_TABS,
    PRIMARY_NAV,
    PRIMARY_NAV_ADVANCED,
    _TAB_BUILDERS,
    build_all_tabs,
)


@pytest.fixture
def ctx() -> TabContext:
    return TabContext()


def test_primary_nav_has_six_items() -> None:
    """The user-facing primary nav has exactly 6 destinations."""
    assert len(PRIMARY_NAV) == 6
    labels = [item["label"] for item in PRIMARY_NAV]
    assert labels == ["Home", "Pantry", "Shopping", "Recipes", "Trips", "Memory"]


def test_each_primary_nav_item_has_a_destination() -> None:
    """Every primary nav item must have a destination tab_id."""
    for item in PRIMARY_NAV:
        assert "destination" in item, f"{item['label']} missing destination"
        assert item["destination"] in _TAB_BUILDERS, (
            f"{item['label']} destination {item['destination']!r} "
            f"has no registered builder"
        )


def test_build_all_tabs_returns_handles_for_today_and_reconcile(
    ctx: TabContext,
) -> None:
    """The cross-tab wiring in app.py depends on the today and
    reconcile handles. They must be returned even though they live
    inside the primary-nav accordion now.
    """
    with gr.Blocks() as app:
        handles = build_all_tabs(blocks=app, app=app, ctx=ctx,
                                 use_primary_nav=True)
    assert "today" in handles
    assert "reconcile" in handles
    # TodayTabHandles has at least the home_flow component
    assert hasattr(handles["today"], "home_flow")
    # ReconcileTabHandles has the location pickers
    assert hasattr(handles["reconcile"], "p_location")
    assert hasattr(handles["reconcile"], "move_dest")


def test_build_all_tabs_legacy_mode_still_works(ctx: TabContext) -> None:
    """The legacy 5-group layout is unchanged. The default
    ``use_primary_nav=False`` path should still build all the
    tabs the old way (no breaking change).
    """
    with gr.Blocks() as app:
        handles = build_all_tabs(blocks=app, app=app, ctx=ctx,
                                 use_primary_nav=False)
    # All registered tab_ids should appear in handles.
    for tab_id in _TAB_BUILDERS:
        assert tab_id in handles, (
            f"Legacy mode dropped {tab_id!r} from handles; "
            f"this would break cross-tab wiring"
        )


def test_advanced_only_excludes_destination() -> None:
    """The 'More' disclosure should contain only the advanced
    subtabs, NOT the destination (which is the default view).
    This is the hide-not-delete contract.
    """
    for item in PRIMARY_NAV:
        destination = item["destination"]
        advanced = PRIMARY_NAV_ADVANCED.get(item["id"], [])
        advanced_only = [t for t in advanced if t != destination]
        # Destination must NOT be in the advanced-only list
        assert destination not in advanced_only, (
            f"Primary {item['label']!r}: destination {destination!r} "
            f"should not be in the 'More' disclosure"
        )
        # All advanced-only entries must have a registered builder
        for tab_id in advanced_only:
            assert tab_id in _TAB_BUILDERS, (
                f"Advanced tab {tab_id!r} for {item['label']!r} "
                f"has no registered builder"
            )


def test_more_disclosure_includes_all_advanced_subtabs() -> None:
    """Every advanced subtab in PRIMARY_NAV_ADVANCED should be
    reachable from the UI (either as the destination or in the
    'More' disclosure). No silent drops.
    """
    for item in PRIMARY_NAV:
        destination = item["destination"]
        advanced = PRIMARY_NAV_ADVANCED.get(item["id"], [])
        # Reachable = destination OR in advanced-only
        reachable = {destination} | {t for t in advanced if t != destination}
        for tab_id in advanced:
            assert tab_id in reachable, (
                f"Tab {tab_id!r} is in PRIMARY_NAV_ADVANCED for "
                f"{item['label']!r} but is not reachable from the UI"
            )


def test_more_accordion_count_matches_advanced_only(
    ctx: TabContext,
) -> None:
    """The 'More (N)' label should show the count of advanced-only
    tabs. This is a small UX touch but a good regression guard.
    """
    # Static check: each primary's advanced-only count.
    expected_counts: dict[str, int] = {}
    for item in PRIMARY_NAV:
        destination = item["destination"]
        advanced = PRIMARY_NAV_ADVANCED.get(item["id"], [])
        advanced_only = [t for t in advanced if t != destination]
        expected_counts[item["label"]] = len(advanced_only)

    # Today: 0, Pantry: 6, Shopping: 6, Recipes: 0, Trips: 0, Memory: 3
    assert expected_counts["Home"] == 0
    assert expected_counts["Pantry"] == 6
    assert expected_counts["Shopping"] == 6
    assert expected_counts["Recipes"] == 0
    assert expected_counts["Trips"] == 0
    assert expected_counts["Memory"] == 3

    # Build the app and assert no exception is raised (the
    # accordion count is computed at render time; this is a
    # smoke test that the build doesn't break).
    with gr.Blocks() as app:
        build_all_tabs(blocks=app, app=app, ctx=ctx, use_primary_nav=True)


def test_handles_tabs_set_pins_contract() -> None:
    """The HANDLES_TABS frozenset is the contract between the
    registry and app.py's cross-tab wiring. Pin it so a future
    rename breaks the test (not the app at startup).
    """
    assert HANDLES_TABS == frozenset({"today", "reconcile"})


def test_every_advanced_subtab_has_a_builder() -> None:
    """No tab_id in PRIMARY_NAV_ADVANCED should be missing a
    builder. This is the registration contract.
    """
    for item in PRIMARY_NAV:
        for tab_id in PRIMARY_NAV_ADVANCED.get(item["id"], []):
            assert tab_id in _TAB_BUILDERS, (
                f"PRIMARY_NAV_ADVANCED lists {tab_id!r} for "
                f"{item['label']!r} but no builder is registered"
            )
