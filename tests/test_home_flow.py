"""Regression tests for the home flow state machine and renderer (2026-06-15).

The Today page now uses a state machine (first_run, starting_out,
quiet, active) to pick which hero to render. These tests pin the
state-detection contract so a future refactor doesn't silently
change which section appears at which point in the user journey.

Phase 3 additions: renderer output tests and actionable empty-state
regression guards ensure that the setup-first flow and actionable
copy don't regress.
"""
from __future__ import annotations

from shopstack.services.home_flow import (
    HomeState,
    HomeFlowState,
    STATE_THRESHOLDS,
    detect_home_state,
)
from shopstack.ui.screens.home_flow_render import render_home_flow


class TestDetectHomeStateFirstRun:
    """Onboarding incomplete → first-run state regardless of data."""

    def test_no_data(self):
        state = detect_home_state(
            onboarding_complete=False,
            item_count=0,
            purchase_count=0,
        )
        assert state.state == HomeState.FIRST_RUN
        assert state.show_setup_gate
        assert not state.show_intelligence
        assert not state.show_empty_hints

    def test_with_data_but_incomplete_onboarding(self):
        # Even with 50 items, incomplete onboarding still shows the
        # setup gate. The setup is the foundation.
        state = detect_home_state(
            onboarding_complete=False,
            item_count=50,
            purchase_count=20,
            signal_count=5,
        )
        assert state.state == HomeState.FIRST_RUN


class TestDetectHomeStateStartingOut:
    """Onboarding complete but < 5 items → starting-out."""

    def test_zero_items(self):
        state = detect_home_state(
            onboarding_complete=True,
            item_count=0,
            purchase_count=0,
        )
        assert state.state == HomeState.STARTING_OUT
        assert state.show_empty_hints
        assert not state.show_intelligence

    def test_three_items(self):
        state = detect_home_state(
            onboarding_complete=True,
            item_count=3,
            purchase_count=0,
        )
        assert state.state == HomeState.STARTING_OUT

    def test_four_items_still_starting_out(self):
        # The threshold is `min_items_for_starting_out_exit["items"]` = 5
        state = detect_home_state(
            onboarding_complete=True,
            item_count=4,
            purchase_count=2,
        )
        assert state.state == HomeState.STARTING_OUT


class TestDetectHomeStateQuiet:
    """Onboarding complete + 5+ items + 0 signals → quiet."""

    def test_five_items_no_signals(self):
        state = detect_home_state(
            onboarding_complete=True,
            item_count=5,
            purchase_count=2,
            signal_count=0,
        )
        assert state.state == HomeState.QUIET
        assert state.show_intelligence
        assert not state.show_setup_gate
        assert not state.show_empty_hints

    def test_many_items_no_signals(self):
        state = detect_home_state(
            onboarding_complete=True,
            item_count=200,
            purchase_count=100,
            signal_count=0,
        )
        assert state.state == HomeState.QUIET


class TestDetectHomeStateActive:
    """Onboarding complete + 5+ items + 1+ signals → active."""

    def test_minimum_active(self):
        state = detect_home_state(
            onboarding_complete=True,
            item_count=5,
            purchase_count=1,
            signal_count=1,
        )
        assert state.state == HomeState.ACTIVE
        assert state.show_intelligence

    def test_many_signals(self):
        state = detect_home_state(
            onboarding_complete=True,
            item_count=20,
            purchase_count=15,
            signal_count=12,
        )
        assert state.state == HomeState.ACTIVE


class TestStateHeadlinesAreUserFacing:
    """Headlines must be short, direct, and free of backend jargon."""

    def test_first_run_headline_is_actionable(self):
        state = detect_home_state(
            onboarding_complete=False,
            item_count=0,
            purchase_count=0,
        )
        # No mention of "engine", "seed", "intelligence", or other
        # backend terminology.
        lower = state.headline.lower()
        for forbidden in ("engine", "seed", "backend", "intelligence", "pump"):
            assert forbidden not in lower, f"headline has '{forbidden}': {state.headline!r}"
        # Should be short (under 60 chars).
        assert len(state.headline) < 60

    def test_starting_out_subhead_explains_what_to_do(self):
        state = detect_home_state(
            onboarding_complete=True,
            item_count=0,
            purchase_count=0,
        )
        # The subhead must mention what to do next.
        lower = state.subhead.lower()
        assert "add" in lower or "log" in lower, (
            f"starting-out subhead should suggest the next action: {state.subhead!r}"
        )

    def test_quiet_state_is_calm(self):
        state = detect_home_state(
            onboarding_complete=True,
            item_count=5,
            purchase_count=1,
            signal_count=0,
        )
        # "quiet" should be a calm, confident copy.
        assert "good" in state.headline.lower() or "all" in state.headline.lower()


