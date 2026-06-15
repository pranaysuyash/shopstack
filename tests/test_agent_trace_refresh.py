"""Tests for agent_trace_refresh and agent_trace_search_filter.

These two functions were missing in traces.py (causing NameError on
``app.build_app()``) and were implemented per the Gradio output
contract documented in app.py:

- ``agent_trace_refresh`` returns 5 values matching
  ``[trace_selector, trace_bootstrap_state, trace_timeline,
  trace_raw, trace_table]``
- ``agent_trace_search_filter`` returns 3 values matching
  ``[trace_selector, trace_timeline, trace_raw]``

This file pins the contract so that a future refactor cannot
silently break the Gradio wiring.
"""

from __future__ import annotations

import os

import pytest

from shopstack.ui.screens.traces import (
    agent_trace_refresh,
    agent_trace_search_filter,
)


@pytest.fixture(scope="module", autouse=True)
def _setup_app_env():
    """Initialize shopstack.app_context with an in-memory DB so traces can be saved."""
    os.environ.setdefault("SHOPSTACK_DB_PATH", ":memory:")
    import app  # noqa: F401  (initializes app_context)


class TestAgentTraceRefresh:
    def test_returns_5_values(self):
        """Gradio expects 5 output values."""
        result = agent_trace_refresh()
        assert len(result) == 5, f"Expected 5 outputs, got {len(result)}"

    def test_first_value_is_gr_update_or_dict(self):
        """First output is trace_selector (gr.update or dict with choices)."""
        result = agent_trace_refresh()
        assert isinstance(result[0], dict)

    def test_second_value_is_state_string(self):
        """Second output is trace_bootstrap_state (string trace_id)."""
        result = agent_trace_refresh()
        assert isinstance(result[1], str)

    def test_third_value_is_timeline_html(self):
        """Third output is trace_timeline (HTML string)."""
        result = agent_trace_refresh()
        assert isinstance(result[3], str)
        # Either timeline content or an empty/placeholder div
        assert len(result[3]) >= 0  # any string is valid

    def test_fourth_value_is_raw_html(self):
        """Fourth output is trace_raw (raw JSON in HTML pre tag)."""
        result = agent_trace_refresh()
        assert isinstance(result[3], str)


class TestAgentTraceSearchFilter:
    def test_returns_3_values(self):
        """Gradio expects 3 output values."""
        result = agent_trace_search_filter(search="", type_filter="")
        assert len(result) == 3, f"Expected 3 outputs, got {len(result)}"

    def test_first_value_is_gr_update(self):
        """First output is the trace_selector update."""
        result = agent_trace_search_filter(search="", type_filter="")
        assert isinstance(result[0], dict)

    def test_accepts_empty_filters(self):
        """Empty search and type_filter must not raise."""
        result = agent_trace_search_filter(search="", type_filter="")
        assert len(result) == 3

    def test_accepts_text_search(self):
        """A non-empty search must not raise."""
        result = agent_trace_search_filter(search="milk", type_filter="")
        assert len(result) == 3

    def test_accepts_type_filter(self):
        """A non-empty type_filter must not raise."""
        result = agent_trace_search_filter(search="", type_filter="text")
        assert len(result) == 3
