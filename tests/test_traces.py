from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from shopstack.app_context import db as app_db, tools as app_tools
from shopstack.traces.export import _redact_trace, create_trace, export_trace_by_id, export_traces_to_jsonl
from shopstack.ui.screens import (
    add_purchase_form,
    agent_trace_bootstrap,
    agent_trace_export_file,
    agent_trace_view,
    ask_shopstack,
    complete_shopping_list,
    confirm_reconciliation,
    market_lens_confirm_buy,
    market_lens_process,
    market_lens_save_trace,
    market_lens_skip,
)
from shopstack.ui.screens.shopping import shopping_list_create
from shopstack.ui.screens.traces import agent_trace_detail


class TestTraceRedaction:
    def test_redact_phone_number(self):
        trace_dict = {
            "user_goal": "Call me at 9876543210",
            "redacted_user_request": "Call me at 9876543210",
            "final_response": "Sure, I'll call 9876543210",
        }
        redacted = _redact_trace(trace_dict)
        assert "[REDACTED_NUMBER]" in redacted["user_goal"]
        assert "9876543210" not in redacted["user_goal"]

    def test_redact_email(self):
        trace_dict = {
            "user_goal": "Email test@example.com",
            "redacted_user_request": "Email test@example.com",
            "final_response": "ok",
        }
        redacted = _redact_trace(trace_dict)
        assert "[REDACTED_EMAIL]" in redacted["user_goal"]
        assert "test@example.com" not in redacted["user_goal"]

    def test_redact_tool_args(self):
        trace_dict = {
            "user_goal": "add item",
            "redacted_user_request": "add item",
            "final_response": "done",
            "proposed_tool_calls": [
                {"tool_name": "add_inventory", "args": {"name": "milk", "phone": "9876543210", "email": "test@test.com"}}
            ],
        }
        redacted = _redact_trace(trace_dict)
        call = redacted["proposed_tool_calls"][0]
        assert call["args"]["phone"] == "[REDACTED]"
        assert call["args"]["email"] == "[REDACTED]"
        assert call["args"]["name"] == "milk"

    def test_redact_nested_text_fields(self):
        trace_dict = {
            "user_goal": "Need details from receipt",
            "redacted_user_request": "Call me 9999999999 and email test@example.com",
            "final_response": "Receipt contains store: ABCMart",
            "perception": {
                "notes": ["send to user@test.com", "phone 1111111111"],
                "details": {"raw_text": "Aadhar 123412341234"},
            },
            "proposed_tool_calls": [
                {"tool_name": "add_inventory", "args": {"raw_text": "phone 1010101010", "store": "Big Basket", "meta": {"aadhar": "ABCDE1234F"}}}
            ],
        }
        redacted = _redact_trace(trace_dict)
        assert "[REDACTED_NUMBER]" in redacted["redacted_user_request"]
        assert "[REDACTED_EMAIL]" in redacted["redacted_user_request"]
        assert "[REDACTED_NUMBER]" in redacted["proposed_tool_calls"][0]["args"]["raw_text"]
        assert redacted["proposed_tool_calls"][0]["args"]["meta"]["aadhar"] == "[REDACTED]"

    def test_redact_aadhar(self):
        trace_dict = {
            "user_goal": "My aadhar is 123456789012",
            "redacted_user_request": "My aadhar is 123456789012",
            "final_response": "ok",
            "proposed_tool_calls": [],
        }
        redacted = _redact_trace(trace_dict)
        assert "[REDACTED_NUMBER]" in redacted["user_goal"]

    def test_redact_pan(self):
        trace_dict = {
            "proposed_tool_calls": [
                {"tool_name": "verify", "args": {"pan": "ABCDE1234F"}}
            ],
            "user_goal": "verify",
            "redacted_user_request": "verify",
            "final_response": "ok",
        }
        redacted = _redact_trace(trace_dict)
        assert redacted["proposed_tool_calls"][0]["args"]["pan"] == "[REDACTED]"


class TestCreateTrace:
    def test_create_basic(self, db):
        trace = create_trace(
            db,
            input_type="voice",
            user_goal="check milk stock",
            redacted_user_request="check milk stock",
            final_response="You have 2L of milk",
        )
        assert trace.trace_id
        assert trace.input_type == "voice"

    def test_create_with_perception(self, db):
        trace = create_trace(
            db,
            input_type="vision",
            user_goal="what's in the fridge",
            perception={"objects": ["milk", "eggs"]},
            decision={"action": "list_items"},
        )
        assert trace.perception["objects"] == ["milk", "eggs"]


class TestExportTraces:
    def test_export_empty(self, db):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = f.name
        try:
            count = export_traces_to_jsonl(db, path)
            assert count == 0
        finally:
            Path(path).unlink(missing_ok=True)

    def test_export_with_data(self, db):
        create_trace(db, input_type="text", user_goal="test", redacted_user_request="test", final_response="ok")
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = f.name
        try:
            count = export_traces_to_jsonl(db, path, redact=True)
            assert count == 1
            with open(path) as f:
                data = json.loads(f.readline())
            assert "user_goal" in data
            assert "_private" not in data
        finally:
            Path(path).unlink(missing_ok=True)

    def test_export_trace_by_id_redacts_and_reports_count(self, db):
        trace = create_trace(
            db,
            input_type="vision",
            user_goal="call 9876543210 for price",
            redacted_user_request="call 9876543210 for price",
            final_response="phone 9876543210 is noted",
        )
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = f.name
        try:
            count = export_trace_by_id(db, trace.trace_id, path, redact=True)
            assert count == 1
            with open(path) as handle:
                exported = json.loads(handle.readline())
            assert "[REDACTED_NUMBER]" in exported["user_goal"]
            assert "[REDACTED_NUMBER]" in exported["final_response"]
        finally:
            Path(path).unlink(missing_ok=True)

    def test_export_trace_by_id_empty_when_missing(self, db):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = f.name
        try:
            count = export_trace_by_id(db, "does-not-exist", path, redact=True)
            assert count == 0
            with open(path) as handle:
                assert handle.read() == ""
        finally:
            Path(path).unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════════
