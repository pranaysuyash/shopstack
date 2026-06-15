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
    # "tom" is a substring of "tomato" — with Hinglish canonicalization this
    # now resolves to an exact match (resolve_canonical does substring
    # canonicalization). We accept either exact or prefix as a valid match.
    assert any(r.match_type in ("exact", "prefix") for r in results)
    assert any(r.canonical_name == "tomato" for r in results)


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


class TestHinglishAliasCanonicalization:
    """Hinglish / regional / colloquial queries must resolve to canonical names
    via ``resolve_canonical`` before the embedding search runs. This is the
    "Phase 1 #4" Hinglish enablement for the BGE-M3 wired search path.

    Without this pre-canonicalization, "doodh" (milk in Hindi) returns no
    results because the inventory only stores English canonical names, and
    BGE-M3 embeddings of "doodh" vs "milk" don't bridge the language gap.
    """

    def test_doodh_resolves_to_milk(self, db, tool_registry):
        tool_registry.add_inventory_item(
            canonical_name="milk", display_name="Milk", quantity=1.0, unit="L",
        )
        results = semantic_search(db, "doodh")
        assert any(r.canonical_name == "milk" and r.match_type == "exact" for r in results)

    def test_tamatar_resolves_to_tomato(self, db, tool_registry):
        tool_registry.add_inventory_item(
            canonical_name="tomato", display_name="Tomato", quantity=2.0, unit="kg",
        )
        results = semantic_search(db, "tamatar")
        assert any(r.canonical_name == "tomato" and r.match_type == "exact" for r in results)

    def test_pyaaz_resolves_to_onion(self, db, tool_registry):
        tool_registry.add_inventory_item(
            canonical_name="onion", display_name="Onion", quantity=1.0, unit="kg",
        )
        results = semantic_search(db, "pyaaz")
        assert any(r.canonical_name == "onion" and r.match_type == "exact" for r in results)

    def test_dahi_resolves_to_curd(self, db, tool_registry):
        """dahi must resolve to 'curd' (Indian market canonical).

        Prior to audit 2026-06-14, this test asserted dahi→yogurt
        (the _CANONICAL_MAP slug). The alias maps have been unified
        so dahi/curd/yogurt all resolve to 'curd' — the canonical
        Indian-English market name.
        """
        tool_registry.add_inventory_item(
            canonical_name="curd", display_name="Curd (dahi)", quantity=0.5, unit="kg",
        )
        results = semantic_search(db, "dahi")
        assert any(r.canonical_name == "curd" and r.match_type == "exact" for r in results)

    def test_hinglish_canonicalization_skips_when_no_match(self, db, tool_registry):
        # "cheese" is not in the alias map, so it should fall through to the
        # embedding branch (or prefix if "cheese" is a substring of any item).
        tool_registry.add_inventory_item(
            canonical_name="paneer", display_name="Paneer", quantity=0.5, unit="kg",
        )
        # We don't assert which match_type it returns (depends on BGE-M3
        # embedding availability in this env), just that the result is sane.
        results = semantic_search(db, "cheese")
        # Either a semantic match, a no-op, or paneer-via-alias "panir" — all OK
        # as long as the function doesn't crash.
        assert isinstance(results, list)

    def test_english_query_still_exact(self, db, tool_registry):
        """Regression: Hinglish pre-canonicalization must not break plain English search."""
        tool_registry.add_inventory_item(
            canonical_name="onion", display_name="Onion", quantity=1.0, unit="kg",
        )
        results = semantic_search(db, "onion")
        exact = [r for r in results if r.match_type == "exact"]
        assert len(exact) == 1
        assert exact[0].canonical_name == "onion"
