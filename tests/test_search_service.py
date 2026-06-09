from __future__ import annotations

from shopstack.services.search import SearchResult, semantic_search


def test_semantic_search_exact_match(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="milk", display_name="Milk", quantity=1.0, unit="L",
    )
    results = semantic_search(db, "milk")
    assert len(results) >= 1
    exact = [r for r in results if r.match_type == "exact"]
    assert len(exact) == 1
    assert exact[0].canonical_name == "milk"
    assert exact[0].score == 1.0


def test_semantic_search_prefix_match(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="tomato", display_name="Tomato", quantity=1.0, unit="kg",
    )
    results = semantic_search(db, "tom")
    assert len(results) >= 1
    prefix = [r for r in results if r.match_type == "prefix"]
    assert len(prefix) >= 1


def test_semantic_search_empty_query(db):
    results = semantic_search(db, "")
    assert results == []


def test_semantic_search_no_match(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="rice", display_name="Rice", quantity=5.0, unit="kg",
    )
    results = semantic_search(db, "unobtainium_xyz")
    assert results == []


def test_semantic_search_case_insensitive(db, tool_registry):
    tool_registry.add_inventory_item(
        canonical_name="onion", display_name="Onion", quantity=1.0, unit="kg",
    )
    results = semantic_search(db, "ONION")
    assert len(results) >= 1
    assert results[0].match_type == "exact"


def test_search_result_fields():
    sr = SearchResult(
        canonical_name="milk",
        display_name="Milk",
        category="dairy",
        match_type="exact",
        score=1.0,
    )
    assert sr.canonical_name == "milk"
    assert sr.match_type == "exact"
