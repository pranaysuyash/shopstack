"""Household-switch state machine for the workspace admin panel.

This module extracts the household-switch closures that were previously
inline in `app.py`'s `build_app()`. The functions are pure: they return
tuples of `gr.update()` objects without referencing any Gradio component
IDs directly. This makes them:
- Testable in isolation (mock the app_context functions, verify the
  right update tuples come back)
- Reusable (any tab or screen can trigger a household switch)
- Documented (the state transitions are visible at the call site)

The state model:
- `household_choices()` — read current household list for the dropdown
- `switch_household_state(household_id)` — set active household, return
  updates to refresh the dropdown and Today tab
- `show_add_form()` / `hide_add_form()` — toggle the add-household form
- `create_household_state(name)` — create a new household, switch to it,
  return updates to refresh the dropdown, hide the form, and refresh
  the Today tab

Why a state module and not a service:
- Services in `shopstack/services/` return domain results (e.g.,
  `ShoppingCompletionResult` with `success`, `items_added`, etc.).
- The household state returns *Gradio-specific* update objects, which
  is a UI concern.
- A state module under `shopstack/ui/state/` keeps the UI-Gradio
  coupling in one place.
"""
from __future__ import annotations

import random
import re

import gradio as gr

from shopstack.app_context import (
    add_household,
    list_households,
    switch_household,
)
from shopstack.ui.screens import today_dashboard


def _slugify_household_id(name: str) -> str:
    """Convert a human-readable name to a stable household ID.

    Examples:
        "My Home" -> "my_home"
        "Beach-House!" -> "beachhouse"
        "" -> ""

    If the slug is empty after sanitization (e.g. the name is all
    punctuation), fall back to a hash-based ID for stability.
    """
    slug = name.lower().replace(" ", "_")
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    if not slug:
        slug = f"household_{abs(hash(name)) % 10000}"
    return slug


def household_choices() -> list[tuple[str, str]]:
    """Return the current list of (display_name, household_id) tuples.

    Used to populate the household-switch dropdown in the workspace
    admin panel. Safe to call at module-load time (no side effects).
    """
    return [(h["name"], h["household_id"]) for h in list_households()]


def switch_household_state(household_id: str) -> tuple:
    """Switch the active household and return Gradio update tuples.

    Returns:
        A tuple of 7 `gr.update()` values:
            - household_dropdown: new value (or no-op if empty)
            - today_stats, today_soon, today_list, today_low,
              today_recent, today_changed: refreshed Today tab content

    If `household_id` is empty, the function is a no-op for the
    switch but still refreshes the dashboard.
    """
    if not household_id:
        return gr.update(), *today_dashboard()
    switch_household(household_id)
    return gr.update(value=household_id), *today_dashboard()


def show_add_form() -> dict:
    """Return a `gr.update()` that shows the add-household form."""
    return gr.update(visible=True)


def hide_add_form() -> dict:
    """Return a `gr.update()` that hides the add-household form."""
    return gr.update(visible=False)


def create_household_state(name: str) -> tuple:
    """Create a new household, switch to it, and return Gradio updates.

    Args:
        name: The human-readable household name from the add form.

    Returns:
        A tuple of 8 `gr.update()` values:
            - household_dropdown: refreshed choices + new value
            - hh_add_row: hidden (visible=False)
            - today_stats, today_soon, today_list, today_low,
              today_recent, today_changed: refreshed Today tab

    If `name` is empty/whitespace, returns a no-op tuple that keeps
    the form hidden and refreshes the dashboard.

    If the slugified household_id collides with an existing one, a
    random suffix is appended to disambiguate.
    """
    name = (name or "").strip()
    if not name:
        return gr.update(), gr.update(visible=False), *today_dashboard()

    household_id = _slugify_household_id(name)
    created = add_household(household_id, name)
    if not created:
        # Collision — append a random suffix and try again
        household_id = f"{household_id}_{random.randint(100, 999)}"
        add_household(household_id, name)

    switch_household(household_id)
    choices = household_choices()
    return (
        gr.update(choices=choices, value=household_id),
        gr.update(visible=False),
        *today_dashboard(),
    )