# User ID scoping tests
# ══════════════════════════════════════════════════════════════════════════

class TestTraceUserScoping:
    """Traces created with different user_ids should be properly scoped per household."""

    def test_create_trace_with_user_id(self, db):
        """create_trace with user_id should store it in the database."""
        trace = create_trace(
            db, input_type="text", user_goal="hh1 task",
            redacted_user_request="hh1 task", final_response="done",
            user_id="household_one",
        )
        # Verify the trace is stored and retrievable
        stored = db.get_trace_by_id(trace.trace_id)
        assert stored is not None
        assert stored.trace_id == trace.trace_id

    def test_get_traces_filters_by_user_id(self, db):
        """get_traces(user_id=...) should only return traces for that user."""
        # Create two traces for different households
        t1 = create_trace(
            db, input_type="text", user_goal="goal_a",
            redacted_user_request="req_a", final_response="resp_a",
            user_id="household_a",
        )
        t2 = create_trace(
            db, input_type="text", user_goal="goal_b",
            redacted_user_request="req_b", final_response="resp_b",
            user_id="household_b",
        )

        traces_a = db.get_traces(user_id="household_a")
        traces_b = db.get_traces(user_id="household_b")
        all_traces = db.get_traces()  # no filter

        ids_a = {t.trace_id for t in traces_a}
        ids_b = {t.trace_id for t in traces_b}
        ids_all = {t.trace_id for t in all_traces}

        assert t1.trace_id in ids_a
        assert t2.trace_id in ids_b
        assert t1.trace_id not in ids_b
        assert t2.trace_id not in ids_a
        assert t1.trace_id in ids_all
        assert t2.trace_id in ids_all

    def test_get_trace_by_id_respects_user_id(self, db):
        """get_trace_by_id(user_id=...) should only find traces belonging to that user."""
        trace = create_trace(
            db, input_type="text", user_goal="secret",
            redacted_user_request="secret", final_response="ok",
            user_id="household_x",
        )
        # Found with correct user_id
        assert db.get_trace_by_id(trace.trace_id, user_id="household_x") is not None
        # Not found with wrong user_id
        assert db.get_trace_by_id(trace.trace_id, user_id="household_y") is None
        # Found without user_id filter
        assert db.get_trace_by_id(trace.trace_id) is not None

    def test_trace_with_empty_user_id_is_unfiltered(self, db):
        """Traces with empty user_id should not appear in scoped queries."""
        create_trace(
            db, input_type="text", user_goal="unowned",
            redacted_user_request="unowned", final_response="done",
        )
        # Trace with no user_id should NOT appear in household-scoped queries
        traces = db.get_traces(user_id="some_household")
        assert len(traces) == 0

    def test_create_shopping_list_trace_scoping(self, db):
        """create_shopping_list_trace should forward user_id."""
        from shopstack.traces.export import create_shopping_list_trace
        create_shopping_list_trace(
            db, goal="weekly",
            items=[{"canonical_name": "milk", "quantity": 2}],
            user_id="household_a",
        )
        traces = db.get_traces(user_id="household_a")
        assert len(traces) >= 1
        assert any(t.user_goal == "weekly" for t in traces)

    def test_create_add_purchase_trace_scoping(self, db):
        """create_add_purchase_trace should forward user_id."""
        from shopstack.traces.export import create_add_purchase_trace
        create_add_purchase_trace(
            db, item_name="milk", quantity=2.0, unit="L",
            price=50.0, store="Walmart",
            user_id="household_b",
        )
        traces = db.get_traces(user_id="household_b")
        assert len(traces) >= 1
        assert any("add_purchase" in t.user_goal for t in traces)

    def test_create_market_lens_trace_scoping(self, db):
        """create_market_lens_trace should forward user_id."""
        from shopstack.traces.export import create_market_lens_trace
        create_market_lens_trace(
            db, items_detected=["tomato", "onion"],
            analysis_text="scanned vegetables",
            analysis_result="found 2 items",
            user_id="household_c",
        )
        traces = db.get_traces(user_id="household_c")
        assert len(traces) >= 1
        assert any(t.input_type == "market_lens" for t in traces)

    def test_multiple_households_isolated(self, db):
        """Multiple households' traces should not bleed into each other."""
        hh_ids = ["household_1", "household_2", "household_3"]
        for i, hh_id in enumerate(hh_ids):
            create_trace(
                db, input_type="text",
                user_goal=f"goal_{i}",
                redacted_user_request=f"req_{i}",
                final_response=f"resp_{i}",
                user_id=hh_id,
            )

        # Each household only sees its own traces
        for hh_id in hh_ids:
            traces = db.get_traces(user_id=hh_id)
            assert len(traces) == 1, f"Expected 1 trace for {hh_id}, got {len(traces)}"

        # Unfiltered query sees all
        all_traces = db.get_traces()
        assert len(all_traces) >= len(hh_ids)

    def test_hh_a_cannot_access_hh_b_trace_by_id(self, db):
        """Trace created by household_a should not be findable by household_b via get_trace_by_id."""
        trace = create_trace(
            db, input_type="text", user_goal="a_private",
            redacted_user_request="a_private", final_response="done",
            user_id="household_a",
        )
        # household_b cannot access it
        assert db.get_trace_by_id(trace.trace_id, user_id="household_b") is None
        # But household_a can
        assert db.get_trace_by_id(trace.trace_id, user_id="household_a") is not None


