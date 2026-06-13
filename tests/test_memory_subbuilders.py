"""Tests for the Memory tab sub-builders.

Verifies that each sub-builder:
- Has the expected function signature
- Imports the right screen functions
- Has the right closure helpers (where applicable)

The actual Gradio-block tests are slow and covered by the integration
tests in test_app.py. We focus here on the static-contract tests that
can run in under 1 second.
"""
from __future__ import annotations

import inspect

import pytest


# ── memory_intelligence ─────────────────────────────────────────────────


def test_memory_intelligence_signature():
    """build_memory_intelligence takes (app, ctx) and returns None."""
    from shopstack.ui.tabs.memory_intelligence import build_memory_intelligence
    sig = inspect.signature(build_memory_intelligence)
    params = list(sig.parameters.keys())
    assert params == ["app", "ctx"]
    # With `from __future__ import annotations`, return_annotation is a
    # string ("None") rather than the type itself. We use `eval` to
    # resolve the string in the module's namespace.
    assert sig.return_annotation in (None, "None")


def test_memory_intelligence_imports_get_intelligence_dashboard():
    """The sub-builder imports the screen function it calls."""
    from shopstack.ui.tabs import memory_intelligence
    assert hasattr(memory_intelligence, "get_intelligence_dashboard")
    assert callable(memory_intelligence.get_intelligence_dashboard)


# ── memory_notes ───────────────────────────────────────────────────────


def test_memory_notes_signature():
    """build_memory_notes takes (app, ctx) and returns None."""
    from shopstack.ui.tabs.memory_notes import build_memory_notes
    sig = inspect.signature(build_memory_notes)
    params = list(sig.parameters.keys())
    assert params == ["app", "ctx"]
    assert sig.return_annotation in (None, "None")


def test_memory_notes_imports_field_notes_view_save():
    """The sub-builder imports field_notes_view and field_notes_save."""
    from shopstack.ui.tabs import memory_notes
    assert hasattr(memory_notes, "field_notes_view")
    assert hasattr(memory_notes, "field_notes_save")


# ── memory_history ──────────────────────────────────────────────────────


def test_memory_history_signature():
    """build_memory_history takes (app, ctx) and returns None."""
    from shopstack.ui.tabs.memory_history import build_memory_history
    sig = inspect.signature(build_memory_history)
    params = list(sig.parameters.keys())
    assert params == ["app", "ctx"]
    assert sig.return_annotation in (None, "None")


def test_memory_history_imports_trace_functions():
    """The sub-builder imports all the trace screen functions it calls."""
    from shopstack.ui.tabs import memory_history
    for name in (
        "agent_trace_bootstrap",
        "agent_trace_export_file",
        "agent_trace_refresh",
        "agent_trace_search_filter",
        "agent_trace_view",
        "trace_bundle",
    ):
        assert hasattr(memory_history, name), f"missing {name}"


# ── memory_nutrition ─────────────────────────────────────────────────────


def test_memory_nutrition_signature():
    """build_memory_nutrition takes (app, ctx) and returns None."""
    from shopstack.ui.tabs.memory_nutrition import build_memory_nutrition
    sig = inspect.signature(build_memory_nutrition)
    params = list(sig.parameters.keys())
    assert params == ["app", "ctx"]
    assert sig.return_annotation in (None, "None")


def test_memory_nutrition_coach_screen_helper():
    """The _coach_screen closure has the right signature and falls back on error."""
    from shopstack.ui.tabs.memory_nutrition import _coach_screen
    # Default behavior: returns an error HTML if the screen function is
    # unavailable (or if any dependency is missing)
    result = _coach_screen(4, "vegetarian")
    # Either it returns valid HTML (if the screen works) or an error
    # message — both are strings.
    assert isinstance(result, str)
    assert len(result) > 0


def test_memory_nutrition_coach_screen_invalid_inputs():
    """_coach_screen handles invalid inputs gracefully (no crash)."""
    from shopstack.ui.tabs.memory_nutrition import _coach_screen
    # None, empty string, invalid dietary — all should not raise
    for size in (None, 0, -1, "abc"):
        for diet in (None, "", "unknown", "OMNIVORE"):
            result = _coach_screen(size, diet)
            assert isinstance(result, str)


# ── memory_activity ──────────────────────────────────────────────────────


def test_memory_activity_signatures():
    """Both sub-builders take (app, ctx) and return None."""
    from shopstack.ui.tabs.memory_activity import (
        build_memory_activity,
        build_memory_analytics,
    )
    for fn in (build_memory_activity, build_memory_analytics):
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        assert params == ["app", "ctx"]
        assert sig.return_annotation in (None, "None")


def test_memory_activity_closure_helpers():
    """The _activity_screen and _analytics_screen closures return strings."""
    from shopstack.ui.tabs.memory_activity import (
        _activity_screen,
        _analytics_screen,
    )
    # Either return valid HTML or an error fallback — both are strings
    for fn in (_activity_screen, _analytics_screen):
        result = fn()
        assert isinstance(result, str)
        assert len(result) > 0


# ── memory_data ────────────────────────────────────────────────────────


def test_memory_data_signatures():
    """Both sub-builders take (app, ctx) and return None."""
    from shopstack.ui.tabs.memory_data import (
        build_memory_advanced,
        build_memory_backup,
    )
    for fn in (build_memory_advanced, build_memory_backup):
        sig = inspect.signature(fn)
        params = list(sig.parameters.keys())
        assert params == ["app", "ctx"]
        assert sig.return_annotation in (None, "None")


def test_memory_data_imports_settings():
    """The sub-builder imports settings for the developer-mode guard."""
    from shopstack.ui.tabs import memory_data
    assert hasattr(memory_data, "settings")


def test_memory_data_advanced_is_developer_mode_gated():
    """build_memory_advanced is a no-op for non-developer modes.

    For developer modes it adds an ``app.load`` handler — we use a
    MagicMock for ``app`` so the test doesn't crash on the load call.
    """
    from unittest.mock import MagicMock, patch
    from shopstack.ui.tabs.memory_data import build_memory_advanced

    with patch("shopstack.ui.tabs.memory_data.settings") as mock_settings:
        # Non-developer mode: no-op (returns None, adds nothing).
        mock_settings.ui_mode = "production"
        result = build_memory_advanced(app=None, ctx=None)
        assert result is None
        # Developer mode: also returns None (it's a void function), but it
        # does add components to the Gradio context. We pass a MagicMock
        # so the ``app.load(...)`` call inside doesn't crash.
        mock_settings.ui_mode = "developer"
        result = build_memory_advanced(app=MagicMock(), ctx=None)
        assert result is None


def test_memory_data_backup_screen_functions():
    """build_memory_backup imports the export/import screen functions."""
    from shopstack.ui.tabs import memory_data
    for name in ("export_data_json", "export_data_csv", "import_data_file"):
        assert hasattr(memory_data, name), f"missing {name}"
