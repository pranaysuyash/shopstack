"""Regression tests for the Recent corrections panel (2026-06-15).

Closes the invisible learning loop surfaced in the 2026-06-15
full-app audit: the system had ``build_correction_event`` and
``PreferenceService.record_correction`` but no user-facing surface
where the user could see what the system had learned, accept it,
or reject it.

These tests pin the new contract:

* ``correction_events`` table exists with the expected columns
* ``db.record_correction_event`` persists a ``CorrectionEvent`` model
* ``db.get_recent_correction_events`` returns events newest first
* ``db.mark_correction_accepted`` toggles the ``accepted`` flag
* ``PreferenceService.record_correction`` writes to the new table
  in addition to producing the preference signal (additive)
* ``render_recent_corrections_html`` renders a card per event and
  returns an actionable empty state when no events exist

Evidence tier: T1 (static inspection) + T2 (this test passes).
"""
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import pytest


# ── Helpers ────────────────────────────────────────────────────────────


@pytest.fixture
def temp_db(monkeypatch):
    """Create a fresh, isolated SQLite database for the test.

    Re-uses the same ``Database`` class the app uses, but with a
    temp file path so each test starts clean. The Database class
    auto-creates the schema on ``__init__`` (which now includes
    the new ``correction_events`` table).
    """
    from shopstack.persistence.database import Database

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(str(db_path))
        yield db
        # Best-effort cleanup; tmpdir cleanup handles the file.
        try:
            db.conn.close()
        except Exception:  # noqa: BLE001
            pass


# ── Tests ──────────────────────────────────────────────────────────────


def test_correction_events_table_exists(temp_db) -> None:
    """The new table must be created by Database.__init__."""
    rows = temp_db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='correction_events'"
    ).fetchall()
    assert rows, "correction_events table should be auto-created by Database.__init__"


def test_correction_events_table_has_expected_columns(temp_db) -> None:
    """Column set is pinned: event_id, timestamp, canonical_name,
    correction_type, old_value, new_value, source, accepted, user_id.
    """
    cols = [
        r[1] for r in temp_db.conn.execute("PRAGMA table_info(correction_events)").fetchall()
    ]
    expected = {
        "event_id", "timestamp", "canonical_name", "correction_type",
        "old_value", "new_value", "source", "accepted", "user_id",
    }
    assert expected.issubset(set(cols)), (
        f"correction_events missing columns: {expected - set(cols)}; "
        f"actual: {cols}"
    )


def test_record_and_retrieve_correction_event(temp_db) -> None:
    """Round-trip: record a CorrectionEvent and read it back."""
    from shopstack.schemas.models import CorrectionEvent

    event = CorrectionEvent(
        canonical_name="tomato",
        correction_type="alias",
        old_value="tamatar",
        new_value="hybrid tomato",
        source="reconciliation",
    )
    saved = temp_db.record_correction_event(event, user_id="")
    assert saved.event_id == event.event_id

    events = temp_db.get_recent_correction_events(user_id="")
    assert len(events) == 1
    assert events[0].canonical_name == "tomato"
    assert events[0].correction_type == "alias"
    assert events[0].old_value == "tamatar"
    assert events[0].new_value == "hybrid tomato"
    assert events[0].source == "reconciliation"


def test_recent_corrections_newest_first(temp_db) -> None:
    """Two events recorded in order: the second is returned first."""
    from shopstack.schemas.models import CorrectionEvent

    e1 = CorrectionEvent(canonical_name="onion", correction_type="alias",
                         old_value="pyaaz", new_value="sambar onion",
                         timestamp=datetime(2026, 6, 1, 10, 0, 0))
    e2 = CorrectionEvent(canonical_name="rice", correction_type="brand",
                         old_value="any", new_value="India Gate",
                         timestamp=datetime(2026, 6, 15, 10, 0, 0))
    temp_db.record_correction_event(e1, user_id="")
    temp_db.record_correction_event(e2, user_id="")

    events = temp_db.get_recent_correction_events(user_id="")
    assert [e.canonical_name for e in events] == ["rice", "onion"]


def test_mark_correction_accepted(temp_db) -> None:
    """Accept/reject toggles the ``accepted`` flag."""
    from shopstack.schemas.models import CorrectionEvent

    event = CorrectionEvent(canonical_name="oil", correction_type="brand",
                            old_value="any", new_value="Fortune")
    temp_db.record_correction_event(event, user_id="")

    # Default: accepted=0 (pending)
    assert temp_db.get_recent_correction_events(user_id="")[0].event_id == event.event_id

    temp_db.mark_correction_accepted(event.event_id, accepted=True)
    accepted = temp_db.get_recent_correction_events(
        limit=10, accepted_only=True, user_id="",
    )
    assert len(accepted) == 1
    assert accepted[0].event_id == event.event_id

    temp_db.mark_correction_accepted(event.event_id, accepted=False)
    accepted_only = temp_db.get_recent_correction_events(
        limit=10, accepted_only=True, user_id="",
    )
    pending = temp_db.get_recent_correction_events(
        limit=10, accepted_only=False, user_id="",
    )
    assert len(accepted_only) == 0
    assert len(pending) == 1


