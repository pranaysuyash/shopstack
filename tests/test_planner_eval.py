"""Planner eval harness — SWE-bench style structured eval scenarios for planner accuracy.

Tests run against whatever planner ProviderRegistry resolves for the default
``planner_backend`` (typically ``local``). When the real backend's deps or
weights are unavailable, the registry falls back to ``MockPlannerProvider`` —
the tests still verify PlannerEngine / planner-interface behavior either way.

Each eval scenario specifies:
  - name: scenario identifier
  - user_input: context prompt to plan from
  - expected_tools: list of tool names that should be called
  - expected_tool_count: (min, max) acceptable tool calls

Run: uv run pytest tests/test_planner_eval.py -v
"""

from __future__ import annotations

import logging
from typing import Any

from shopstack.planner.engine import PlannerEngine

logger = logging.getLogger(__name__)

EVAL_SCENARIOS: list[dict[str, Any]] = [
    {
        "name": "planner_returns_tool_calls",
        "user_input": "I need groceries",
        "expected_min_tool_calls": 1,
        "expected_max_tool_calls": 5,
        "description": "Planner returns structured tool calls",
    },
]


def _build_engine() -> PlannerEngine:
    """Create an isolated PlannerEngine with :memory: DB and default backends.

    No explicit backend is requested — ProviderRegistry resolves the default
    and falls back to MockPlannerProvider silently when the real backend
    can't load.
    """
    from shopstack.config import Settings
    from shopstack.persistence.database import Database
    from shopstack.providers.registry import ProviderRegistry
    from shopstack.tools.registry import ToolRegistry

    s = Settings(
        _env_file=None,
        db_path=":memory:",
        off_the_grid=True,
        local_auto_download=False,
    )
    database = Database(s.db_path)
    provider_registry = ProviderRegistry(s)
    tool_registry = ToolRegistry(database)
    return PlannerEngine(database, tool_registry, provider_registry)


def test_planner_returns_valid_tool_calls() -> None:
    """Verify the resolved planner's plan() returns properly structured tool calls."""
    from shopstack.config import Settings
    from shopstack.persistence.database import Database
    from shopstack.providers.registry import ProviderRegistry

    s = Settings(
        _env_file=None,
        db_path=":memory:",
        off_the_grid=True,
        local_auto_download=False,
    )
    Database(s.db_path)
    provider_registry = ProviderRegistry(s)
    provider = provider_registry.planner

    context = {
        "prompt": "What's in my kitchen?",
        "question": "What's in my kitchen?",
        "system": "You are a helpful shopping assistant.",
        "max_tokens": 128,
        "temperature": 0.0,
    }
    result = provider.plan(context)

    assert isinstance(result, list), f"plan() should return a list, got {type(result)}"
    assert len(result) >= 1, "plan() should return at least 1 tool call"
    assert len(result) <= 5, "plan() should return at most 5 tool calls"

    for tc in result:
        assert "tool" in tc, f"Tool call missing 'tool' key: {tc}"
        assert "args" in tc, f"Tool call missing 'args' key: {tc}"
        assert isinstance(tc["args"], dict), f"Tool args must be dict: {tc}"

    valid_tools = {
        "respond", "add_inventory_item", "consume_inventory_item",
        "update_inventory_item", "move_inventory_item", "find_item",
        "create_or_update_shopping_list", "compare_visible_item_to_inventory",
        "record_price_observation", "get_use_soon_items",
        "get_next_buy_suggestions", "get_inventory",
    }
    for tc in result:
        assert tc["tool"] in valid_tools, (
            f"Unknown tool '{tc['tool']}'. Valid: {valid_tools}"
        )


def test_planner_eval_all_tool_names_valid() -> None:
    """Verify the resolved planner only returns tools that exist in the registry."""
    from shopstack.config import Settings
    from shopstack.persistence.database import Database
    from shopstack.providers.registry import ProviderRegistry
    from shopstack.tools.registry import ToolRegistry

    s = Settings(
        _env_file=None,
        db_path=":memory:",
        off_the_grid=True,
        local_auto_download=False,
    )
    database = Database(s.db_path)
    tool_registry = ToolRegistry(database)
    provider_registry = ProviderRegistry(s)
    provider = provider_registry.planner

    available_tools = set()
    for t in tool_registry.list_tools():
        available_tools.add(t.get("name", ""))
    available_tools.add("respond")  # special built-in tool

    queries = [
        "What's in my fridge?",
        "I need milk, bread, and eggs",
        "Do I have any milk left?",
        "I bought 2kg of rice from DMart",
    ]

    for query in queries:
        result = provider.plan({
            "prompt": query,
            "question": query,
            "system": "You are a helpful shopping assistant.",
            "max_tokens": 128,
            "temperature": 0.0,
        })
        for tc in result:
            tool_name = tc["tool"]
            assert tool_name in available_tools, (
                f"Tool '{tool_name}' not in registered tools: {available_tools}"
            )


def test_planner_eval_edge_cases() -> None:
    """Test edge cases the planner provider should handle gracefully."""
    from shopstack.config import Settings
    from shopstack.persistence.database import Database
    from shopstack.providers.registry import ProviderRegistry

    s = Settings(
        _env_file=None,
        db_path=":memory:",
        off_the_grid=True,
        local_auto_download=False,
    )
    Database(s.db_path)
    provider_registry = ProviderRegistry(s)
    provider = provider_registry.planner

    edge_cases = [
        ({}, "Empty context should not crash"),
        ({"prompt": ""}, "Empty prompt should not crash"),
        (None, "None context should not crash"),
    ]

    for ctx, description in edge_cases:
        try:
            result = provider.plan(ctx)
            assert isinstance(result, list), f"plan() must return a list for: {description}"
            for tc in result:
                assert "tool" in tc, f"Tool call missing 'tool': {tc}"
        except Exception as e:
            import pytest
            pytest.fail(f"Planner crashed on '{description}': {e}")


def test_planner_eval_returns_html() -> None:
    """Verify PlannerEngine.process() returns non-empty HTML."""
    engine = _build_engine()
    result = engine.process("What's in my kitchen?")

    assert result is not None, "Planner returned None"
    assert isinstance(result, str), f"process() returns HTML string, got {type(result)}"
    assert len(result) > 0, "Planner returned empty string"
    assert "<div" in result, "Expected HTML output from process()"
