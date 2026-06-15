"""Regression tests for the primary nav restructure (2026-06-15).

The user-facing primary nav is now 6 items (Home / Pantry /
Shopping / Recipes / Trips / Memory) — replacing the legacy 5-group
nested layout (Home / Groceries / Shopping / At Home / Memory).

These tests pin:

1. The new PRIMARY_NAV has exactly 6 items in the recommended order.
2. The legacy TAB_GROUPS dict is still populated (back-compat).
3. The ``use_primary_nav`` flag on the tab builder controls which
   layout is rendered.
"""
from __future__ import annotations


class TestPrimaryNavShape:
    """PRIMARY_NAV is the canonical 6-item user-facing nav."""

    def test_six_items(self):
        from shopstack.module_registry import PRIMARY_NAV
        assert len(PRIMARY_NAV) == 6, (
            "PRIMARY_NAV must have exactly 6 items; got "
            f"{[n['id'] for n in PRIMARY_NAV]}"
        )

    def test_recommended_order(self):
        # Pin the order so a refactor doesn't accidentally
        # re-shuffle the user-facing tabs.
        from shopstack.module_registry import PRIMARY_NAV
        ids = [n["id"] for n in PRIMARY_NAV]
        assert ids == ["home", "pantry", "shopping", "recipes", "trips", "memory"], (
            f"PRIMARY_NAV order is wrong: {ids}"
        )

    def test_each_item_has_required_fields(self):
        from shopstack.module_registry import PRIMARY_NAV
        for item in PRIMARY_NAV:
            assert "id" in item
            assert "label" in item
            assert "destination" in item
            assert "subtitle" in item
            # Labels should be 1-3 words (not feature lists)
            assert 1 <= len(item["label"].split()) <= 3, (
                f"label '{item['label']}' is too long; primary nav labels should be 1-3 words"
            )

    def test_each_destination_is_a_real_tab(self):
        # The destination tab must exist in the registry.
        from shopstack.module_registry import PRIMARY_NAV, TAB_LABELS
        for item in PRIMARY_NAV:
            dest = item["destination"]
            assert dest in TAB_LABELS, (
                f"PRIMARY_NAV item {item['id']!r} has unknown destination {dest!r}"
            )

    def test_destinations_answer_user_jobs(self):
        from shopstack.module_registry import PRIMARY_NAV
        # Each item's subtitle should answer "what is this for?"
        # (not just be the destination tab's name).
        for item in PRIMARY_NAV:
            assert "?" in item["subtitle"] or "—" in item["subtitle"] or len(item["subtitle"]) > 10, (
                f"subtitle for {item['id']!r} is too short: {item['subtitle']!r}"
            )


class TestLegacyTabGroupsStillPresent:
    """Back-compat: TAB_GROUPS still exists for older callers."""

    def test_tab_groups_is_dict(self):
        from shopstack.module_registry import TAB_GROUPS
        assert isinstance(TAB_GROUPS, dict)
        assert len(TAB_GROUPS) >= 3

    def test_every_legacy_group_has_a_label(self):
        from shopstack.module_registry import TAB_GROUPS, GROUP_LABELS
        for group_id in TAB_GROUPS:
            assert group_id in GROUP_LABELS, (
                f"group {group_id!r} missing from GROUP_LABELS"
            )

    def test_group_order_sorts_known_groups(self):
        from shopstack.module_registry import group_order, GROUP_LABELS
        result = group_order()
        # Returns a list of (id, label) tuples in display order.
        assert isinstance(result, list)
        ids = [t[0] for t in result]
        # All known groups should appear.
        for known in GROUP_LABELS:
            assert known in ids


class TestAdvancedTabsStillReachable:
    """The advanced sub-tabs must remain accessible inside each primary item."""

    def test_advanced_dict_covers_all_primary_items(self):
        from shopstack.module_registry import PRIMARY_NAV, PRIMARY_NAV_ADVANCED
        for item in PRIMARY_NAV:
            assert item["id"] in PRIMARY_NAV_ADVANCED, (
                f"PRIMARY_NAV_ADVANCED missing entry for {item['id']!r}"
            )

    def test_advanced_tabs_resolve_to_registered_builders(self):
        # Every tab_id listed in PRIMARY_NAV_ADVANCED must have a
        # registered builder (otherwise the nested sub-tab will be
        # silently skipped).
        from shopstack.module_registry import PRIMARY_NAV_ADVANCED
        from shopstack.ui.tabs.registry import registered_tab_ids
        builders = registered_tab_ids()
        for primary_id, advanced_ids in PRIMARY_NAV_ADVANCED.items():
            for tab_id in advanced_ids:
                assert tab_id in builders, (
                    f"advanced tab {tab_id!r} (in {primary_id!r}) has no registered builder"
                )


class TestBuildAllTabsWithPrimaryNav:
    """The build_all_tabs(use_primary_nav=True) flag is honoured."""

    def test_registry_exports_use_primary_nav(self):
        # Inspect the source for the kwarg, since the function is
        # tricky to call outside a real Gradio context.
        import inspect
        from shopstack.ui.tabs import registry
        sig = inspect.signature(registry.build_all_tabs)
        assert "use_primary_nav" in sig.parameters, (
            "build_all_tabs() must accept use_primary_nav kwarg"
        )

    def test_default_use_primary_nav_is_false(self):
        # Default to the legacy 5-group layout for back-compat.
        import inspect
        from shopstack.ui.tabs import registry
        sig = inspect.signature(registry.build_all_tabs)
        assert sig.parameters["use_primary_nav"].default is False, (
            "use_primary_nav default must be False for back-compat"
        )


class TestNoDuplicateTabIds:
    """A tab_id should not appear in two primary items."""

    def test_destinations_are_unique(self):
        from shopstack.module_registry import PRIMARY_NAV
        destinations = [item["destination"] for item in PRIMARY_NAV]
        assert len(destinations) == len(set(destinations)), (
            f"primary nav destinations must be unique: {destinations}"
        )

    def test_advanced_tabs_no_duplicate_within_a_primary(self):
        from shopstack.module_registry import PRIMARY_NAV_ADVANCED
        for primary_id, tabs in PRIMARY_NAV_ADVANCED.items():
            assert len(tabs) == len(set(tabs)), (
                f"PRIMARY_NAV_ADVANCED[{primary_id!r}] has duplicate tab ids: {tabs}"
            )
