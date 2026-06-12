"""Tests for shopstack/services/trace.py and household CRUD in database.

Simple TraceService methods use conftest fixtures (``db``).
Household CRUD methods on the Database class use conftest fixtures (``db``).

Both follow the same pattern as test_shopping_service.py: class-per-feature
grouping, imports inside test methods (though none of these need the heavy
``app`` fixture since they're pure DB/service operations), and comprehensive
edge-case coverage.
"""

from __future__ import annotations

import os
import json

import pytest


# ══════════════════════════════════════════════════════════════════════════
# TraceService — get_trace
# ══════════════════════════════════════════════════════════════════════════

class TestTraceServiceGetTrace:
    def test_get_existing_trace(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_trace(input_type="test", user_goal="get_test")
        fetched = svc.get_trace(trace.trace_id)
        assert fetched is not None
        assert fetched.trace_id == trace.trace_id
        assert fetched.input_type == "test"
        assert fetched.user_goal == "get_test"

    def test_get_nonexistent_trace(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        fetched = svc.get_trace("nonexistent-id")
        assert fetched is None

    def test_get_empty_id(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        fetched = svc.get_trace("")
        assert fetched is None

    def test_get_whitespace_id(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        fetched = svc.get_trace("   ")
        assert fetched is None


# ══════════════════════════════════════════════════════════════════════════
# TraceService — list_traces
# ══════════════════════════════════════════════════════════════════════════

class TestTraceServiceListTraces:
    def test_empty_db(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        traces = svc.list_traces()
        assert traces == []

    def test_returns_all_traces(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        svc.create_trace(input_type="a", user_goal="first")
        svc.create_trace(input_type="b", user_goal="second")
        svc.create_trace(input_type="c", user_goal="third")
        traces = svc.list_traces()
        assert len(traces) == 3

    def test_ordered_descending(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        t1 = svc.create_trace(input_type="a", user_goal="first")
        t2 = svc.create_trace(input_type="b", user_goal="second")
        traces = svc.list_traces()
        assert traces[0].trace_id == t2.trace_id
        assert traces[1].trace_id == t1.trace_id

    def test_limit_parameter(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        svc.create_trace(input_type="a", user_goal="first")
        svc.create_trace(input_type="b", user_goal="second")
        svc.create_trace(input_type="c", user_goal="third")
        traces = svc.list_traces(limit=2)
        assert len(traces) == 2


# ══════════════════════════════════════════════════════════════════════════
# TraceService — filter_traces
# ══════════════════════════════════════════════════════════════════════════

class TestTraceServiceFilterTraces:
    def test_filter_by_search_text(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        svc.create_trace(input_type="voice", user_goal="add milk to list")
        svc.create_trace(input_type="text", user_goal="check weather")
        results = svc.filter_traces(search="milk")
        assert len(results) == 1
        assert results[0].user_goal == "add milk to list"

    def test_filter_by_input_type(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        svc.create_trace(input_type="voice", user_goal="item 1")
        svc.create_trace(input_type="text", user_goal="item 2")
        svc.create_trace(input_type="voice", user_goal="item 3")
        results = svc.filter_traces(input_type_filter="voice")
        assert len(results) == 2
        assert all(t.input_type == "voice" for t in results)

    def test_filter_by_both(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        svc.create_trace(input_type="voice", user_goal="add milk")
        svc.create_trace(input_type="text", user_goal="add milk")
        svc.create_trace(input_type="voice", user_goal="check weather")
        results = svc.filter_traces(search="milk", input_type_filter="voice")
        assert len(results) == 1
        assert results[0].user_goal == "add milk"
        assert results[0].input_type == "voice"

    def test_filter_no_match(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        svc.create_trace(input_type="voice", user_goal="add milk")
        results = svc.filter_traces(search="unobtainium")
        assert results == []

    def test_filter_empty_search_and_type(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        svc.create_trace(input_type="voice", user_goal="add milk")
        results = svc.filter_traces(search="", input_type_filter="")
        assert len(results) == 1

    def test_filter_case_insensitive(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        svc.create_trace(input_type="Voice", user_goal="Add Milk")
        results = svc.filter_traces(search="milk", input_type_filter="voice")
        assert len(results) == 1


# ══════════════════════════════════════════════════════════════════════════
# TraceService — create_trace
# ══════════════════════════════════════════════════════════════════════════

class TestTraceServiceCreateTrace:
    def test_basic_creation(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_trace(input_type="test", user_goal="test_goal")
        assert trace.trace_id is not None
        assert trace.input_type == "test"
        assert trace.user_goal == "test_goal"

    def test_with_all_fields(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_trace(
            input_type="voice",
            user_goal="buy milk",
            redacted_user_request="buy [REDACTED]",
            perception={"items": ["milk"]},
            inventory_context={"milk": {"qty": 1}},
            decision={"action": "add_to_list"},
            proposed_tool_calls=[{"tool_name": "add_inventory_item", "args": {"name": "milk"}}],
            final_response="Added milk",
            human_confirmation="confirmed",
        )
        assert trace.redacted_user_request == "buy [REDACTED]"
        assert trace.perception == {"items": ["milk"]}
        assert trace.final_response == "Added milk"
        assert trace.human_confirmation == "confirmed"

    def test_with_tool_calls_list_of_dicts(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        calls = [
            {"tool": "find_item", "args": {"name": "milk"}, "success": True},
            {"tool_name": "add_inventory_item", "args": {"name": "eggs"}, "confirmed": True},
        ]
        trace = svc.create_trace(
            input_type="test",
            user_goal="test",
            proposed_tool_calls=calls,
        )
        assert len(trace.proposed_tool_calls) == 2
        assert trace.proposed_tool_calls[0].tool_name == "find_item"
        assert trace.proposed_tool_calls[1].tool_name == "add_inventory_item"

    def test_with_empty_tool_calls(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_trace(input_type="test", user_goal="test", proposed_tool_calls=[])
        assert trace.proposed_tool_calls == []

    def test_with_none_tool_calls(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_trace(input_type="test", user_goal="test", proposed_tool_calls=None)
        assert trace.proposed_tool_calls == []

    def test_with_invalid_tool_call(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_trace(
            input_type="test",
            user_goal="test",
            proposed_tool_calls=[{"bad": "payload"}],
        )
        assert len(trace.proposed_tool_calls) == 1
        assert trace.proposed_tool_calls[0].tool_name == "respond"


# ══════════════════════════════════════════════════════════════════════════
# TraceService — create_market_lens_trace
# ══════════════════════════════════════════════════════════════════════════

class TestTraceServiceCreateMarketLensTrace:
    def test_basic_creation(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_market_lens_trace()
        assert trace.input_type == "market_lens"
        assert trace.user_goal == "market_lens"

    def test_with_detected_items(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_market_lens_trace(
            items_detected=["tomato", "onion"],
            analysis_text="Found vegetables",
            analysis_result="Buy both",
        )
        assert trace.perception.get("items_detected") == ["tomato", "onion"]
        assert trace.final_response == "Buy both"

    def test_with_barcode_data(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_market_lens_trace(barcode_data="8901234567890")
        assert trace.perception.get("barcode") == "8901234567890"

    def test_with_audio_and_image(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_market_lens_trace(audio_present=True, image_present=True)
        assert trace.perception["audio"] is True
        assert trace.perception["image"] is True

    def test_with_decision_items(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        items = [{"name": "tomato", "decision": "buy"}, {"name": "onion", "decision": "skip"}]
        trace = svc.create_market_lens_trace(decision_items=items)
        assert trace.decision.get("items") == items


# ══════════════════════════════════════════════════════════════════════════
# TraceService — export
# ══════════════════════════════════════════════════════════════════════════

class TestTraceServiceExport:
    def test_export_trace_to_jsonl_success(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_trace(input_type="export_test", user_goal="test")
        path = svc.export_trace_to_jsonl(trace.trace_id)
        assert path != ""
        assert path.endswith(".jsonl")
        with open(path) as f:
            content = f.read().strip()
            assert len(content) > 0
            parsed = json.loads(content)
            assert parsed["trace_id"] == trace.trace_id
        os.remove(path)

    def test_export_trace_to_jsonl_nonexistent(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        path = svc.export_trace_to_jsonl("nonexistent-id")
        assert path == ""

    def test_export_trace_to_jsonl_empty_id(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        path = svc.export_trace_to_jsonl("")
        assert path == ""

    def test_export_all_to_jsonl(self, db, tmp_path):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        svc.create_trace(input_type="a", user_goal="first")
        svc.create_trace(input_type="b", user_goal="second")
        out_path = tmp_path / "test_trace_export_all.jsonl"
        count = svc.export_all_to_jsonl(str(out_path))
        assert count == 2
        with open(out_path) as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_export_all_to_jsonl_limit(self, db, tmp_path):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        svc.create_trace(input_type="a", user_goal="first")
        svc.create_trace(input_type="b", user_goal="second")
        svc.create_trace(input_type="c", user_goal="third")
        out_path = tmp_path / "test_trace_export_limit.jsonl"
        count = svc.export_all_to_jsonl(str(out_path), limit=2)
        assert count == 2

    def test_export_all_to_jsonl_empty_db(self, db, tmp_path):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        out_path = tmp_path / "test_trace_export_empty.jsonl"
        count = svc.export_all_to_jsonl(str(out_path))
        assert count == 0
        with open(out_path) as f:
            lines = f.readlines()
        assert len(lines) == 0

    def test_export_all_to_jsonl_scoped_per_household(self, db, tmp_path):
        """``export_all_to_jsonl`` with ``user_id`` only exports traces for that household."""
        from shopstack.services.trace import TraceService
        svc = TraceService(db)

        # Create traces for two different households
        svc.create_trace(input_type="text", user_goal="household_a_task", user_id="household_a")
        svc.create_trace(input_type="text", user_goal="household_b_task", user_id="household_b")

        # Export scoped to household_a
        out_a = tmp_path / "export_a.jsonl"
        count_a = svc.export_all_to_jsonl(str(out_a), user_id="household_a")
        assert count_a == 1, f"Expected 1 trace for household_a, got {count_a}"
        with open(out_a) as f:
            lines_a = f.readlines()
        assert len(lines_a) == 1
        assert "household_a_task" in lines_a[0]

        # Export scoped to household_b
        out_b = tmp_path / "export_b.jsonl"
        count_b = svc.export_all_to_jsonl(str(out_b), user_id="household_b")
        assert count_b == 1, f"Expected 1 trace for household_b, got {count_b}"
        with open(out_b) as f:
            lines_b = f.readlines()
        assert len(lines_b) == 1
        assert "household_b_task" in lines_b[0]

        # Export without user_id sees both
        out_all = tmp_path / "export_all.jsonl"
        count_all = svc.export_all_to_jsonl(str(out_all))
        assert count_all == 2, f"Expected 2 traces unfiltered, got {count_all}"

    def test_export_all_to_jsonl_scoped_empty_household(self, db, tmp_path):
        """``export_all_to_jsonl`` for a household with no traces returns 0."""
        from shopstack.services.trace import TraceService
        svc = TraceService(db)

        svc.create_trace(input_type="text", user_goal="exists", user_id="household_a")

        out = tmp_path / "empty_export.jsonl"
        count = svc.export_all_to_jsonl(str(out), user_id="household_with_no_traces")
        assert count == 0, f"Expected 0 traces for empty household, got {count}"
        with open(out) as f:
            assert f.read() == ""

    def test_export_trace_to_jsonl_scoped_found(self, db):
        """``export_trace_to_jsonl`` with matching ``user_id`` returns the export path."""
        from shopstack.services.trace import TraceService
        svc = TraceService(db)

        trace = svc.create_trace(
            input_type="text",
            user_goal="scoped_export_test",
            user_id="household_export_user",
        )

        path = svc.export_trace_to_jsonl(trace.trace_id, user_id="household_export_user")
        assert path != "", "Expected non-empty path for matching user_id"
        assert path.endswith(".jsonl")
        with open(path) as f:
            content = f.read().strip()
            assert len(content) > 0
            parsed = json.loads(content)
            assert parsed["trace_id"] == trace.trace_id
        os.remove(path)

    def test_export_trace_to_jsonl_scoped_blocked(self, db):
        """``export_trace_to_jsonl`` with a non-matching ``user_id`` returns empty string."""
        from shopstack.services.trace import TraceService
        svc = TraceService(db)

        trace = svc.create_trace(
            input_type="text",
            user_goal="blocked_export_test",
            user_id="household_owner",
        )

        path = svc.export_trace_to_jsonl(trace.trace_id, user_id="household_intruder")
        assert path == "", "Expected empty string for mismatched user_id"

    def test_export_trace_to_jsonl_scoped_without_user_id_finds_any(self, db):
        """``export_trace_to_jsonl`` without ``user_id`` finds any trace."""
        from shopstack.services.trace import TraceService
        svc = TraceService(db)

        trace = svc.create_trace(
            input_type="text",
            user_goal="unfiltered_export",
            user_id="household_someone",
        )

        path = svc.export_trace_to_jsonl(trace.trace_id)  # no user_id
        assert path != "", "Expected non-empty path without user_id"
        assert path.endswith(".jsonl")
        with open(path) as f:
            content = f.read().strip()
            assert len(content) > 0
            parsed = json.loads(content)
            assert parsed["trace_id"] == trace.trace_id
        os.remove(path)

    # ══════════════════════════════════════════════════════════════════════
    # TraceService export — user_id pass-through delegation tests
    # ══════════════════════════════════════════════════════════════════════

    def test_export_trace_to_jsonl_forwards_user_id(self, db):
        """export_trace_to_jsonl passes ``user_id`` through to ``_export_trace_by_id``."""
        from unittest.mock import patch
        from shopstack.services.trace import TraceService
        svc = TraceService(db)

        with patch("shopstack.services.trace._export_trace_by_id", return_value=True) as mock_fn:
            result = svc.export_trace_to_jsonl("trace-abc", user_id="household_test_user")

            mock_fn.assert_called_once()
            _args, kwargs = mock_fn.call_args
            assert kwargs.get("user_id") == "household_test_user", (
                f"Expected user_id='household_test_user', got {kwargs.get('user_id')!r}"
            )
            if result:
                import os
                os.remove(result)

    def test_export_all_to_jsonl_forwards_user_id(self, db, tmp_path):
        """export_all_to_jsonl passes ``user_id`` through to ``_export_traces_to_jsonl``."""
        from unittest.mock import patch
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        out = tmp_path / "fwd_test.jsonl"

        with patch("shopstack.services.trace._export_traces_to_jsonl", return_value=3) as mock_fn:
            svc.export_all_to_jsonl(str(out), user_id="household_bulk_test")

            mock_fn.assert_called_once()
            _args, kwargs = mock_fn.call_args
            assert kwargs.get("user_id") == "household_bulk_test", (
                f"Expected user_id='household_bulk_test', got {kwargs.get('user_id')!r}"
            )

    def test_export_trace_to_jsonl_default_user_id_empty(self, db):
        """export_trace_to_jsonl defaults ``user_id`` to ``""`` when not provided."""
        from unittest.mock import patch
        from shopstack.services.trace import TraceService
        svc = TraceService(db)

        with patch("shopstack.services.trace._export_trace_by_id", return_value=True) as mock_fn:
            result = svc.export_trace_to_jsonl("trace-def")

            mock_fn.assert_called_once()
            _args, kwargs = mock_fn.call_args
            assert kwargs.get("user_id") == "", (
                f"Expected user_id='', got {kwargs.get('user_id')!r}"
            )
            if result:
                import os
                os.remove(result)

    def test_export_all_to_jsonl_default_user_id_empty(self, db, tmp_path):
        """export_all_to_jsonl defaults ``user_id`` to ``""`` when not provided."""
        from unittest.mock import patch
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        out = tmp_path / "def_test.jsonl"

        with patch("shopstack.services.trace._export_traces_to_jsonl", return_value=0) as mock_fn:
            svc.export_all_to_jsonl(str(out))

            mock_fn.assert_called_once()
            _args, kwargs = mock_fn.call_args
            assert kwargs.get("user_id") == "", (
                f"Expected user_id='', got {kwargs.get('user_id')!r}"
            )

    # ══════════════════════════════════════════════════════════════════════
    # TraceService — get_trace / update_confirmation user_id forwarding
    # ══════════════════════════════════════════════════════════════════════

    def test_get_trace_forwards_user_id(self, db):
        """get_trace passes ``user_id`` through to ``_find_trace_by_id``."""
        from unittest.mock import patch
        from shopstack.services.trace import TraceService
        svc = TraceService(db)

        with patch("shopstack.services.trace._find_trace_by_id", return_value=None) as mock_fn:
            svc.get_trace("trace-123", user_id="household_get_user")

            mock_fn.assert_called_once()
            _args, kwargs = mock_fn.call_args
            assert kwargs.get("user_id") == "household_get_user", (
                f"Expected user_id='household_get_user', got {kwargs.get('user_id')!r}"
            )

    def test_get_trace_default_user_id_empty(self, db):
        """get_trace defaults ``user_id`` to ``""`` when not provided."""
        from unittest.mock import patch
        from shopstack.services.trace import TraceService
        svc = TraceService(db)

        with patch("shopstack.services.trace._find_trace_by_id", return_value=None) as mock_fn:
            svc.get_trace("trace-def")

            mock_fn.assert_called_once()
            _args, kwargs = mock_fn.call_args
            assert kwargs.get("user_id") == "", (
                f"Expected user_id='', got {kwargs.get('user_id')!r}"
            )

    def test_update_confirmation_forwards_user_id(self, db):
        """update_confirmation passes ``user_id`` through to ``_update_trace_confirmation``."""
        from unittest.mock import patch
        from shopstack.services.trace import TraceService
        svc = TraceService(db)

        with patch("shopstack.services.trace._update_trace_confirmation", return_value=True) as mock_fn:
            svc.update_confirmation("trace-456", "approved", user_id="household_update_user")

            mock_fn.assert_called_once()
            _args, kwargs = mock_fn.call_args
            assert kwargs.get("user_id") == "household_update_user", (
                f"Expected user_id='household_update_user', got {kwargs.get('user_id')!r}"
            )

    def test_update_confirmation_default_user_id_empty(self, db):
        """update_confirmation defaults ``user_id`` to ``""`` when not provided."""
        from unittest.mock import patch
        from shopstack.services.trace import TraceService
        svc = TraceService(db)

        with patch("shopstack.services.trace._update_trace_confirmation", return_value=True) as mock_fn:
            svc.update_confirmation("trace-def", "skip")

            mock_fn.assert_called_once()
            _args, kwargs = mock_fn.call_args
            assert kwargs.get("user_id") == "", (
                f"Expected user_id='', got {kwargs.get('user_id')!r}"
            )

    # ══════════════════════════════════════════════════════════════════════
    # TraceService — create_trace / create_market_lens_trace user_id forwarding
    # ══════════════════════════════════════════════════════════════════════

    def test_create_trace_forwards_user_id(self, db):
        """create_trace passes ``user_id`` through to ``_create_trace``."""
        from unittest.mock import patch
        from shopstack.services.trace import TraceService
        from shopstack.schemas.models import Trace as _Trace
        svc = TraceService(db)
        mock_trace = _Trace(input_type="mock")

        with patch("shopstack.services.trace._create_trace", return_value=mock_trace) as mock_fn:
            svc.create_trace(input_type="test", user_goal="test_goal", user_id="household_create_user")

            mock_fn.assert_called_once()
            _args, kwargs = mock_fn.call_args
            assert kwargs.get("user_id") == "household_create_user", (
                f"Expected user_id='household_create_user', got {kwargs.get('user_id')!r}"
            )

    def test_create_trace_default_user_id_empty(self, db):
        """create_trace defaults ``user_id`` to ``""`` when not provided."""
        from unittest.mock import patch
        from shopstack.services.trace import TraceService
        from shopstack.schemas.models import Trace as _Trace
        svc = TraceService(db)
        mock_trace = _Trace(input_type="mock")

        with patch("shopstack.services.trace._create_trace", return_value=mock_trace) as mock_fn:
            svc.create_trace(input_type="test", user_goal="test_goal")

            mock_fn.assert_called_once()
            _args, kwargs = mock_fn.call_args
            assert kwargs.get("user_id") == "", (
                f"Expected user_id='', got {kwargs.get('user_id')!r}"
            )

    def test_create_market_lens_trace_forwards_user_id(self, db):
        """create_market_lens_trace passes ``user_id`` through to ``_create_market_lens_trace``."""
        from unittest.mock import patch
        from shopstack.services.trace import TraceService
        from shopstack.schemas.models import Trace as _Trace
        svc = TraceService(db)
        mock_trace = _Trace(input_type="market_lens")

        with patch("shopstack.services.trace._create_market_lens_trace", return_value=mock_trace) as mock_fn:
            svc.create_market_lens_trace(items_detected=["tomato"], user_id="household_ml_user")

            mock_fn.assert_called_once()
            _args, kwargs = mock_fn.call_args
            assert kwargs.get("user_id") == "household_ml_user", (
                f"Expected user_id='household_ml_user', got {kwargs.get('user_id')!r}"
            )

    def test_create_market_lens_trace_default_user_id_empty(self, db):
        """create_market_lens_trace defaults ``user_id`` to ``""`` when not provided."""
        from unittest.mock import patch
        from shopstack.services.trace import TraceService
        from shopstack.schemas.models import Trace as _Trace
        svc = TraceService(db)
        mock_trace = _Trace(input_type="market_lens")

        with patch("shopstack.services.trace._create_market_lens_trace", return_value=mock_trace) as mock_fn:
            svc.create_market_lens_trace()

            mock_fn.assert_called_once()
            _args, kwargs = mock_fn.call_args
            assert kwargs.get("user_id") == "", (
                f"Expected user_id='', got {kwargs.get('user_id')!r}"
            )


# ══════════════════════════════════════════════════════════════════════════
# TraceService — trace_payload & redact_payload
# ══════════════════════════════════════════════════════════════════════════

class TestTraceServicePayload:
    def test_trace_payload_basic(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_trace(input_type="test", user_goal="test_payload")
        payload = svc.trace_payload(trace, redact=False)
        assert payload["trace_id"] == trace.trace_id
        assert payload["input_type"] == "test"

    def test_trace_payload_redacted(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_trace(
            input_type="test",
            user_goal="buy milk call 9876543210",
        )
        payload = svc.trace_payload(trace, redact=True)
        assert "[REDACTED_NUMBER]" in payload.get("user_goal", "")
        assert "9876543210" not in payload.get("user_goal", "")


class TestTraceServiceRedactPayload:
    def test_redacts_phone_numbers(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        payload = {"user_goal": "call 9876543210 please"}
        redacted = svc.redact_payload(payload)
        assert "[REDACTED_NUMBER]" in redacted["user_goal"]
        assert "9876543210" not in redacted["user_goal"]

    def test_redacts_emails(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        payload = {"user_goal": "email test@example.com"}
        redacted = svc.redact_payload(payload)
        assert "[REDACTED_EMAIL]" in redacted["user_goal"]
        assert "test@example.com" not in redacted["user_goal"]

    def test_does_not_redact_short_numbers(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        payload = {"user_goal": "item 123 is good"}
        redacted = svc.redact_payload(payload)
        assert "123" in redacted["user_goal"]

    def test_redacts_address_in_args(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        payload = {
            "proposed_tool_calls": [
                {"args": {"address": "123 Main St"}, "tool_name": "deliver"}
            ]
        }
        redacted = svc.redact_payload(payload)
        assert redacted["proposed_tool_calls"][0]["args"]["address"] == "[REDACTED]"

    def test_preserves_non_pii_fields(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        payload = {"user_goal": "buy milk", "final_response": "done"}
        redacted = svc.redact_payload(payload)
        assert redacted["user_goal"] == "buy milk"
        assert redacted["final_response"] == "done"

    def test_handles_nested_dicts(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        payload = {"perception": {"name": "John", "phone": "9876543210"}}
        redacted = svc.redact_payload(payload)
        assert redacted["perception"]["phone"] == "[REDACTED_NUMBER]"
        assert redacted["perception"]["name"] == "John"


# ══════════════════════════════════════════════════════════════════════════
# TraceService — update_confirmation
# ══════════════════════════════════════════════════════════════════════════

class TestTraceServiceUpdateConfirmation:
    def test_update_existing_trace(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_trace(input_type="test", user_goal="test")
        result = svc.update_confirmation(trace.trace_id, "approved")
        assert result is True
        updated = svc.get_trace(trace.trace_id)
        assert updated is not None
        assert updated.human_confirmation == "approved"

    def test_update_nonexistent_trace(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        result = svc.update_confirmation("nonexistent", "approved")
        assert result is False

    def test_update_empty_id(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        result = svc.update_confirmation("", "approved")
        assert result is False

    def test_update_overwrites_previous(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_trace(
            input_type="test", user_goal="test", human_confirmation="initial"
        )
        svc.update_confirmation(trace.trace_id, "revised")
        updated = svc.get_trace(trace.trace_id)
        assert updated is not None
        assert updated.human_confirmation == "revised"

    def test_update_to_none_then_back(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        trace = svc.create_trace(
            input_type="test", user_goal="test", human_confirmation="okay"
        )
        svc.update_confirmation(trace.trace_id, "")
        updated = svc.get_trace(trace.trace_id)
        assert updated is not None
        assert updated.human_confirmation == ""


# ══════════════════════════════════════════════════════════════════════════
# TraceService — prune
# ══════════════════════════════════════════════════════════════════════════

class TestTraceServicePrune:
    def test_prune_by_max_rows(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        for i in range(10):
            svc.create_trace(input_type="test", user_goal=f"trace_{i}")
        removed = svc.prune(max_rows=5)
        assert removed >= 5
        remaining = svc.list_traces()
        assert len(remaining) <= 5

    def test_prune_preserves_newest_only(self, db):
        """Pruning with max_rows=1 keeps only the newest trace."""
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        for i in range(3):
            svc.create_trace(input_type="test", user_goal=f"trace_{i}")
        removed = svc.prune(max_rows=1)
        assert removed >= 2
        remaining = svc.list_traces()
        assert len(remaining) == 1

    def test_prune_by_ttl_returns_integer(self, db):
        """prune with a reasonable TTL runs without error."""
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        svc.create_trace(input_type="test", user_goal="trace")
        # TTL=36500 days (~100yr) — no traces are old enough
        removed = svc.prune(ttl_days=36500)
        assert isinstance(removed, int)

    def test_prune_noop_with_high_limit(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        for i in range(3):
            svc.create_trace(input_type="test", user_goal=f"trace_{i}")
        removed = svc.prune(max_rows=100)
        assert removed == 0
        remaining = svc.list_traces()
        assert len(remaining) == 3

    def test_prune_without_params(self, db):
        from shopstack.services.trace import TraceService
        svc = TraceService(db)
        svc.create_trace(input_type="test", user_goal="trace")
        removed = svc.prune(max_rows=None, ttl_days=None)
        assert removed == 0


# ══════════════════════════════════════════════════════════════════════════
# Household CRUD — database-level tests
# ══════════════════════════════════════════════════════════════════════════

class TestHouseholdDefaultSeed:
    def test_default_household_exists(self, db):
        households = db.list_households()
        assert len(households) >= 1
        ids = [h["household_id"] for h in households]
        assert "default_household" in ids

    def test_default_household_is_active(self, db):
        assert db.active_household_id == "default_household"


class TestHouseholdList:
    def test_list_returns_dicts(self, db):
        households = db.list_households()
        for h in households:
            assert "household_id" in h
            assert "name" in h
            assert "created_at" in h

    def test_list_includes_added_households(self, db):
        db.add_household("family_1", "Family 1")
        db.add_household("family_2", "Family 2")
        households = db.list_households()
        ids = [h["household_id"] for h in households]
        assert "family_1" in ids
        assert "family_2" in ids


class TestHouseholdAdd:
    def test_add_new_household(self, db):
        result = db.add_household("test_household", "Test Household")
        assert result is True
        h = db.conn.execute(
            "SELECT * FROM households WHERE household_id = ?", ("test_household",)
        ).fetchone()
        assert h is not None
        assert h["name"] == "Test Household"
        assert h["notes"] == ""

    def test_add_with_notes(self, db):
        result = db.add_household("notes_household", "Notes Household", notes="Some notes")
        assert result is True
        h = db.conn.execute(
            "SELECT * FROM households WHERE household_id = ?", ("notes_household",)
        ).fetchone()
        assert h["notes"] == "Some notes"

    def test_add_duplicate_returns_false(self, db):
        first = db.add_household("dup_household", "First")
        assert first is True
        second = db.add_household("dup_household", "Second")
        assert second is False


class TestHouseholdRemove:
    def test_remove_existing_household(self, db):
        db.add_household("remove_me", "Remove Me")
        result = db.remove_household("remove_me")
        assert result is True
        h = db.conn.execute(
            "SELECT * FROM households WHERE household_id = ?", ("remove_me",)
        ).fetchone()
        assert h is None

    def test_remove_nonexistent_is_harmless(self, db):
        """SQLite DELETE succeeds even when no row matches."""
        result = db.remove_household("nonexistent")
        assert result is True
        # Table still has only the default household
        remaining = db.list_households()
        assert len(remaining) == 1

    def test_remove_then_re_add(self, db):
        db.add_household("temp", "Temp")
        db.remove_household("temp")
        re_added = db.add_household("temp", "Re-added")
        assert re_added is True

    def test_remove_default_household(self, db):
        # Should be allowed — no FK constraints protect the default
        result = db.remove_household("default_household")
        assert result is True
        remaining = db.list_households()
        ids = [h["household_id"] for h in remaining]
        assert "default_household" not in ids


class TestHouseholdActiveId:
    def test_default_active_household(self, db):
        assert db.active_household_id == "default_household"

    def test_set_and_get_active_household(self, db):
        db.add_household("primary", "Primary Household")
        db.active_household_id = "primary"
        assert db.active_household_id == "primary"

    def test_active_household_persists_in_config(self, db):
        db.add_household("persist_test", "Persist Test")
        db.active_household_id = "persist_test"
        stored = db.get_config_value("active_household_id", "")
        assert stored == "persist_test"

    def test_switch_household(self, db):
        db.add_household("h1", "Household 1")
        db.add_household("h2", "Household 2")
        db.active_household_id = "h1"
        assert db.active_household_id == "h1"
        db.active_household_id = "h2"
        assert db.active_household_id == "h2"

    def test_switch_to_nonexistent_household(self, db):
        # Setting active_household_id doesn't validate existence
        db.active_household_id = "nonexistent"
        assert db.active_household_id == "nonexistent"

    def test_clear_active_household_returns_empty(self, db):
        """Setting active_household_id to empty string disables filtering."""
        db.set_config_value("active_household_id", "")
        assert db.active_household_id == ""

    def test_switch_multiple_times_maintains_last(self, db):
        db.add_household("a", "A")
        db.add_household("b", "B")
        db.add_household("c", "C")
        db.active_household_id = "a"
        db.active_household_id = "b"
        db.active_household_id = "c"
        assert db.active_household_id == "c"
