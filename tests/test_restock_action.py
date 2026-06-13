"""Tests for the restock action service.

The service adds a ``predict_restock_needs()`` prediction to the active
shopping list. Tests cover:

- Adding to an existing list (no goal change).
- Creating a list when none exists.
- Invalid input (missing canonical_name) returns ``added=False`` without
  raising.
- Priority mapping from urgency (overdue → must_buy, due_today → must_buy,
  due_soon → optional).
- Reason text gets the "from restock prediction" suffix.
- Scoping: the added item is tied to the active household.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from shopstack.config import Settings
from shopstack.persistence.database import Database
from shopstack.services.restock_action import add_prediction_to_list


@pytest.fixture()
def fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    import os
    os.close(fd)
    s = Settings(_env_file=None, db_path=path, off_the_grid=True, planner_backend="mock")
    db = Database(path)
    yield db, path
    Path(path).unlink(missing_ok=True)


def _prediction(cname: str = "milk", **overrides) -> dict:
    base = {
        "canonical_name": cname,
        "reason": "Usually bought every 3 days — due in 1 day",
        "urgency": "due_today",
        "days_until_restock": 1,
        "avg_interval_days": 3,
        "days_since_last": 2,
        "typical_qty": 1.0,
        "typical_unit": "L",
        "quantity_at_home": 0.2,
    }
    base.update(overrides)
    return base


class TestAddPredictionToList:
    def test_creates_list_when_none_exists(self, fresh_db):
        db, _ = fresh_db
        db.set_config_value("active_household_id", "hh1")
        result = add_prediction_to_list(db, _prediction("milk"))
        assert result["added"] is True
        assert result["list_id"]
        # Verify the list was created with the item
        items = db.get_list_items(result["list_id"], user_id="hh1")
        assert any(it.canonical_name == "milk" for it in items)

    def test_appends_to_existing_list(self, fresh_db):
        db, _ = fresh_db
        db.set_config_value("active_household_id", "hh1")
        # First prediction → creates the list
        add_prediction_to_list(db, _prediction("milk"))
        # Second prediction → appends to the same list
        result = add_prediction_to_list(db, _prediction("bread"))
        items = db.get_list_items(result["list_id"], user_id="hh1")
        names = {it.canonical_name for it in items}
        assert "milk" in names
        assert "bread" in names

    def test_invalid_canonical_name_returns_false(self, fresh_db):
        db, _ = fresh_db
        db.set_config_value("active_household_id", "hh1")
        result = add_prediction_to_list(db, {"canonical_name": ""})
        assert result["added"] is False
        assert "missing canonical_name" in result["reason"]

    def test_overdue_urgency_maps_to_must_buy(self, fresh_db):
        db, _ = fresh_db
        db.set_config_value("active_household_id", "hh1")
        result = add_prediction_to_list(db, _prediction("tomato", urgency="overdue"))
        assert result["item"]["priority"] == "must_buy"

    def test_due_today_urgency_maps_to_must_buy(self, fresh_db):
        db, _ = fresh_db
        db.set_config_value("active_household_id", "hh1")
        result = add_prediction_to_list(db, _prediction("milk", urgency="due_today"))
        assert result["item"]["priority"] == "must_buy"

    def test_due_soon_urgency_maps_to_optional(self, fresh_db):
        db, _ = fresh_db
        db.set_config_value("active_household_id", "hh1")
        result = add_prediction_to_list(db, _prediction("rice", urgency="due_soon"))
        assert result["item"]["priority"] == "optional"

    def test_unknown_urgency_defaults_to_optional(self, fresh_db):
        db, _ = fresh_db
        db.set_config_value("active_household_id", "hh1")
        result = add_prediction_to_list(db, _prediction("oil", urgency="some_future_state"))
        assert result["item"]["priority"] == "optional"

    def test_quantity_and_unit_propagate(self, fresh_db):
        db, _ = fresh_db
        db.set_config_value("active_household_id", "hh1")
        result = add_prediction_to_list(
            db,
            _prediction("rice", typical_qty=5.0, typical_unit="kg"),
        )
        assert result["item"]["requested_quantity"] == 5.0
        assert result["item"]["unit"] == "kg"

    def test_default_quantity_is_one(self, fresh_db):
        db, _ = fresh_db
        db.set_config_value("active_household_id", "hh1")
        result = add_prediction_to_list(
            db,
            _prediction("salt", typical_qty=None, typical_unit=None),
        )
        assert result["item"]["requested_quantity"] == 1.0
        assert result["item"]["unit"] == "unit"

    def test_reason_gets_prediction_suffix(self, fresh_db):
        db, _ = fresh_db
        db.set_config_value("active_household_id", "hh1")
        result = add_prediction_to_list(
            db,
            _prediction("onion", reason="Custom reason from somewhere"),
        )
        assert "Custom reason from somewhere" in result["item"]["reason"]
        assert "from restock prediction" in result["item"]["reason"]

    def test_household_scoping(self, fresh_db):
        db, _ = fresh_db
        db.set_config_value("active_household_id", "hh1")
        result1 = add_prediction_to_list(db, _prediction("milk"))
        # Switch household and add a different item
        db.set_config_value("active_household_id", "hh2")
        result2 = add_prediction_to_list(db, _prediction("bread"))
        # hh1 should still see only milk
        items1 = db.get_list_items(result1["list_id"], user_id="hh1")
        names1 = {it.canonical_name for it in items1}
        assert names1 == {"milk"}
        # hh2 should see only bread
        items2 = db.get_list_items(result2["list_id"], user_id="hh2")
        names2 = {it.canonical_name for it in items2}
        assert names2 == {"bread"}
