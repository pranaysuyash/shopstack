"""Regression tests for the cross-tab household event wiring.

The cross-tab event wiring (household dropdown, add-household form,
per-render location refresh, post-load JS shims) was extracted
from ``app.py`` into :mod:`shopstack.ui.state.household_wiring` so
``app.py`` stays a pure composition layer under the 300-line cap.

These tests pin the extraction:
1. The sub-builder module is importable and exports the documented
   public API.
2. ``app.py`` calls ``wire_household_handlers()`` (no inline event
   handlers for the household dropdown).
3. ``app.py`` does not retain the ``_household_switch_reload_js``
   helper (it was moved into the sub-builder).
4. The ``HouseholdWiringHandles`` dataclass exposes the 9 components
   ``app.py`` needs to reference.
"""
from __future__ import annotations

from dataclasses import is_dataclass


class TestWiringModuleExports:
    """The household-wiring sub-builder is the canonical home for the
    cross-tab event handlers."""

    def test_module_is_importable(self):
        from shopstack.ui.state import household_wiring
        assert hasattr(household_wiring, "wire_household_handlers")
        assert hasattr(household_wiring, "HouseholdWiringHandles")

    def test_handles_is_a_dataclass(self):
        from shopstack.ui.state.household_wiring import HouseholdWiringHandles
        assert is_dataclass(HouseholdWiringHandles)

    def test_handles_has_expected_components(self):
        # The dataclass exposes the components app.py would need
        # back-reference to (today's app.py doesn't use the return
        # value, but the contract is documented for future use).
        from shopstack.ui.state.household_wiring import HouseholdWiringHandles
        expected = {
            "today_stats", "today_soon", "today_list", "today_low",
            "today_recent", "today_changed", "home_flow",
            "p_location", "move_dest",
        }
        actual = set(HouseholdWiringHandles.__dataclass_fields__.keys())
        assert actual >= expected, (
            f"HouseholdWiringHandles missing fields: {expected - actual}"
        )


class TestAppCompositionUsesWiringSubBuilder:
    """The composition layer in app.py delegates to the sub-builder."""

    def test_app_calls_wire_household_handlers(self):
        from pathlib import Path
        app_source = Path("app.py").read_text()
        assert "wire_household_handlers" in app_source, (
            "app.py must call wire_household_handlers() to register "
            "the cross-tab event handlers."
        )

    def test_app_does_not_have_inline_household_dropdown_change(self):
        # The household-dropdown change handler was extracted to
        # the sub-builder. app.py should not have a local
        # ``household_dropdown.change(...)`` call — the handler
        # is now inside the sub-builder.
        from pathlib import Path
        app_source = Path("app.py").read_text()
        assert "household_dropdown.change(" not in app_source, (
            "app.py must not have an inline household_dropdown.change "
            "handler — the cross-tab wiring was extracted to "
            "shopstack/ui/state/household_wiring.py."
        )

    def test_app_does_not_have_inline_create_household_handler(self):
        from pathlib import Path
        app_source = Path("app.py").read_text()
        # The create_household click handler was extracted. The
        # only remaining call site for create_household_state is
        # inside the sub-builder, not in app.py itself.
        assert "create_household_state(" not in app_source, (
            "app.py must not have an inline create_household_state "
            "call — the cross-tab wiring was extracted to "
            "shopstack/ui/state/household_wiring.py."
        )

    def test_app_does_not_have_inline_refresh_location_choices(self):
        from pathlib import Path
        app_source = Path("app.py").read_text()
        assert "_refresh_location_choices" not in app_source, (
            "app.py must not have an inline _refresh_location_choices "
            "function — the cross-tab wiring was extracted."
        )

    def test_app_does_not_have_inline_household_switch_reload_js(self):
        from pathlib import Path
        app_source = Path("app.py").read_text()
        assert "_household_switch_reload_js" not in app_source, (
            "app.py must not have the _household_switch_reload_js "
            "helper — it was moved into the household_wiring sub-builder."
        )


class TestAppLineCount:
    """app.py must stay under the 300-line cap."""

    def test_app_under_300_lines(self):
        from pathlib import Path
        line_count = sum(1 for _ in Path("app.py").open())
        assert line_count <= 300, (
            f"app.py is {line_count} lines (> 300). The cross-tab "
            "wiring extraction should keep it at or under 300. See "
            "docs/audits/audit_03_gradio_app_architecture.md."
        )

    def test_wiring_module_is_substantial(self):
        # The sub-builder should be at least 50 lines — the inline
        # wiring we extracted was ~50 lines and we want to make
        # sure we didn't accidentally lose anything in the move.
        from pathlib import Path
        line_count = sum(
            1 for _ in Path("shopstack/ui/state/household_wiring.py").open()
        )
        assert line_count >= 50, (
            f"shopstack/ui/state/household_wiring.py is only "
            f"{line_count} lines — the sub-builder may have lost "
            f"functionality during the extraction."
        )
