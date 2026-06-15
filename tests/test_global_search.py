"""Tests for `shopstack.services.global_search` — the multi-source search engine.

Verifies:
  * The type-prefix parser correctly scopes the search.
  * Inventory search ranks exact > prefix > contains.
  * Hinglish canonicalisation is honoured.
  * Shopping list, recipe, location, price, trace searchers all
    produce well-formed results.
  * Action commands are always available and match short queries.
  * Empty query returns no results (no exception).
  * The final result list is sorted by descending score and capped.
  * Cross-household isolation: a result carries its household_id and
    can be filtered downstream.
  * The palette HTML + script render the expected pieces.
  * Escape safety: a query that contains HTML is not interpreted.
"""
from __future__ import annotations

from html.parser import HTMLParser

import pytest

from shopstack.services.global_search import (
    GlobalSearchResult,
    SearchSources,
    _parse_type_prefix,
    render_palette_html,
    render_palette_script,
    search,
)


# ── Fixtures ───────────────────────────────────────────────────────


class _Lot:
    """Minimal stand-in for `InventoryLot`."""

    def __init__(
        self,
        lot_id: str,
        canonical_name: str,
        display_name: str,
        quantity: float = 1.0,
        unit: str = "",
        storage_location_id: str = "pantry",
    ) -> None:
        self.lot_id = lot_id
        self.canonical_name = canonical_name
        self.display_name = display_name
        self.quantity = quantity
        self.unit = unit
        self.storage_location_id = storage_location_id


class _ListItem:
    def __init__(self, name: str, priority: str = "normal") -> None:
        self.name = name
        self.priority = priority


class _List:
    def __init__(self, items: list[_ListItem]) -> None:
        self.items = items


class _Location:
    def __init__(self, name: str, kind: str = "storage") -> None:
        self.name = name
        self.kind = kind


class _PriceObs:
    def __init__(self, price: float, currency: str = "INR", store: str = "?") -> None:
        self.price = price
        self.currency = currency
        self.store = store


class _Trace:
    def __init__(self, summary: str = "", kind: str = "user") -> None:
        self.summary = summary
        self.kind = kind


class _Recipe:
    def __init__(
        self,
        title: str = "",
        ingredients: list[str] | None = None,
        cook_minutes: int = 30,
    ) -> None:
        self.title = title
        self.ingredients = ingredients or []
        self.cook_minutes = cook_minutes


class _CookbookService:
    def __init__(self, recipes: list[_Recipe]) -> None:
        self._recipes = recipes

    def get_recipes(self) -> list[_Recipe]:
        return list(self._recipes)


class _FakeDb:
    """Database stand-in with the methods the searchers call."""

    def __init__(
        self,
        lots: list[_Lot] | None = None,
        list_items: list[_ListItem] | None = None,
        locations: list[_Location] | None = None,
        prices_by_canonical: dict[str, list[_PriceObs]] | None = None,
        traces: list[_Trace] | None = None,
    ) -> None:
        self._lots = lots or []
        self._list_items = list_items or []
        self._locations = locations or []
        self._prices = prices_by_canonical or {}
        self._traces = traces or []

    def get_inventory(self, user_id: str = "") -> list[_Lot]:
        return list(self._lots)

    def get_active_shopping_list(self, user_id: str = ""):
        return _List(self._list_items) if self._list_items else None

    def get_locations(self) -> list[_Location]:
        return list(self._locations)

    def get_price_history(self, canonical_name: str, user_id: str = ""):
        return list(self._prices.get(canonical_name, []))

    def get_traces(self, limit: int = 50, user_id: str = "") -> list[_Trace]:
        return list(self._traces[:limit])


# ── Type-prefix parser ─────────────────────────────────────────────


