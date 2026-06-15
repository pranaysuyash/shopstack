from __future__ import annotations

from shopstack.services.dashboard import DashboardState, build_dashboard_state


def test_build_dashboard_state_empty(db, tool_registry):
    state = build_dashboard_state(db, tool_registry)

    assert isinstance(state, DashboardState)
    assert state.active_inventory == []
    assert state.low_items == []
    assert state.recent_purchases == []
    assert state.use_soon_count == 0


def test_build_dashboard_state_counts_inventory(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="milk",
        display_name="Milk",
        quantity=0.25,
        unit="L",
    )
    tool_registry.add_inventory_item(
        canonical_name="rice",
        display_name="Rice",
        quantity=5,
        unit="kg",
    )

    state = build_dashboard_state(db, tool_registry)

    assert len(state.active_inventory) == 2
    assert len(state.low_items) == 1
    assert state.low_items[0].canonical_name == "milk"
    assert len(state.decision_set.buy) >= 1


def test_build_dashboard_state_includes_active_list(db, tool_registry):
    tool_registry.create_or_update_shopping_list(
        items=[{"canonical_name": "tomato", "requested_quantity": 1, "unit": "kg"}],
        goal="Vegetables",
    )

    state = build_dashboard_state(db, tool_registry)

    assert state.active_list is not None
    assert state.active_list.goal == "Vegetables"
    assert any(d.canonical_name == "tomato" for d in state.decision_set.decisions)


def test_dashboard_state_use_soon_count_property():
    state = DashboardState(
        decision_set=None,
        market_snapshot=None,
        use_soon={"count": 3, "items": [{"name": "milk"}, {"name": "bread"}]},
        active_list=None,
    )
    assert state.use_soon_count == 3


def test_dashboard_state_use_soon_items_property():
    items = [{"name": "milk"}, {"name": "bread"}]
    state = DashboardState(
        decision_set=None,
        market_snapshot=None,
        use_soon={"count": 2, "items": items},
        active_list=None,
    )
    assert state.use_soon_items == items


def test_dashboard_state_use_soon_empty():
    state = DashboardState(
        decision_set=None,
        market_snapshot=None,
        use_soon={},
        active_list=None,
    )
    assert state.use_soon_count == 0
    assert state.use_soon_items == []


def test_build_dashboard_state_includes_cadence_data(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="milk",
        display_name="Milk",
        quantity=1.0,
        unit="L",
        source_event_id="test",
    )
    state = build_dashboard_state(db, tool_registry)
    assert isinstance(state.cadence_data, dict)


def test_build_dashboard_state_includes_waste_data(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="milk",
        display_name="Milk",
        quantity=1.0,
        unit="L",
    )
    state = build_dashboard_state(db, tool_registry)
    assert isinstance(state.waste_data, list)


def test_build_dashboard_state_recent_purchases(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="rice",
        display_name="Rice",
        quantity=5.0,
        unit="kg",
    )
    state = build_dashboard_state(db, tool_registry)
    assert isinstance(state.recent_purchases, list)


def test_build_dashboard_state_low_items_filter(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="onion",
        display_name="Onion",
        quantity=0.1,
        unit="kg",
    )
    tool_registry.add_inventory_item(
        canonical_name="potato",
        display_name="Potato",
        quantity=2.0,
        unit="kg",
    )
    state = build_dashboard_state(db, tool_registry)
    low_names = {item.canonical_name for item in state.low_items}
    assert "onion" in low_names
    assert "potato" not in low_names


class TestClearDashboardCache:
    """The dashboard cache is a per-user memoization of DashboardState.

    The cache is exposed for invalidation from mutation handlers
    (consume, add, etc.) so users see fresh data immediately after
    a mutation rather than on the next periodic refresh.
    """

    def test_clear_with_no_user_id_clears_entire_cache(self):
        """Clearing with user_id=None drops the entire cache (test pattern)."""
        from shopstack.services.dashboard import (
            _DASHBOARD_CACHE,
            clear_dashboard_cache,
        )
        _DASHBOARD_CACHE["user1"] = "fake_state"
        _DASHBOARD_CACHE["user2"] = "fake_state"
        clear_dashboard_cache(None)
        assert _DASHBOARD_CACHE == {}

    def test_clear_with_user_id_drops_only_that_user(self):
        """Clearing with a specific user_id drops only that user's state."""
        from shopstack.services.dashboard import (
            _DASHBOARD_CACHE,
            clear_dashboard_cache,
        )
        _DASHBOARD_CACHE["user1"] = "user1_state"
        _DASHBOARD_CACHE["user2"] = "user2_state"
        clear_dashboard_cache("user1")
        assert "user1" not in _DASHBOARD_CACHE
        assert "user2" in _DASHBOARD_CACHE

    def test_clear_unknown_user_is_safe(self):
        """Clearing a user that was never cached is a no-op (no exception)."""
        from shopstack.services.dashboard import (
            _DASHBOARD_CACHE,
            clear_dashboard_cache,
        )
        _DASHBOARD_CACHE["user1"] = "user1_state"
        clear_dashboard_cache("nonexistent_user")
        assert "user1" in _DASHBOARD_CACHE  # untouched
