"""Tests for shopstack.domain.storage_locations."""

from __future__ import annotations

import pytest

from shopstack.domain.storage_locations import (
    LocationNode,
    flatten_hierarchy,
    get_location_hierarchy,
    is_parent_of,
    location_path,
)


def _flat_dicts():
    """Standard test data: home > kitchen > fridge."""
    return [
        {"location_id": "home", "name": "Home", "parent_location_id": None, "location_type": "room"},
        {"location_id": "kitchen", "name": "Kitchen", "parent_location_id": "home", "location_type": "room"},
        {"location_id": "fridge", "name": "Fridge", "parent_location_id": "kitchen", "location_type": "container"},
        {"location_id": "freezer", "name": "Freezer", "parent_location_id": "fridge", "location_type": "container"},
    ]


def _node_dict():
    """Same as _flat_dicts but as a dict of LocationNode."""
    return {
        "home": LocationNode(location_id="home", name="Home", parent_location_id=None, location_type="room"),
        "kitchen": LocationNode(location_id="kitchen", name="Kitchen", parent_location_id="home", location_type="room"),
        "fridge": LocationNode(location_id="fridge", name="Fridge", parent_location_id="kitchen", location_type="container"),
        "freezer": LocationNode(location_id="freezer", name="Freezer", parent_location_id="fridge", location_type="container"),
    }


class TestLocationNode:
    """Tests for LocationNode dataclass."""

    def test_minimal_construction(self):
        node = LocationNode(location_id="x", name="X")
        assert node.parent_location_id is None
        assert node.location_type == ""
        assert node.depth == 0
        assert node.children == []

    def test_full_construction(self):
        node = LocationNode(
            location_id="x", name="X",
            parent_location_id="y", location_type="bin", depth=2,
        )
        assert node.parent_location_id == "y"
        assert node.location_type == "bin"
        assert node.depth == 2

    def test_to_dict_round_trip(self):
        node = LocationNode(
            location_id="x", name="X", parent_location_id="y", location_type="bin",
        )
        node.children = [LocationNode(location_id="a", name="A")]
        d = node.to_dict()
        assert d["location_id"] == "x"
        assert d["name"] == "X"
        assert d["parent_location_id"] == "y"
        assert d["location_type"] == "bin"
        assert len(d["children"]) == 1
        assert d["children"][0]["location_id"] == "a"

    def test_default_factory_for_children(self):
        # Each instance should get its own list, not share
        a = LocationNode(location_id="a", name="A")
        b = LocationNode(location_id="b", name="B")
        a.children.append(LocationNode(location_id="c", name="C"))
        assert b.children == []


class TestIsParentOf:
    """Tests for is_parent_of — ancestor check."""

    def test_direct_parent(self):
        assert is_parent_of("kitchen", "fridge", _node_dict()) is True

    def test_grandparent(self):
        assert is_parent_of("home", "fridge", _node_dict()) is True

    def test_great_grandparent(self):
        assert is_parent_of("home", "freezer", _node_dict()) is True

    def test_not_ancestor(self):
        assert is_parent_of("freezer", "home", _node_dict()) is False

    def test_siblings_not_ancestors(self):
        # Need to test with siblings
        nodes = {
            "kitchen": LocationNode(location_id="kitchen", name="Kitchen", parent_location_id="home"),
            "pantry": LocationNode(location_id="pantry", name="Pantry", parent_location_id="home"),
        }
        assert is_parent_of("pantry", "kitchen", nodes) is False

    def test_same_id_returns_false(self):
        assert is_parent_of("kitchen", "kitchen", _node_dict()) is False

    def test_accepts_list_of_dicts(self):
        assert is_parent_of("home", "fridge", _flat_dicts()) is True

    def test_none_locations(self):
        assert is_parent_of("kitchen", "fridge", None) is False

    def test_missing_child(self):
        nodes = _node_dict()
        assert is_parent_of("home", "nonexistent", nodes) is False

    def test_cycle_protection(self):
        # Construct a cycle manually
        nodes = {
            "a": LocationNode(location_id="a", name="A", parent_location_id="b"),
            "b": LocationNode(location_id="b", name="B", parent_location_id="a"),
        }
        # Should not infinite loop
        result = is_parent_of("a", "b", nodes)
        assert isinstance(result, bool)