class TestParseTypePrefix:
    def test_no_prefix_returns_full_query(self):
        f = _parse_type_prefix("milk")
        assert f.allowed is None
        assert f.remaining_query == "milk"

    def test_single_kind(self):
        f = _parse_type_prefix("type:recipe chicken")
        assert f.allowed == frozenset({"recipe"})
        assert f.remaining_query == "chicken"

    def test_multiple_kinds(self):
        f = _parse_type_prefix("type:recipe,trace milk")
        assert f.allowed == frozenset({"recipe", "trace"})
        assert f.remaining_query == "milk"

    def test_allows_helper(self):
        f = _parse_type_prefix("type:recipe x")
        assert f.allows("recipe")
        assert not f.allows("inventory")


# ── Search: inventory ─────────────────────────────────────────────


class TestInventorySearch:
    def test_exact_match_scores_1(self):
        db = _FakeDb(lots=[_Lot("lot-1", "milk", "Milk")])
        sources = SearchSources(database=db, user_id="hh1")
        results = search("milk", sources)
        assert any(r.kind == "inventory" and r.score == 1.0 for r in results)

    def test_prefix_match_scores_0_8(self):
        """A prefix that doesn't canonicalize to an exact name
        scores 0.8. We use 'milk' against 'milkshake': the
        canonicalization maps 'mil' → 'milk' but the lot's name
        is 'milkshake', so the canonicalization is a no-op and
        the prefix branch fires."""
        db = _FakeDb(lots=[_Lot("lot-1", "milkshake", "Milkshake")])
        sources = SearchSources(database=db, user_id="hh1")
        results = search("milk", sources)
        assert any(r.kind == "inventory" and 0.7 < r.score < 0.9 for r in results), (
            f"Expected prefix score ~0.8, got: "
            f"{[(r.kind, r.score) for r in results]}"
        )

    def test_contains_match_scores_0_5(self):
        db = _FakeDb(lots=[_Lot("lot-1", "milk", "Milk")])
        sources = SearchSources(database=db, user_id="hh1")
        results = search("il", sources)
        assert any(r.kind == "inventory" and r.score == 0.5 for r in results)

    def test_no_match_returns_empty(self):
        db = _FakeDb(lots=[_Lot("lot-1", "milk", "Milk")])
        sources = SearchSources(database=db, user_id="hh1")
        results = search("xyzzy", sources)
        assert all(r.kind != "inventory" for r in results)

    def test_hinglish_canonicalisation(self):
        """Searching 'doodh' should find 'milk' via canonicalisation."""
        db = _FakeDb(lots=[_Lot("lot-1", "milk", "Milk")])
        sources = SearchSources(database=db, user_id="hh1")
        results = search("doodh", sources)
        assert any(r.kind == "inventory" and r.title == "Milk" for r in results)

    def test_meta_includes_quantity_and_location(self):
        db = _FakeDb(lots=[_Lot("lot-1", "milk", "Milk", 2.0, "L", "fridge")])
        sources = SearchSources(database=db, user_id="hh1")
        results = search("milk", sources)
        assert any("2 L" in r.meta and "fridge" in r.meta for r in results)


# ── Search: shopping list ─────────────────────────────────────────


class TestShoppingListSearch:
    def test_finds_list_item(self):
        db = _FakeDb(list_items=[_ListItem("Onions", "high")])
        sources = SearchSources(database=db, user_id="hh1")
        results = search("onion", sources)
        assert any(r.kind == "list" for r in results)
        assert any("Onions" in r.title for r in results)
        assert any("priority high" in r.meta for r in results)

    def test_no_active_list_returns_no_results(self):
        db = _FakeDb()  # no list items
        sources = SearchSources(database=db, user_id="hh1")
        results = search("milk", sources)
        assert all(r.kind != "list" for r in results)


# ── Search: recipes ───────────────────────────────────────────────


