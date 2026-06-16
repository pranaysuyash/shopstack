"""End-to-end integration: planner.process() leaves an o/p eval record.

Asserts the wiring in shopstack/planner/engine.py actually persists a
ModelCallRecord to the SQLite sink with the expected domain_route,
capability, and outcome.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from shopstack.eval import (
    CAP_PLANNER_TOOL_CALLING,
    ModelCallRecorder,
    OUTCOME_SUCCESS,
    SHAPE_TOOL_CALLS,
    SqliteSink,
)
from shopstack.eval.checks import EvalCheckRegistry


class _RecordingCheck:
    def __init__(self, name: str, passed: bool = True, score: float = 1.0):
        from shopstack.eval import CheckResult
        self._result = CheckResult(name, passed, score, "ok")
        self.calls: list = []

    def __call__(self, record, history, **kwargs):
        from shopstack.eval import CheckResult
        self.calls.append(record.record_id)
        return self._result


class _NoOpRegistry:
    def __init__(self):
        from shopstack.eval import CheckResult
        self.always = CheckResult("noop", True, 1.0, "")
        self.history: list = []

    def run(self, record):
        self.history.append(record)
        return [self.always]


@pytest.fixture()
def recorder_with_temp_db(monkeypatch, tmp_path):
    """Replace the singleton recorder with one that writes to a temp DB."""
    sqlite = SqliteSink(tmp_path / "test.db")
    reg = _NoOpRegistry()
    ModelCallRecorder.reset_instance()
    ModelCallRecorder._instance = ModelCallRecorder(
        jsonl_sink=_NoOpJsonl(),
        sqlite_sink=sqlite,
        check_registry=reg,
    )
    yield sqlite
    ModelCallRecorder.reset_instance()


class _NoOpJsonl:
    """JsonlSink stub for tests — no real file write."""

    def write(self, record):  # pragma: no cover - trivial
        pass

    def read_all(self):  # pragma: no cover - trivial
        return []


def test_planner_process_records_eval(tmp_path, monkeypatch):
    """Run planner.process() with a mock provider and assert a record
    lands in the SQLite sink with the expected fields."""
    # Use a fresh recorder for this test (don't use the shared fixture
    # because we want the planner's call to use the same instance)
    sqlite = SqliteSink(tmp_path / "test.db")
    reg = _NoOpRegistry()
    ModelCallRecorder.reset_instance()
    ModelCallRecorder._instance = ModelCallRecorder(
        jsonl_sink=_NoOpJsonl(),
        sqlite_sink=sqlite,
        check_registry=reg,
    )

    # Build a minimal in-process planner with a mock provider.
    from shopstack.planner.engine import PlannerEngine

    # Tiny mock provider that returns a known tool_calls payload.
    mock_provider = SimpleNamespace(
        plan=lambda payload: {
            "tool_calls": [
                {"tool": "respond", "args": {"message": "hello"}},
            ],
            "text": '[{"tool": "respond", "args": {"message": "hello"}}]',
            "model": "mock-eval-test",
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            "cost": {"usd": 0.0, "latency_ms": 50.0},
        },
        available=True,
        name="mock_eval_provider",
        backend="mock",
        model_id="mock-eval-test",
    )

    mock_registry = SimpleNamespace(planner=mock_provider)

    # Real DB + tool registry for a meaningful run.
    from shopstack.persistence.database import Database
    from shopstack.tools.registry import ToolRegistry
    db = Database(db_path=str(tmp_path / "shop.db"))
    tools = ToolRegistry(db)

    engine = PlannerEngine(db=db, tool_registry=tools, provider_registry=mock_registry)
    # Bypass cost guard (we have no real session)
    engine._cost_tracker = SimpleNamespace(over_budget=False)  # type: ignore[attr-defined]

    out = engine.process("test question")
    assert "hello" in out or "Planner" in out

    # The recorder should have written one row to the SQLite sink
    rows = sqlite.query(domain_route="planner")
    assert len(rows) == 1
    row = rows[0]
    assert row["capability"] == CAP_PLANNER_TOOL_CALLING
    assert row["capability_shape"] == SHAPE_TOOL_CALLS
    assert row["domain_route"] == "planner"
    assert row["model"] == "mock-eval-test"
    assert row["backend"] == "mock"
    assert row["outcome"] == OUTCOME_SUCCESS
    assert row["input_tokens"] == 7
    assert row["output_tokens"] == 3
    assert row["eval_passed"] == 1
    # The code route format is module.func:line; just check the prefix
    assert "planner.engine.process" in row["code_route"]
    assert "shopstack." in row["code_route"]
    assert "test question" in row["prompt"]


def test_planner_process_records_exception_outcome(tmp_path):
    """When the provider raises, the recorder captures outcome=exception."""
    from shopstack.eval import OUTCOME_EXCEPTION
    sqlite = SqliteSink(tmp_path / "test.db")
    reg = _NoOpRegistry()
    ModelCallRecorder.reset_instance()
    ModelCallRecorder._instance = ModelCallRecorder(
        jsonl_sink=_NoOpJsonl(),
        sqlite_sink=sqlite,
        check_registry=reg,
    )

    def _explode(_payload):
        raise RuntimeError("provider blew up")

    mock_provider = SimpleNamespace(
        plan=_explode,
        available=True,
        name="mock_exploder",
        backend="mock",
        model_id="mock-ex",
    )
    mock_registry = SimpleNamespace(planner=mock_provider)

    from shopstack.persistence.database import Database
    from shopstack.tools.registry import ToolRegistry
    from shopstack.planner.engine import PlannerEngine

    db = Database(db_path=str(tmp_path / "shop.db"))
    tools = ToolRegistry(db)
    engine = PlannerEngine(db=db, tool_registry=tools, provider_registry=mock_registry)
    engine._cost_tracker = SimpleNamespace(over_budget=False)  # type: ignore[attr-defined]

    out = engine.process("this will fail")
    assert "error" in out.lower() or "Planner error" in out

    rows = sqlite.query(domain_route="planner")
    assert len(rows) == 1
    assert rows[0]["outcome"] == OUTCOME_EXCEPTION
    assert "provider blew up" in rows[0]["error"]
