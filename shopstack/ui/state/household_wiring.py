"""Cross-tab household event wiring.

**Why this exists (motto_v3 §0.14 product reality):**

When the user switches households via the workspace admin panel, the
Today tab's 6 HTML outputs are refreshed (via
:func:`shopstack.ui.state.household.switch_household_state`).
But the other 20+ tabs (Basket, Memory, Timeline, Find, etc.) would
otherwise show stale data from the previous household until the user
manually refreshed each tab. That was a broken user workflow
(per the 2026-06-14 audit finding #7 — also re-pinned in the
2026-06-15 Home screen review).

This module extracts the cross-tab event wiring — the household
dropdown's ``change`` handler, the per-render refresh of
location-dependent dropdowns, the post-launch JS shims, and the
add-household form's ``click`` handlers — into a single sub-builder.
``app.py`` is now a pure composition layer: it builds the components
and delegates the wiring to this module, so the file stays under
the 300-line cap (per ``tests/test_app_composition.py::test_app_py_under_300_lines``).

**Supersession (motto_v3 §7):**

The wiring was previously inline in ``app.py`` (lines 220-278 of
the pre-Pass-14 version). It is *not* removed — it is moved here,
preserved verbatim, and the public surface (``wire_household_handlers``)
is the new canonical entry point. Old call sites that imported
``switch_household_state`` etc. directly continue to work.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import gradio as gr

from shopstack.app_context import current_user_id, db
from shopstack.ui.components.js_helpers import (
    autocomplete_injector_js,
    script_bootstrap_js,
    url_state_sync_js,
)
from shopstack.ui.state.household import (
    create_household_state,
    hide_add_form,
    household_choices,
    show_add_form,
    switch_household_state,
)

logger = logging.getLogger(__name__)


# JS that reloads the page after a household switch.
#
# Per audit 2026-06-14 finding #7: the household dropdown switch
# only refreshed the Today tab's 6 HTML outputs. The other 20+ tabs
# (Basket, Memory, Timeline, Find, etc.) continued showing stale
# data from the previous household until the user manually refreshed
# each tab — a broken user workflow per motto_v3 §0.14 (Product
# Reality and Operator Workflow Rule).
#
# The robust fix is a full page reload. This guarantees every tab
# re-fetches its data through the active household, the user sees
# a clean view of the new household, and no tab silently displays
# the wrong household's data.
#
# We use ``setTimeout(50)`` to give the Today tab refresh time to
# commit to the DOM before the reload tears it down, so the user
# doesn't see a flash of the old household on Today.
_HOUSEHOLD_SWITCH_RELOAD_JS: str = (
    "() => {"
    "setTimeout(function(){"
    # Preserve the URL hash so the user lands on the same tab.
    "var hash = window.location.hash || '';"
    "window.location.href = window.location.pathname + hash;"
    "}, 50);"
    "}"
)


@dataclass
class HouseholdWiringHandles:
    """Components and event-handler references exposed to ``app.py``.

    We expose the components (so app.py can read them back if it
    needs to) but the *event wiring itself* is done inside
    :func:`wire_household_handlers` — no further setup is required
    from app.py.
    """

    # Components refreshed on household change
    today_stats: gr.HTML
    today_soon: gr.HTML
    today_list: gr.HTML
    today_low: gr.HTML
    today_recent: gr.HTML
    today_changed: gr.HTML
    home_flow: gr.HTML
    # Location-dependent dropdowns refreshed on app load
    p_location: gr.components.Component
    move_dest: gr.components.Component


def wire_household_handlers(
    app: gr.Blocks,
    *,
    household_dropdown: gr.components.Component,
    add_hh_btn: gr.components.Component,
    hh_add_row: gr.components.Component,
    hh_name_input: gr.components.Component,
    hh_create_btn: gr.components.Component,
    hh_cancel_btn: gr.components.Component,
    today_handles: Any,
    reconcile_handles: Any,
) -> HouseholdWiringHandles:
    """Wire all cross-tab household event handlers.

    Registers:

    * ``app.load`` — refresh the household dropdown choices and the
      per-render location-dependent dropdowns.
    * ``household_dropdown.change`` — switch household and refresh
      the Today tab (8 outputs now, including the new
      ``home_flow`` handle). Then trigger a full page reload via JS
      so the other 20+ tabs see fresh data.
    * ``add_hh_btn.click`` — show the add-household form.
    * ``hh_cancel_btn.click`` — hide the add-household form.
    * ``hh_create_btn.click`` — create + switch + refresh.
    * Three ``app.load`` JS shims (autocomplete, URL state, script
      bootstrap re-exec).

    Args:
        app: The root :class:`gr.Blocks` instance.
        household_dropdown, add_hh_btn, hh_add_row, hh_name_input,
        hh_create_btn, hh_cancel_btn: Components from
        :func:`shopstack.ui.household_settings.build_household_settings`.
        today_handles: The :class:`TodayTabHandles` returned by
            ``build_today_tab``.
        reconcile_handles: The :class:`ReconcileTabHandles` returned
            by ``build_reconcile_tab``.

    Returns:
        A :class:`HouseholdWiringHandles` so ``app.py`` can read
        back the components if it needs to (today's code doesn't
        use the return value, but the dataclass preserves the
        contract for future refactors).
    """
    today_stats = today_handles.today_stats
    today_soon = today_handles.today_soon
    today_list = today_handles.today_list
    today_low = today_handles.today_low
    today_recent = today_handles.today_recent
    today_changed = today_handles.today_changed
    home_flow = today_handles.home_flow
    p_location = reconcile_handles.p_location
    move_dest = reconcile_handles.move_dest

    # Refresh dropdown choices on initial load.
    app.load(
        lambda: gr.update(choices=household_choices(), value=current_user_id()),
        outputs=household_dropdown,
    )

    # Wire household dropdown change after all output components are defined.
    # Also refresh the new home_flow panel so the state-aware hero
    # re-evaluates with the new household's data.
    household_dropdown.change(
        switch_household_state,
        household_dropdown,
        [
            household_dropdown, today_stats, today_soon, today_list,
            today_low, today_recent, today_changed, home_flow,
        ],
        api_name="switch_household",
        api_description="Switch active household and refresh dashboard",
    ).then(
        None,
        js=_HOUSEHOLD_SWITCH_RELOAD_JS,
        api_name="after_switch_household",
        api_description="Reload the page after household switch so all tabs show fresh data",
    )

    # Per-render refresh of location-dependent dropdowns.
    def _refresh_location_choices() -> gr.update:
        return gr.update(choices=[(l.name, l.location_id) for l in db.get_locations()])

    app.load(_refresh_location_choices, outputs=p_location)
    app.load(_refresh_location_choices, outputs=move_dest)

    # Post-render JS: inject `autocomplete="off"` into every Gradio
    # text/number input. Vercel WIG requires this on every form input.
    app.load(None, js=autocomplete_injector_js())
    # URL state sync: clicking a tab updates the URL hash, and
    # opening the app with `#basket` deep-links to the Shopping tab.
    app.load(None, js=url_state_sync_js())
    # Bootstrap re-execution: re-run inline <script data-ss-exec> tags
    # that Gradio's head=/gr.HTML injection left inert (item #99).
    app.load(None, js=script_bootstrap_js())

    # Wire add-household button and form.
    add_hh_btn.click(
        show_add_form,
        outputs=hh_add_row,
        api_name="show_add_household",
        api_description="Show the add-household form",
    )
    hh_cancel_btn.click(
        hide_add_form,
        outputs=hh_add_row,
        api_name="cancel_add_household",
        api_description="Hide the add-household form without creating",
    )
    hh_create_btn.click(
        create_household_state,
        hh_name_input,
        [
            household_dropdown, hh_add_row, today_stats, today_soon,
            today_list, today_low, today_recent, today_changed, home_flow,
        ],
        api_name="create_household",
        api_description="Create a new household, switch to it, and refresh the dashboard",
    )

    return HouseholdWiringHandles(
        today_stats=today_stats,
        today_soon=today_soon,
        today_list=today_list,
        today_low=today_low,
        today_recent=today_recent,
        today_changed=today_changed,
        home_flow=home_flow,
        p_location=p_location,
        move_dest=move_dest,
    )


__all__ = [
    "HouseholdWiringHandles",
    "wire_household_handlers",
]