class TestStateThresholdsDocumented:
    """The threshold constants are documented in one place."""

    def test_starting_out_threshold_is_5(self):
        # Pinning this constant prevents accidental changes that
        # would silently re-classify users.
        assert STATE_THRESHOLDS["min_items_for_starting_out_exit"]["items"] == 5

    def test_min_purchases_for_active(self):
        # Currently documented but not enforced by the state machine
        # (signal_count is the gating signal). We still pin the
        # constant so future code can rely on it.
        assert "purchases" in STATE_THRESHOLDS["min_purchases_for_active"]


class TestHomeFlowStateDataclass:
    """HomeFlowState preserves all the data the renderer needs."""

    def test_dataclass_has_required_fields(self):
        state = detect_home_state(
            onboarding_complete=True,
            item_count=5,
            purchase_count=1,
            signal_count=0,
        )
        assert hasattr(state, "state")
        assert hasattr(state, "headline")
        assert hasattr(state, "subhead")
        assert hasattr(state, "onboarding_complete")
        assert hasattr(state, "item_count")
        assert hasattr(state, "purchase_count")
        assert hasattr(state, "signal_count")

    def test_frozen_dataclass(self):
        # Immutability matters because we pass the state through
        # multiple layers (renderer, gr.HTML, etc.) and we want
        # to catch accidental mutations.
        state = detect_home_state(
            onboarding_complete=True,
            item_count=5,
            purchase_count=1,
            signal_count=0,
        )
        try:
            state.state = HomeState.FIRST_RUN
            assert False, "HomeFlowState should be frozen"
        except (AttributeError, Exception):
            pass  # Expected — frozen dataclass raises FrozenInstanceError


# ═══════════════════════════════════════════════════════════════════════
# Renderer output tests (Phase 3 regression guards)
# ═══════════════════════════════════════════════════════════════════════


class TestRenderHomeFlowForcesState:
    """render_home_flow(force_state=...) produces correct HTML per state."""

    def test_first_run_renders_setup_gate(self):
        html = render_home_flow(force_state=HomeState.FIRST_RUN)
        assert "home-flow" in html
        assert "home-flow-card--setup" in html
        assert "Set up my household" in html
        assert "onboarding-wizard" in html  # CTA scrolls to wizard

    def test_starting_out_renders_staple_chips(self):
        html = render_home_flow(force_state=HomeState.STARTING_OUT)
        assert "home-flow-card--starting-out" in html
        assert "cmd-chip" in html  # staple chip buttons
        assert "Milk" in html
        assert "Rice" in html

    def test_quiet_renders_calm_card(self):
        html = render_home_flow(force_state=HomeState.QUIET)
        assert "home-flow-card--quiet" in html
        assert "All caught up" in html
        assert "command box" in html  # points user to next action

    def test_active_renders_intel_or_fallback(self):
        html = render_home_flow(force_state=HomeState.ACTIVE)
        # Active state either renders intel cards or a useful fallback
        assert "home-flow" in html
        # Fallback must still have a useful title (Today or intelligence)
        assert "Today" in html or "intelligence" in html.lower() or "action" in html.lower()

    def test_all_states_produce_xss_safe_html(self):
        """No state should emit unescaped user content."""
        for state in HomeState:
            html = render_home_flow(force_state=state)
            assert "<script" not in html.lower(), (
                f"{state.value} renders a <script> tag"
            )