# ══════════════════════════════════════════════════════════════════════════
# Export functions with user_id filtering
# ══════════════════════════════════════════════════════════════════════════


class TestExportWithUserScoping:
    """export_traces_to_jsonl and export_trace_by_id should respect user_id filtering."""

    def test_export_traces_to_jsonl_filters_by_user_id(self, db):
        """Exporting with user_id should only export traces for that user."""
        create_trace(db, input_type="text", user_goal="hh_a_task",
                     redacted_user_request="req_a", final_response="ok",
                     user_id="household_a")
        create_trace(db, input_type="text", user_goal="hh_b_task",
                     redacted_user_request="req_b", final_response="ok",
                     user_id="household_b")

        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path_a = f.name
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path_b = f.name
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path_all = f.name
        try:
            # Export filtered by household_a
            count_a = export_traces_to_jsonl(db, path_a, user_id="household_a")
            assert count_a == 1
            with open(path_a) as f:
                data = json.loads(f.readline())
            assert data["user_goal"] == "hh_a_task"

            # Export filtered by household_b
            count_b = export_traces_to_jsonl(db, path_b, user_id="household_b")
            assert count_b == 1
            with open(path_b) as f:
                data = json.loads(f.readline())
            assert data["user_goal"] == "hh_b_task"

            # Export without filter sees both
            count_all = export_traces_to_jsonl(db, path_all)
            assert count_all == 2
        finally:
            Path(path_a).unlink(missing_ok=True)
            Path(path_b).unlink(missing_ok=True)
            Path(path_all).unlink(missing_ok=True)

    def test_export_traces_to_jsonl_with_user_id_isolates_households(self, db):
        """Traces from household_a should not appear in household_b's export."""
        create_trace(db, input_type="voice", user_goal="a_voice",
                     redacted_user_request="req_a", final_response="ok",
                     user_id="household_a")
        create_trace(db, input_type="voice", user_goal="b_voice",
                     redacted_user_request="req_b", final_response="ok",
                     user_id="household_b")

        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path_a = f.name
        try:
            count_a = export_traces_to_jsonl(db, path_a, user_id="household_a")
            assert count_a == 1
            with open(path_a) as f:
                line = f.readline()
                assert "a_voice" in line
                assert "b_voice" not in line
        finally:
            Path(path_a).unlink(missing_ok=True)

    def test_export_traces_to_jsonl_without_user_id_exports_all(self, db):
        """Exporting without user_id filter should export all traces."""
        create_trace(db, input_type="text", user_goal="goal_a",
                     redacted_user_request="req_a", final_response="ok",
                     user_id="household_x")
        create_trace(db, input_type="text", user_goal="goal_b",
                     redacted_user_request="req_b", final_response="ok",
                     user_id="household_y")
        create_trace(db, input_type="text", user_goal="goal_c",
                     redacted_user_request="req_c", final_response="ok",
                     user_id="household_z")

        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = f.name
        try:
            count = export_traces_to_jsonl(db, path)  # no user_id filter — default ""
            assert count == 3
            with open(path) as f:
                lines = f.readlines()
            assert len(lines) == 3
        finally:
            Path(path).unlink(missing_ok=True)

    def test_export_trace_by_id_respects_user_id(self, db):
        """export_trace_by_id with user_id should only find traces for that user."""
        trace = create_trace(db, input_type="vision", user_goal="secret",
                             redacted_user_request="secret", final_response="ok",
                             user_id="household_x")

        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path_ok = f.name
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path_blocked = f.name
        try:
            # Can export with correct user_id
            success = export_trace_by_id(db, trace.trace_id, path_ok, user_id="household_x")
            assert success is True
            with open(path_ok) as f:
                data = json.loads(f.readline())
            assert data["user_goal"] == "secret"

            # Cannot export with wrong user_id
            blocked = export_trace_by_id(db, trace.trace_id, path_blocked, user_id="household_y")
            assert blocked is False
            # File should be empty
            with open(path_blocked) as f:
                assert f.read() == ""
        finally:
            Path(path_ok).unlink(missing_ok=True)
            Path(path_blocked).unlink(missing_ok=True)

    def test_export_trace_by_id_without_user_id_finds_any(self, db):
        """export_trace_by_id without user_id should find any trace."""
        trace = create_trace(db, input_type="text", user_goal="anyone",
                             redacted_user_request="anyone", final_response="ok",
                             user_id="household_z")

        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = f.name
        try:
            success = export_trace_by_id(db, trace.trace_id, path)  # no user_id
            assert success is True
        finally:
            Path(path).unlink(missing_ok=True)

    def test_export_trace_by_id_missing_trace(self, db):
        """export_trace_by_id with a non-existent trace should return False."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path = f.name
        try:
            result = export_trace_by_id(db, "nonexistent", path, user_id="household_a")
            assert result is False
            with open(path) as f:
                assert f.read() == ""
        finally:
            Path(path).unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════════
# End-to-end trace scoping integration tests (through screen builders)
# ══════════════════════════════════════════════════════════════════════════


class TestEndToEndTraceScoping:
    """Integration tests: traces created through screen builders must respect household isolation.

    These tests exercise the full chain:
      screen builder → _user_id() / current_user_id() → create_trace(..., user_id=uid) → db.save_trace()

    The ``app`` fixture (from conftest.py) provides the full app module so screen builders
    have their ``db``, ``tools``, and ``current_user_id()`` correctly wired.

    The ``household_green`` / ``household_blue`` / ``household_red`` identifiers
    are used as both household ids and member ids. Phase 11 write paths call
    ``require_write(user_id, household_id, db)`` which verifies membership —
    so each test household must exist and have itself as an owner before any
    screen builder can persist a trace through it.
    """

    _TEST_HOUSEHOLDS = (
        "household_a", "household_b", "household_c",
        "household_x", "household_y", "household_z",
        "household_one",
        "household_green", "household_blue", "household_red",
        "household_audio_blue", "household_audio_red",
        "household_dual_a", "household_dual_b",
        "household_export_a", "household_export_b", "household_export_empty",
        "household_isolated",
        "household_market_blue", "household_market_green",
        "household_ml_a", "household_ml_b", "household_ml_c", "household_ml_d", "household_ml_e",
        "household_recon_a", "household_recon_b", "household_recon_c", "household_recon_d",
        "household_shopping_a", "household_shopping_b",
    )

    def setup_method(self, _method) -> None:
        for hid in self._TEST_HOUSEHOLDS:
            app_db.add_household(hid, hid.replace("_", " ").title())
            app_db.add_household_member(hid, hid, role="owner")

    def test_add_purchase_trace_scoped(self, app):
        """add_purchase_form creates a trace visible only to the active household."""
        app_db.active_household_id = "household_green"

        from datetime import date
        result = add_purchase_form(
            "Milk", 2.0, "L", 64.0, "Store A", "fridge",
            date.today().isoformat(), "Dairy",
        )
        assert "Added" in result

        # Trace is visible to household_green
        hh_traces = app_db.get_traces(user_id="household_green")
        assert len(hh_traces) == 1
        assert hh_traces[0].user_goal == "add_purchase"

        # Same trace is NOT visible to a different household
        other_traces = app_db.get_traces(user_id="household_blue")
        assert len(other_traces) == 0

        # Trace is findable by ID when scoped to the correct household
        trace = hh_traces[0]
        stored = app_db.get_trace_by_id(trace.trace_id, user_id="household_green")
        assert stored is not None

        # Trace is NOT findable by ID when scoped to a different household
        assert app_db.get_trace_by_id(trace.trace_id, user_id="household_blue") is None

    def test_shopping_list_trace_scoped(self, app):
        """shopping_list_create creates a trace visible only to the active household."""

        app_db.active_household_id = "household_blue"

        result = shopping_list_create(
            "Weekly groceries", '[{"canonical_name":"milk","requested_quantity":2}]',
        )
        assert "Created list" in result

        # Trace is visible to household_blue
        hh_traces = app_db.get_traces(user_id="household_blue")
        assert len(hh_traces) >= 1
        # The trace goal varies; the key assertion is that some trace exists
        # and the same trace is absent from the other household's view

        # Other household sees nothing
        other_traces = app_db.get_traces(user_id="household_red")
        assert len(other_traces) == 0

        # Every trace for household_blue is isolated from household_red
        for t in hh_traces:
            assert app_db.get_trace_by_id(t.trace_id, user_id="household_red") is None

    def test_ask_shopstack_trace_scoped(self, app):
        """ask_shopstack creates a trace visible only to the active household."""

        app_db.active_household_id = "household_red"

        # Seed some inventory so the heuristic path has data to find
        from shopstack.schemas.models import InventoryLot
        app_db.add_inventory_lot(
            InventoryLot(canonical_name="tomato", display_name="Tomato",
                         quantity=2.0, unit="kg"),
            user_id="household_red",
        )

        result = ask_shopstack("Do we have tomato?")
        assert isinstance(result, dict)

        # Trace exists for household_red
        hh_traces = app_db.get_traces(user_id="household_red")
        assert len(hh_traces) >= 1

        # No traces leak to a different household
        other = app_db.get_traces(user_id="household_green")
        assert len(other) == 0

        # Cross-tenant get_trace_by_id is blocked
        for t in hh_traces:
            assert app_db.get_trace_by_id(t.trace_id, user_id="household_green") is None

    def test_multiple_households_fully_isolated_via_screens(self, app):
        """Sequential screen operations across different households remain isolated."""

        from datetime import date

        # ── Household A: add purchase + shopping list ──────────────
        app_db.active_household_id = "household_a"
        add_purchase_form("Milk", 2.0, "L", 64.0, "Store A", "fridge",
                              date.today().isoformat(), "Dairy")
        shopping_list_create(
            "A's list", '[{"canonical_name":"eggs","requested_quantity":6}]',
        )

        # ── Household B: add purchase only ─────────────────────────
        app_db.active_household_id = "household_b"
        add_purchase_form("Bread", 1.0, "loaf", 40.0, "Bakery", "fridge_top",
                              date.today().isoformat(), "Bakery")

        # ── Household C: add purchase only ─────────────────────────
        app_db.active_household_id = "household_c"
        add_purchase_form("Salt", 1.0, "kg", 20.0, "Store C", "pantry",
                              date.today().isoformat(), "Spices")

        # Each household sees its own traces
        a_traces = app_db.get_traces(user_id="household_a")
        assert len(a_traces) >= 2  # add + shopping list

        b_traces = app_db.get_traces(user_id="household_b")
        assert len(b_traces) >= 1

        c_traces = app_db.get_traces(user_id="household_c")
        assert len(c_traces) >= 1

        # No cross-household bleed
        for t in a_traces:
            assert app_db.get_trace_by_id(t.trace_id, user_id="household_b") is None
            assert app_db.get_trace_by_id(t.trace_id, user_id="household_c") is None

        for t in b_traces:
            assert app_db.get_trace_by_id(t.trace_id, user_id="household_a") is None
            assert app_db.get_trace_by_id(t.trace_id, user_id="household_c") is None

        # Unfiltered query sees all traces across households
        all_traces = app_db.get_traces()
        assert len(all_traces) >= 4  # A(2) + B(1) + C(1) = 4

    def test_trace_view_scoped_per_household(self, app):
        """agent_trace_view filters traces based on the currently active household."""

        from datetime import date

        # Create traces for household_green
        app_db.active_household_id = "household_green"
        add_purchase_form("Rice", 2.0, "kg", 100.0, "Store", "pantry",
                              date.today().isoformat(), "Grains")

        # Create traces for household_blue
        app_db.active_household_id = "household_blue"
        add_purchase_form("Bread", 1.0, "loaf", 40.0, "Bakery", "fridge_top",
                              date.today().isoformat(), "Bakery")

        # View from household_green — should only see their own traces
        app_db.active_household_id = "household_green"
        green_view, _ = agent_trace_view()
        green_text = str(green_view)
        assert "rice" in green_text.lower() or "add_purchase" in green_text
        # Negative: household_green should NOT see household_blue's trace
        assert "bread" not in green_text.lower()

        # View from household_blue — should only see their own traces
        app_db.active_household_id = "household_blue"
        blue_view, _ = agent_trace_view()
        blue_text = str(blue_view)
        assert "bread" in blue_text.lower() or "add_purchase" in blue_text
        # Negative: household_blue should NOT see household_green's trace
        assert "rice" not in blue_text.lower()

    def test_trace_bootstrap_scoped_per_household(self, app):
        """agent_trace_bootstrap returns traces scoped to the active household."""

        from datetime import date

        # Create traces for two households
        app_db.active_household_id = "household_green"
        add_purchase_form("Milk", 2.0, "L", 64.0, "Store", "fridge",
                              date.today().isoformat(), "Dairy")

        app_db.active_household_id = "household_blue"
        add_purchase_form("Eggs", 12.0, "pieces", 60.0, "Store", "fridge_top",
                              date.today().isoformat(), "Dairy")

        # Bootstrap from household_green
        app_db.active_household_id = "household_green"
        green_boot = agent_trace_bootstrap()
        assert len(green_boot) == 4
        # household_green's trace should be the default
        assert green_boot[1]  # non-empty trace_id
        assert green_boot[3]  # non-empty raw JSON

        # Bootstrap from household_blue
        app_db.active_household_id = "household_blue"
        blue_boot = agent_trace_bootstrap()
        assert len(blue_boot) == 4
        assert blue_boot[1]  # non-empty trace_id
        assert blue_boot[3]  # non-empty raw JSON

        # The trace IDs should differ since they belong to different households
        assert green_boot[1] != blue_boot[1]

    def test_trace_detail_scoped_per_household(self, app):
        """agent_trace_detail should only show traces from the active household."""

        from datetime import date

        app_db.active_household_id = "household_green"
        add_purchase_form("Milk", 2.0, "L", 64.0, "Store", "fridge",
                              date.today().isoformat(), "Dairy")
        green_traces = app_db.get_traces(user_id="household_green")
        green_tid = green_traces[0].trace_id

        app_db.active_household_id = "household_blue"
        add_purchase_form("Eggs", 12.0, "pieces", 60.0, "Store", "fridge_top",
                              date.today().isoformat(), "Dairy")

        # household_green can see its own trace
        app_db.active_household_id = "household_green"
        detail = agent_trace_detail(green_tid)
        assert "not found" not in detail.lower()

        # household_blue cannot see household_green's trace
        app_db.active_household_id = "household_blue"
        blocked = agent_trace_detail(green_tid)
        assert "not found" in blocked.lower()
        # household_blue's own trace is still visible
        blue_traces = app_db.get_traces(user_id="household_blue")
        assert len(blue_traces) == 1

    def test_trace_export_scoped_per_household(self, app):
        """Trace export via agent_trace_export_file respects household scoping."""

        from datetime import date

        # Create traces for two households
        app_db.active_household_id = "household_green"
        add_purchase_form("Milk", 2.0, "L", 64.0, "Store", "fridge",
                              date.today().isoformat(), "Dairy")

        app_db.active_household_id = "household_blue"
        add_purchase_form("Eggs", 12.0, "pieces", 60.0, "Store", "fridge_top",
                              date.today().isoformat(), "Dairy")

        green_traces = app_db.get_traces(user_id="household_green")
        blue_traces = app_db.get_traces(user_id="household_blue")

        # household_green can export its own trace
        app_db.active_household_id = "household_green"
        exported = agent_trace_export_file(green_traces[0].trace_id)
        assert exported.endswith(".jsonl") or exported == ""

        # household_green CANNOT export household_blue's trace (lookup is scoped)
        blocked = agent_trace_export_file(blue_traces[0].trace_id)
        assert blocked == ""  # trace not found => empty string

        # household_blue CAN export its own trace
        app_db.active_household_id = "household_blue"
        blue_export = agent_trace_export_file(blue_traces[0].trace_id)
        assert blue_export.endswith(".jsonl")

    # ══════════════════════════════════════════════════════════════════
    # Market Lens trace scoping (uses mock providers — no real images)
    # ══════════════════════════════════════════════════════════════════

    def test_market_lens_image_trace_scoped(self, app):
        """market_lens_process with image creates a trace scoped to the active household."""

        app_db.active_household_id = "household_market_green"

        # market_lens_process with a fake image path uses mock providers
        result_html, detected_items, analysis, ml_trace_id, barcode_json = market_lens_process(
            "fake-market-image.jpg", None,
        )
        assert "Market Lens" in result_html
        assert ml_trace_id, "Expected a non-empty trace ID from market_lens_process"

        # Trace is visible to the owning household
        stored = app_db.get_trace_by_id(ml_trace_id, user_id="household_market_green")
        assert stored is not None
        assert stored.user_goal == "market_lens"
        assert stored.human_confirmation == "uncommitted"

        # Trace is NOT visible to a different household
        assert app_db.get_trace_by_id(ml_trace_id, user_id="household_market_blue") is None

        # Trace appears in household-scoped listing
        hh_traces = app_db.get_traces(user_id="household_market_green")
        assert any(t.trace_id == ml_trace_id for t in hh_traces)

        # Different household sees no traces
        other_traces = app_db.get_traces(user_id="household_market_blue")
        assert all(t.trace_id != ml_trace_id for t in other_traces)

    def test_market_lens_audio_trace_scoped(self, app):
        """market_lens_process with audio creates a trace scoped to the active household."""

        app_db.active_household_id = "household_audio_red"

        # Audio-only market lens uses mock STT + falls through to ask_shopstack
        result_html, detected_items, analysis, ml_trace_id, barcode_json = market_lens_process(
            None, "fake-audio-query.wav",
        )
        assert ml_trace_id, "Expected a non-empty trace ID from market_lens_process with audio"

        # Trace is visible to the owning household
        stored = app_db.get_trace_by_id(ml_trace_id, user_id="household_audio_red")
        assert stored is not None
        assert stored.input_type in ("audio", "text")  # may become "text" via ask_shopstack path

        # Trace is NOT visible to a different household
        assert app_db.get_trace_by_id(ml_trace_id, user_id="household_audio_blue") is None

    def test_market_lens_image_audio_dual_trace_scoped(self, app):
        """market_lens_process with both image+audio creates a single trace scoped to the household."""

        app_db.active_household_id = "household_dual_a"

        result_html, detected_items, analysis, ml_trace_id, barcode_json = market_lens_process(
            "fake-dual-image.jpg", "fake-dual-audio.wav",
        )
        assert ml_trace_id, "Expected a non-empty trace ID"

        # Single trace created
        stored = app_db.get_trace_by_id(ml_trace_id, user_id="household_dual_a")
        assert stored is not None

        # Different household cannot access it
        assert app_db.get_trace_by_id(ml_trace_id, user_id="household_dual_b") is None

    def test_market_lens_multiple_households_isolated(self, app):
        """market_lens_process traces from different households stay isolated."""


        # Household A does a market lens scan
        app_db.active_household_id = "household_ml_a"
        _, _, _, trace_a_id, _ = market_lens_process("scan-image-a.jpg", None)
        assert trace_a_id

        # Household B does a market lens scan
        app_db.active_household_id = "household_ml_b"
        _, _, _, trace_b_id, _ = market_lens_process("scan-image-b.jpg", None)
        assert trace_b_id

        # Household A's trace is only visible to household A
        assert app_db.get_trace_by_id(trace_a_id, user_id="household_ml_a") is not None
        assert app_db.get_trace_by_id(trace_a_id, user_id="household_ml_b") is None

        # Household B's trace is only visible to household B
        assert app_db.get_trace_by_id(trace_b_id, user_id="household_ml_b") is not None
        assert app_db.get_trace_by_id(trace_b_id, user_id="household_ml_a") is None

        # Each sees only their own in listings
        a_traces = app_db.get_traces(user_id="household_ml_a")
        b_traces = app_db.get_traces(user_id="household_ml_b")
        assert any(t.trace_id == trace_a_id for t in a_traces)
        assert any(t.trace_id == trace_b_id for t in b_traces)
        assert all(t.trace_id != trace_b_id for t in a_traces)
        assert all(t.trace_id != trace_a_id for t in b_traces)

    def test_market_lens_confirm_buy_updates_own_trace(self, app):
        """market_lens_confirm_buy updates the trace scoped to the active household."""

        app_db.active_household_id = "household_ml_c"

        _, _, analysis, ml_trace_id, _ = market_lens_process("scan-confirm.jpg", None)
        assert ml_trace_id

        # Confirm the buy — forwards user_id via current_user_id()
        result = market_lens_confirm_buy(analysis, ml_trace_id)
        assert "Added" in result or "No BUY items" in result

        # Trace is findable by household_ml_c (user_id preserved by fix)
        stored = app_db.get_trace_by_id(ml_trace_id, user_id="household_ml_c")
        assert stored is not None

    def test_market_lens_skip_updates_own_trace(self, app):
        """market_lens_skip updates the trace scoped to the active household."""

        app_db.active_household_id = "household_ml_d"

        _, _, analysis, ml_trace_id, _ = market_lens_process("scan-skip.jpg", None)
        assert ml_trace_id

        # Skip the trace — forwards user_id via current_user_id()
        result = market_lens_skip(analysis, ml_trace_id)
        assert "skip" in result.lower() or "Saved" in result

        # Trace is findable by household_ml_d (user_id preserved by fix)
        stored = app_db.get_trace_by_id(ml_trace_id, user_id="household_ml_d")
        assert stored is not None

    # ══════════════════════════════════════════════════════════════════
    # Shopping list completion trace scoping
    # ══════════════════════════════════════════════════════════════════

    def test_complete_shopping_list_trace_scoped(self, app):
        """complete_shopping_list creates a trace scoped to the active household."""

        app_db.active_household_id = "household_shopping_a"

        # Create a shopping list first
        result = shopping_list_create(
            "Weekly shop", '[{"canonical_name":"milk","requested_quantity":2}]',
        )
        assert "Created list" in result

        # Get the list ID
        sl = app_db.get_active_shopping_list()
        assert sl is not None, "No active shopping list"
        list_id = sl.list_id

        # Complete the shopping list
        completion = complete_shopping_list(list_id)
        assert "List completed" in completion or "completed" in completion.lower()

        # Trace should exist for household_shopping_a
        hh_traces = app_db.get_traces(user_id="household_shopping_a")
        assert len(hh_traces) >= 1
        assert any(
            t.user_goal == "complete_shopping_list"
            or t.user_goal == "Plan shopping list"
            for t in hh_traces
        )

        # Other household should not see these traces
        other_traces = app_db.get_traces(user_id="household_shopping_b")
        assert len(other_traces) == 0

        # Cross-tenant get_trace_by_id blocked
        for t in hh_traces:
            assert app_db.get_trace_by_id(t.trace_id, user_id="household_shopping_b") is None

    def test_complete_shopping_list_multi_household_isolated(self, app):
        """complete_shopping_list in different households produces isolated traces."""


        # Household X: create and complete a list
        app_db.active_household_id = "household_x"
        shopping_list_create(
            "X groceries", '[{"canonical_name":"rice","requested_quantity":1}]',
        )
        sl_x = app_db.get_active_shopping_list()
        assert sl_x is not None, "No active shopping list"
        list_x_id = sl_x.list_id
        complete_shopping_list(list_x_id)

        # Household Y: create and complete a different list
        app_db.active_household_id = "household_y"
        shopping_list_create(
            "Y items", '[{"canonical_name":"paneer","requested_quantity":1}]',
        )
        sl_y = app_db.get_active_shopping_list()
        assert sl_y is not None, "No active shopping list"
        list_y_id = sl_y.list_id
        complete_shopping_list(list_y_id)

        # Each household sees only its own complete_shopping_list traces
        x_traces = app_db.get_traces(user_id="household_x")
        y_traces = app_db.get_traces(user_id="household_y")

        assert len(x_traces) >= 1
        assert len(y_traces) >= 1

        # No traces leaked
        for t in x_traces:
            assert app_db.get_trace_by_id(t.trace_id, user_id="household_y") is None
        for t in y_traces:
            assert app_db.get_trace_by_id(t.trace_id, user_id="household_x") is None

    # ══════════════════════════════════════════════════════════════════
    # Reconcile shopping trip trace scoping
    # ══════════════════════════════════════════════════════════════════

    def test_reconcile_shopping_trip_trace_scoped(self, app):
        """reconcile_shopping_trip creates a trace scoped to the specified user_id."""


        from shopstack.services.reconciliation import reconcile_shopping_trip

        # Reconcile a trip for household_a
        result = reconcile_shopping_trip(
            planned_items=[{"canonical_name": "milk"}],
            actual_items=[{"canonical_name": "milk", "action": "bought", "price_paid": 64.0}],
            tools=app_tools,
            database=app_db,
            user_id="household_recon_a",
        )
        assert result.success

        # Trace should exist for household_recon_a
        hh_traces = app_db.get_traces(user_id="household_recon_a")
        assert len(hh_traces) >= 1
        assert any(t.user_goal == "post_shopping_reconciliation" for t in hh_traces)

        # Other household should not see these traces
        other_traces = app_db.get_traces(user_id="household_recon_b")
        assert len(other_traces) == 0

        # Cross-tenant get_trace_by_id blocked
        for t in hh_traces:
            assert app_db.get_trace_by_id(t.trace_id, user_id="household_recon_b") is None

    def test_reconcile_shopping_trip_multi_household_isolated(self, app):
        """reconcile_shopping_trip traces from different households stay isolated."""


        from shopstack.services.reconciliation import reconcile_shopping_trip

        # Household A reconciliation
        reconcile_shopping_trip(
            planned_items=[{"canonical_name": "milk"}, {"canonical_name": "bread"}],
            actual_items=[
                {"canonical_name": "milk", "action": "bought", "price_paid": 64.0},
                {"canonical_name": "bread", "action": "skipped"},
            ],
            tools=app_tools,
            database=app_db,
            user_id="household_recon_a",
        )

        # Household B reconciliation
        reconcile_shopping_trip(
            planned_items=[{"canonical_name": "eggs"}],
            actual_items=[{"canonical_name": "eggs", "action": "bought", "price_paid": 60.0}],
            tools=app_tools,
            database=app_db,
            user_id="household_recon_b",
        )

        # Each household sees only its own traces
        a_traces = app_db.get_traces(user_id="household_recon_a")
        b_traces = app_db.get_traces(user_id="household_recon_b")

        assert len(a_traces) >= 1
        assert len(b_traces) >= 1

        # No cross-tenant bleed
        for t in a_traces:
            assert app_db.get_trace_by_id(t.trace_id, user_id="household_recon_b") is None
        for t in b_traces:
            assert app_db.get_trace_by_id(t.trace_id, user_id="household_recon_a") is None

        # Unfiltered query sees all
        all_traces = app_db.get_traces()
        assert len(all_traces) >= 2

    def test_reconcile_shopping_trip_without_user_id_unscoped(self, app):
        """reconcile_shopping_trip without user_id creates an unscoped trace."""


        from shopstack.services.reconciliation import reconcile_shopping_trip

        # Reconcile without user_id (empty string default)
        result = reconcile_shopping_trip(
            planned_items=[{"canonical_name": "salt"}],
            actual_items=[{"canonical_name": "salt", "action": "bought"}],
            tools=app_tools,
            database=app_db,
        )
        assert result.success

        # Trace with empty user_id should NOT appear in scoped queries
        scoped_traces = app_db.get_traces(user_id="some_household")
        assert len(scoped_traces) == 0

    # ══════════════════════════════════════════════════════════════════
    # Reconciliation screen (confirm_reconciliation) scoping
    # ══════════════════════════════════════════════════════════════════

    def test_confirm_reconciliation_scoped_per_household(self, app):
        """confirm_reconciliation scopes events via user_id from current_user_id()."""

        app_db.active_household_id = "household_recon_c"

        # Create a shopping list to get a list_id
        result = shopping_list_create(
            "Recon test", '[{"canonical_name":"milk","requested_quantity":2}]',
        )
        assert "Created list" in result

        sl = app_db.get_active_shopping_list()
        assert sl is not None, "No active shopping list"
        list_id = sl.list_id

        # Call confirm_reconciliation with mock data
        recon_data = [
            ["milk", "2", "L", "bought", "64.0", ""],
        ]
        result = confirm_reconciliation(recon_data, list_id)
        assert "Reconciliation complete" in result

        # Reconciliation events should be scoped to the household
        events = app_db.get_reconciliation_events(user_id="household_recon_c")
        assert len(events) >= 1
        assert any(e.canonical_name == "milk" for e in events)

        # Other household should not see these events
        other_events = app_db.get_reconciliation_events(user_id="household_recon_d")
        assert all(e.canonical_name != "milk" for e in other_events)

    def test_confirm_reconciliation_multi_household_isolated(self, app):
        """confirm_reconciliation events from different households are isolated."""


        # Household C: list + reconciliation
        app_db.active_household_id = "household_recon_c"
        shopping_list_create(
            "C list", '[{"canonical_name":"milk","requested_quantity":2}]',
        )
        sl_c = app_db.get_active_shopping_list()
        assert sl_c is not None, "No active shopping list"
        list_c_id = sl_c.list_id
        confirm_reconciliation([["milk", "2", "L", "bought", "64.0", ""]], list_c_id)

        # Household D: list + reconciliation
        app_db.active_household_id = "household_recon_d"
        shopping_list_create(
            "D list", '[{"canonical_name":"eggs","requested_quantity":6}]',
        )
        sl_d = app_db.get_active_shopping_list()
        assert sl_d is not None, "No active shopping list"
        list_d_id = sl_d.list_id
        confirm_reconciliation([["eggs", "6", "pieces", "bought", "60.0", ""]], list_d_id)

        # Each household sees only its own events
        c_events = app_db.get_reconciliation_events(user_id="household_recon_c")
        d_events = app_db.get_reconciliation_events(user_id="household_recon_d")

        assert len(c_events) >= 1
        assert len(d_events) >= 1
        assert any(e.canonical_name == "milk" for e in c_events)
        assert any(e.canonical_name == "eggs" for e in d_events)
        assert all(e.canonical_name != "eggs" for e in c_events)
        assert all(e.canonical_name != "milk" for e in d_events)

    # ══════════════════════════════════════════════════════════════════
    # Bulk export trace scoping (via screen layer)
    # ══════════════════════════════════════════════════════════════════

    def test_export_all_to_jsonl_scoped_per_household(self, app):
        """``export_traces_to_jsonl`` respects household boundaries when
        called through the screen's ``TraceService``.

        Creates test data via screen builders (``add_purchase_form``),
        then verifies that the same export function used by the screen
        (``TraceService.export_all_to_jsonl`` → ``export_traces_to_jsonl``)
        properly filters by ``user_id``.
        """

        from datetime import date

        # Create traces for two households via screen ops
        app_db.active_household_id = "household_export_a"
        add_purchase_form(
            "Rice", 2.0, "kg", 100.0, "Store", "pantry",
            date.today().isoformat(), "Grains",
        )

        app_db.active_household_id = "household_export_b"
        add_purchase_form(
            "Bread", 1.0, "loaf", 40.0, "Bakery", "fridge_top",
            date.today().isoformat(), "Bakery",
        )

        # Same export function as TestExportWithUserScoping, called
        # through the same database the screen builders use.
        # (``TraceService`` is not used directly to avoid singleton
        # lifecycle issues in the session-scoped fixture.)

        # ── Scoped export: household_export_a ─────────────────────
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path_a = f.name
        try:
            count_a = export_traces_to_jsonl(app_db, path_a, user_id="household_export_a")
            assert count_a >= 1, f"Expected >=1 trace for household_export_a, got {count_a}"
            with open(path_a) as f:
                lines = f.readlines()
            assert len(lines) >= 1
        finally:
            Path(path_a).unlink(missing_ok=True)

        # ── Scoped export: household_export_b ─────────────────────
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path_b = f.name
        try:
            count_b = export_traces_to_jsonl(app_db, path_b, user_id="household_export_b")
            assert count_b >= 1, f"Expected >=1 trace for household_export_b, got {count_b}"
            with open(path_b) as f:
                lines = f.readlines()
            assert len(lines) >= 1
        finally:
            Path(path_b).unlink(missing_ok=True)

        # ── Unfiltered export sees more than either scoped ────────
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path_all = f.name
        try:
            count_all = export_traces_to_jsonl(app_db, path_all)  # no user_id filter
            assert count_all >= 2, f"Expected >=2 traces unfiltered, got {count_all}"
            with open(path_all) as f:
                lines = f.readlines()
            assert len(lines) >= 2
        finally:
            Path(path_all).unlink(missing_ok=True)

        # ── Empty household export is 0 ───────────────────────────
        with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
            path_empty = f.name
        try:
            count_empty = export_traces_to_jsonl(app_db, path_empty, user_id="household_export_empty")
            assert count_empty == 0, f"Expected 0 traces for empty household, got {count_empty}"
            with open(path_empty) as f:
                assert f.read() == ""
        finally:
            Path(path_empty).unlink(missing_ok=True)

    def test_market_lens_save_trace_preserves_household(self, app):
        """market_lens_save_trace preserves the trace scoped to the active household."""

        app_db.active_household_id = "household_ml_e"

        _, _, analysis, ml_trace_id, _ = market_lens_process("scan-save.jpg", None)
        assert ml_trace_id

        # Save the trace — forwards user_id via current_user_id()
        result = market_lens_save_trace(analysis, ml_trace_id)
        assert "Trace" in result or "saved" in result.lower()

        # Trace is findable by household_ml_e (user_id preserved by fix)
        stored = app_db.get_trace_by_id(ml_trace_id, user_id="household_ml_e")
        assert stored is not None

    # ══════════════════════════════════════════════════════════════════
