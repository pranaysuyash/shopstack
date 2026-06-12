from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from shopstack.traces.export import _redact_trace, create_trace, export_trace_by_id, export_traces_to_jsonl


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
# End-to-end trace scoping integration tests (through screen builders)
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="session")
def _e2e_app_session():
    """Import the full app module once per session with in-memory DB and mock planner."""
    os.environ["SHOPSTACK_DB_PATH"] = ":memory:"
    os.environ["SHOPSTACK_PLANNER_BACKEND"] = "mock"
    import app as _app
    return _app


@pytest.fixture
def e2e_app(_e2e_app_session):
    """Return the session-scoped app, clearing all data tables and household between tests."""
    app_mod = _e2e_app_session
    app_mod.db.active_household_id = ""
    conn = app_mod.db.conn
    for table in ["inventory_lots", "shopping_list_items", "shopping_lists",
                  "movement_events", "price_observations", "purchase_events",
                  "traces"]:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
    return app_mod


class TestEndToEndTraceScoping:
    """Integration tests: traces created through screen builders must respect household isolation.

    These tests exercise the full chain:
      screen builder → _user_id() / current_user_id() → create_trace(..., user_id=uid) → db.save_trace()

    The ``e2e_app`` fixture provides the full app module so screen builders
    have their ``db``, ``tools``, and ``current_user_id()`` correctly wired.
    """

    def test_add_purchase_trace_scoped(self, e2e_app):
        """add_purchase_form creates a trace visible only to the active household."""
        app = e2e_app
        app.db.active_household_id = "household_green"

        from datetime import date
        result = app.add_purchase_form(
            "Milk", 2.0, "L", 64.0, "Store A", "fridge",
            date.today().isoformat(), "Dairy",
        )
        assert "Added" in result

        # Trace is visible to household_green
        hh_traces = app.db.get_traces(user_id="household_green")
        assert len(hh_traces) == 1
        assert hh_traces[0].user_goal == "add_purchase"

        # Same trace is NOT visible to a different household
        other_traces = app.db.get_traces(user_id="household_blue")
        assert len(other_traces) == 0

        # Trace is findable by ID when scoped to the correct household
        trace = hh_traces[0]
        stored = app.db.get_trace_by_id(trace.trace_id, user_id="household_green")
        assert stored is not None

        # Trace is NOT findable by ID when scoped to a different household
        assert app.db.get_trace_by_id(trace.trace_id, user_id="household_blue") is None

    def test_shopping_list_trace_scoped(self, e2e_app):
        """shopping_list_create creates a trace visible only to the active household."""
        app = e2e_app
        app.db.active_household_id = "household_blue"

        result = app.shopping_list_create(
            "Weekly groceries", '[{"canonical_name":"milk","requested_quantity":2}]',
        )
        assert "Created list" in result

        # Trace is visible to household_blue
        hh_traces = app.db.get_traces(user_id="household_blue")
        assert len(hh_traces) >= 1
        # The trace goal varies; the key assertion is that some trace exists
        # and the same trace is absent from the other household's view

        # Other household sees nothing
        other_traces = app.db.get_traces(user_id="household_red")
        assert len(other_traces) == 0

        # Every trace for household_blue is isolated from household_red
        for t in hh_traces:
            assert app.db.get_trace_by_id(t.trace_id, user_id="household_red") is None

    def test_ask_shopstack_trace_scoped(self, e2e_app):
        """ask_shopstack creates a trace visible only to the active household."""
        app = e2e_app
        app.db.active_household_id = "household_red"

        # Seed some inventory so the heuristic path has data to find
        from shopstack.schemas.models import InventoryLot
        app.db.add_inventory_lot(
            InventoryLot(canonical_name="tomato", display_name="Tomato",
                         quantity=2.0, unit="kg"),
            user_id="household_red",
        )

        result = app.ask_shopstack("Do we have tomato?")
        assert isinstance(result, dict)

        # Trace exists for household_red
        hh_traces = app.db.get_traces(user_id="household_red")
        assert len(hh_traces) >= 1

        # No traces leak to a different household
        other = app.db.get_traces(user_id="household_green")
        assert len(other) == 0

        # Cross-tenant get_trace_by_id is blocked
        for t in hh_traces:
            assert app.db.get_trace_by_id(t.trace_id, user_id="household_green") is None

    def test_multiple_households_fully_isolated_via_screens(self, e2e_app):
        """Sequential screen operations across different households remain isolated."""
        app = e2e_app
        from datetime import date

        # ── Household A: add purchase + shopping list ──────────────
        app.db.active_household_id = "household_a"
        app.add_purchase_form("Milk", 2.0, "L", 64.0, "Store A", "fridge",
                              date.today().isoformat(), "Dairy")
        app.shopping_list_create(
            "A's list", '[{"canonical_name":"eggs","requested_quantity":6}]',
        )

        # ── Household B: add purchase only ─────────────────────────
        app.db.active_household_id = "household_b"
        app.add_purchase_form("Bread", 1.0, "loaf", 40.0, "Bakery", "fridge_top",
                              date.today().isoformat(), "Bakery")

        # ── Household C: add purchase only ─────────────────────────
        app.db.active_household_id = "household_c"
        app.add_purchase_form("Salt", 1.0, "kg", 20.0, "Store C", "pantry",
                              date.today().isoformat(), "Spices")

        # Each household sees its own traces
        a_traces = app.db.get_traces(user_id="household_a")
        assert len(a_traces) >= 2  # add + shopping list

        b_traces = app.db.get_traces(user_id="household_b")
        assert len(b_traces) >= 1

        c_traces = app.db.get_traces(user_id="household_c")
        assert len(c_traces) >= 1

        # No cross-household bleed
        for t in a_traces:
            assert app.db.get_trace_by_id(t.trace_id, user_id="household_b") is None
            assert app.db.get_trace_by_id(t.trace_id, user_id="household_c") is None

        for t in b_traces:
            assert app.db.get_trace_by_id(t.trace_id, user_id="household_a") is None
            assert app.db.get_trace_by_id(t.trace_id, user_id="household_c") is None

        # Unfiltered query sees all traces across households
        all_traces = app.db.get_traces()
        assert len(all_traces) >= 4  # A(2) + B(1) + C(1) = 4

    def test_trace_view_scoped_per_household(self, e2e_app):
        """agent_trace_view filters traces based on the currently active household."""
        app = e2e_app
        from datetime import date

        # Create traces for household_green
        app.db.active_household_id = "household_green"
        app.add_purchase_form("Rice", 2.0, "kg", 100.0, "Store", "pantry",
                              date.today().isoformat(), "Grains")

        # Create traces for household_blue
        app.db.active_household_id = "household_blue"
        app.add_purchase_form("Bread", 1.0, "loaf", 40.0, "Bakery", "fridge_top",
                              date.today().isoformat(), "Bakery")

        # View from household_green — should only see their own traces
        app.db.active_household_id = "household_green"
        green_view, _ = app.agent_trace_view()
        green_text = str(green_view)
        assert "rice" in green_text.lower() or "add_purchase" in green_text
        # Negative: household_green should NOT see household_blue's trace
        assert "bread" not in green_text.lower()

        # View from household_blue — should only see their own traces
        app.db.active_household_id = "household_blue"
        blue_view, _ = app.agent_trace_view()
        blue_text = str(blue_view)
        assert "bread" in blue_text.lower() or "add_purchase" in blue_text
        # Negative: household_blue should NOT see household_green's trace
        assert "rice" not in blue_text.lower()

    def test_trace_bootstrap_scoped_per_household(self, e2e_app):
        """agent_trace_bootstrap returns traces scoped to the active household."""
        app = e2e_app
        from datetime import date

        # Create traces for two households
        app.db.active_household_id = "household_green"
        app.add_purchase_form("Milk", 2.0, "L", 64.0, "Store", "fridge",
                              date.today().isoformat(), "Dairy")

        app.db.active_household_id = "household_blue"
        app.add_purchase_form("Eggs", 12.0, "pieces", 60.0, "Store", "fridge_top",
                              date.today().isoformat(), "Dairy")

        # Bootstrap from household_green
        app.db.active_household_id = "household_green"
        green_boot = app.agent_trace_bootstrap()
        assert len(green_boot) == 4
        # household_green's trace should be the default
        assert green_boot[1]  # non-empty trace_id
        assert green_boot[3]  # non-empty raw JSON

        # Bootstrap from household_blue
        app.db.active_household_id = "household_blue"
        blue_boot = app.agent_trace_bootstrap()
        assert len(blue_boot) == 4
        assert blue_boot[1]  # non-empty trace_id
        assert blue_boot[3]  # non-empty raw JSON

        # The trace IDs should differ since they belong to different households
        assert green_boot[1] != blue_boot[1]

    def test_trace_detail_scoped_per_household(self, e2e_app):
        """agent_trace_detail should only show traces from the active household."""
        app = e2e_app
        from datetime import date

        app.db.active_household_id = "household_green"
        app.add_purchase_form("Milk", 2.0, "L", 64.0, "Store", "fridge",
                              date.today().isoformat(), "Dairy")
        green_traces = app.db.get_traces(user_id="household_green")
        green_tid = green_traces[0].trace_id

        app.db.active_household_id = "household_blue"
        app.add_purchase_form("Eggs", 12.0, "pieces", 60.0, "Store", "fridge_top",
                              date.today().isoformat(), "Dairy")

        # household_green can see its own trace
        app.db.active_household_id = "household_green"
        detail = app.agent_trace_detail(green_tid)
        assert "not found" not in detail.lower()

        # household_blue cannot see household_green's trace
        app.db.active_household_id = "household_blue"
        blocked = app.agent_trace_detail(green_tid)
        assert "not found" in blocked.lower()
        # household_blue's own trace is still visible
        blue_traces = app.db.get_traces(user_id="household_blue")
        assert len(blue_traces) == 1

    def test_trace_export_scoped_per_household(self, e2e_app):
        """Trace export via agent_trace_export_file respects household scoping."""
        app = e2e_app
        from datetime import date

        # Create traces for two households
        app.db.active_household_id = "household_green"
        app.add_purchase_form("Milk", 2.0, "L", 64.0, "Store", "fridge",
                              date.today().isoformat(), "Dairy")

        app.db.active_household_id = "household_blue"
        app.add_purchase_form("Eggs", 12.0, "pieces", 60.0, "Store", "fridge_top",
                              date.today().isoformat(), "Dairy")

        green_traces = app.db.get_traces(user_id="household_green")
        blue_traces = app.db.get_traces(user_id="household_blue")

        # household_green can export its own trace
        app.db.active_household_id = "household_green"
        exported = app.agent_trace_export_file(green_traces[0].trace_id)
        assert exported.endswith(".jsonl") or exported == ""

        # household_green CANNOT export household_blue's trace (lookup is scoped)
        blocked = app.agent_trace_export_file(blue_traces[0].trace_id)
        assert blocked == ""  # trace not found => empty string

        # household_blue CAN export its own trace
        app.db.active_household_id = "household_blue"
        blue_export = app.agent_trace_export_file(blue_traces[0].trace_id)
        assert blue_export.endswith(".jsonl")
