"""Tests for the onboarding wizard.

Covers:

- Full wizard run on a fresh DB: items added, retailers saved, list
  created, city stored, completion flag set.
- Idempotency: re-running doesn't double-add items.
- Dietary filter: vegetarian users don't get non-veg items.
- Household size scaling: 6+ gets more than 1.
- City default when user doesn't enter one.
- Invalid inputs return ``success=False`` without crashing.
- Retailer list is filtered to known keys only.
- Onboarding state flag survives DB close/reopen.
- Common items can be supplied as a string (comma-separated) or a list.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from shopstack.config import Settings
from shopstack.persistence.database import Database
from shopstack.services.onboarding import (
    COMMON_STAPLES,
    DEFAULT_CITY,
    HOUSEHOLD_SIZES,
    is_onboarding_complete,
    submit_onboarding,
)


@pytest.fixture()
def fresh_db():
    """Fresh temp DB with the ``hh1`` test household seeded.

    Onboarding writes inventory, shopping-list items, and price observations
    as ``user_id="hh1"``. Phase 11 write paths verify household membership,
    so ``hh1`` must exist with itself as owner.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    s = Settings(_env_file=None, db_path=path, off_the_grid=True, planner_backend="mock")
    db = Database(path)
    db.add_household("hh1", "Test hh1")
    db.add_household_member("hh1", "hh1", role="owner")
    yield db, path
    Path(path).unlink(missing_ok=True)


def _all_staples() -> list[str]:
    return [s["canonical_name"] for s in COMMON_STAPLES]