class TestGetLocationHierarchy:
    """Tests for get_location_hierarchy — build tree from flat data."""

    def test_builds_tree_from_dicts(self):
        roots = get_location_hierarchy(_flat_dicts())
        assert len(roots) == 1
        home = roots[0]
        assert home.name == "Home"
        assert home.depth == 0
        assert len(home.children) == 1
        kitchen = home.children[0]
        assert kitchen.name == "Kitchen"
        assert kitchen.depth == 1
        assert len(kitchen.children) == 1
        fridge = kitchen.children[0]
        assert fridge.name == "Fridge"
        assert fridge.depth == 2

    def test_builds_tree_from_node_dict(self):
        roots = get_location_hierarchy(_node_dict())
        assert len(roots) == 1
        assert roots[0].name == "Home"

    def test_subtree_from_root_id(self):
        roots = get_location_hierarchy(_flat_dicts(), root_id="kitchen")
        assert len(roots) == 1
        kitchen = roots[0]
        assert kitchen.name == "Kitchen"
        assert len(kitchen.children) == 1
        assert kitchen.children[0].name == "Fridge"

    def test_multiple_roots(self):
        nodes = [
            {"location_id": "home1", "name": "Home1", "parent_location_id": None},
            {"location_id": "home2", "name": "Home2", "parent_location_id": None},
            {"location_id": "room1", "name": "Room1", "parent_location_id": "home1"},
        ]
        roots = get_location_hierarchy(nodes)
        assert len(roots) == 2

    def test_orphan_node(self):
        # Node whose parent doesn't exist in the set
        nodes = [
            {"location_id": "room1", "name": "Room1", "parent_location_id": "ghost"},
        ]
        roots = get_location_hierarchy(nodes)
        # "room1" with no parent in the set is treated as a root
        assert len(roots) == 1
        assert roots[0].name == "Room1"

    def test_empty_input(self):
        assert get_location_hierarchy([]) == []


class TestFlattenHierarchy:
    """Tests for flatten_hierarchy — DFS back to list."""

    def test_flatten_simple_tree(self):
        roots = get_location_hierarchy(_flat_dicts())
        flat = flatten_hierarchy(roots)
        names = [n.name for n in flat]
        assert names == ["Home", "Kitchen", "Fridge", "Freezer"]

    def test_flatten_multiple_roots(self):
        nodes = [
            {"location_id": "a", "name": "A", "parent_location_id": None},
            {"location_id": "b", "name": "B", "parent_location_id": None},
        ]
        roots = get_location_hierarchy(nodes)
        flat = flatten_hierarchy(roots)
        assert len(flat) == 2

    def test_flatten_empty(self):
        assert flatten_hierarchy([]) == []


class TestLocationPath:
    """Tests for location_path — return path from root to target."""

    def test_path_to_deep_node(self):
        path = location_path("freezer", _node_dict())
        assert path == ["Home", "Kitchen", "Fridge", "Freezer"]

    def test_path_to_root(self):
        path = location_path("home", _node_dict())
        assert path == ["Home"]

    def test_path_with_list_input(self):
        path = location_path("freezer", _flat_dicts())
        assert path == ["Home", "Kitchen", "Fridge", "Freezer"]

    def test_path_to_nonexistent(self):
        path = location_path("nonexistent", _node_dict())
        assert path == []

    def test_path_to_orphan(self):
        # Node with parent that doesn't exist in the set
        nodes = [
            {"location_id": "room1", "name": "Room1", "parent_location_id": "ghost"},
        ]
        path = location_path("room1", nodes)
        assert path == ["Room1"]
