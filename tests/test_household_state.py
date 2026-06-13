"""Tests for the household state machine.

Verifies:
- Pure functions return the right Gradio update tuples
- The state transitions (switch, create, show/hide form) are honored
- Edge cases (empty household_id, empty name, slug collisions) are handled

The state module is pure (no Gradio component references) so it can be
tested without rendering any Gradio UI.
"""
from __future__ import annotations

import os

import gradio as gr
import pytest

os.environ.setdefault("SHOPSTACK_DB_PATH", ":memory:")


@pytest.fixture
def app():
    """Import app fresh for each test, giving a clean :memory: DB."""
    import sys
    _preserved = {"shopstack.schemas", "shopstack.schemas.models"}
    for mod in list(sys.modules.keys()):
        if mod in ("app",) or (mod.startswith("shopstack") and mod not in _preserved):
            del sys.modules[mod]
    import app as _app
    return _app


class TestSlugifyHouseholdId:
    """Test the internal slugification helper."""

    def test_simple_name(self):
        from shopstack.ui.state.household import _slugify_household_id
        assert _slugify_household_id("My Home") == "my_home"

    def test_special_chars_removed(self):
        from shopstack.ui.state.household import _slugify_household_id
        assert _slugify_household_id("Beach-House!") == "beachhouse"

    def test_empty_after_sanitization_falls_back_to_hash(self):
        from shopstack.ui.state.household import _slugify_household_id
        slug = _slugify_household_id("!!!")
        # Should start with "household_" and have a numeric suffix
        assert slug.startswith("household_")
        # Suffix is a 4-digit number (mod 10000)
        suffix = slug.split("_")[1]
        assert suffix.isdigit()
        assert 0 <= int(suffix) < 10000

    def test_unicode_chars_removed(self):
        from shopstack.ui.state.household import _slugify_household_id
        # Non-ASCII letters are stripped (only a-z0-9_ allowed)
        assert _slugify_household_id("Hôtel") == "htel"


class TestHouseholdChoices:
    """Test the dropdown choices reader."""

    def test_returns_list_of_tuples(self, app):
        from shopstack.ui.state.household import household_choices
        choices = household_choices()
        assert isinstance(choices, list)
        assert all(isinstance(c, tuple) and len(c) == 2 for c in choices)
        # Each tuple is (display_name, household_id)
        for display_name, household_id in choices:
            assert isinstance(display_name, str)
            assert isinstance(household_id, str)


class TestSwitchHouseholdState:
    """Test the household switcher + dashboard refresher."""

    def test_empty_household_id_refreshes_without_switching(self, app):
        from shopstack.ui.state.household import switch_household_state
        # Pre-condition: no active household set explicitly
        result = switch_household_state("")
        # Returns 1 gr.update (dropdown) + 6 dashboard updates = 7 items
        assert len(result) == 7
        # First item is the dropdown update (gr.update returns a dict)
        assert result[0]["__type__"] == "update"

    def test_valid_household_id_switches_and_refreshes(self, app):
        from shopstack.ui.state.household import (
            household_choices,
            switch_household_state,
        )
        choices = household_choices()
        assert choices, "Need at least one household to test switch"
        target_id = choices[0][1]
        result = switch_household_state(target_id)
        assert len(result) == 7
        # First item should update the dropdown to the new value
        # (we don't introspect the .value field; just verify shape)

    def test_nonexistent_household_id_is_handled_gracefully(self, app):
        """A nonexistent ID should not crash; it may set active_household_id to that value."""
        from shopstack.ui.state.household import switch_household_state
        result = switch_household_state("nonexistent_household_xyz")
        # Should not raise; returns the expected tuple shape
        assert len(result) == 7


class TestShowHideAddForm:
    """Test the visibility toggles."""

    def test_show_add_form_returns_visible_true(self):
        from shopstack.ui.state.household import show_add_form
        result = show_add_form()
        # gr.update() is a dict-like; the .visible field should be True
        assert result["visible"] is True

    def test_hide_add_form_returns_visible_false(self):
        from shopstack.ui.state.household import hide_add_form
        result = hide_add_form()
        assert result["visible"] is False


class TestCreateHouseholdState:
    """Test the household creator + switcher."""

    def test_empty_name_is_noop(self, app):
        from shopstack.ui.state.household import create_household_state
        result = create_household_state("")
        # 1 dropdown update (no-op) + 1 form-hide update + 6 dashboard updates = 8 items
        assert len(result) == 8

    def test_whitespace_name_is_noop(self, app):
        from shopstack.ui.state.household import create_household_state
        result = create_household_state("   ")
        assert len(result) == 8

    def test_valid_name_creates_and_switches(self, app):
        from shopstack.ui.state.household import (
            create_household_state,
            household_choices,
        )
        before = len(household_choices())
        result = create_household_state("Test Household XYZ")
        after = len(household_choices())
        # New household was added
        assert after == before + 1
        # The new household is in the choices
        assert any(name == "Test Household XYZ" for name, _ in household_choices())
        # Returns the expected tuple shape
        assert len(result) == 8

    def test_duplicate_name_handles_collision(self, app):
        """Creating a household with the same name twice should not crash."""
        from shopstack.ui.state.household import (
            create_household_state,
            household_choices,
        )
        # First creation
        create_household_state("Collision Test")
        # Second creation with same name — should get a random suffix
        result = create_household_state("Collision Test")
        assert len(result) == 8
        # The choices list should have two entries with the same display name
        # but different household_ids
        matches = [hid for name, hid in household_choices() if name == "Collision Test"]
        assert len(matches) >= 2
        assert len(set(matches)) == len(matches), "household_ids must be unique"

    def test_name_with_special_chars_uses_slugified_id(self, app):
        from shopstack.ui.state.household import (
            create_household_state,
            household_choices,
        )
        create_household_state("Beach House!")
        # The slug should be "beach_house" (no special chars)
        assert any(hid == "beach_house" for _, hid in household_choices())