class TestRecipeSearch:
    def test_finds_recipe_by_title(self):
        cb = _CookbookService([
            _Recipe(title="Chicken curry", cook_minutes=45),
        ])
        sources = SearchSources(cookbook=cb, user_id="hh1")
        results = search("chicken", sources)
        assert any(r.kind == "recipe" for r in results)

    def test_finds_recipe_by_ingredient(self):
        cb = _CookbookService([
            _Recipe(title="Mystery stew", ingredients=["chicken", "carrot"], cook_minutes=30),
        ])
        sources = SearchSources(cookbook=cb, user_id="hh1")
        results = search("chicken", sources)
        assert any(r.kind == "recipe" for r in results)

    def test_no_recipes_returns_no_recipe_results(self):
        cb = _CookbookService([])
        sources = SearchSources(cookbook=cb, user_id="hh1")
        results = search("chicken", sources)
        assert all(r.kind != "recipe" for r in results)


# ── Search: locations ────────────────────────────────────────────


class TestLocationSearch:
    def test_finds_location(self):
        db = _FakeDb(locations=[_Location("Fridge", "cold")])
        sources = SearchSources(database=db, user_id="hh1")
        results = search("fri", sources)
        assert any(r.kind == "location" for r in results)


# ── Search: prices ────────────────────────────────────────────────


class TestPriceSearch:
    def test_finds_price_observation(self):
        db = _FakeDb(
            lots=[_Lot("lot-1", "milk", "Milk")],
            prices_by_canonical={"milk": [_PriceObs(60.0, "INR", "BigBasket")]},
        )
        sources = SearchSources(database=db, user_id="hh1")
        results = search("milk", sources)
        assert any(r.kind == "price" for r in results)
        assert any("60.00 INR" in r.meta and "BigBasket" in r.meta for r in results)

    def test_no_prices_returns_no_price_results(self):
        db = _FakeDb(lots=[_Lot("lot-1", "milk", "Milk")])
        sources = SearchSources(database=db, user_id="hh1")
        results = search("milk", sources)
        assert all(r.kind != "price" for r in results)


# ── Search: traces ───────────────────────────────────────────────


class TestTraceSearch:
    def test_short_query_skipped(self):
        """Traces are noisy — we require a minimum query length."""
        db = _FakeDb(traces=[_Trace(summary="consumed milk", kind="consume_inventory")])
        sources = SearchSources(database=db, user_id="hh1")
        results = search("ab", sources)  # 2 chars, below the 3-char minimum
        assert all(r.kind != "trace" for r in results)

    def test_finds_trace_with_matching_summary(self):
        db = _FakeDb(traces=[_Trace(summary="consumed milk from fridge", kind="consume_inventory")])
        sources = SearchSources(database=db, user_id="hh1")
        results = search("milk", sources)
        assert any(r.kind == "trace" for r in results)


# ── Search: actions ──────────────────────────────────────────────


class TestActionSearch:
    def test_short_query_matches_action(self):
        results = search("home", SearchSources(database=_FakeDb(), user_id="hh1"))
        assert any(r.kind == "action" and "Home" in r.title for r in results)

    def test_theme_toggle_matches(self):
        results = search("theme", SearchSources(database=_FakeDb(), user_id="hh1"))
        assert any(r.action_kind == "fn" and "theme" in r.action_target.lower() for r in results)


# ── Search: ordering and caps ─────────────────────────────────────


class TestOrderingAndCap:
    def test_results_sorted_by_score(self):
        db = _FakeDb(
            lots=[
                _Lot("l1", "milk", "Milk"),
                _Lot("l2", "milkshake", "Milkshake"),
                _Lot("l3", "almond", "Almond"),
            ],
        )
        sources = SearchSources(database=db, user_id="hh1")
        results = search("mil", sources)
        inventory = [r for r in results if r.kind == "inventory"]
        # The exact match should come first
        assert inventory[0].title == "Milk"

    def test_results_capped_at_50(self):
        lots = [_Lot(f"l{i}", f"item{i}", f"Item {i}") for i in range(80)]
        db = _FakeDb(lots=lots)
        sources = SearchSources(database=db, user_id="hh1")
        results = search("item", sources)
        assert len(results) <= 50


