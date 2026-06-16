"""Regression tests for the Today → "Recent changes" undo bar (2026-06-15).

The 2026-06-15 audit flagged that the ``undo_ledger`` service was
fully built but had no user-facing surface — the user could not
recover from an accidental mutation. The fix is additive per
motto_v3 §11:

* New visible components on the Today tab: an ``undo_bar`` HTML
  panel and an "Undo last change" button.
* New handler: ``_undo_then_refresh`` that calls ``undo_last``
  and refreshes both the bar and the home flow.
* Hidden when the ledger is empty (the renderer returns "" so
  the default view stays clean).
* Backed by the existing ``shopstack.services.undo_ledger``
  infrastructure (no DB changes, no new tables).

These tests pin the contract:

* The bar is hidden when there are no recent entries.
* The bar shows up to ``_MAX_UNDO_ENTRIES_SHOWN`` entries.
* Each entry row is XSS-safe (uses ``html.escape``).
* The Undo button handler returns the (bar, home_flow) pair.
* The undo call goes through the existing ledger, not a duplicate.
* ``TodayTabHandles`` exposes the new ``undo_bar`` field.

Evidence tier: T1 (static inspection) + T2 (this test passes).
"""
from __future__ import annotations

import pytest

from shopstack.services.undo_ledger import UndoEntry, get_ledger
from shopstack.ui.tabs.today import (
    _MAX_UNDO_ENTRIES_SHOWN,
    _format_undo_entry_html,
    _render_undo_bar_html,
    _undo_then_refresh,
    build_today_tab,
)


@pytest.fixture(autouse=True)
def _reset_ledger():
    """Each test starts with a clean ledger so the assertions are
    independent. ``reset_ledger`` is the canonical way to do this
    (it lives next to ``get_ledger``).
    """
    from shopstack.services.undo_ledger import reset_ledger
    reset_ledger()
    yield
    reset_ledger()


# ── Render functions ───────────────────────────────────────────────


def test_render_undo_bar_empty_when_no_recent_entries() -> None:
    """The bar is hidden when the ledger is empty. The
    renderer returns an empty string so the default view
    stays clean (per motto_v3 §11 — hide, not delete).
    """
    html = _render_undo_bar_html("h-empty")
    assert html == "", (
        f"Empty ledger should render empty string; got: {html!r}"
    )


def test_render_undo_bar_shows_recent_entries() -> None:
    """After registering a mutation, the bar shows it."""
    ledger = get_ledger()
    ledger.register(
        kind="consume_inventory",
        before={"qty": 12},
        after={"qty": 10},
        description="Consumed 2 of milk",
        household_id="h-test",
    )
    html = _render_undo_bar_html("h-test")
    assert "Recent changes" in html
    assert "Consumed 2 of milk" in html
    assert "consume_inventory" in html


def test_render_undo_bar_caps_at_max_entries() -> None:
    """The bar shows at most ``_MAX_UNDO_ENTRIES_SHOWN`` entries.

    This is the compactness contract — the bar should never
    dominate the home view.
    """
    ledger = get_ledger()
    for i in range(10):
        ledger.register(
            kind="consume_inventory",
            before={"qty": i},
            after={"qty": i - 1},
            description=f"Consumed item {i}",
            household_id="h-cap",
        )
    html = _render_undo_bar_html("h-cap")
    # Count occurrences of the undo-row class. The bar
    # structure has 1 row per entry.
    assert html.count("undo-row") == _MAX_UNDO_ENTRIES_SHOWN, (
        f"Expected {_MAX_UNDO_ENTRIES_SHOWN} rows, got "
        f"{html.count('undo-row')}"
    )


def test_format_undo_entry_html_escapes_special_chars() -> None:
    """XSS safety: special chars in description / kind are escaped."""
    entry = UndoEntry(
        entry_id="e-1",
        household_id="h-xss",
        kind="<script>alert(1)</script>",
        before={"qty": 0},
        description="Tom & Jerry's <milk>",
    )
    html = _format_undo_entry_html(entry)
    assert "<script>alert(1)</script>" not in html
    assert "Tom &amp; Jerry" in html or "Tom &amp;Jerry" in html
    assert "&lt;milk&gt;" in html
    # The kind field is also escaped
    assert "&lt;script&gt;" in html


# ── Click handlers ────────────────────────────────────────────────


def test_undo_then_refresh_returns_bar_and_home_flow() -> None:
    """The undo handler returns a 2-tuple: (bar_html, home_flow_html).

    Both are strings. The first may be empty (after the undo
    empties the ledger); the second is the re-rendered home
    flow panel.
    """
    ledger = get_ledger()
    ledger.register(
        kind="consume_inventory",
        before={"qty": 5},
        after={"qty": 4},
        description="Consumed 1 of bread",
        household_id="h-click",
    )
    bar, home = _undo_then_refresh()
    assert isinstance(bar, str)
    assert isinstance(home, str)
    # After undo, the ledger is empty → bar is ""
    assert bar == ""


def test_undo_then_refresh_handles_empty_ledger_gracefully() -> None:
    """If the user clicks Undo when there's nothing to undo, the
    handler should NOT raise. It returns the (empty bar, home
    flow) pair.
    """
    bar, home = _undo_then_refresh()  # ledger is empty
    assert bar == ""
    assert isinstance(home, str)


# ── Tab integration ────────────────────────────────────────────────


def test_build_today_tab_exposes_undo_bar_handle() -> None:
    """The new ``undo_bar`` field is part of TodayTabHandles.

    This is the contract for any future cross-tab wiring
    (e.g., app.py household-switch could refresh the bar too).
    """
    import dataclasses

    from shopstack.ui.tabs.today import TodayTabHandles

    field_names = {f.name for f in dataclasses.fields(TodayTabHandles)}
    assert "undo_bar" in field_names, (
        f"TodayTabHandles missing undo_bar field; "
        f"fields: {field_names}"
    )


def test_build_today_tab_returns_handles_with_undo_bar() -> None:
    """Building the today tab produces a handles object with a
    non-None ``undo_bar`` (it's a ``gr.HTML`` component).
    """
    import gradio as gr

    from shopstack.ui.tabs.context import TabContext
    from shopstack.ui.tabs.today import TodayTabHandles

    with gr.Blocks() as app:
        handles = build_today_tab(
            blocks=app, app=app, ctx=TabContext(),
        )
    assert isinstance(handles, TodayTabHandles)
    # The undo_bar component is registered with Gradio; we just
    # check it's not None.
    assert handles.undo_bar is not None
    # And the existing handles are still present (back-compat).
    assert handles.home_flow is not None
    assert handles.today_stats is not None
