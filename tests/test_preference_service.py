from __future__ import annotations

import pytest
from datetime import datetime

from shopstack.schemas.models import PreferenceSignal, ReconciliationEvent
from shopstack.services.preference import PreferenceService


@pytest.fixture
def pref_service(db):
    return PreferenceService(db)


def test_record_signal(pref_service):
    signal = pref_service.record_signal(
        canonical_name="coriander",
        signal_type="staple",
        value="true",
        source="explicit",
        confidence=0.9,
    )
    assert signal.canonical_name == "coriander"
    assert signal.signal_type == "staple"
    assert signal.value == "true"
    assert signal.confidence == 0.9

    loaded = pref_service.get_preferences(canonical_name="coriander")
    assert len(loaded) == 1
    assert loaded[0].canonical_name == "coriander"


def test_get_staples_disliked_avoided(pref_service):
    pref_service.record_signal("milk", "staple", "true")
    pref_service.record_signal("broccoli", "disliked", "avoid")
    pref_service.record_signal("coriander", "often_wasted", "true")

    assert "milk" in pref_service.get_staples()
    assert "broccoli" in pref_service.get_disliked()
    assert "broccoli" in pref_service.get_avoided()
    assert "coriander" in pref_service.get_avoided()
    assert pref_service.is_staple("milk")
    assert not pref_service.is_staple("broccoli")


def test_learn_from_reconciliation(pref_service, db):
    # Prepare some mock reconciliation history in DB to trigger learn threshold of 3
    for _ in range(3):
        db.add_reconciliation_event(
            ReconciliationEvent(
                canonical_name="onion",
                planned_action="buy",
                actual_action="bought",
                quantity=1.0,
                unit="kg",
            )
        )
        db.add_reconciliation_event(
            ReconciliationEvent(
                canonical_name="brinjal",
                planned_action="buy",
                actual_action="skipped",
                quantity=1.0,
                unit="kg",
            )
        )

    events = [
        ReconciliationEvent(
            canonical_name="onion",
            planned_action="buy",
            actual_action="bought",
            quantity=1.0,
            unit="kg",
        ),
        ReconciliationEvent(
            canonical_name="brinjal",
            planned_action="buy",
            actual_action="skipped",
            quantity=1.0,
            unit="kg",
        ),
        ReconciliationEvent(
            canonical_name="tomato",
            planned_action="buy",
            actual_action="substituted",
            substituted_with="cherry_tomato",
            quantity=1.0,
            unit="kg",
        ),
    ]

    added = pref_service.learn_from_reconciliation(events)
    assert added == 3

    assert "onion" in pref_service.get_staples()
    assert "brinjal" in pref_service.get_disliked()
    
    prefs = pref_service.get_preferences(canonical_name="tomato")
    assert any(p.signal_type == "brand_preferred" and p.value == "cherry_tomato" for p in prefs)


def test_legacy_compatibility(pref_service):
    # Test record_correction
    signal = pref_service.record_correction(
        {
            "canonical_name": "coriander",
            "correction_type": "avoid",
            "new_value": "dislike",
        }
    )
    assert signal is not None
    assert signal.signal_type == "disliked"
    assert signal.value == "avoid"

    assert "coriander" in pref_service.get_avoid_list()
