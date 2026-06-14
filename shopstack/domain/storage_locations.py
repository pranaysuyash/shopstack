"""Storage location hierarchy and parent-child queries.

Pure business logic — no external dependencies.
Supersedes scattered location logic in shopstack/ui/screens/other.py
and shopstack/services/find.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LocationNode:
    """A node in the location hierarchy tree."""
    location_id: str
    name: str
    parent_location_id: str | None = None
    location_type: str = ""
    depth: int = 0
    children: list[LocationNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "location_id": self.location_id,
            "name": self.name,
            "parent_location_id": self.parent_location_id,
            "location_type": self.location_type,
            "depth": self.depth,
            "children": [c.to_dict() for c in self.children],
        }


def is_parent_of(
    parent_id: str,
    child_id: str,
    locations: dict[str, LocationNode] | list[dict] | None = None,
) -> bool:
    """Check if parent_id is an ancestor of child_id in the location tree.

    Walks up from child_id looking for parent_id. Handles arbitrary depth.
    Accepts a dict mapping location_id -> LocationNode, or a list of dicts
    with 'location_id' and 'parent_location_id' keys.
    """
    if parent_id == child_id:
        return False

    if locations is None:
        return False

    # Build lookup if needed
    if isinstance(locations, list):
        parent_map = {
            loc.get("location_id", ""): loc.get("parent_location_id")
            for loc in locations
        }
    elif isinstance(locations, dict):
        parent_map = {
            lid: node.parent_location_id
            for lid, node in locations.items()
            if hasattr(node, "parent_location_id")
        }
    else:
        return False

    current = child_id
    visited = set()
    while current and current not in visited:
        if current == parent_id:
            return True
        visited.add(current)
        current = parent_map.get(current)

    return False


def get_location_hierarchy(
    locations: list[dict] | dict[str, LocationNode],
    root_id: str | None = None,
) -> list[LocationNode]:
    """Build a hierarchical tree of LocationNode from flat location data.

    Args:
        locations: Flat list of dicts with location_id, name, parent_location_id
                   OR dict mapping location_id -> LocationNode.
        root_id: If given, return only the subtree rooted here.
                 If None, return all root-level nodes.

    Returns:
        List of root LocationNode with children nested.
    """
    # Normalize to dict of LocationNode
    if isinstance(locations, dict):
        nodes = {lid: node for lid, node in locations.items()}
    else:
        nodes = {}
        for loc in locations:
            lid = loc.get("location_id", "")
            if lid:
                nodes[lid] = LocationNode(
                    location_id=lid,
                    name=loc.get("name", ""),
                    parent_location_id=loc.get("parent_location_id"),
                    location_type=loc.get("location_type", ""),
                )

    # Build parent->children mapping
    children_map: dict[str | None, list[LocationNode]] = {}
    for lid, node in nodes.items():
        parent = node.parent_location_id
        children_map.setdefault(parent, []).append(node)

    # Assign depth and recurse
    def _assign_depth(node: LocationNode, depth: int) -> None:
        node.depth = depth
        for child in node.children:
            _assign_depth(child, depth + 1)

    def _build_tree(parent_id: str | None) -> list[LocationNode]:
        children = children_map.get(parent_id, [])
        for child in children:
            child.children = _build_tree(child.location_id)
            _assign_depth(child, (nodes[parent_id].depth + 1) if parent_id and parent_id in nodes else 0)
        return children

    if root_id and root_id in nodes:
        root = nodes[root_id]
        root.children = _build_tree(root_id)
        _assign_depth(root, 0)
        return [root]

    # Find all roots (no parent or parent not in set)
    all_parent_ids = {node.parent_location_id for node in nodes.values() if node.parent_location_id}
    roots = [nodes[lid] for lid in nodes if lid not in all_parent_ids]

    for root in roots:
        root.children = _build_tree(root.location_id)
        _assign_depth(root, 0)

    return roots


def flatten_hierarchy(roots: list[LocationNode]) -> list[LocationNode]:
    """Flatten a tree of LocationNodes back to a list (DFS order)."""
    result = []
    stack = list(roots)
    while stack:
        node = stack.pop()
        result.append(node)
        stack.extend(reversed(node.children))
    return result


def location_path(
    target_id: str,
    locations: dict[str, LocationNode] | list[dict],
) -> list[str]:
    """Return the path from root to target_id as a list of location names."""
    if isinstance(locations, list):
        parent_map = {
            loc.get("location_id", ""): (
                loc.get("name", ""),
                loc.get("parent_location_id"),
            )
            for loc in locations
        }
    elif isinstance(locations, dict):
        parent_map = {
            lid: (node.name, node.parent_location_id)
            for lid, node in locations.items()
        }
    else:
        return []

    path = []
    current = target_id
    visited = set()
    while current and current not in visited:
        if current not in parent_map:
            break
        name, parent = parent_map[current]
        path.append(name)
        visited.add(current)
        current = parent

    return list(reversed(path))