def test_user_scoping(temp_db) -> None:
    """The active user filter isolates the events correctly.

    We use distinct active households for each user_id by setting
    ``active_household_id`` between calls. This exercises the
    user-scoping path that the production app uses.
    """
    from shopstack.schemas.models import CorrectionEvent

    temp_db.set_config_value("active_household_id", "h1")
    temp_db.record_correction_event(
        CorrectionEvent(canonical_name="x", correction_type="alias",
                        old_value="a", new_value="b"),
        user_id="h1",
    )
    temp_db.set_config_value("active_household_id", "h2")
    temp_db.record_correction_event(
        CorrectionEvent(canonical_name="y", correction_type="alias",
                        old_value="c", new_value="d"),
        user_id="h2",
    )
    # Without setting the active household, user_id="" means
    # "use the active household" (h2), so we see only y.
    assert len(temp_db.get_recent_correction_events(user_id="")) == 1
    assert temp_db.get_recent_correction_events(user_id="")[0].canonical_name == "y"

    # Switch back to h1 and verify isolation.
    temp_db.set_config_value("active_household_id", "h1")
    assert len(temp_db.get_recent_correction_events(user_id="")) == 1
    assert temp_db.get_recent_correction_events(user_id="")[0].canonical_name == "x"


def test_preference_service_record_correction_writes_to_new_table(temp_db) -> None:
    """The additive change: ``PreferenceService.record_correction``
    persists the raw event to the new ``correction_events`` table
    in addition to producing the preference signal.
    """
    from shopstack.services.preference import PreferenceService

    service = PreferenceService(temp_db)
    result = service.record_correction(
        {
            "canonical_name": "TOMATO",
            "correction_type": "alias",
            "old_value": "tamatar",
            "new_value": "hybrid tomato",
            "source": "user_correction",
        },
        user_id="",  # empty = use active household
    )
    assert result is not None  # preference signal produced

    # And the raw correction event is also in the new table.
    events = temp_db.get_recent_correction_events(user_id="")
    assert len(events) == 1
    assert events[0].canonical_name == "tomato"  # lowercased
    assert events[0].correction_type == "alias"
    assert events[0].old_value == "tamatar"
    assert events[0].new_value == "hybrid tomato"


def test_render_recent_corrections_html_empty_state(monkeypatch) -> None:
    """The HTML renderer must return an actionable empty state when
    there are no events, not a passive 'nothing here' message.
    """
    # Provide a stub db that returns [] for get_recent_correction_events.
    class _StubDb:
        def get_recent_correction_events(self, limit=20, accepted_only=False, user_id=""):
            return []

    import shopstack.ui.screens.corrections as corr_mod
    monkeypatch.setattr(corr_mod, "db", _StubDb())
    monkeypatch.setattr(corr_mod, "current_user_id", lambda: "h1")

    html = corr_mod.render_recent_corrections_html()
    # Actionable empty state must include a verb like "Accept" or "reject"
    # (per the empty-state lint, see tests/test_empty_state_lint.py).
    assert "Accept" in html or "accept" in html
    assert "Reject" in html or "reject" in html


def test_render_recent_corrections_html_renders_rows(monkeypatch) -> None:
    """The HTML renderer must render one card per event with
    canonical_name, old → new, and an event id.
    """
    from shopstack.schemas.models import CorrectionEvent

    class _StubDb:
        def get_recent_correction_events(self, limit=20, accepted_only=False, user_id=""):
            return [
                CorrectionEvent(
                    canonical_name="tomato",
                    correction_type="alias",
                    old_value="tamatar",
                    new_value="hybrid tomato",
                    source="reconciliation",
                ),
                CorrectionEvent(
                    canonical_name="onion",
                    correction_type="alias",
                    old_value="pyaaz",
                    new_value="sambar onion",
                ),
            ]

    import shopstack.ui.screens.corrections as corr_mod
    monkeypatch.setattr(corr_mod, "db", _StubDb())
    monkeypatch.setattr(corr_mod, "current_user_id", lambda: "h1")

    html = corr_mod.render_recent_corrections_html()
    assert "tomato" in html
    assert "onion" in html
    assert "tamatar" in html
    assert "hybrid tomato" in html
    # Two cards. Count the row-div class with an exact match so the
    # per-row action classes (correction-row-actions, correction-row-accept,
    # and correction-row-reject) are not counted as cards.
    assert html.count("class='correction-row'") == 2


def test_memory_corrections_subtab_is_wired() -> None:
    """Static check: the memory tab must include the corrections sub-tab."""
    src = Path("shopstack/ui/tabs/memory.py").read_text()
    assert "build_memory_corrections" in src
    # And the import exists
    assert "from shopstack.ui.tabs.memory_data import" in src
    assert "build_memory_corrections" in src
