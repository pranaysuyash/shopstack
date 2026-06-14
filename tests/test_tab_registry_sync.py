"""Tests that the tab builder registry and module registry stay in sync.

These tests prevent the declarative/imperative drift that existed before
the registry-driven composition refactor. If someone adds a tab to TAB_ORDER
but forgets to register its builder (or vice versa), these tests catch it.
"""
from __future__ import annotations

from shopstack.module_registry import TAB_ORDER, TAB_LABELS, tab_order, get_by_tab_id
from shopstack.ui.tabs.registry import registered_tab_ids


def test_every_tab_order_entry_has_a_builder():
    """Every tab_id in TAB_ORDER must have a registered builder function.

    If you add a tab to TAB_ORDER, you must also add its builder to
    ``shopstack/ui/tabs/registry.py::_TAB_BUILDERS``.
    """
    registry_ids = registered_tab_ids()
    missing_builders = set(TAB_ORDER) - registry_ids
    assert not missing_builders, (
        f"TAB_ORDER has entries with no registered builder: {missing_builders}. "
        f"Add them to shopstack/ui/tabs/registry.py::_TAB_BUILDERS."
    )


def test_every_builder_has_a_tab_order_entry():
    """Every registered builder must have a TAB_ORDER entry.

    If you add a builder to the registry, you must also declare its
    position in ``module_registry.TAB_ORDER`` and its label in
    ``TAB_LABELS``.
    """
    registry_ids = registered_tab_ids()
    missing_order = registry_ids - set(TAB_ORDER)
    assert not missing_order, (
        f"Registry has builders with no TAB_ORDER entry: {missing_order}. "
        f"Add them to module_registry.TAB_ORDER and TAB_LABELS."
    )


def test_every_tab_has_a_label():
    """Every tab in TAB_ORDER must have a TAB_LABELS entry."""
    missing_labels = set(TAB_ORDER) - set(TAB_LABELS)
    assert not missing_labels, (
        f"Tabs missing from TAB_LABELS: {missing_labels}. "
        f"Add display labels for every tab."
    )


def test_tab_order_returns_all_tabs():
    """tab_order() must return exactly the tabs in TAB_ORDER."""
    result = tab_order()
    returned_ids = {tab_id for tab_id, _ in result}
    assert returned_ids == set(TAB_ORDER), (
        f"tab_order() returned {returned_ids} which differs from "
        f"TAB_ORDER keys {set(TAB_ORDER)}."
    )


def test_tab_order_is_sorted():
    """tab_order() must return tabs sorted by their TAB_ORDER value."""
    result = tab_order()
    orders = [TAB_ORDER[tab_id] for tab_id, _ in result]
    assert orders == sorted(orders), (
        f"tab_order() is not sorted by TAB_ORDER values: {orders}."
    )


def test_every_tab_has_at_least_one_module():
    """Every tab in TAB_ORDER must belong to at least one module.

    This ensures metadata surfaces (summary tables, get_by_tab_id,
    navigation) work correctly for every tab.
    """
    orphan_tabs = [tid for tid in TAB_ORDER if not get_by_tab_id(tid)]
    assert not orphan_tabs, (
        f"These tabs belong to no module: {orphan_tabs}. "
        f"Add them to the appropriate module's tab_ids in module_registry.py."
    )