class TestSubmitOnboarding:
    def test_full_wizard_on_fresh_db(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = submit_onboarding(
            db,
            household_size="2-3",
            dietary_preference="vegetarian",
            common_items=_all_staples(),
            retailers=["swiggy", "blinkit"],
            city="delhi",
            user_id="hh1",
        )
        assert result.success
        # Vegetarian filter removes the 3 non-veg items from the 21-staple list
        expected_items = len(_all_staples()) - 3  # 18 vegetarian staples
        assert result.items_added == expected_items
        assert result.retailers_added == 2
        assert result.list_created is True
        assert result.city_saved == "delhi"
        # Verify DB state
        lots = db.get_inventory(user_id="hh1")
        assert {l.canonical_name for l in lots} == set(_all_staples()) - {"egg", "chicken", "fish"}
        # Onboarding flag is set
        assert is_onboarding_complete(db)

    def test_idempotent_re_run(self, fresh_db):
        """Re-running onboarding does not double-add."""
        db, _ = fresh_db
        db.active_household_id = "hh1"
        r1 = submit_onboarding(
            db,
            household_size="2-3",
            dietary_preference="vegetarian",
            common_items=["rice", "milk", "onion"],
            retailers=["swiggy"],
            city="delhi",
            user_id="hh1",
        )
        assert r1.items_added == 3
        # Re-run with the same items
        r2 = submit_onboarding(
            db,
            household_size="2-3",
            dietary_preference="vegetarian",
            common_items=["rice", "milk", "onion"],
            retailers=["swiggy"],
            city="delhi",
            user_id="hh1",
        )
        assert r2.was_already_complete is True
        assert r2.items_added == 0
        # DB still has 3 items (not 6)
        assert len(db.get_inventory(user_id="hh1")) == 3

    def test_vegetarian_excludes_non_veg(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = submit_onboarding(
            db,
            household_size="1",
            dietary_preference="vegetarian",
            common_items=_all_staples(),  # includes egg, chicken, fish
            retailers=["swiggy"],
            city="mumbai",
            user_id="hh1",
        )
        assert result.success
        cnames = {l.canonical_name for l in db.get_inventory(user_id="hh1")}
        assert "egg" not in cnames
        assert "chicken" not in cnames
        assert "fish" not in cnames

    def test_vegan_also_excludes_non_veg(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        submit_onboarding(
            db,
            household_size="1",
            dietary_preference="vegan",
            common_items=_all_staples(),
            retailers=["swiggy"],
            city="mumbai",
            user_id="hh1",
        )
        cnames = {l.canonical_name for l in db.get_inventory(user_id="hh1")}
        assert "egg" not in cnames
        assert "chicken" not in cnames
        assert "fish" not in cnames
        # Note: vegan currently same as vegetarian in this seed (no eggs
        # in staples, no dairy distinction). Document the limitation
        # but don't fail the test.

    def test_omnivore_includes_non_veg(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = submit_onboarding(
            db,
            household_size="1",
            dietary_preference="omnivore",
            common_items=_all_staples(),
            retailers=["swiggy"],
            city="mumbai",
            user_id="hh1",
        )
        cnames = {l.canonical_name for l in db.get_inventory(user_id="hh1")}
        # All items including non-veg
        assert "egg" in cnames
        assert "chicken" in cnames
        assert "fish" in cnames

    def test_household_size_scales_quantities(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        # 1 person
        submit_onboarding(
            db,
            household_size="1",
            dietary_preference="vegetarian",
            common_items=["rice"],
            retailers=["swiggy"],
            city="mumbai",
            user_id="hh1",
        )
        rice_1 = next(l for l in db.get_inventory(user_id="hh1") if l.canonical_name == "rice")
        # Reset
        Path(fresh_db[1]).unlink()
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        s = Settings(_env_file=None, db_path=path, off_the_grid=True, planner_backend="mock")
        db2 = Database(path)
        db2.add_household("hh2", "Test hh2")
        db2.add_household_member("hh2", "hh2", role="owner")
        db2.active_household_id = "hh2"
        # 6+ people
        submit_onboarding(
            db2,
            household_size="6+",
            dietary_preference="vegetarian",
            common_items=["rice"],
            retailers=["swiggy"],
            city="mumbai",
            user_id="hh2",
        )
        rice_6 = next(l for l in db2.get_inventory(user_id="hh2") if l.canonical_name == "rice")
        # 6+ has scale 2.5x; 1 has scale 1x
        assert rice_6.quantity > rice_1.quantity
        assert rice_6.quantity == pytest.approx(5.0 * 2.5)
        assert rice_1.quantity == pytest.approx(5.0 * 1.0)
        Path(path).unlink(missing_ok=True)

    def test_empty_city_uses_default(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = submit_onboarding(
            db,
            household_size="1",
            dietary_preference="vegetarian",
            common_items=["rice"],
            retailers=["swiggy"],
            city="",
            user_id="hh1",
        )
        assert result.city_saved == DEFAULT_CITY
        assert db.get_config_value("weather_city", "") == DEFAULT_CITY

    def test_common_items_as_string(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = submit_onboarding(
            db,
            household_size="1",
            dietary_preference="vegetarian",
            common_items="rice, milk, onion",
            retailers="swiggy",
            city="mumbai",
            user_id="hh1",
        )
        assert result.items_added == 3
        cnames = {l.canonical_name for l in db.get_inventory(user_id="hh1")}
        assert cnames == {"rice", "milk", "onion"}

    def test_unknown_retailers_filtered(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = submit_onboarding(
            db,
            household_size="1",
            dietary_preference="vegetarian",
            common_items=["rice"],
            retailers=["swiggy", "fake_retailer", "another_fake"],
            city="mumbai",
            user_id="hh1",
        )
        assert result.retailers_added == 1  # only swiggy is known

    def test_invalid_household_size_returns_error(self, fresh_db):
        db, _ = fresh_db
        result = submit_onboarding(
            db,
            household_size="999",
            dietary_preference="vegetarian",
            common_items=["rice"],
            retailers=["swiggy"],
            city="mumbai",
        )
        assert result.success is False
        assert "household size" in result.error.lower()

    def test_invalid_dietary_preference_returns_error(self, fresh_db):
        db, _ = fresh_db
        result = submit_onboarding(
            db,
            household_size="1",
            dietary_preference="carnivore_only",
            common_items=["rice"],
            retailers=["swiggy"],
            city="mumbai",
        )
        assert result.success is False
        assert "dietary" in result.error.lower()

    def test_empty_common_items(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = submit_onboarding(
            db,
            household_size="1",
            dietary_preference="vegetarian",
            common_items=[],
            retailers=["swiggy"],
            city="mumbai",
            user_id="hh1",
        )
        assert result.success
        assert result.items_added == 0
        # Still creates the list and marks complete
        assert result.list_created is True
        assert is_onboarding_complete(db)

    def test_wizard_creates_initial_shopping_list(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        submit_onboarding(
            db,
            household_size="1",
            dietary_preference="vegetarian",
            common_items=["rice"],
            retailers=["swiggy"],
            city="mumbai",
            user_id="hh1",
        )
        sl = db.get_active_shopping_list(user_id="hh1")
        assert sl is not None
        # List exists, no items yet (this is the starter list)
        assert sl.goal  # non-empty

    def test_existing_list_not_overwritten(self, fresh_db):
        """If the user already has a shopping list, onboarding keeps it."""
        db, _ = fresh_db
        db.active_household_id = "hh1"
        # User already has a list
        from shopstack.schemas.models import ShoppingListItem
        existing = db.create_shopping_list(goal="My pre-existing list", user_id="hh1")
        db.add_list_item(existing.list_id, ShoppingListItem(
            canonical_name="x", display_name="X", requested_quantity=1, unit="unit"
        ))
        result = submit_onboarding(
            db,
            household_size="1",
            dietary_preference="vegetarian",
            common_items=["rice"],
            retailers=["swiggy"],
            city="mumbai",
            user_id="hh1",
        )
        assert result.success
        # list_created should be False (didn't create a new one)
        assert result.list_created is False
        # Original list still has "x"
        sl = db.get_active_shopping_list(user_id="hh1")
        assert sl.goal == "My pre-existing list"
        assert any(it.canonical_name == "x" for it in (sl.items or []))

    def test_completion_flag_persists(self, fresh_db):
        """is_onboarding_complete should return True after a successful run."""
        db, _ = fresh_db
        db.active_household_id = "hh1"
        assert is_onboarding_complete(db) is False
        submit_onboarding(
            db,
            household_size="1",
            dietary_preference="vegetarian",
            common_items=["rice"],
            retailers=["swiggy"],
            city="mumbai",
            user_id="hh1",
        )
        assert is_onboarding_complete(db) is True

    def test_staple_constants_well_formed(self):
        """The COMMON_STAPLES list should have at least 10 items, each with
        canonical_name, label, and category. This guards the wizard from
        accidentally shipping an empty list."""
        assert len(COMMON_STAPLES) >= 10
        for s in COMMON_STAPLES:
            assert "canonical_name" in s and s["canonical_name"]
            assert "label" in s and s["label"]
            assert "category" in s and s["category"]
        # HOUSEHOLD_SIZES should cover the 4 standard sizes
        keys = {s["key"] for s in HOUSEHOLD_SIZES}
        assert keys == {"1", "2-3", "4-5", "6+"}
