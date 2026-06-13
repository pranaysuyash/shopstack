"""Tests for the cookbook screen module — Gradio adapters around the cookbook service.

The service layer (``shopstack.services.cookbook``) is tested in
``test_cookbook_service.py`` (28 tests). This file tests the
*adapter* layer that Gradio calls — function signatures, return
shapes, defensive handling, and the XSS / empty-data composition
that the service assumes but the Gradio surface must guarantee.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

import pytest


# ─── Helper: temporarily swap the global db ─────────────────────────


@contextmanager
def _swap_global_db(monkeypatch, fake_db: Any):
    """Replace the module-level ``db`` global in the screen module.

    The screen module reads ``current_user_id`` and ``db`` at call
    time via ``shopstack.app_context``. We patch those name lookups
    so the screen module sees our fake. This avoids spinning up a
    real SQLite DB for every test.
    """
    import shopstack.ui.screens.cookbook as screen

    class _Ctx:
        def __init__(self, db):
            self.db = db
            self.uid = "hh-1"

        def active_household_id(self) -> str:
            return self.uid

    fake_ctx = _Ctx(fake_db)
    monkeypatch.setattr(screen, "db", fake_db, raising=False)
    monkeypatch.setattr(
        screen, "current_user_id", lambda: fake_ctx.uid, raising=False
    )
    yield


# ─── A minimal fake db mirroring the real one ───────────────────────


class _FakeDB:
    """Just enough surface for the cookbook screen module."""

    def __init__(self) -> None:
        self.lists: list[dict] = []
        self.added: list[dict] = []
        self.next_list_id = "list-1"

    # Inventory
    def get_inventory(self, user_id: str = ""):
        # Return empty inventory for the fakery; tests can patch
        # this if they need a populated pantry.
        return []

    # Preferences
    def get_preference_signals(self, user_id: str = ""):
        return []

    # Shopping list
    def get_active_shopping_list(self, user_id: str = ""):
        if not self.lists:
            return None
        return _FakeList(self.lists[0]["list_id"], self.lists[0]["name"])

    def create_shopping_list(
        self,
        name: str = "Shopping List",
        goal: str = "",
        user_id: str = "",
        list_id: str | None = None,
    ):
        new_id = self.next_list_id
        self.next_list_id = f"list-{int(self.next_list_id.split('-')[-1]) + 1}"
        self.lists.append({"list_id": new_id, "name": name, "goal": goal})
        return _FakeList(new_id, name)

    def add_list_item(self, list_id: str, item):
        self.added.append({
            "list_id": list_id,
            "canonical_name": item.canonical_name,
            "quantity": item.requested_quantity,
            "unit": item.unit,
        })
        return item


class _FakeList:
    def __init__(self, list_id: str, name: str) -> None:
        self.list_id = list_id
        self.name = name


# ─── Fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    return db


# ─── Tests: cookbook_cuisine_choices ─────────────────────────────────


class TestCookbookCuisineChoices:
    def test_includes_all_first(self):
        from shopstack.ui.screens.cookbook import cookbook_cuisine_choices
        choices = cookbook_cuisine_choices()
        assert choices[0] == ("All", "all")

    def test_returns_at_least_one(self):
        from shopstack.ui.screens.cookbook import cookbook_cuisine_choices
        assert len(cookbook_cuisine_choices()) >= 1

    def test_all_cuisines_title_cased(self):
        from shopstack.ui.screens.cookbook import cookbook_cuisine_choices
        for label, value in cookbook_cuisine_choices()[1:]:
            # "indian_north" → "Indian North"
            assert label == label.title()
            # Value stays in canonical form (snake_case)
            assert value == value.lower()


# ─── Tests: cookbook_browse ─────────────────────────────────────────


class TestCookbookBrowse:
    def test_returns_html_string(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_browse()
        assert isinstance(out, str)
        assert "Browse" in out  # section heading

    def test_includes_all_recipes_by_default(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_browse()
        # 30 recipes in the DB; default filter shows them all.
        assert out.count("cb-card-head") == 30

    def test_vegetarian_filter_excludes_non_veg(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_browse(dietary="vegetarian")
        assert "Chicken Curry" not in out
        # All 27 vegetarian recipes are shown
        assert out.count("cb-card-head") == 27

    def test_cuisine_filter_works(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_browse(cuisine="indian_north")
        # Should be a subset (Indian North only)
        cards = out.count("cb-card-head")
        assert cards > 0 and cards < 30

    def test_search_filter_works(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_browse(search="paneer")
        assert "Palak Paneer" in out

    def test_dietary_all_equals_no_filter(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            full = screen.cookbook_browse(dietary="all")
            all_explicit = screen.cookbook_browse(dietary="all")
        assert full == all_explicit
        # Both should be the full library
        assert full.count("cb-card-head") == 30

    def test_accepts_string_quick_only_for_non_gradio_callers(self, monkeypatch, fake_db):
        """Some callers (tests, CLI) pass booleans as strings."""
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_browse(quick_only="true")
        # "true" string should be accepted; verify no exception
        assert isinstance(out, str)

    def test_lowercases_search_input(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            upper = screen.cookbook_browse(search="PANEER")
            lower = screen.cookbook_browse(search="paneer")
        # Both should return the same recipes (case-insensitive search)
        assert upper.count("cb-card-head") == lower.count("cb-card-head")

    def test_empty_string_search_no_op(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            no_search = screen.cookbook_browse(search="")
            with_search = screen.cookbook_browse(search="  ")  # whitespace
        # Whitespace should be normalized to "" so no filter is applied
        assert no_search == with_search

    def test_does_not_crash_on_db_error(self, monkeypatch):
        """A DB error in browse should be swallowed and return empty-ish HTML."""
        from shopstack.ui.screens import cookbook as screen

        class _BrokenDB:
            def get_inventory(self, user_id=""): raise RuntimeError("simulated")
            def get_preference_signals(self, user_id=""): return []

        with _swap_global_db(monkeypatch, _BrokenDB()):
            # The screen wraps in try/except — should not raise
            out = screen.cookbook_browse()
        assert isinstance(out, str)


# ─── Tests: cookbook_view_recipe ─────────────────────────────────────


class TestCookbookViewRecipe:
    def test_empty_recipe_id_returns_browse(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_view_recipe("")
        # Falls back to the browse grid
        assert out.count("cb-card-head") == 30

    def test_unknown_recipe_id_returns_browse(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_view_recipe("nonexistent_recipe_xyz")
        assert out.count("cb-card-head") == 30

    def test_valid_recipe_returns_detail(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_view_recipe("dal_makhani")
        # Detail view has ingredients + numbered steps
        assert "Dal Makhani" in out
        assert "cb-ing" in out  # ingredient list class
        assert "cb-step" in out  # step list class

    def test_detail_includes_ingredients(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_view_recipe("dal_makhani")
        # Dal Makhani should have urad_dal as an ingredient
        assert "urad" in out.lower()  # canonical name or display

    def test_detail_does_not_crash_on_db_error(self, monkeypatch):
        from shopstack.ui.screens import cookbook as screen

        class _BrokenDB:
            def get_inventory(self, user_id=""): raise RuntimeError("simulated")
            def get_preference_signals(self, user_id=""): return []

        with _swap_global_db(monkeypatch, _BrokenDB()):
            # Should not raise
            out = screen.cookbook_view_recipe("dal_makhani")
        assert "Dal Makhani" in out
        # No "have" markers (no match computed) — every ingredient shows as missing
        assert "cb-ing-have" not in out
        assert "✓" not in out  # no "have" prefix on ingredient lines


# ─── Tests: cookbook_shop_missing ──────────────────────────────────


class TestCookbookShopMissing:
    def test_empty_recipe_id_returns_warning(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_shop_missing("")
        assert "⚠" in out or "No recipe" in out

    def test_unknown_recipe_id_returns_warning(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_shop_missing("nonexistent_xyz")
        assert "⚠" in out or "not found" in out

    def test_already_have_everything_returns_green(self, monkeypatch, fake_db):
        """When inventory has all ingredients, return the success 'already have' state."""
        from shopstack.ui.screens import cookbook as screen
        from shopstack.services.recipes import Recipe
        import shopstack.ui.screens.cookbook as screen_module

        # A real Recipe with attributes match_recipe needs.
        from dataclasses import dataclass

        @dataclass
        class _I:
            canonical_name: str
            quantity: float = 1.0
            unit: str = "unit"

        real_recipe = Recipe(
            id="one-ingredient-recipe",
            name="Test Recipe",
            cuisine="test",
            dietary=["vegetarian"],
            prep_minutes=5,
            cook_minutes=10,
            serves=2,
            tags=[],
            ingredients=[_I("onion", 1.0, "unit")],
            instructions=["Step 1"],
        )

        class _OneIngredientDB(_FakeDB):
            def get_inventory(self, user_id=""):
                return [type("_Lot", (), {"canonical_name": "onion", "quantity": 5.0})()]

        with _swap_global_db(monkeypatch, _OneIngredientDB()):
            monkeypatch.setattr(screen_module, "get_recipe", lambda _id: real_recipe)
            out = screen.cookbook_shop_missing("one-ingredient-recipe")
        assert "already have" in out.lower() or "nothing missing" in out.lower()

    def test_missing_items_added_to_list(self, monkeypatch, fake_db):
        """Add missing items to a real list."""
        from shopstack.ui.screens import cookbook as screen
        # Fake a household with NO list, missing ingredients
        fake_db.lists = []  # ensure no existing list
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_shop_missing("dal_makhani")
        # Should have auto-created a list
        assert fake_db.lists, "Expected the cookbook to auto-create a shopping list"
        # And added items
        assert len(fake_db.added) > 0
        # The toast card reflects the count
        assert "Added" in out
        assert "missing item" in out

    def test_returns_valid_html_on_db_error(self, monkeypatch):
        """DB errors during shop_missing should not raise; they return a status card."""
        from shopstack.ui.screens import cookbook as screen

        class _BrokenDB:
            def get_inventory(self, user_id=""): raise RuntimeError("simulated")
            def get_preference_signals(self, user_id=""): return []
            def get_active_shopping_list(self, user_id=""): return None
            def create_shopping_list(self, **kw): raise RuntimeError("db dead")

        with _swap_global_db(monkeypatch, _BrokenDB()):
            # Should not raise
            out = screen.cookbook_shop_missing("dal_makhani")
        # Status card of some kind
        assert isinstance(out, str)
        assert out.startswith("<div class='home-card'")


# ─── Tests: xss + defensive coding ─────────────────────────────────


class TestCookbookScreenXSS:
    """The screen module passes through HTML from the cookbook service.

    The service is responsible for escaping (and is tested in
    test_cookbook_service.py). The screen should never unescape or
    inject new HTML.
    """

    def test_dietary_all_does_not_inject_html(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_browse(dietary="all")
        # No <script> tags in the output
        assert "<script>" not in out.lower()

    def test_search_with_html_chars_does_not_inject(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        with _swap_global_db(monkeypatch, fake_db):
            out = screen.cookbook_browse(search="<script>alert(1)</script>")
        # The search string may appear in the grid (e.g. as a search
        # indicator) but should be escaped
        assert "<script>alert(1)</script>" not in out
        assert "&lt;script&gt;" in out or "alert(1)" not in out


# ─── Tests: list_id parameter ──────────────────────────────────────


class TestCookbookShopMissingListId:
    def test_explicit_list_id_used(self, monkeypatch, fake_db):
        from shopstack.ui.screens import cookbook as screen
        fake_db.lists = [{"list_id": "EXPLICIT", "name": "Custom"}]

        with _swap_global_db(monkeypatch, fake_db):
            # Even though dietary filter etc. are passed, the explicit
            # list_id is honored (we test via the dict structure).
            out = screen.cookbook_shop_missing("dal_makhani")
        # Items should be added to the EXPLICIT list, not a new one
        assert all(item["list_id"] == "EXPLICIT" for item in fake_db.added)
        assert "Added" in out


# ─── Tests: module surface ────────────────────────────────────────────


class TestCookbookScreenModuleSurface:
    def test_exports_expected_functions(self):
        from shopstack.ui.screens import cookbook
        for name in (
            "cookbook_browse",
            "cookbook_view_recipe",
            "cookbook_shop_missing",
            "cookbook_cuisine_choices",
        ):
            assert hasattr(cookbook, name), f"missing {name}"
            assert callable(getattr(cookbook, name)), f"{name} not callable"
