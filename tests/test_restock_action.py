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
    """Fresh temp DB with test households seeded.

    Tests in this module write as ``hh1`` (and ``hh2`` for scoping
    assertions). Phase 11 write paths verify household membership, so
    each test household must exist with itself as owner.
    """
    fd, path = tempfile.mkstemp(suffix=".db")
    import os
    os.close(fd)
    s = Settings(_env_file=None, db_path=path, off_the_grid=True, local_auto_download=False)
    db = Database(path)
    for hid in ("hh1", "hh2"):
        db.add_household(hid, f"Test {hid}")
        db.add_household_member(hid, hid, role="owner")
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
        db.active_household_id = "hh1"
        result = add_prediction_to_list(db, _prediction("milk"))
        assert result["added"] is True
        assert result["list_id"]
        sl = db.get_active_shopping_list(user_id="hh1")
        assert sl is not None
        assert any(it.canonical_name == "milk" for it in (sl.items or []))

    def test_appends_to_existing_list(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        add_prediction_to_list(db, _prediction("milk"))
        result = add_prediction_to_list(db, _prediction("bread"))
        sl = db.get_active_shopping_list(user_id="hh1")
        names = {it.canonical_name for it in (sl.items or [])}
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
        db.active_household_id = "hh1"
        result = add_prediction_to_list(db, _prediction("tomato", urgency="overdue"))
        assert result["item"]["priority"] == "must_buy"

    def test_due_today_urgency_maps_to_must_buy(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = add_prediction_to_list(db, _prediction("milk", urgency="due_today"))
        assert result["item"]["priority"] == "must_buy"

    def test_due_soon_urgency_maps_to_optional(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = add_prediction_to_list(db, _prediction("rice", urgency="due_soon"))
        assert result["item"]["priority"] == "optional"

    def test_unknown_urgency_defaults_to_optional(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = add_prediction_to_list(db, _prediction("oil", urgency="some_future_state"))
        assert result["item"]["priority"] == "optional"

    def test_quantity_and_unit_propagate(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = add_prediction_to_list(
            db,
            _prediction("rice", typical_qty=5.0, typical_unit="kg"),
        )
        assert result["item"]["requested_quantity"] == 5.0
        assert result["item"]["unit"] == "kg"

    def test_default_quantity_is_one(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = add_prediction_to_list(
            db,
            _prediction("salt", typical_qty=None, typical_unit=None),
        )
        assert result["item"]["requested_quantity"] == 1.0
        assert result["item"]["unit"] == "unit"

    def test_reason_gets_prediction_suffix(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result = add_prediction_to_list(
            db,
            _prediction("onion", reason="Custom reason from somewhere"),
        )
        assert "Custom reason from somewhere" in result["item"]["reason"]
        assert "from restock prediction" in result["item"]["reason"]

    def test_household_scoping(self, fresh_db):
        db, _ = fresh_db
        db.active_household_id = "hh1"
        result1 = add_prediction_to_list(db, _prediction("milk"))
        db.active_household_id = "hh2"
        result2 = add_prediction_to_list(db, _prediction("bread"))
        sl1 = db.get_active_shopping_list(user_id="hh1")
        names1 = {it.canonical_name for it in (sl1.items or [])}
        assert names1 == {"milk"}
        sl2 = db.get_active_shopping_list(user_id="hh2")
        names2 = {it.canonical_name for it in (sl2.items or [])}
        assert names2 == {"bread"}
