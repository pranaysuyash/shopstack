from __future__ import annotations

from shopstack.planner.continuation import BindingError, is_empty_result, resolve_result_references
from shopstack.planner.engine import PlannerEngine


class _SequentialPlanner:
    available = True
    name = "continuation-test"
    backend = "mock"
    model_id = "continuation-test"

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0

    def plan(self, _payload):
        self.calls += 1
        return next(self.responses)


def _provider_registry(providers, provider):
    providers.register("planner", provider)
    return providers


def test_result_reference_resolver_is_explicit_and_recursive():
    resolved, resolutions = resolve_result_references(
        {
            "items": [{"canonical_name": {"$from": "step_1.result.0.substitute"}}],
            "note": "step_1.result.0.substitute is ordinary text here",
        },
        {"step_1": {"result": [{"substitute": "tofu"}]}},
    )

    assert resolved["items"][0]["canonical_name"] == "tofu"
    assert resolved["note"].startswith("step_1")
    assert resolutions == [{"reference": "step_1.result.0.substitute", "value": "tofu"}]


def test_result_reference_resolver_fails_closed():
    try:
        resolve_result_references(
            {"value": {"$from": "step_1.result.0.missing"}},
            {"step_1": {"result": [{"substitute": "tofu"}]}},
        )
    except BindingError as exc:
        assert "has no key 'missing'" in str(exc)
    else:  # pragma: no cover - assertion makes the failure explicit
        raise AssertionError("missing result reference was accepted")


def test_empty_result_detects_common_tool_envelopes():
    assert is_empty_result({"results": [], "count": 0})
    assert is_empty_result({"suggestions": []})
    assert not is_empty_result({"results": [{"name": "milk"}], "count": 1})


def test_continuation_binds_lookup_result_before_shopping_mutation(
    db, tool_registry, providers, monkeypatch
):
    provider = _SequentialPlanner([
        {"tool_calls": [{"tool": "find_substitute", "args": {"canonical_name": "paneer"}}]},
        {"tool_calls": [{
            "tool": "create_or_update_shopping_list",
            "args": {
                "items": [{
                    "canonical_name": {"$from": "step_1.result.0.substitute"},
                    "requested_quantity": 1,
                    "unit": "unit",
                    "priority": "must_buy",
                }],
                "goal": "Replace unavailable paneer",
            },
        }]},
    ])
    _provider_registry(providers, provider)
    original_execute = tool_registry.execute

    def execute(tool_name, **kwargs):
        if tool_name == "find_substitute":
            return {"success": True, "result": [{"substitute": "tofu"}], "tool": tool_name}
        return original_execute(tool_name, **kwargs)

    monkeypatch.setattr(tool_registry, "execute", execute)
    monkeypatch.setattr("shopstack.planner.engine.settings.planner_allow_writes", True)
    engine = PlannerEngine(db, tool_registry, providers, allow_confirmed_writes=True)

    response = engine.process_continuation("Find a substitute for paneer and add it to my list.")

    assert response["status"] == "write_completed"
    assert response["steps_executed"] == 2
    assert response["steps"][1]["binding_resolutions"][0]["value"] == "tofu"
    shopping_list = db.get_active_shopping_list()
    assert shopping_list is not None
    assert [item.canonical_name for item in shopping_list.items] == ["tofu"]
    assert provider.calls == 2


def test_continuation_stops_on_empty_intermediate_result(db, tool_registry, providers, monkeypatch):
    provider = _SequentialPlanner([
        {"tool_calls": [{"tool": "find_substitute", "args": {"canonical_name": "paneer"}}]},
        {"tool_calls": [{"tool": "respond", "args": {"message": "should not run"}}]},
    ])
    _provider_registry(providers, provider)
    original_execute = tool_registry.execute

    def execute(tool_name, **kwargs):
        if tool_name == "find_substitute":
            return {"success": True, "result": [], "tool": tool_name}
        return original_execute(tool_name, **kwargs)

    monkeypatch.setattr(tool_registry, "execute", execute)
    engine = PlannerEngine(db, tool_registry, providers)

    response = engine.process_continuation("Find a substitute for paneer and add it to my list.")

    assert response["status"] == "empty_intermediate"
    assert response["steps_executed"] == 1
    assert provider.calls == 1


def test_continuation_distinguishes_stale_intermediate_result(
    db, tool_registry, providers, monkeypatch
):
    provider = _SequentialPlanner([
        {"tool_calls": [{"tool": "find_substitute", "args": {"canonical_name": "paneer"}}]},
        {"tool_calls": [{"tool": "respond", "args": {"message": "should not run"}}]},
    ])
    _provider_registry(providers, provider)
    original_execute = tool_registry.execute

    def execute(tool_name, **kwargs):
        if tool_name == "find_substitute":
            return {
                "success": True,
                "result": {"stale": True, "items": [], "message": "source is stale"},
                "tool": tool_name,
            }
        return original_execute(tool_name, **kwargs)

    monkeypatch.setattr(tool_registry, "execute", execute)
    engine = PlannerEngine(db, tool_registry, providers)

    response = engine.process_continuation("Find a substitute for paneer and add it to my list.")

    assert response["status"] == "stale_intermediate"
    assert response["steps_executed"] == 1
    assert provider.calls == 1


def test_continuation_stops_before_duplicate_action(db, tool_registry, providers, monkeypatch):
    provider = _SequentialPlanner([
        {"tool_calls": [{"tool": "find_item", "args": {"query": "milk"}}]},
        {"tool_calls": [{"tool": "find_item", "args": {"query": "milk"}}]},
    ])
    _provider_registry(providers, provider)
    original_execute = tool_registry.execute
    calls = []

    def execute(tool_name, **kwargs):
        calls.append((tool_name, kwargs))
        if tool_name == "find_item":
            return {"success": True, "result": {"results": [{"canonical_name": "milk"}]}, "tool": tool_name}
        return original_execute(tool_name, **kwargs)

    monkeypatch.setattr(tool_registry, "execute", execute)
    engine = PlannerEngine(db, tool_registry, providers)

    response = engine.process_continuation("Find milk, then verify it again.")

    assert response["status"] == "duplicate_action"
    assert response["steps_executed"] == 2
    assert len(calls) == 1


def test_continuation_preserves_production_confirmation_boundary(
    db, tool_registry, providers, monkeypatch
):
    provider = _SequentialPlanner([
        {"tool_calls": [{"tool": "find_substitute", "args": {"canonical_name": "paneer"}}]},
        {"tool_calls": [{
            "tool": "add_inventory_item",
            "args": {
                "canonical_name": {"$from": "step_1.result.0.substitute"},
            },
        }]},
    ])
    _provider_registry(providers, provider)
    original_execute = tool_registry.execute

    def execute(tool_name, **kwargs):
        if tool_name == "find_substitute":
            return {"success": True, "result": [{"substitute": "tofu"}], "tool": tool_name}
        return original_execute(tool_name, **kwargs)

    monkeypatch.setattr(tool_registry, "execute", execute)
    monkeypatch.setattr("shopstack.planner.engine.settings.planner_allow_writes", False)
    engine = PlannerEngine(db, tool_registry, providers)

    response = engine.process_continuation("Find a substitute for paneer and add it to my list.")

    assert response["status"] == "tool_failed"
    assert response["steps"][1]["execution"]["status"] == "partial_failure"
    assert db.get_inventory() == []
