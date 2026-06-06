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
