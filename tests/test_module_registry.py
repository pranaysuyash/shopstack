"""Tests for shopstack/module_registry.py — module metadata system."""

from __future__ import annotations

from shopstack.module_registry import (
    SHOPAGENT,
    SHOPBASKET,
    SHOPCOMPARE,
    SHOPLENS,
    SHOPMEMORY,
    SHOPNUTRITION,
    SHOPSTOCK,
    RUNTIME,
    SOURCES,
    ModuleMetadata,
    get_all,
    get_by_slug,
    get_by_tab_id,
    get_tab_ids,
    module_dependencies,
    navigation,
    summary_table,
)


def test_all_modules_have_required_fields():
    """Every registered module must have name, slug, label, and description."""
    for m in get_all():
        assert m.name, f"Module missing name: {m}"
        assert m.slug, f"Module missing slug: {m}"
        assert m.label, f"Module missing label: {m}"
        assert m.description, f"Module missing description: {m}"


def test_slugs_are_unique():
    """No two modules share the same slug."""
    slugs = [m.slug for m in get_all()]
    assert len(slugs) == len(set(slugs)), f"Duplicate slugs: {slugs}"


def test_eight_modules_registered():
    """There should be exactly 9 modules registered."""
    modules = get_all()
    assert len(modules) == 9


def test_specific_modules_present():
    """All expected modules are registered with correct names."""
    expected = {
        "stock": "ShopStock",
        "basket": "ShopBasket",
        "compare": "ShopCompare",
        "lens": "ShopLens",
        "memory": "ShopMemory",
        "agent": "ShopAgent",
        "sources": "Sources",
        "runtime": "Runtime",
        "nutrition": "ShopNutrition",
    }
    for slug, name in expected.items():
        m = get_by_slug(slug)
        assert m is not None, f"Module '{slug}' not found"
        assert m.name == name, f"Module '{slug}' name mismatch: {m.name} != {name}"


def test_get_by_tab_id():
    """Lookup by tab ID returns correct module(s)."""
    assert any(m.slug == "basket" for m in get_by_tab_id("basket"))
    assert any(m.slug == "compare" for m in get_by_tab_id("basket"))
    assert any(m.slug == "lens" for m in get_by_tab_id("market"))
    assert any(m.slug == "agent" for m in get_by_tab_id("today"))
    assert any(m.slug == "stock" for m in get_by_tab_id("reconcile"))
    assert any(m.slug == "agent" for m in get_by_tab_id("memory"))
    assert any(m.slug == "memory" for m in get_by_tab_id("memory"))
    assert any(m.slug == "nutrition" for m in get_by_tab_id("memory"))
    assert any(m.slug == "runtime" for m in get_by_tab_id("memory"))


def test_get_by_tab_id_returns_empty_for_unknown():
    """Unknown tab ID returns empty list."""
    assert get_by_tab_id("nonexistent_tab") == []


def test_get_tab_ids():
    """Tab IDs are returned correctly for each module."""
    assert "basket" in get_tab_ids("basket")
    assert "market" in get_tab_ids("lens")
    assert "today" in get_tab_ids("agent")
    assert "memory" in get_tab_ids("agent")
    assert "reconcile" in get_tab_ids("stock")
    assert "basket" in get_tab_ids("compare")


def test_get_tab_ids_unknown():
    """Unknown slug returns empty tuple."""
    assert get_tab_ids("nonexistent") == ()


def test_sources_has_no_tabs():
    """Sources module is marked as source and has no tab IDs."""
    assert SOURCES.is_source is True
    assert SOURCES.tab_ids == ()


def test_runtime_has_memory_tab():
    """Runtime module is exposed under the Memory/System area."""
    assert "memory" in RUNTIME.tab_ids
    assert RUNTIME.label == "System"


def test_dependencies():
    """ShopAgent depends on stock, basket, and memory."""
    deps = module_dependencies("agent")
    dep_slugs = [d.slug for d in deps]
    assert "stock" in dep_slugs
    assert "basket" in dep_slugs
    assert "memory" in dep_slugs


def test_five_primary_tabs_in_order():
    """TAB_ORDER has exactly 6 primary tabs."""
    from shopstack.module_registry import TAB_ORDER
    assert len(TAB_ORDER) == 6
    assert (
        TAB_ORDER["today"]
        < TAB_ORDER["cookbook"]
        < TAB_ORDER["basket"]
        < TAB_ORDER["market"]
        < TAB_ORDER["reconcile"]
        < TAB_ORDER["memory"]
    )


def test_navigation_returns_tab_entries():
    """navigation() returns list of (tab_id, label, module_name) tuples."""
    entries = navigation()
    assert len(entries) > 0
    for tab_id, label, module_name in entries:
        assert isinstance(tab_id, str)
        assert isinstance(label, str)
        assert isinstance(module_name, str)


def test_summary_table_has_all_modules():
    """summary_table() returns a dict for each module with expected keys."""
    rows = summary_table()
    assert len(rows) == 12
    for row in rows:
        assert "Module" in row
        assert "Label" in row
        assert "Description" in row
        assert "Tabs" in row


def test_module_level_variables_referenced():
    """Module-level variables reference the same objects as lookups."""
    assert SHOPSTOCK is get_by_slug("stock")
    assert SHOPBASKET is get_by_slug("basket")
    assert SHOPCOMPARE is get_by_slug("compare")
    assert SHOPLENS is get_by_slug("lens")
    assert SHOPMEMORY is get_by_slug("memory")
    assert SHOPAGENT is get_by_slug("agent")
    assert SOURCES is get_by_slug("sources")
    assert RUNTIME is get_by_slug("runtime")
    assert SHOPNUTRITION is get_by_slug("nutrition")


def test_descriptions_are_unique():
    """Each module should have a distinct description."""
    descriptions = [m.description for m in get_all()]
    assert len(descriptions) == len(set(descriptions)), "Duplicate descriptions found"