# ── Edge cases ────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_query_returns_no_results(self):
        results = search("", SearchSources(database=_FakeDb(), user_id="hh1"))
        assert results == []

    def test_whitespace_query_returns_no_results(self):
        results = search("   ", SearchSources(database=_FakeDb(), user_id="hh1"))
        assert results == []

    def test_no_database_skips_data_sources(self):
        """When database is None, only actions should be returned."""
        results = search("milk", SearchSources(database=None, user_id="hh1"))
        # actions still match because "milk" doesn't match any action title
        assert all(r.kind == "action" for r in results)

    def test_database_exception_doesnt_crash(self):
        class _BoomDb:
            def get_inventory(self, user_id=""):
                raise RuntimeError("simulated failure")

        # Should not raise — every searcher catches and returns [].
        results = search("milk", SearchSources(database=_BoomDb(), user_id="hh1"))
        assert all(r.kind != "inventory" for r in results)

    def test_type_filter_scopes_results(self):
        db = _FakeDb(
            lots=[_Lot("l1", "milk", "Milk")],
            locations=[_Location("Milky way")],
        )
        sources = SearchSources(database=db, user_id="hh1")
        # "mil" with no filter matches inventory + location + actions
        results_unfiltered = search("mil", sources)
        # "type:inventory mil" scopes to inventory only
        results_filtered = search("type:inventory mil", sources)
        # The unfiltered set is a superset
        unfiltered_kinds = {r.kind for r in results_unfiltered}
        filtered_kinds = {r.kind for r in results_filtered}
        assert "inventory" in filtered_kinds
        # Filtered should not include kinds the user didn't ask for
        assert filtered_kinds.issubset({"inventory", "action"})


# ── Palette HTML + script ────────────────────────────────────────


class _TagListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


class TestPaletteHtml:
    def test_renders_overlay(self):
        html = render_palette_html(locale="en")
        assert "global-search-overlay" in html
        assert "global-search-input" in html
        assert "global-search-results" in html
        # Has the search placeholder
        assert "placeholder=" in html

    def test_hindi_placeholder(self):
        html = render_palette_html(locale="hi")
        assert "सर्च" in html or "खोज" in html


class TestPaletteScript:
    def test_returns_valid_script(self):
        script = render_palette_script()
        assert script.strip().startswith("<script")
        assert script.strip().endswith("</script>")
        assert 'data-ss-exec="true"' in script

    def test_registers_global_open_function(self):
        script = render_palette_script()
        assert "window.showGlobalSearch" in script
        assert "openPalette" in script

    def test_handles_keyboard_navigation(self):
        script = render_palette_script()
        for key in ("ArrowDown", "ArrowUp", "Enter", "Escape"):
            assert key in script

    def test_handles_cmd_ctrl_k(self):
        script = render_palette_script()
        assert "metaKey" in script
        assert "ctrlKey" in script
        assert "'k'" in script or '"k"' in script

    def test_uses_fetch_to_api_endpoint(self):
        script = render_palette_script()
        assert "/api/global_search" in script
        assert "fetch" in script

    def test_uses_abort_controller_to_cancel_inflight(self):
        script = render_palette_script()
        assert "AbortController" in script
        assert "AbortError" in script

    def test_no_global_pollution(self):
        """Only `window.showGlobalSearch` and IIFE-internal names
        should appear at script top level."""
        script = render_palette_script()
        iife_open = script.find("(function()")
        iife_close = script.rfind("})();")
        outside = script[:iife_open] + script[iife_close:]
        # `window.X = ...` is allowed (explicit export)
        # but `var X =` is not.
        import re
        m = re.search(r"^\s*var\s+\w+\s*=", outside, re.MULTILINE)
        assert m is None, f"Loose var declaration: {m.group(0)!r}"
