"""End-to-end integration: planner.process() leaves an o/p eval record.

Asserts the wiring in shopstack/planner/engine.py actually persists a
ModelCallRecord to the SQLite sink with the expected domain_route,
capability, and outcome.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from shopstack.eval import (
    CAP_PLANNER_TOOL_CALLING,
    OUTCOME_PARSE_ERROR,
    OUTCOME_SUCCESS,
    OUTCOME_TOOL_FAILURE,
    SHAPE_TOOL_CALLS,
    ModelCallRecorder,
    SqliteSink,
)


class _RecordingCheck:
    def __init__(self, name: str, passed: bool = True, score: float = 1.0):
        from shopstack.eval import CheckResult
        self._result = CheckResult(name, passed, score, "ok")
        self.calls: list = []

    def __call__(self, record, history, **kwargs):
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
    from shopstack.planner.engine import PlannerEngine
    from shopstack.tools.registry import ToolRegistry

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


def _make_engine(tmp_path, provider, recorder_registry=None):
    from shopstack.persistence.database import Database
    from shopstack.planner.engine import PlannerEngine
    from shopstack.tools.registry import ToolRegistry

    sqlite = SqliteSink(tmp_path / "test.db")
    ModelCallRecorder.reset_instance()
    ModelCallRecorder._instance = ModelCallRecorder(
        jsonl_sink=_NoOpJsonl(),
        sqlite_sink=sqlite,
        check_registry=recorder_registry or _NoOpRegistry(),
    )
    db = Database(db_path=str(tmp_path / "shop.db"))
    tools = ToolRegistry(db)
    engine = PlannerEngine(
        db=db,
        tool_registry=tools,
        provider_registry=SimpleNamespace(planner=provider),
    )
    engine._cost_tracker = SimpleNamespace(over_budget=False)  # type: ignore[attr-defined]
    return engine, tools, sqlite


def test_planner_structured_rejects_parser_fallback_and_records_parse_error(tmp_path):
    provider = SimpleNamespace(
        plan=lambda _payload: {
            "text": "not structured output",
            "model": "mock-malformed",
        },
        available=True,
        name="mock_eval_provider",
        backend="mock",
        model_id="mock-malformed",
    )
    engine, _tools, sqlite = _make_engine(tmp_path, provider)

    result = engine.process_structured("find something")

    assert result["type"] == "error"
    assert "valid action plan" in result["error"]
    row = sqlite.query(domain_route="planner")[0]
    assert row["outcome"] == OUTCOME_PARSE_ERROR
    assert json.loads(row["execution_meta"])["status"] == "parse_failed"


def test_planner_records_tool_failure_separately_from_provider_success(tmp_path, monkeypatch):
    provider = SimpleNamespace(
        plan=lambda _payload: {
            "tool_calls": [{"tool": "find_item", "args": {"query": "milk"}}],
            "model": "mock-tool-failure",
        },
        available=True,
        name="mock_eval_provider",
        backend="mock",
        model_id="mock-tool-failure",
    )
    engine, tools, sqlite = _make_engine(tmp_path, provider)
    monkeypatch.setattr(
        tools,
        "execute",
        lambda _tool, **_args: {"success": False, "error": "fixture unavailable"},
    )

    result = engine.process_structured("find milk")

    assert result["type"] == "tool_calls"
    assert result["outcomes"][0]["success"] is False
    row = sqlite.query(domain_route="planner")[0]
    assert row["outcome"] == OUTCOME_TOOL_FAILURE
    execution = json.loads(row["execution_meta"])
    assert execution["status"] == "partial_failure"
    assert execution["tool_calls_failed"] == 1


def test_planner_records_respond_execution_as_completed(tmp_path):
    provider = SimpleNamespace(
        plan=lambda _payload: {
            "tool_calls": [{"tool": "respond", "args": {"message": "hello"}}],
            "model": "mock-respond",
        },
        available=True,
        name="mock_eval_provider",
        backend="mock",
        model_id="mock-respond",
    )
    engine, _tools, sqlite = _make_engine(tmp_path, provider)

    result = engine.process_structured("say hello")

    assert result["type"] == "tool_calls"
    row = sqlite.query(domain_route="planner")[0]
    assert row["outcome"] == OUTCOME_SUCCESS
    assert json.loads(row["execution_meta"])["status"] == "completed"