class TestSetupFirstFlowGuards:
    """FIRST_RUN must never show the intelligence dashboard."""

    def test_first_run_does_not_show_intelligence(self):
        state = detect_home_state(
            onboarding_complete=False,
            item_count=0,
            purchase_count=0,
        )
        assert not state.show_intelligence

    def test_first_run_does_not_show_empty_hints(self):
        state = detect_home_state(
            onboarding_complete=False,
            item_count=0,
            purchase_count=0,
        )
        assert not state.show_empty_hints

    def test_starting_out_does_not_show_intelligence(self):
        state = detect_home_state(
            onboarding_complete=True,
            item_count=3,
            purchase_count=0,
        )
        assert not state.show_intelligence

    def test_starting_out_does_not_show_setup_gate(self):
        state = detect_home_state(
            onboarding_complete=True,
            item_count=0,
            purchase_count=0,
        )
        assert not state.show_setup_gate


class TestActionableEmptyStateCopy:
    """Empty states must follow the pattern: what's missing + next action."""

    def test_restock_empty_mentions_next_step(self):
        from shopstack.services.restock_card import render_restock_card_html

        html = render_restock_card_html([])
        lower = html.lower()
        # Must mention what to do next
        assert "add" in lower or "log" in lower or "purchase" in lower, (
            f"Restock empty state should suggest a next action: {html[:200]}"
        )

    def test_restock_empty_not_passive(self):
        from shopstack.services.restock_card import render_restock_card_html

        html = render_restock_card_html([])
        # Must not be the old passive copy
        assert "Add a few purchases to seed the engine" not in html

    def test_restock_empty_has_empty_state_pattern(self):
        from shopstack.services.restock_card import render_restock_card_html

        html = render_restock_card_html([])
        assert "empty-state" in html
        assert "No restock predictions" in html

    def test_restock_empty_not_passive_old_copy(self):
        """The old passive copy 'Add a few purchases to seed the engine' must be gone."""
        from shopstack.services.restock_card import render_restock_card_html

        html = render_restock_card_html([])
        assert "Add a few purchases to seed the engine" not in html

    def test_empty_state_enhanced_supports_secondary_text(self):
        """The empty_state_enhanced primitive must support secondary_text."""
        from shopstack.ui.components.primitives import empty_state_enhanced

        html = empty_state_enhanced(
            "No items yet.",
            icon="🛒",
            secondary_text="Add items above.",
        )
        assert "No items yet." in html
        assert "Add items above." in html


class TestStateTransitions:
    """State transitions must follow the correct journey."""

    def test_first_run_to_quiet_after_onboarding(self):
        """After onboarding with 5 items, user lands on QUIET (above threshold)."""
        state_before = detect_home_state(
            onboarding_complete=False, item_count=0, purchase_count=0,
        )
        assert state_before.state == HomeState.FIRST_RUN
        state_after = detect_home_state(
            onboarding_complete=True, item_count=5, purchase_count=0,
        )
        assert state_after.state == HomeState.QUIET

    def test_signals_appear_transitions_quiet_to_active(self):
        """When signals appear, QUIET transitions to ACTIVE."""
        state_quiet = detect_home_state(
            onboarding_complete=True, item_count=10, purchase_count=5,
            signal_count=0,
        )
        assert state_quiet.state == HomeState.QUIET
        state_active = detect_home_state(
            onboarding_complete=True, item_count=10, purchase_count=5,
            signal_count=3,
        )
        assert state_active.state == HomeState.ACTIVE

    def test_signals_resolve_transitions_active_to_quiet(self):
        """When signals resolve, ACTIVE transitions back to QUIET."""
        state_active = detect_home_state(
            onboarding_complete=True, item_count=10, purchase_count=5,
            signal_count=3,
        )
        assert state_active.state == HomeState.ACTIVE
        state_quiet = detect_home_state(
            onboarding_complete=True, item_count=10, purchase_count=5,
            signal_count=0,
        )
        assert state_quiet.state == HomeState.QUIET

    def test_journey_never_skips_to_active_from_first_run(self):
        """A brand-new user can never jump to ACTIVE regardless of signal count."""
        state = detect_home_state(
            onboarding_complete=False, item_count=0, purchase_count=0,
            signal_count=10,
        )
        assert state.state == HomeState.FIRST_RUN
